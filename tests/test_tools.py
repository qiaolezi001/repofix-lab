"""Patch integrity, strict schemas, path policy, and durable replay verification."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from repofix.sandbox import Sandbox
from repofix.tools import ToolRegistry
from repofix.workspace import MAX_FILE_BYTES, Workspace, WorkspaceError


@pytest.fixture
def registry(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (source / "other.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "tests").mkdir()
    (source / "tests" / "test_calc.py").write_text(
        "def test_add():\n    assert True\n", encoding="utf-8"
    )
    (source / ".env").write_text("PRIVATE_VALUE=example", encoding="utf-8")
    (source / "api_key.py").write_text("PRIVATE_VALUE = 'example'", encoding="utf-8")
    (source / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    return ToolRegistry(Workspace(source, tmp_path / "task"), Sandbox())


def patch(registry, *, action_id=None):
    return registry.execute(
        "apply_patch",
        {"edits": [{"path": "calc.py", "old": "return a - b", "new": "return a + b"}]},
        action_id,
    )


def test_copy_filters_secrets_and_preserves_original(registry):
    assert registry.workspace.files() == ["calc.py", "other.py", "tests/test_calc.py"]
    result = patch(registry)
    assert result["ok"]
    assert "return a + b" in (registry.workspace.repo / "calc.py").read_text()
    assert "return a - b" in (registry.workspace.baseline / "calc.py").read_text()
    source = registry.workspace.root.parent / "source"
    assert "return a - b" in (source / "calc.py").read_text()
    assert "+    return a + b" in result["data"]["diff"]


@pytest.mark.parametrize(
    "path",
    [
        "../source/calc.py",
        "/etc/passwd",
        "C:/Windows/test.py",
        "tests/../calc.py",
        "calc.py:secret",
        "tests\\test_calc.py",
        ".env",
        "api_key.py",
        "new.py",
    ],
)
def test_path_escapes_and_disallowed_files_rejected(registry, path):
    result = registry.execute("read_file", {"path": path})
    assert not result["ok"]


def test_tests_cannot_be_patched(registry):
    result = registry.execute(
        "apply_patch",
        {"edits": [{"path": "tests/test_calc.py", "old": "assert True", "new": "pass"}]},
    )
    assert not result["ok"]
    assert "protected" in result["error"]["message"]


def test_all_patch_preconditions_checked_before_writes(registry):
    before = (registry.workspace.repo / "calc.py").read_bytes()
    result = registry.execute(
        "apply_patch",
        {
            "edits": [
                {"path": "calc.py", "old": "return a - b", "new": "return a + b"},
                {"path": "other.py", "old": "missing snippet", "new": "VALUE = 2"},
            ]
        },
    )
    assert not result["ok"]
    assert (registry.workspace.repo / "calc.py").read_bytes() == before


def test_write_failure_rolls_back_every_replaced_file(registry, monkeypatch):
    import repofix.tools as tool_module

    replace = tool_module.os.replace
    failed = False

    def injected_failure(source, target):
        nonlocal failed
        if Path(target).name == "other.py" and not failed:
            failed = True
            raise OSError("simulated failed atomic replace")
        replace(source, target)

    monkeypatch.setattr(tool_module.os, "replace", injected_failure)
    result = registry.execute(
        "apply_patch",
        {
            "edits": [
                {"path": "calc.py", "old": "return a - b", "new": "return a + b"},
                {"path": "other.py", "old": "VALUE = 1", "new": "VALUE = 2"},
            ]
        },
        "rollback",
    )
    assert not result["ok"] and result["error"]["code"] == "IO_ERROR"
    registry.workspace.validate()
    assert registry.full_diff() == ""


@pytest.mark.parametrize("failure_point", ["open", "write", "fsync"])
def test_staging_io_failure_cleans_temp_and_allows_retry(registry, monkeypatch, failure_point):
    import repofix.tools as tool_module

    original = (registry.workspace.repo / "calc.py").read_bytes()
    real_open = Path.open

    class PartialWrite:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, data):
            self.stream.write(data[:2])
            raise OSError("simulated ENOSPC after partial staging write")

    def fail_open(path, *args, **kwargs):
        if ".repofix-" in path.name:
            if failure_point == "open":
                raise OSError("simulated staging open failure")
            if failure_point == "write":
                return PartialWrite(real_open(path, *args, **kwargs))
        return real_open(path, *args, **kwargs)

    def fail_fsync(file_descriptor):
        raise OSError("simulated staging fsync failure")

    with monkeypatch.context() as failure:
        if failure_point == "fsync":
            failure.setattr(tool_module.os, "fsync", fail_fsync)
        else:
            failure.setattr(Path, "open", fail_open)
        result = patch(registry)
    assert not result["ok"] and result["error"]["code"] == "IO_ERROR"
    assert (registry.workspace.repo / "calc.py").read_bytes() == original
    assert not list(registry.workspace.repo.rglob("*.repofix-*"))
    registry.workspace.validate()
    assert patch(registry)["ok"]
    assert b"return a + b" in (registry.workspace.repo / "calc.py").read_bytes()
    registry.workspace.validate()


def test_receipt_io_failure_cleans_temp_and_allows_retry(registry, monkeypatch):
    import repofix.tools as tool_module

    original = (registry.workspace.repo / "calc.py").read_bytes()

    def fail_fsync(file_descriptor):
        raise OSError("simulated receipt fsync failure")

    with monkeypatch.context() as failure:
        failure.setattr(tool_module.os, "fsync", fail_fsync)
        result = patch(registry, action_id="receipt_failure")
    assert not result["ok"] and result["error"]["code"] == "IO_ERROR"
    assert not list((registry.workspace.root / ".receipts").glob("*.tmp"))
    assert (registry.workspace.repo / "calc.py").read_bytes() == original
    registry.workspace.validate()
    assert patch(registry, action_id="receipt_failure")["ok"]
    assert registry.patch_count == 1


def test_result_receipt_failure_cleans_temp_and_recovers_applied_patch(registry, monkeypatch):
    import repofix.tools as tool_module

    real_fsync = tool_module.os.fsync
    calls = 0

    def fail_result_fsync(file_descriptor):
        nonlocal calls
        calls += 1
        # Intent receipt, staged source, then the result receipt.
        if calls == 3:
            raise OSError("simulated result receipt fsync failure")
        real_fsync(file_descriptor)

    with monkeypatch.context() as failure:
        failure.setattr(tool_module.os, "fsync", fail_result_fsync)
        result = patch(registry, action_id="result_failure")
    assert not result["ok"] and result["error"]["code"] == "IO_ERROR"
    assert not list((registry.workspace.root / ".receipts").glob("*.tmp"))
    assert b"return a + b" in (registry.workspace.repo / "calc.py").read_bytes()
    registry.workspace.validate()
    retry = patch(registry, action_id="result_failure")
    assert retry["ok"] and retry["data"]["recovered"]
    assert registry.patch_count == 1


def test_nonunique_snippet_rejected(registry):
    assert not registry.execute(
        "apply_patch", {"edits": [{"path": "calc.py", "old": "a", "new": "c"}]}
    )["ok"]


def test_argument_validation_is_strict(registry):
    assert not registry.execute("search_code", {"query": "add", "limit": "5"})["ok"]
    assert not registry.execute("list_files", {"unexpected": True})["ok"]
    assert not registry.execute("read_file", {"path": "calc.py", "start_line": 1, "end_line": 500})[
        "ok"
    ]
    assert not registry.execute("apply_patch", {"edits": []})["ok"]
    assert registry.execute("unknown", {})["error"]["code"] == "UNKNOWN_TOOL"


def test_strict_provider_schemas_require_every_field(registry):
    for tool in registry.schemas:
        schema = tool["function"]["parameters"]
        assert tool["function"]["strict"] is True
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
    test_schema = next(item for item in registry.schemas if item["function"]["name"] == "run_tests")
    assert {
        variant["type"]
        for variant in test_schema["function"]["parameters"]["properties"]["tests"]["anyOf"]
    } == {"array", "null"}


def test_evidence_has_lines_version_and_content_hash(registry):
    search = registry.execute("search_code", {"query": "add", "limit": 5})
    read = registry.execute("read_file", {"path": "calc.py", "start_line": 1, "end_line": 2})
    assert search["data"]["results"]
    assert read["data"]["text"].endswith("return a - b")
    assert read["data"]["version"] == registry.workspace.version
    assert len(read["data"]["content_sha256"]) == 64
    assert len(registry.evidence) >= 2


def test_receipt_replay_does_not_double_apply(registry):
    first = patch(registry, action_id="run_1")
    second = patch(registry, action_id="run_1")
    assert first == second and first["ok"]
    assert registry.patch_count == 1
    recovered = ToolRegistry(Workspace.open(registry.workspace.root), Sandbox())
    assert patch(recovered, action_id="run_1") == first
    assert recovered.patch_count == 1


def test_patch_export_marks_missing_final_newline(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "value.py").write_bytes(b"VALUE = 1")
    tools = ToolRegistry(Workspace(source, tmp_path / "task"), Sandbox())
    assert tools.execute("apply_patch", {"edits": [{"path": "value.py", "old": "1", "new": "2"}]})[
        "ok"
    ]
    assert tools.full_diff().count("\\ No newline at end of file") == 2
    assert "-VALUE = 1\n" in tools.full_diff()
    assert "+VALUE = 2\n" in tools.full_diff()


@pytest.mark.parametrize("file_ending", ["\n", "\r\n"])
@pytest.mark.parametrize("edit_ending", ["\n", "\r\n"])
def test_multiline_edits_preserve_uniform_file_newlines(tmp_path, file_ending, edit_ending):
    source = tmp_path / "source"
    source.mkdir()
    old = "def add(a, b):\n    return a - b\n"
    new = "def add(a, b):\n    return a + b\n"
    initial = old.replace("\n", file_ending).encode()
    (source / "calc.py").write_bytes(initial)
    tools = ToolRegistry(Workspace(source, tmp_path / "task"), Sandbox())
    arguments = {
        "edits": [
            {
                "path": "calc.py",
                "old": old.replace("\n", edit_ending),
                "new": new.replace("\n", edit_ending),
            }
        ]
    }
    result = tools.execute("apply_patch", arguments, "newline")
    assert result["ok"]
    assert (tools.workspace.repo / "calc.py").read_bytes() == new.replace(
        "\n", file_ending
    ).encode()
    assert (tools.workspace.baseline / "calc.py").read_bytes() == initial
    assert tools.execute("apply_patch", arguments, "newline") == result


def test_mixed_newline_file_keeps_exact_matching(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    old = "def add(a, b):\r\n    return a - b\n"
    (source / "calc.py").write_bytes(old.encode())
    tools = ToolRegistry(Workspace(source, tmp_path / "task"), Sandbox())
    mismatch = tools.execute(
        "apply_patch",
        {"edits": [{"path": "calc.py", "old": old.replace("\r\n", "\n"), "new": "pass\n"}]},
    )
    assert not mismatch["ok"] and "exact matching" in mismatch["error"]["message"]
    new = old.replace("a - b", "a + b")
    assert tools.execute("apply_patch", {"edits": [{"path": "calc.py", "old": old, "new": new}]})[
        "ok"
    ]
    assert (tools.workspace.repo / "calc.py").read_bytes() == new.encode()


def test_completed_patch_without_result_receipt_recovers(registry):
    assert patch(registry, action_id="crash")["ok"]
    (registry.workspace.root / ".receipts" / "crash.result.json").unlink()
    recovered = ToolRegistry(Workspace.open(registry.workspace.root), Sandbox())
    result = patch(recovered, action_id="crash")
    assert result["ok"] and result["data"]["recovered"]
    assert recovered.patch_count == 1


def test_action_id_collision_and_mixed_transaction_stop(registry):
    arguments = {
        "edits": [
            {"path": "calc.py", "old": "return a - b", "new": "return a + b"},
            {"path": "other.py", "old": "VALUE = 1", "new": "VALUE = 2"},
        ]
    }
    assert registry.execute("apply_patch", arguments, "multi")["ok"]
    assert not registry.execute("apply_patch", {"edits": [arguments["edits"][0]]}, "multi")["ok"]
    (registry.workspace.root / ".receipts" / "multi.result.json").unlink()
    (registry.workspace.repo / "other.py").write_bytes(
        (registry.workspace.baseline / "other.py").read_bytes()
    )
    result = registry.execute("apply_patch", arguments, "multi")
    assert not result["ok"] and "mixed contents" in result["error"]["message"]


def test_tampered_test_or_baseline_detected(registry):
    (registry.workspace.repo / "tests/test_calc.py").write_text("pass\n", encoding="utf-8")
    assert not registry.execute("list_files", {})["ok"]
    with pytest.raises(WorkspaceError, match="Protected test"):
        Workspace.open(registry.workspace.root)


def test_oversize_file_warns_and_is_not_copied(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "ok.py").write_text("value = 1\n", encoding="utf-8")
    (source / "large.py").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    workspace = Workspace(source, tmp_path / "task")
    assert workspace.files() == ["ok.py"]
    assert any("over" in warning for warning in workspace.warnings)


def test_symlinks_rejected(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "ok.py").write_text("value = 1\n", encoding="utf-8")
    try:
        (source / "linked.py").symlink_to(source / "ok.py")
    except OSError:
        pytest.skip("Host lacks permission to create symbolic links")
    with pytest.raises(WorkspaceError, match="Symbolic links"):
        Workspace(source, tmp_path / "task")


def test_windows_junction_reparse_point_detected_without_link_privilege():
    from repofix.workspace import is_link

    link = SimpleNamespace(
        is_symlink=lambda: False, lstat=lambda: SimpleNamespace(st_file_attributes=0x400)
    )
    normal = SimpleNamespace(
        is_symlink=lambda: False, lstat=lambda: SimpleNamespace(st_file_attributes=0x20)
    )
    assert is_link(link)
    assert not is_link(normal)


def test_cancel_event_is_forwarded_to_sandbox(registry, monkeypatch):
    token = object()
    registry.cancel_event = token
    captured = {}

    def run(repo, tests, cancel_event):
        captured["token"] = cancel_event
        return {"status": "cancelled"}

    monkeypatch.setattr(registry.sandbox, "run", run)
    assert registry.execute("run_tests", {"tests": None})["data"]["status"] == "cancelled"
    assert captured["token"] is token
