"""Six validated agent tools, with protected tests and durable patch receipts."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .index import Index
from .sandbox import Sandbox
from .workspace import (
    MAX_FILE_BYTES,
    MAX_REPO_BYTES,
    Workspace,
    WorkspaceError,
    atomic_json,
    digest,
)

MAX_RESULT_CHARS = 48_000


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyArguments(Arguments):
    pass


class SearchArguments(Arguments):
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=10)


class ReadArguments(Arguments):
    path: str = Field(min_length=1, max_length=500)
    start_line: int = Field(default=1, ge=1)
    end_line: int = Field(default=100, ge=1)


class Edit(Arguments):
    path: str = Field(min_length=1, max_length=500)
    old: str = Field(min_length=1, max_length=MAX_FILE_BYTES)
    new: str = Field(max_length=MAX_FILE_BYTES)


class PatchArguments(Arguments):
    edits: list[Edit] = Field(min_length=1, max_length=20)


class TestArguments(Arguments):
    tests: list[str] | None = Field(default=None, max_length=100)


TOOL_MODELS: dict[str, tuple[type[Arguments], str]] = {
    "list_files": (EmptyArguments, "List accepted project files and baseline version."),
    "search_code": (SearchArguments, "Retrieve Python AST code evidence with BM25."),
    "read_file": (ReadArguments, "Read a bounded range of lines from an accepted project file."),
    "apply_patch": (
        PatchArguments,
        "Replace exact, unique source snippets. Tests and configs are protected.",
    ),
    "run_tests": (
        TestArguments,
        "Run selected public test files in Docker; null runs the complete suite.",
    ),
    "get_diff": (
        EmptyArguments,
        "Return the candidate unified diff against the immutable baseline.",
    ),
}


def _strict_schema(schema: dict) -> dict:
    """Provider strict mode requires every property and forbids extra keys."""
    schema = json.loads(json.dumps(schema))

    def visit(item):
        if isinstance(item, dict):
            item.pop("default", None)
            if item.get("type") == "object":
                item["additionalProperties"] = False
                item["required"] = list(item.get("properties", {}))
            for value in item.values():
                visit(value)
        elif isinstance(item, list):
            for value in item:
                visit(value)

    visit(schema)
    return schema


def _file_diff(workspace: Workspace, relative: str) -> str:
    before = (workspace.baseline / relative).read_bytes().decode("utf-8").splitlines(keepends=True)
    after = (workspace.repo / relative).read_bytes().decode("utf-8").splitlines(keepends=True)
    result = []
    for line in difflib.unified_diff(
        before, after, fromfile="a/" + relative, tofile="b/" + relative
    ):
        if line.endswith("\n"):
            result.append(line)
        else:
            result.append(line + "\n\\ No newline at end of file\n")
    return "".join(result)


def _normalize_edit(old: str, new: str, original: str) -> tuple[str, str, bool]:
    """Read tools emit LF; map edits back to uniform source LF/CRLF endings.

    Mixed or legacy CR-only files retain exact text matching. Journal hashes
    always describe actual bytes, while action fingerprints retain raw inputs.
    """
    styles = set(re.findall(r"\r\n|\r|\n", original))
    if len(styles) > 1 or styles == {"\r"}:
        return old, new, True
    ending = next(iter(styles), "\n")

    def convert(value: str) -> str:
        normalized = value.replace("\r\n", "\n")
        if "\r" in normalized:
            raise WorkspaceError("Uniform LF/CRLF files require LF or CRLF patch text")
        return normalized.replace("\n", ending)

    return convert(old), convert(new), False


def _write_receipt(path: Path, value: dict) -> None:
    """Keep failed journal/result writes from leaving their temporary sibling."""
    try:
        atomic_json(path, value)
    finally:
        path.with_suffix(path.suffix + ".tmp").unlink(missing_ok=True)


class ToolRegistry:
    def __init__(self, workspace: Workspace, sandbox: Sandbox, cancel_event=None):
        self.workspace, self.sandbox = workspace, sandbox
        self.cancel_event = cancel_event
        self.evidence: list[dict] = []
        self._local_patches = 0

    @property
    def schemas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "strict": True,
                    "parameters": _strict_schema(model.model_json_schema()),
                },
            }
            for name, (model, description) in TOOL_MODELS.items()
        ]

    @property
    def patch_count(self) -> int:
        count = self._local_patches
        folder = self.workspace.root / ".receipts"
        if folder.exists():
            for path in folder.glob("*.result.json"):
                receipt = json.loads(path.read_text(encoding="utf-8"))
                if receipt["name"] == "apply_patch" and receipt["result"]["ok"]:
                    count += 1
        return count

    def execute(self, name: str, arguments: dict, action_id: str | None = None) -> dict:
        if name not in TOOL_MODELS:
            return self._error("UNKNOWN_TOOL", f"Unknown tool: {name}")
        try:
            parsed = TOOL_MODELS[name][0].model_validate(arguments)
            if action_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", action_id):
                raise WorkspaceError("Action id must use letters, digits, underscores, or hyphens")
            self.workspace.validate()
            fingerprint = hashlib.sha256(
                json.dumps(
                    {"name": name, "arguments": parsed.model_dump()},
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            receipt_path = self._receipt_path(action_id, "result") if action_id else None
            if name == "apply_patch" and receipt_path and receipt_path.exists():
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if receipt["arguments_sha256"] != fingerprint:
                    raise WorkspaceError("Action id was reused with different tool arguments")
                return receipt["result"]
            if name == "apply_patch":
                assert isinstance(parsed, PatchArguments)
                data = self._patch(parsed, action_id, fingerprint)
                if action_id is None:
                    self._local_patches += 1
            else:
                data = getattr(self, "_" + name)(parsed)
            result = {"ok": True, "data": data, "error": None}
            if receipt_path:
                _write_receipt(
                    receipt_path, {"name": name, "arguments_sha256": fingerprint, "result": result}
                )
            return result
        except ValidationError as exc:
            # Do not echo rejected values: a malformed argument might contain secrets.
            fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
            return self._error(
                "INVALID_ARGUMENTS", "Invalid tool arguments at: " + ", ".join(fields)
            )
        except (WorkspaceError, ValueError) as exc:
            return self._error("POLICY_OR_PRECONDITION", str(exc))
        except OSError as exc:
            return self._error("IO_ERROR", f"Filesystem operation failed: {type(exc).__name__}")

    @staticmethod
    def _error(code: str, message: str) -> dict:
        return {"ok": False, "data": None, "error": {"code": code, "message": message}}

    def _receipt_path(self, action_id: str, kind: str) -> Path:
        return self.workspace.root / ".receipts" / f"{action_id}.{kind}.json"

    def _list_files(self, args: EmptyArguments) -> dict:
        return {
            "files": self.workspace.files(),
            "version": self.workspace.version,
            "warnings": self.workspace.warnings[:100],
        }

    def _search_code(self, args: SearchArguments) -> dict:
        index = Index(self.workspace.repo, self.workspace.version)
        found = index.search(args.query, args.limit)
        results, size = [], 0
        for item in found:
            if size + len(item["text"]) > MAX_RESULT_CHARS:
                break
            results.append(item)
            size += len(item["text"])
        self.evidence.extend(results)
        return {
            "results": results,
            "warnings": index.warnings[:100],
            "truncated": len(results) < len(found),
        }

    def _read_file(self, args: ReadArguments) -> dict:
        if args.end_line < args.start_line or args.end_line - args.start_line >= 200:
            raise WorkspaceError("Line range must be ordered and at most 200 lines")
        path = self.workspace.resolve(args.path)
        data = path.read_bytes()
        lines = data.decode("utf-8").splitlines()
        if args.start_line > len(lines):
            raise WorkspaceError("Requested start line is beyond the end of the file")
        text = "\n".join(lines[args.start_line - 1 : args.end_line])
        evidence = {
            "path": args.path,
            "symbol": "<read>",
            "start_line": args.start_line,
            "end_line": min(args.end_line, len(lines)),
            "text": text[:MAX_RESULT_CHARS],
            "version": self.workspace.version,
            "content_sha256": digest(data),
            "truncated": len(text) > MAX_RESULT_CHARS,
        }
        self.evidence.append(evidence)
        return evidence

    def _get_diff(self, args: EmptyArguments) -> dict:
        difference = "".join(
            _file_diff(self.workspace, relative) for relative in self.workspace.files()
        )
        return {
            "diff": difference[:MAX_RESULT_CHARS],
            "truncated": len(difference) > MAX_RESULT_CHARS,
        }

    def full_diff(self) -> str:
        """Complete patch export for the host application (tool output is capped)."""
        self.workspace.validate()
        return "".join(_file_diff(self.workspace, relative) for relative in self.workspace.files())

    def _run_tests(self, args: TestArguments) -> dict:
        return self.sandbox.run(self.workspace.repo, args.tests, cancel_event=self.cancel_event)

    def _patch(self, args: PatchArguments, action_id: str | None, fingerprint: str) -> dict:
        journal_path = self._receipt_path(action_id, "intent") if action_id else None
        if journal_path and journal_path.exists():
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            if journal["arguments_sha256"] != fingerprint:
                raise WorkspaceError("Action id was reused with different patch arguments")
            plans = journal["plans"]
            state = [
                digest(self.workspace.resolve(relative, writable=True).read_bytes())
                for relative in plans
            ]
            if all(
                actual == plans[relative]["after_sha256"]
                for relative, actual in zip(plans, state, strict=True)
            ):
                return self._patch_result(list(plans), len(args.edits), recovered=True)
            if not all(
                actual == plans[relative]["before_sha256"]
                for relative, actual in zip(plans, state, strict=True)
            ):
                raise WorkspaceError(
                    "Interrupted multi-file patch has mixed contents; inspect intent journal before recovery"
                )
        else:
            plans = {}
            for edit in args.edits:
                path = self.workspace.resolve(edit.path, writable=True)
                before = path.read_bytes().decode("utf-8")
                original = plans.get(edit.path, {}).get("before", before)
                current = plans.get(edit.path, {}).get("after", before)
                old, new, exact_only = _normalize_edit(edit.old, edit.new, original)
                if current.count(old) != 1:
                    detail = "; mixed/CR-only newlines require exact matching" if exact_only else ""
                    raise WorkspaceError(f"Patch requires exactly one match in {edit.path}{detail}")
                after = current.replace(old, new, 1)
                if after == current:
                    raise WorkspaceError("Patch does not change source text")
                if len(after.encode("utf-8")) > MAX_FILE_BYTES:
                    raise WorkspaceError("Patch exceeds the per-file byte limit")
                plans[edit.path] = {
                    "before": original,
                    "after": after,
                    "before_sha256": digest(original.encode("utf-8")),
                    "after_sha256": digest(after.encode("utf-8")),
                }
            total = sum(
                (self.workspace.repo / relative).stat().st_size
                for relative in self.workspace.files()
            )
            total += sum(
                len(plan["after"].encode()) - len(plan["before"].encode())
                for plan in plans.values()
            )
            if total > MAX_REPO_BYTES:
                raise WorkspaceError("Patch exceeds the repository byte limit")
            if journal_path:
                _write_receipt(journal_path, {"arguments_sha256": fingerprint, "plans": plans})
        staged: dict[str, Path] = {}
        replaced: list[str] = []
        try:
            for relative, plan in plans.items():
                path = self.workspace.resolve(relative, writable=True)
                temporary = path.with_name(path.name + ".repofix-" + uuid.uuid4().hex)
                # Register before open/write/fsync so every failure path cleans up.
                staged[relative] = temporary
                with temporary.open("wb") as stream:
                    stream.write(plan["after"].encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
            for relative, temporary in staged.items():
                os.replace(temporary, self.workspace.resolve(relative, writable=True))
                replaced.append(relative)
        except OSError:
            for relative in replaced:
                (self.workspace.repo / relative).write_bytes(
                    plans[relative]["before"].encode("utf-8")
                )
            raise
        finally:
            for temporary in staged.values():
                temporary.unlink(missing_ok=True)
        return self._patch_result(list(plans), len(args.edits), recovered=False)

    def _patch_result(self, paths: list[str], count: int, recovered: bool) -> dict:
        return {
            "changed_files": paths,
            "patch_count": count,
            "recovered": recovered,
            **self._get_diff(EmptyArguments()),
        }
