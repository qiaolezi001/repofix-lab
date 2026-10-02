"""Dependency-free BM25 retrieval over Python AST symbols and module statements."""

from __future__ import annotations

import ast
import math
import re
from collections import Counter
from pathlib import Path

from .workspace import MAX_FILE_BYTES, denied_path, digest, is_link


def tokenize(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ")
    return re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", value.lower())


class Index:
    def __init__(self, root: Path, version: str):
        self.root, self.version = Path(root), version
        self.warnings: list[str] = []
        self.chunks: list[dict] = []
        for file in sorted(self.root.rglob("*.py")):
            relative = file.relative_to(self.root).as_posix()
            if is_link(file) or denied_path(relative):
                self.warnings.append(f"Excluded path: {relative}")
                continue
            if file.stat().st_size > MAX_FILE_BYTES:
                self.warnings.append(f"Skipped oversized file: {relative}")
                continue
            try:
                data = file.read_bytes()
                source = data.decode("utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                self.warnings.append(f"Cannot read {relative}: {type(exc).__name__}")
                continue
            lines = source.splitlines()
            try:
                tree = ast.parse(source, filename=relative)
            except SyntaxError as exc:
                self.warnings.append(
                    f"Syntax error in {relative}:{exc.lineno}; indexed bounded text"
                )
                self._add(relative, "<syntax-error>", 1, len(lines), lines, digest(data))
                continue

            def visit(nodes: list[ast.stmt], prefix: str = "") -> None:
                for node in nodes:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        symbol = prefix + node.name
                        self._add(
                            relative,
                            symbol,
                            node.lineno,
                            node.end_lineno or node.lineno,
                            lines,
                            digest(data),
                        )
                        visit(node.body, symbol + ".")
                    elif not prefix:
                        self._add(
                            relative,
                            "<module>",
                            node.lineno,
                            node.end_lineno or node.lineno,
                            lines,
                            digest(data),
                        )

            visit(tree.body)
        self._counts = [
            Counter(tokenize(chunk["symbol"] + " " + chunk["path"] + " " + chunk["text"]))
            for chunk in self.chunks
        ]
        self._lengths = [sum(count.values()) for count in self._counts]
        self._average = sum(self._lengths) / max(len(self.chunks), 1)
        self._frequency = Counter(term for count in self._counts for term in count)

    def _add(
        self, path: str, symbol: str, start: int, end: int, lines: list[str], sha: str
    ) -> None:
        if end < start:
            return
        # Split large symbols into bounded passages without inventing line numbers.
        for first in range(start, end + 1, 100):
            last = min(first + 99, end)
            text = "\n".join(lines[first - 1 : last])
            if len(text) > 16_000:
                self.warnings.append(f"Skipped oversized code passage: {path}:{first}-{last}")
                continue
            self.chunks.append(
                {
                    "path": path,
                    "symbol": symbol,
                    "start_line": first,
                    "end_line": last,
                    "text": text,
                    "version": self.version,
                    "content_sha256": sha,
                }
            )

    def search(self, query: str, limit: int = 5) -> list[dict]:
        if not query.strip() or not 1 <= limit <= 10:
            return []
        terms = set(tokenize(query))
        scored: list[tuple[float, int]] = []
        number = len(self.chunks)
        for position, frequencies in enumerate(self._counts):
            score = 0.0
            for term in terms:
                tf = frequencies.get(term, 0)
                if not tf:
                    continue
                df = self._frequency[term]
                idf = math.log(1 + (number - df + 0.5) / (df + 0.5))
                score += (
                    idf
                    * tf
                    * 2.5
                    / (tf + 1.5 * (0.25 + 0.75 * self._lengths[position] / max(self._average, 1)))
                )
            if score > 0:
                scored.append((score, position))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            dict(self.chunks[position], score=round(score, 6)) for score, position in scored[:limit]
        ]
