"""Run untrusted project tests only inside a bounded, offline Docker container."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .workspace import is_link, is_test

MAX_OUTPUT_BYTES = 64 * 1024
# The wrapper lives in the container image's interpreter, outside the copied repo.
RUNNER = """
import hashlib, json, os, pathlib, shutil, subprocess, sys, xml.etree.ElementTree as ET
shutil.copytree('/source', '/tmp/work')
os.chdir('/tmp/work')
tests = json.loads(sys.argv[1])
protected = {p: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in pathlib.Path('.').rglob('*.py')
             if p.name.startswith('test_') or p.name.endswith('_test.py')
             or any(v in {'tests', 'test', 'testing'} for v in p.parts[:-1])}
environment = {'PATH': os.environ['PATH'], 'HOME': '/tmp',
               'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
bootstrap = "import pytest, sys; sys.path.insert(0, '/tmp/work'); sys.exit(pytest.main(sys.argv[1:]))"
result = subprocess.run([sys.executable, '-I', '-c', bootstrap, '-q', '-c', '/dev/null',
                         '--override-ini=addopts=', '-p', 'no:cacheprovider',
                         '--junitxml=/tmp/public-results.xml', '--', *tests],
                        env=environment)
summary = {'tests_count': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'errors': 0}
valid = False
try:
    report = ET.parse('/tmp/public-results.xml').getroot()
    cases = list(report.iter('testcase'))
    summary['tests_count'] = len(cases)
    summary['failed'] = sum(case.find('failure') is not None for case in cases)
    summary['skipped'] = sum(case.find('skipped') is not None for case in cases)
    summary['errors'] = max(sum(case.find('error') is not None for case in cases),
                            sum(int(suite.get('errors', '0')) for suite in report.iter('testsuite')))
    summary['passed'] = sum(all(case.find(tag) is None for tag in ('failure', 'skipped', 'error'))
                            for case in cases)
    valid = bool(cases) and all(summary[key] == 0 for key in ('failed', 'skipped', 'errors'))
except (OSError, ET.ParseError, ValueError):
    print('Missing or malformed JUnit report; test success cannot be verified', flush=True)
print('REPOFIX_TEST_SUMMARY=' + json.dumps(summary), flush=True)
if any(not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != value
       for p, value in protected.items()):
    print('Protected tests were modified during execution', flush=True)
    sys.exit(79)
if result.returncode == 0 and not valid:
    print('Verification requires a nonempty JUnit report with zero skips and errors', flush=True)
    sys.exit(79)
sys.exit(result.returncode)
"""


class Sandbox:
    def __init__(self, timeout: float = 30, image: str = "repofix-sandbox:0.1"):
        if not 0 < timeout <= 300:
            raise ValueError("Sandbox timeout must be in (0, 300] seconds")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9./:_@-]{0,200}", image):
            raise ValueError("Invalid Docker image name")
        self.timeout, self.image = timeout, image

    def available(self) -> dict:
        docker = shutil.which("docker")
        if docker is None:
            return {
                "status": "unavailable",
                "details": "Docker CLI is not installed; host tests are disabled",
            }
        try:
            info = subprocess.run(
                [docker, "info", "--format", "{{.OSType}}"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if info.returncode != 0:
                return {"status": "unavailable", "details": "Docker daemon is not reachable"}
            if info.stdout.strip() != "linux":
                return {"status": "unavailable", "details": "Docker must use Linux containers"}
            image = subprocess.run(
                [docker, "image", "inspect", self.image],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if image.returncode != 0:
                return {
                    "status": "unavailable",
                    "details": f"Build the local sandbox image first: {self.image}",
                }
        except (OSError, subprocess.TimeoutExpired):
            return {
                "status": "unavailable",
                "details": "Docker availability check failed or timed out",
            }
        return {
            "status": "available",
            "details": "Linux Docker daemon and local sandbox image available",
        }

    def _command(self, repo: Path, tests: list[str], name: str) -> list[str]:
        source = str(repo.resolve())
        if "," in source or "\n" in source or "\r" in source:
            raise ValueError("Docker bind source cannot contain a comma or newline")
        return [
            "docker",
            "run",
            "--rm",
            "--pull",
            "never",
            "--name",
            name,
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "65534:65534",
            "--read-only",
            "--pids-limit",
            "64",
            "--cpus",
            "1",
            "--memory",
            "256m",
            "--memory-swap",
            "256m",
            "--ulimit",
            "nofile=128:128",
            "--ulimit",
            "fsize=16777216:16777216",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=67108864,mode=1777",
            "--mount",
            f"type=bind,source={source},target=/source,readonly",
            "--entrypoint",
            "python",
            self.image,
            "-I",
            "-c",
            RUNNER,
            json.dumps(tests),
        ]

    @staticmethod
    def _test_paths(repo: Path, tests: list[str] | None) -> tuple[list[str], bool]:
        known = sorted(
            p.relative_to(repo).as_posix()
            for p in repo.rglob("*.py")
            if p.is_file() and is_test(p.relative_to(repo).as_posix())
        )
        if tests is None:
            return known, True
        selected = []
        for relative in tests:
            path = PurePosixPath(relative)
            if (
                not relative
                or "\\" in relative
                or path.is_absolute()
                or PureWindowsPath(relative).drive
                or ".." in path.parts
                or ":" in relative
                or relative.startswith("-")
            ):
                raise ValueError(
                    "Tests must be existing relative test-file paths, without CLI flags"
                )
            if relative not in known:
                raise ValueError(f"Not an accepted test file: {relative}")
            selected.append(relative)
        if not selected:
            raise ValueError(
                "Empty test selection is forbidden; use null to run the complete suite"
            )
        return sorted(set(selected)), set(selected) == set(known)

    def run(self, repo: Path, tests: list[str] | None = None, cancel_event=None) -> dict:
        started = time.monotonic()
        base: dict[str, Any] = {
            "exit_code": None,
            "output": "",
            "tests": [],
            "complete_suite": False,
        }
        if cancel_event is not None and cancel_event.is_set():
            return dict(base, status="cancelled", duration_seconds=0.0)
        if is_link(Path(repo)):
            raise ValueError("Sandbox repository root must not be a symbolic link or junction")
        repo = Path(repo).resolve(strict=True)
        if not repo.is_dir() or is_link(repo):
            raise ValueError("Sandbox repository must be a directory without symbolic links")
        for current, dirs, files in os.walk(repo, followlinks=False):
            if any(is_link(Path(current) / name) for name in dirs + files):
                raise ValueError("Sandbox repository contains a symbolic link or junction")
        paths, complete = self._test_paths(repo, tests)
        base.update(tests=paths, complete_suite=complete)
        if not paths:
            return dict(
                base,
                status="failed",
                output="No test files found; zero tests cannot pass",
                duration_seconds=round(time.monotonic() - started, 6),
            )
        availability = self.available()
        if availability["status"] != "available":
            return dict(
                base,
                status="unavailable",
                output=availability["details"],
                duration_seconds=round(time.monotonic() - started, 6),
            )
        name = "repofix-" + uuid.uuid4().hex
        output = bytearray()
        truncated = threading.Event()
        process = None
        status = "failed"
        reader = None
        try:
            process = subprocess.Popen(
                self._command(repo, paths, name),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )

            def drain() -> None:
                assert process is not None and process.stdout is not None
                while data := process.stdout.read(4096):
                    remaining = MAX_OUTPUT_BYTES - len(output)
                    output.extend(data[: max(remaining, 0)])
                    if len(data) > remaining:
                        truncated.set()

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    status = "cancelled"
                    break
                if time.monotonic() - started >= self.timeout:
                    status = "timeout"
                    break
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    continue
            else:
                status = "passed" if process.returncode == 0 else "failed"
        except OSError:
            status = "unavailable"
            output.extend(b"Docker process could not be started")
        finally:
            # Kill the named container, not just the local Docker client process.
            try:
                subprocess.run(
                    ["docker", "rm", "--force", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
            if process is not None:
                if process.poll() is None:
                    process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            if reader is not None:
                reader.join(timeout=2)
        rendered = bytes(output).decode("utf-8", errors="replace")
        if truncated.is_set():
            rendered += "\n[Output truncated at 64 KiB]"
        summaries = re.findall(r"^REPOFIX_TEST_SUMMARY=(.+)$", rendered, flags=re.MULTILINE)
        summary = None
        if summaries:
            try:
                summary = json.loads(summaries[-1])
            except json.JSONDecodeError:
                pass
        return dict(
            base,
            status=status,
            exit_code=process.returncode if process is not None else None,
            output=rendered,
            test_summary=summary,
            duration_seconds=round(time.monotonic() - started, 6),
        )
