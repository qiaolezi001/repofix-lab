"""Opt-in real Docker acceptance; standalone CI script avoids duplicate runs."""

import os

import pytest

from scripts.docker_verify import verify


@pytest.mark.skipif(
    os.environ.get("REPOFIX_DOCKER_INTEGRATION") != "1",
    reason="Set REPOFIX_DOCKER_INTEGRATION=1 to require real Docker acceptance",
)
def test_real_docker_acceptance():
    report = verify(os.environ.get("REPOFIX_SANDBOX_IMAGE", "repofix-sandbox:0.1"))
    assert report["status"] == "passed", report
    assert len(report["checks"]) == 10
    assert all(check["passed"] for check in report["checks"])
    assert report["model_effectiveness"] == "not_measured"
