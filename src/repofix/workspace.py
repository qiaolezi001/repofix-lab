"""Bounded, secret-filtered working copies; task tools never touch the source repo."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath

MAX_FILE_BYTES = 256 * 1024
MAX_REPO_BYTES = 8 * 1024 * 1024
MAX_FILES = 500
ALLOWED_SUFFIXES = {".py", ".md"}
DENIED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    ".receipts",
    "benchmarks",
    "benchmark",
    "private_tests",
    "hidden_tests",
    "oracle",
    "solutions",
    "answers",
    ".github",
}
DENIED_NAMES = {
    "conftest.py",
    "setup.py",
    "metadata.py",
    "answer.py",
    "solution.py",
    "reference.py",
    "reference_patch.py",
    "oracle.py",
    "pytest.py",
    "sitecustomize.py",
    "usercustomize.py",
    "evaluation.py",
    "evaluate.py",
}


class WorkspaceError(ValueError):
    """A user-readable working-copy or path policy violation."""


def denied_path(relative: str) -> bool:
    """Keep secrets, hidden files, answers, and environment infrastructure out."""
    if any(ord(character) < 32 for character in relative) or ":" in relative or "\\" in relative:
        return True
    parts = PurePosixPath(relative).parts
    for part in parts:
        name = part.lower()
        if name in DENIED_DIRS or name.startswith("."):
            return True
        if any(word in name for word in ("secret", "credential", "api_key", "apikey")):
            return True
        if name in {"id_rsa", "id_ed25519"} or name.endswith((".pem", ".key", ".p12")):
            return True
    return parts[-1].lower() in DENIED_NAMES if parts else True


def is_test(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (
        any(part.lower() in {"test", "tests", "testing"} for part in path.parts[:-1])
        or path.name.lower().startswith("test_")
        or path.name.lower().endswith("_test.py")
        or path.name.lower() == "conftest.py"
    )


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_link(path: Path) -> bool:
    """Windows junctions are reparse points even when is_symlink() is false."""
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class Workspace:
    """A logical immutable baseline and an isolated mutable repo.

    The manifest is outside the agent-visible repo. Tools verify the baseline and
    every protected test against it. The caller owns the task root directory.
    """

    def __init__(self, source: Path, root: Path):
        if is_link(Path(source)):
            raise WorkspaceError("Source directory must not be a symbolic link or junction")
        source = Path(source).resolve(strict=True)
        self.root = Path(root).resolve()
        if not source.is_dir():
            raise WorkspaceError("Source must be a directory")
        if source == self.root or source in self.root.parents or self.root in source.parents:
            raise WorkspaceError("Source and task workspace must not overlap")
        self.repo, self.baseline = self.root / "repo", self.root / "baseline"
        if self.repo.exists() or self.baseline.exists() or (self.root / "manifest.json").exists():
            raise WorkspaceError("Task workspace already exists; use Workspace.open for recovery")
        self.warnings: list[str] = []
        files: dict[str, bytes] = {}
        total = 0
        visited = 0
        for current, dirs, names in os.walk(source, followlinks=False):
            visited += len(dirs) + len(names)
            if visited > 10_000:
                raise WorkspaceError("Repository scan exceeds 10,000 entries")
            for dirname in list(dirs):
                item = Path(current) / dirname
                if is_link(item):
                    raise WorkspaceError(
                        f"Symbolic links are not accepted: {item.relative_to(source)}"
                    )
                if denied_path(item.relative_to(source).as_posix() + "/placeholder.py"):
                    dirs.remove(dirname)
            for name in sorted(names):
                item = Path(current) / name
                relative = item.relative_to(source).as_posix()
                if is_link(item):
                    raise WorkspaceError(f"Symbolic links are not accepted: {relative}")
                if denied_path(relative) or item.suffix.lower() not in ALLOWED_SUFFIXES:
                    self.warnings.append(f"Excluded by file policy: {relative}")
                    continue
                if item.stat().st_size > MAX_FILE_BYTES:
                    self.warnings.append(f"Skipped file over {MAX_FILE_BYTES} bytes: {relative}")
                    continue
                data = item.read_bytes()
                try:
                    data.decode("utf-8")
                except UnicodeDecodeError:
                    self.warnings.append(f"Skipped non-UTF-8 text: {relative}")
                    continue
                total += len(data)
                if total > MAX_REPO_BYTES or len(files) >= MAX_FILES:
                    raise WorkspaceError("Repository exceeds the file count or total byte limit")
                files[relative] = data
        if not any(name.endswith(".py") for name in files):
            raise WorkspaceError("Source contains no accepted Python files")
        self._manifest = {name: digest(data) for name, data in sorted(files.items())}
        self.version = digest(json.dumps(self._manifest, sort_keys=True).encode())
        for directory in (self.baseline, self.repo):
            directory.mkdir(parents=True, exist_ok=True)
            for relative, data in files.items():
                target = directory / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        atomic_json(
            self.root / "manifest.json",
            {
                "version": self.version,
                "files": self._manifest,
                "warnings": self.warnings,
            },
        )

    @classmethod
    def open(cls, root: Path) -> Workspace:
        instance = cls.__new__(cls)
        instance.root = Path(root).resolve(strict=True)
        instance.repo, instance.baseline = instance.root / "repo", instance.root / "baseline"
        manifest = json.loads((instance.root / "manifest.json").read_text(encoding="utf-8"))
        instance.version = manifest["version"]
        instance._manifest = manifest["files"]
        instance.warnings = manifest["warnings"]
        instance.validate()
        return instance

    def resolve(self, relative: str, *, writable: bool = False) -> Path:
        if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
            raise WorkspaceError("Use a nonempty POSIX relative path")
        posix, windows = PurePosixPath(relative), PureWindowsPath(relative)
        if posix.is_absolute() or windows.drive or ".." in posix.parts or ":" in relative:
            raise WorkspaceError("Absolute paths and traversal are forbidden")
        if denied_path(relative) or posix.suffix.lower() not in ALLOWED_SUFFIXES:
            raise WorkspaceError("Path is excluded by the file policy")
        if relative not in self._manifest:
            raise WorkspaceError("Only files from the original accepted snapshot are accessible")
        current = self.repo
        for part in posix.parts:
            current = current / part
            if is_link(current):
                raise WorkspaceError("Symbolic link access is forbidden")
        resolved = current.resolve(strict=True)
        if self.repo.resolve() not in resolved.parents or not resolved.is_file():
            raise WorkspaceError("Path escapes the working copy or is not a file")
        if writable and (posix.suffix.lower() != ".py" or is_test(relative)):
            raise WorkspaceError("Only source Python files may be patched; tests are protected")
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise WorkspaceError("File exceeds the byte limit")
        return resolved

    def validate(self) -> None:
        for base in (self.repo, self.baseline):
            if is_link(base) or not base.is_dir():
                raise WorkspaceError("Working copy or baseline is missing or is a symbolic link")
            actual: set[str] = set()
            for current, dirs, names in os.walk(base, followlinks=False):
                for name in dirs + names:
                    if is_link(Path(current) / name):
                        raise WorkspaceError("Symbolic links are forbidden in a task workspace")
                for name in names:
                    actual.add((Path(current) / name).relative_to(base).as_posix())
            if actual != set(self._manifest):
                raise WorkspaceError("Snapshot file set changed outside the patch tool")
        total = 0
        for relative, expected in self._manifest.items():
            if digest((self.baseline / relative).read_bytes()) != expected:
                raise WorkspaceError(f"Immutable baseline was modified: {relative}")
            target = self.resolve(relative)
            total += target.stat().st_size
            if is_test(relative) and digest(target.read_bytes()) != expected:
                raise WorkspaceError(f"Protected test was modified: {relative}")
        if total > MAX_REPO_BYTES:
            raise WorkspaceError("Patched repository exceeds total byte limit")

    def files(self) -> list[str]:
        return sorted(self._manifest)

    def test_files(self) -> list[str]:
        return [name for name in self.files() if name.endswith(".py") and is_test(name)]
