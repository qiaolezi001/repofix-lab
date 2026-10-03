"""Real Docker acceptance checks. This script never measures model effectiveness.

Build Dockerfile.sandbox first, then run:
    uv run python scripts/docker_verify.py --output reports/docker-validation.json
An unavailable Docker daemon/image writes an unavailable report and exits 2.
Candidate fixture code executes only through the production Docker Sandbox.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repofix.config import DEMO_ISSUE, Settings, demo_source
from repofix.engine import Engine
from repofix.reports import public_state
from repofix.sandbox import Sandbox
from repofix.tools import ToolRegistry
from repofix.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]


def invoke(command: list[str], timeout: float = 6) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def metadata(image: str) -> dict[str, Any]:
    result: dict[str, Any] = {"python": platform.python_version(), "platform": platform.system()}
    commit = invoke(["git", "rev-parse", "HEAD"])
    result["git_commit"] = commit.stdout.strip() if commit.returncode == 0 else None
    dirty = invoke(["git", "status", "--porcelain"])
    result["git_dirty"] = bool(dirty.stdout.strip()) if dirty.returncode == 0 else None
    for label, command in [
        ("docker", ["docker", "version", "--format", "{{json .}}"]),
        ("image", ["docker", "image", "inspect", image]),
    ]:
        response = invoke(command)
        if response.returncode:
            raise RuntimeError(f"Could not read {label} metadata")
        data = json.loads(response.stdout)
        if label == "docker":
            result[label] = {
                side.lower(): {
                    key: data.get(side, {}).get(key)
                    for key in ("Version", "ApiVersion", "GitCommit", "Os", "Arch")
                }
                for side in ("Client", "Server")
            }
        else:
            result[label] = {
                key: data[0].get(key)
                for key in ("Id", "RepoDigests", "Created", "Architecture", "Os")
            }
            result[label]["requested_tag"] = image
    return result


def filtered_inspect(data: dict[str, Any]) -> dict[str, Any]:
    """Retain policy evidence without host mount sources or environment values."""
    host = data["HostConfig"]
    return {
        "running": data["State"]["Running"],
        "user": data["Config"]["User"],
        "host_config": {
            key: host.get(key)
            for key in (
                "NetworkMode",
                "ReadonlyRootfs",
                "Memory",
                "MemorySwap",
                "NanoCpus",
                "PidsLimit",
                "CapDrop",
                "CapAdd",
                "SecurityOpt",
                "Tmpfs",
                "Privileged",
            )
        },
        "mounts": [
            {key: mount.get(key) for key in ("Type", "Destination", "RW")}
            for mount in data.get("Mounts", [])
        ],
        "environment_keys": sorted(item.split("=", 1)[0] for item in data["Config"].get("Env", [])),
    }


def inspect_policy_passed(snapshot: dict[str, Any] | None) -> bool:
    if not snapshot:
        return False
    host = snapshot["host_config"]
    bind_mounts = [mount for mount in snapshot["mounts"] if mount["Type"] == "bind"]
    return (
        snapshot["user"] == "65534:65534"
        and host["NetworkMode"] == "none"
        and host["ReadonlyRootfs"] is True
        and host["Memory"] == 256 * 1024 * 1024
        and host["MemorySwap"] == 256 * 1024 * 1024
        and host["NanoCpus"] == 1_000_000_000
        and host["PidsLimit"] == 64
        and "ALL" in (host["CapDrop"] or [])
        and not host["CapAdd"]
        and not host["Privileged"]
        and any(value.startswith("no-new-privileges") for value in host["SecurityOpt"] or [])
        and "/tmp" in (host["Tmpfs"] or {})
        and "size=67108864" in host["Tmpfs"]["/tmp"]
        and bind_mounts == [{"Type": "bind", "Destination": "/source", "RW": False}]
        and "REPOFIX_HOST_ONLY_SENTINEL" not in snapshot["environment_keys"]
    )


class ObservedSandbox(Sandbox):
    """Observe the production command/container; keep production execution intact."""

    def __init__(
        self, *, image: str, timeout: float = 20, observe: bool = False, cancellation=None
    ):
        super().__init__(timeout=timeout, image=image)
        self.container_name: str | None = None
        self.snapshot: dict[str, Any] | None = None
        self.observe = observe or cancellation is not None
        self.cancellation = cancellation
        self.observer: threading.Thread | None = None
        self.stop_observer = threading.Event()

    def _command(self, repo: Path, tests: list[str], name: str) -> list[str]:
        command = super()._command(repo, tests, name)
        self.container_name = name
        if self.observe:
            self.observer = threading.Thread(target=self._observe, daemon=True)
            self.observer.start()
        return command

    def _observe(self) -> None:
        deadline = time.monotonic() + 10
        while not self.stop_observer.is_set() and time.monotonic() < deadline:
            try:
                response = invoke(["docker", "inspect", str(self.container_name)], timeout=3)
                if response.returncode == 0:
                    snapshot = filtered_inspect(json.loads(response.stdout)[0])
                    if snapshot["running"]:
                        self.snapshot = snapshot
                        if self.cancellation is not None:
                            # This fires after a real container is running, not before launch.
                            self.stop_observer.wait(0.5)
                            self.cancellation.set()
                        return
            except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
                pass
            self.stop_observer.wait(0.1)

    def close_observer(self) -> None:
        self.stop_observer.set()
        if self.observer is not None:
            self.observer.join(timeout=4)

    def cleanup_evidence(self) -> dict[str, Any]:
        self.close_observer()
        if self.container_name is None:
            return {"checked": False, "reason": "No container command was issued"}
        response = invoke(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=^/{self.container_name}$",
                "--format",
                "{{.ID}}",
            ]
        )
        remaining = [line for line in response.stdout.splitlines() if line.strip()]
        evidence = {
            "checked": response.returncode == 0,
            "remaining_container_ids": remaining,
            "container_name": self.container_name,
        }
        if remaining:
            # Preserve failed cleanup evidence, then avoid leaking a failed test's container.
            cleanup = invoke(["docker", "rm", "--force", self.container_name])
            evidence["fallback_cleanup_exit_code"] = cleanup.returncode
        return evidence


def fixture(directory: Path, name: str, files: dict[str, str]) -> Path:
    repo = directory / name
    repo.mkdir(parents=True)
    for relative, content in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    return repo


def run_check(
    report: dict[str, Any],
    name: str,
    repo: Path,
    expected: str,
    sandbox: ObservedSandbox,
    *,
    cancel_event=None,
    expected_exit: int | None = None,
    require_inspect: bool = False,
) -> dict[str, Any]:
    try:
        result = sandbox.run(repo, cancel_event=cancel_event)
    finally:
        cleanup = sandbox.cleanup_evidence()
    passed = (
        result["status"] == expected
        and cleanup.get("checked") is True
        and cleanup["remaining_container_ids"] == []
        and (expected_exit is None or result["exit_code"] == expected_exit)
        and (not require_inspect or inspect_policy_passed(sandbox.snapshot))
    )
    check = {
        "name": name,
        "passed": passed,
        "expected_status": expected,
        "result": result,
        "cleanup": cleanup,
    }
    if sandbox.observe:
        check["container_inspect"] = sandbox.snapshot
    report["checks"].append(check)
    return check


ISOLATION_TEST = """import os
from pathlib import Path
import socket
import time

def test_real_container_isolation():
    assert os.getuid() == 65534
    assert os.getgid() == 65534
    status = Path('/proc/self/status').read_text()
    fields = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
    assert int(fields['CapEff'].strip(), 16) == 0
    assert fields['NoNewPrivs'].strip() == '1'
    assert {name for _, name in socket.if_nameindex()} == {'lo'}
    assert 'REPOFIX_HOST_ONLY_SENTINEL' not in os.environ
    assert not Path('/var/run/docker.sock').exists()
    for path in (Path('/source/probe.py'), Path('/repofix-root-write-denied')):
        try:
            path.write_text('forbidden')
        except OSError:
            pass
        else:
            raise AssertionError('Read-only filesystem write unexpectedly succeeded')
    Path('scratch-write.txt').write_text('allowed in tmpfs working copy')
    assert Path('scratch-write.txt').read_text() == 'allowed in tmpfs working copy'
    time.sleep(2)
"""


def verify(image: str = "repofix-sandbox:0.1") -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "not_run",
        "scope": "Real Docker engineering acceptance using self-authored fixtures",
        "candidate_execution": "Docker only; no host execution",
        "model_effectiveness": "not_measured",
        "model_requests": 0,
        "checks": [],
    }
    started = time.monotonic()
    availability = Sandbox(image=image).available()
    report["availability"] = availability
    if availability["status"] != "available":
        report["status"] = "unavailable"
        report["duration_seconds"] = round(time.monotonic() - started, 3)
        return report
    try:
        report["environment"] = metadata(image)
        with tempfile.TemporaryDirectory(prefix="repofix-docker-verification-") as temporary:
            directory = Path(temporary)
            source = fixture(
                directory,
                "original",
                {
                    "calc.py": "def add(a, b):\n    return a - b\n",
                    "tests/test_calc.py": "from calc import add\n\ndef test_sum():\n    assert add(2, 3) == 5\n\ndef test_signed():\n    assert add(-1, 1) == 0\n",
                },
            )
            workspace = Workspace(source, directory / "task")
            run_check(
                report,
                "original_public_tests_fail",
                workspace.repo,
                "failed",
                ObservedSandbox(image=image),
                expected_exit=1,
            )
            registry = ToolRegistry(workspace, Sandbox(image=image))
            patch_result = registry.execute(
                "apply_patch",
                {
                    "edits": [
                        {
                            "path": "calc.py",
                            "old": "return a - b",
                            "new": "return a + b",
                        }
                    ]
                },
                action_id="docker-verification-patch",
            )
            report["patch"] = {
                "ok": patch_result["ok"],
                "baseline_version": workspace.version,
                "source_unchanged": (source / "calc.py").read_bytes()
                == (workspace.baseline / "calc.py").read_bytes(),
            }
            run_check(
                report,
                "patched_public_tests_pass",
                workspace.repo,
                "passed",
                ObservedSandbox(image=image),
                expected_exit=0,
            )
            for name, content, exit_code in [
                (
                    "skip_is_rejected",
                    "import pytest\n\ndef test_skip():\n    pytest.skip('synthetic guardrail fixture')\n",
                    79,
                ),
                ("empty_test_file_is_rejected", "# Intentionally contains zero test cases.\n", 5),
                (
                    "early_zero_exit_is_rejected",
                    "import os\n\ndef test_early_exit():\n    os._exit(0)\n",
                    79,
                ),
                (
                    "test_mutation_is_rejected",
                    "from pathlib import Path\n\ndef test_mutation():\n    Path(__file__).write_text('# changed only inside scratch copy\\n')\n    assert True\n",
                    79,
                ),
            ]:
                repo = fixture(directory, name, {"tests/test_guard.py": content})
                run_check(
                    report,
                    name,
                    repo,
                    "failed",
                    ObservedSandbox(image=image),
                    expected_exit=exit_code,
                )
            isolation = fixture(
                directory,
                "isolation",
                {
                    "probe.py": "VALUE = 1\n",
                    "tests/test_isolation.py": ISOLATION_TEST,
                },
            )
            previous = os.environ.get("REPOFIX_HOST_ONLY_SENTINEL")
            os.environ["REPOFIX_HOST_ONLY_SENTINEL"] = "synthetic-not-a-credential"
            try:
                run_check(
                    report,
                    "actual_isolation_policy",
                    isolation,
                    "passed",
                    ObservedSandbox(image=image, observe=True),
                    expected_exit=0,
                    require_inspect=True,
                )
            finally:
                if previous is None:
                    os.environ.pop("REPOFIX_HOST_ONLY_SENTINEL", None)
                else:
                    os.environ["REPOFIX_HOST_ONLY_SENTINEL"] = previous
            sleeper = fixture(
                directory,
                "sleep",
                {
                    "tests/test_sleep.py": "import time\n\ndef test_sleep():\n    time.sleep(120)\n",
                },
            )
            run_check(
                report,
                "timeout_removes_actual_container",
                sleeper,
                "timeout",
                ObservedSandbox(image=image, timeout=5, observe=True),
                require_inspect=True,
            )
            cancellation = threading.Event()
            run_check(
                report,
                "active_cancellation_removes_actual_container",
                sleeper,
                "cancelled",
                ObservedSandbox(image=image, cancellation=cancellation),
                cancel_event=cancellation,
                require_inspect=True,
            )
            engine = Engine(Settings(data_dir=directory / "mock-engine", sandbox_image=image))
            task = engine.create(demo_source(), DEMO_ISSUE, mode="mock")
            demo = public_state(engine.run(task["id"]))
            report["checks"].append(
                {
                    "name": "mock_agent_end_to_end",
                    "mode": "mock",
                    "model_effectiveness": "not_measured",
                    "result": demo,
                    "passed": demo["status"] == "succeeded"
                    and demo["public_tests"]["status"] == "passed"
                    and demo["public_tests"]["complete_suite"]
                    and bool(demo["candidate_patch"]),
                }
            )
            report["status"] = (
                "passed"
                if (
                    len(report["checks"]) == 10
                    and all(check["passed"] for check in report["checks"])
                    and report["patch"]["ok"]
                    and report["patch"]["source_unchanged"]
                )
                else "failed"
            )
            # Exception text from fixture commands can contain temporary host paths.
            report = scrub_paths(report, directory)
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError) as exc:
        report["status"] = "failed"
        report["error"] = f"Acceptance infrastructure failed ({type(exc).__name__})"
    report["duration_seconds"] = round(time.monotonic() - started, 3)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


def scrub_paths(value: Any, directory: Path) -> Any:
    if isinstance(value, str):
        return value.replace(str(directory), "<fixture-root>").replace(str(ROOT), "<project-root>")
    if isinstance(value, list):
        return [scrub_paths(item, directory) for item in value]
    if isinstance(value, dict):
        return {key: scrub_paths(item, directory) for key, item in value.items()}
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports/docker-validation.json"))
    parser.add_argument("--image", default="repofix-sandbox:0.1")
    arguments = parser.parse_args(argv)
    report = verify(arguments.image)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "checks": len(report["checks"]),
                "passed": sum(check["passed"] for check in report["checks"]),
                "model_effectiveness": "not_measured",
            }
        )
    )
    return 0 if report["status"] == "passed" else 2 if report["status"] == "unavailable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
