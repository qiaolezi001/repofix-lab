"""Validate ONLY our trusted self-authored fixtures; never execute Agent edits here."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repofix.config import Settings
from repofix.evaluation import (
    benchmark_root,
    evaluate,
    load_tasks,
    verify_snapshot,
)
from repofix.evaluation import (
    test_integrity as inspect_test_integrity,
)


def test_frozen_manifest_and_provenance():
    tasks = load_tasks("all")
    assert len(tasks) == 15
    assert len({task["id"] for task in tasks}) == 15
    assert len(load_tasks("dev")) == 6
    assert len(load_tasks("eval")) == 9
    assert {task["project"] for task in tasks} == {"numeric", "text", "catalog"}
    assert {task["category"] for task in tasks} >= {"cross_file", "exception", "boundary"}
    for task in tasks:
        metadata = verify_snapshot(benchmark_root() / "tasks" / task["id"])
        assert metadata["initial_version"] == task["initial_version"]
        assert "artificially" in metadata["provenance"]
        repo = benchmark_root() / "tasks" / task["id"] / "repo"
        assert not list(repo.rglob("reference.json"))
        assert not list(repo.rglob("test_acceptance.py"))
        assert not list(repo.rglob("meta.json"))


def _run_authored_tests(repo: Path) -> subprocess.CompletedProcess:
    # Only called after checking the immutable release hashes of fixtures
    # written by this project, or after applying their author reference patch.
    environment = dict(os.environ)
    environment.update(
        PYTHONPATH=str(repo),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    environment.pop("PYTEST_ADDOPTS", None)
    # On Windows, NUL resolves to a device path: pytest may scan outside the
    # fixture while determining its collection root. Use a real empty config
    # outside the frozen repo and explicitly bound collection to its test dir.
    config = repo.parent / "authoring-pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-c",
            str(config),
            "--rootdir",
            str(repo),
            "--confcutdir",
            str(repo),
            "-p",
            "no:cacheprovider",
            str(repo / "tests"),
        ],
        cwd=repo,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_fixture_collection_ignores_sibling_tests_and_inherited_options(tmp_path, monkeypatch):
    repo = tmp_path / "fixture"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests/test_public.py").write_text(
        "def test_local():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "test_outside.py").write_text(
        "raise RuntimeError('Outside fixture must not be collected')\n", encoding="utf-8"
    )
    monkeypatch.setenv("PYTEST_ADDOPTS", "--invalid-inherited-option")
    result = _run_authored_tests(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


@pytest.mark.parametrize("task_id", [task["id"] for task in load_tasks("all")])
def test_authored_bug_reproduces_and_reference_passes(task_id, tmp_path):
    task = benchmark_root() / "tasks" / task_id
    verify_snapshot(task)
    repo = tmp_path / "fixture"
    shutil.copytree(
        task / "repo", repo, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache")
    )
    original = _run_authored_tests(repo)
    assert original.returncode == 1, original.stdout + original.stderr
    reference = json.loads((task / "reference.json").read_text(encoding="utf-8"))
    for edit in reference["edits"]:
        path = repo / edit["path"]
        text = path.read_text(encoding="utf-8")
        assert text.count(edit["old"]) == 1
        path.write_text(text.replace(edit["old"], edit["new"], 1), encoding="utf-8")
    shutil.copy2(task / "hidden" / "test_acceptance.py", repo / "tests" / "test_acceptance.py")
    fixed = _run_authored_tests(repo)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr


def test_changed_fixture_is_rejected(tmp_path):
    task = benchmark_root() / "tasks" / "numeric-01"
    copied = tmp_path / "task"
    shutil.copytree(task, copied, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (copied / "repo" / "numberkit" / "bounds.py").write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity mismatch"):
        verify_snapshot(copied)


def test_public_test_tampering_and_pytest_config_are_rejected(tmp_path):
    original = benchmark_root() / "tasks" / "numeric-01" / "repo"
    repaired = tmp_path / "repo"
    shutil.copytree(original, repaired)
    assert inspect_test_integrity(original, repaired) == []
    public = repaired / "tests" / "test_public.py"
    public.write_text("def test_nothing():\n    pass\n", encoding="utf-8")
    (repaired / "conftest.py").write_text("import pytest\n", encoding="utf-8")
    errors = inspect_test_integrity(original, repaired)
    assert any("Published test" in error for error in errors)
    assert any("Pytest control" in error for error in errors)


def test_live_evaluation_requires_explicit_authorization(tmp_path):
    with pytest.raises(ValueError, match="allow-paid"):
        evaluate(Settings(data_dir=tmp_path), mode="live")
    assert not list(tmp_path.iterdir())


def test_live_evaluation_requires_local_credentials(tmp_path):
    with pytest.raises(ValueError, match="Configure API key"):
        evaluate(Settings(data_dir=tmp_path), mode="live", allow_paid=True)


def test_mock_evaluation_keeps_real_model_metrics_unknown(tmp_path, monkeypatch):
    import repofix.engine
    import repofix.sandbox
    from repofix.workspace import Workspace

    class FakeEngine:
        def __init__(self, settings):
            self.settings = settings
            self.count = 0

        def create(self, source, issue, **kwargs):
            self.count += 1
            task_id = str(self.count)
            # The source contains neither acceptance tests nor answer metadata.
            assert source.name == "repo"
            assert not (source / "reference.json").exists()
            assert not list(source.rglob("test_acceptance.py"))
            Workspace(source, self.settings.data_dir / "tasks" / task_id)
            return {"id": task_id}

        def run(self, task_id):
            return {
                "id": task_id,
                "status": "completed",
                "candidate_patch": "",
                "public_tests": {"status": "passed"},
                "usage": {"mock": True},
            }

    class FakeSandbox:
        def __init__(self, **kwargs):
            pass

        def run(self, *args, **kwargs):
            raise AssertionError("Mock must not measure independent model performance")

    monkeypatch.setattr(repofix.engine, "Engine", FakeEngine)
    monkeypatch.setattr(repofix.sandbox, "Sandbox", FakeSandbox)
    output = tmp_path / "results"
    summary = evaluate(Settings(data_dir=tmp_path / "data"), output=output)
    assert len(summary["records"]) == 12
    assert summary["config"]["budgets"]["maximum_total_model_calls"] == 0
    assert "ENGINEERING ONLY" in summary["config"]["disclaimer"]
    for metrics in summary["metrics"].values():
        assert metrics["repair_successes"] is None
        assert metrics["repair_success_rate"] is None
        assert metrics["regression_passes"] is None
        assert metrics["configured_tasks"] == 6
        assert metrics["independently_tested_tasks"] == 0
    assert len(list((output / "tasks").glob("*.json"))) == 12
    with pytest.raises(ValueError, match="already contains a run"):
        evaluate(Settings(data_dir=tmp_path / "data"), output=output)
