"""Acceptance harness checks; these tests do not execute candidate code."""

import json

from scripts import docker_verify


def test_unavailable_report_is_not_a_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(
        docker_verify.Sandbox,
        "available",
        lambda self: {
            "status": "unavailable",
            "details": "Test fixture: no Docker daemon",
        },
    )
    output = tmp_path / "docker-validation.json"
    assert docker_verify.main(["--output", str(output)]) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "unavailable" and report["checks"] == []
    assert report["model_effectiveness"] == "not_measured"


def test_inspect_filter_omits_host_sources_and_env_values():
    snapshot = docker_verify.filtered_inspect(
        {
            "State": {"Running": True},
            "Config": {"User": "65534:65534", "Env": ["PATH=/bin", "SENTINEL=private-value"]},
            "HostConfig": {"NetworkMode": "none"},
            "Mounts": [
                {
                    "Type": "bind",
                    "Destination": "/source",
                    "RW": False,
                    "Source": "/home/private-host-user/repo",
                }
            ],
        }
    )
    encoded = json.dumps(snapshot)
    assert "/home/private-host-user" not in encoded
    assert "private-value" not in encoded
    assert "SENTINEL" in snapshot["environment_keys"]


def test_failed_exit_and_leftover_container_never_count_as_pass(monkeypatch, tmp_path):
    class HarnessStub:
        observe = False

        def run(self, *args, **kwargs):
            return {"status": "failed", "exit_code": 1}

        def cleanup_evidence(self):
            return {"checked": True, "remaining_container_ids": ["leftover-fixture-id"]}

    report = {"checks": []}
    check = docker_verify.run_check(
        report, "cleanup", tmp_path, "failed", HarnessStub(), expected_exit=1
    )
    assert not check["passed"]


def test_scrub_paths_preserves_container_paths(tmp_path):
    value = {"output": f"host={tmp_path}; container=/tmp/work/tests/test_example.py"}
    scrubbed = docker_verify.scrub_paths(value, tmp_path)
    assert str(tmp_path) not in scrubbed["output"]
    assert "/tmp/work/tests/test_example.py" in scrubbed["output"]
