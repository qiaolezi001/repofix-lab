import ast
import io
import json
import os
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from repofix.sandbox import RUNNER, Sandbox


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_sample.py").write_text(
        "def test_value():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    return tmp_path


def test_hardened_command_has_no_network_socket_or_host_env(repo):
    command = Sandbox()._command(repo, ["tests/test_sample.py"], "repofix-test")
    for option, value in [
        ("--network", "none"),
        ("--user", "65534:65534"),
        ("--cap-drop", "ALL"),
        ("--memory", "256m"),
        ("--pids-limit", "64"),
        ("--pull", "never"),
    ]:
        assert command[command.index(option) + 1] == value
    assert "--read-only" in command
    assert "readonly" in command[command.index("--mount") + 1]
    assert "--tmpfs" in command
    assert "docker.sock" not in " ".join(command)
    assert "--env" not in command and "--env-file" not in command


def test_docker_absent_does_not_run_host_tests(repo, monkeypatch):
    monkeypatch.setattr("repofix.sandbox.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "repofix.sandbox.subprocess.Popen", lambda *a, **kw: pytest.fail("No process expected")
    )
    result = Sandbox().run(repo)
    assert result["status"] == "unavailable"
    assert "host tests are disabled" in result["output"]


@pytest.mark.parametrize(
    "selection",
    [["../outside.py"], ["-q"], ["source.py"], [], ["tests/test_sample.py::test_value"]],
)
def test_invalid_test_selection_rejected(repo, selection):
    with pytest.raises(ValueError):
        Sandbox().run(repo, selection)


def test_full_suite_cannot_be_claimed_for_subset(repo):
    (repo / "tests/test_other.py").write_text(
        "def test_other():\n    assert True\n", encoding="utf-8"
    )
    paths, complete = Sandbox._test_paths(repo, ["tests/test_sample.py"])
    assert paths == ["tests/test_sample.py"] and not complete
    assert Sandbox._test_paths(repo, None)[1]


def test_cancellation_before_launch(repo):
    cancellation = threading.Event()
    cancellation.set()
    assert Sandbox().run(repo, cancel_event=cancellation)["status"] == "cancelled"


def test_zero_tests_is_failed(tmp_path):
    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")
    result = Sandbox().run(tmp_path)
    assert result["status"] == "failed"
    assert "zero tests cannot pass" in result["output"]


def test_daemon_and_image_checks(monkeypatch):
    calls = []
    monkeypatch.setattr("repofix.sandbox.shutil.which", lambda name: "/bin/docker")

    def invoke(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="linux\n")

    monkeypatch.setattr("repofix.sandbox.subprocess.run", invoke)
    assert Sandbox().available()["status"] == "available"
    assert calls[1][-2:] == ["inspect", "repofix-sandbox:0.1"]


@pytest.mark.parametrize("exit_code,status", [(0, "passed"), (1, "failed")])
def test_container_exit_result_and_cleanup(repo, monkeypatch, exit_code, status):
    calls = []

    class Process:
        stdout = io.BytesIO(b"test result\n")
        returncode = exit_code

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            return self.returncode

    monkeypatch.setattr(Sandbox, "available", lambda self: {"status": "available"})
    monkeypatch.setattr("repofix.sandbox.subprocess.Popen", lambda *a, **kw: Process())
    monkeypatch.setattr(
        "repofix.sandbox.subprocess.run", lambda command, **kw: calls.append(command)
    )
    result = Sandbox().run(repo)
    assert result["status"] == status and result["exit_code"] == exit_code
    assert "test result" in result["output"]
    assert result["complete_suite"]
    assert calls[0][:3] == ["docker", "rm", "--force"]


def test_timeout_removes_container_and_kills_client(repo, monkeypatch):
    calls = []

    class Process:
        stdout = io.BytesIO(b"running\n")
        returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            if self.returncode is None:
                raise subprocess.TimeoutExpired("docker", timeout)
            return self.returncode

        def kill(self):
            self.returncode = -9

    process = Process()
    monkeypatch.setattr(Sandbox, "available", lambda self: {"status": "available"})
    monkeypatch.setattr("repofix.sandbox.subprocess.Popen", lambda *a, **kw: process)
    monkeypatch.setattr(
        "repofix.sandbox.subprocess.run", lambda command, **kw: calls.append(command)
    )
    result = Sandbox(timeout=0.001).run(repo)
    assert result["status"] == "timeout" and process.returncode == -9
    assert calls[0][:3] == ["docker", "rm", "--force"]


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("passed", 0),
        ("early_exit", 79),
        ("skipped", 79),
        ("empty", 79),
        ("collection_error", 79),
        ("mutated_test", 79),
    ],
)
def test_trusted_wrapper_rejects_unverified_child_success(
    repo, tmp_path, monkeypatch, scenario, expected
):
    """Execute only our trusted wrapper; replace child execution with a stub.

    No candidate project code runs on the host. An early exit simulates a child
    that returns zero without producing JUnit; skip simulates pytest skip output.
    """
    scratch = tmp_path / "scratch"
    report = tmp_path / "public-results.xml"
    mapping = {
        "/source": str(repo),
        "/tmp/work": str(scratch),
        "/tmp/public-results.xml": str(report),
    }

    class LocalPaths(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str) and node.value in mapping:
                return ast.copy_location(ast.Constant(mapping[node.value]), node)
            return node

    script = LocalPaths().visit(ast.parse(RUNNER))
    ast.fix_missing_locations(script)
    captured = []

    def fake_child(command, **kwargs):
        captured.append(command)
        if scenario != "early_exit":
            case = '<testcase name="test_example"/>'
            errors = 0
            if scenario == "skipped":
                case = '<testcase name="test_example"><skipped/></testcase>'
            elif scenario == "empty":
                case = ""
            elif scenario == "collection_error":
                errors = 1
                case = '<testcase name="collection"><error/></testcase>'
            report.write_text(
                f'<testsuites><testsuite errors="{errors}">{case}</testsuite></testsuites>',
                encoding="utf-8",
            )
        if scenario == "mutated_test":
            (scratch / "tests/test_sample.py").write_text("pass\n", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_child)
    monkeypatch.setattr(sys, "argv", ["runner", json.dumps(["tests/test_sample.py"])])
    previous = os.getcwd()
    try:
        with pytest.raises(SystemExit) as stopped:
            exec(compile(script, "trusted-runner-fixture", "exec"), {})
    finally:
        os.chdir(previous)
    assert stopped.value.code == expected
    assert captured[0][1:3] == ["-I", "-c"]
    assert "import pytest" in captured[0][3]
