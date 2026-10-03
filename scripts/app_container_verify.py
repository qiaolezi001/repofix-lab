"""Start the actual app image and verify its documented diagnosis-only mode."""

import argparse
import json
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx


def docker(*arguments: str) -> str:
    result = subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, timeout=30, check=True
    )
    return result.stdout.strip()


def verify(image: str) -> dict:
    name = "repofix-app-check-" + uuid.uuid4().hex
    volume = name + "-data"
    report = {"status": "failed", "mode": "mock", "model_effectiveness": "not_measured"}
    report["created_at"] = datetime.now(UTC).isoformat()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
    report["source_commit"] = commit.stdout.strip() if commit.returncode == 0 else None
    started = time.monotonic()
    try:
        docker(
            "run",
            "--detach",
            "--rm",
            "--pull",
            "never",
            "--name",
            name,
            "--publish",
            "127.0.0.1::8765",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=67108864,mode=1777",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--pids-limit",
            "128",
            "--mount",
            f"type=volume,source={volume},target=/data",
            image,
        )
        snapshot = json.loads(docker("inspect", name))[0]
        port = snapshot["NetworkSettings"]["Ports"]["8765/tcp"][0]["HostPort"]
        report["image_id"] = snapshot["Image"]
        report["user"] = snapshot["Config"]["User"]
        report["mount_destinations"] = [entry["Destination"] for entry in snapshot["Mounts"]]
        report["environment_keys"] = sorted(
            value.split("=", 1)[0] for value in snapshot["Config"]["Env"]
        )
        assert report["user"] == "65534:65534"
        assert all(entry["Type"] != "bind" for entry in snapshot["Mounts"])
        assert not {"REPOFIX_API_KEY", "OPENAI_API_KEY"}.intersection(report["environment_keys"])
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=5
        ) as client:
            deadline = time.monotonic() + 30
            while True:
                try:
                    health = client.get("/api/health")
                    health.raise_for_status()
                    report["health"] = health.json()
                    break
                except httpx.HTTPError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.2)
            assert report["health"]["mode"] == "mock"
            assert report["health"]["docker"]["status"] == "unavailable"
            assert client.get("/").status_code == 200
            assert client.get("/openapi.json").status_code == 200
            demo = client.get("/api/demo").json()
            response = client.post("/api/tasks", json={**demo, "mode": "mock"})
            assert response.status_code == 202
            task_id = response.json()["id"]
            deadline = time.monotonic() + 30
            while True:
                state = client.get(f"/api/tasks/{task_id}").json()
                if state["status"] in {
                    "completed",
                    "succeeded",
                    "failed",
                    "timed_out",
                    "cancelled",
                }:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Application task did not finish")
                time.sleep(0.2)
            assert state["status"] == "completed"
            assert state["public_tests"]["status"] == "unavailable"
            assert state["candidate_patch"]
            assert state["evidence"]
            assert client.get(f"/api/tasks/{task_id}/report?format=md").status_code == 200
            report["task"] = state
            report["status"] = "passed"
    except (
        OSError,
        ValueError,
        KeyError,
        AssertionError,
        TimeoutError,
        httpx.HTTPError,
        subprocess.SubprocessError,
    ) as exc:
        report["error"] = type(exc).__name__
    finally:
        for command in [("rm", "--force", name), ("volume", "rm", volume)]:
            try:
                docker(*command)
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            remaining = docker("ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.ID}}")
            remaining_volume = docker(
                "volume", "ls", "--filter", f"name=^{volume}$", "--format", "{{.Name}}"
            )
            report["cleanup"] = {
                "container_removed": not remaining,
                "volume_removed": not remaining_volume,
            }
            if remaining or remaining_volume:
                report["status"] = "failed"
        except (OSError, subprocess.SubprocessError):
            report["cleanup"] = {"status": "unknown"}
            report["status"] = "failed"
        report["duration_seconds"] = round(time.monotonic() - started, 3)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="repofix-app:validation")
    parser.add_argument("--output", type=Path, default=Path("reports/docker-app-validation.json"))
    arguments = parser.parse_args()
    report = verify(arguments.image)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "mode": "mock"}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
