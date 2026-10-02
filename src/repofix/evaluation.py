"""Frozen synthetic evaluation; acceptance data never enters Agent workspaces."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Settings, project_root


def benchmark_root() -> Path:
    return project_root() / "benchmarks"


def load_tasks(split: str = "dev", root: Path | None = None) -> list[dict[str, Any]]:
    if split not in {"dev", "eval", "all"}:
        raise ValueError("split must be dev, eval, or all")
    root = root or benchmark_root()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return [item for item in manifest["tasks"] if split == "all" or item["split"] == split]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_snapshot(task: Path) -> dict[str, Any]:
    """Reject changed fixture releases rather than silently change the benchmark."""
    meta = json.loads((task / "meta.json").read_text(encoding="utf-8"))
    repo = task / "repo"
    files = {p.relative_to(repo).as_posix(): p for p in repo.rglob("*") if p.is_file()}
    # Python-generated caches do not form part of the released snapshot.
    files = {name: path for name, path in files.items() if "__pycache__" not in path.parts}
    files = {name: path for name, path in files.items() if ".pytest_cache" not in path.parts}
    if set(files) != set(meta["source_sha256"]):
        raise ValueError(f"Fixture file set changed: {meta['id']}")
    for relative, digest in meta["source_sha256"].items():
        path = files[relative]
        if path.is_symlink() or sha256(path) != digest:
            raise ValueError(f"Fixture integrity mismatch: {meta['id']}/{relative}")
    for relative, key in (
        ("issue.md", "issue_sha256"),
        ("hidden/test_acceptance.py", "acceptance_sha256"),
    ):
        if sha256(task / relative) != meta[key]:
            raise ValueError(f"Evaluation data integrity mismatch: {meta['id']}/{relative}")
    return meta


def test_integrity(original: Path, repaired: Path) -> list[str]:
    """Check the published tests and reject added pytest control files."""
    errors = []
    if any(path.is_symlink() for path in repaired.rglob("*")):
        return ["Symbolic links are forbidden in a repair"]
    originals = {
        p.relative_to(original).as_posix(): sha256(p)
        for p in (original / "tests").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    current = {
        p.relative_to(repaired).as_posix(): sha256(p)
        for p in (repaired / "tests").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    if originals != current:
        errors.append("Published test files were modified, removed, or added")
    forbidden = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"}
    for path in repaired.rglob("*"):
        if path.name in forbidden:
            relative = path.relative_to(repaired)
            before = original / relative
            if not path.is_file() or not before.is_file() or sha256(path) != sha256(before):
                errors.append(f"Pytest control file changed: {relative.as_posix()}")
    return sorted(set(errors))


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _failed_type(state: dict, public: dict, acceptance: dict, integrity: list) -> str | None:
    if integrity:
        return "test_integrity_violation"
    if public.get("status") == "unavailable" or acceptance.get("status") == "unavailable":
        return "sandbox_unavailable"
    if state.get("status") in {"timed_out", "cancelled"}:
        return state["status"]
    if state.get("model_errors", 0) and state.get("error"):
        return "model_error"
    if "budget exhausted" in str(state.get("summary", "")).lower():
        return "budget_exhausted"
    if not state.get("candidate_patch"):
        return "no_patch"
    if public.get("status") != "passed":
        return "public_test_failure"
    if acceptance.get("status") != "passed":
        return "acceptance_failure"
    return None


def evaluate(
    settings: Settings,
    split: str = "dev",
    mode: str = "mock",
    output: Path | None = None,
    allow_paid: bool = False,
    max_calls: int = 12,
) -> dict[str, Any]:
    """Run paired baseline/Agent tasks, retaining unknown measurements as null.

    allow_paid acknowledges a bounded live run, not an automatic spending cap.
    The CLI prints the upper bound before any request. Model cost is unknown
    until independently priced; no token price is invented by this evaluator.
    """
    if mode not in {"mock", "live"}:
        raise ValueError("mode must be mock or live")
    if not 1 <= max_calls <= 33:
        raise ValueError("max_calls must be between 1 and 33")
    if mode == "live" and not allow_paid:
        raise ValueError("Live batch evaluation requires --allow-paid and an explicit call budget")
    if mode == "live" and (not settings.api_key or not settings.model):
        raise ValueError("Configure API key and model locally before live evaluation")

    # Imports stay here so fixture validation needs no Engine or Docker runtime.
    from .engine import Engine
    from .sandbox import Sandbox
    from .workspace import Workspace

    root = benchmark_root()
    tasks = load_tasks(split, root)
    output = Path(output or Path("evaluation-results") / f"{mode}-{split}").resolve()
    if (output / "summary.json").exists():
        raise ValueError(
            "Evaluation output already contains a run; choose a fresh output directory"
        )
    output.mkdir(parents=True, exist_ok=True)
    for item in tasks:
        meta = verify_snapshot(root / "tasks" / item["id"])
        if meta["initial_version"] != item["initial_version"]:
            raise ValueError("Manifest and fixture versions differ")
    config: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark": "synthetic-v0.1",
        "provenance": "self-authored artificial bugs; MIT",
        "mode": mode,
        "split": split,
        "task_ids": [item["id"] for item in tasks],
        "model": settings.model if mode == "live" else "scripted-demo-mock",
        "sandbox_image": settings.sandbox_image,
        "cost_usd": None,
        "budgets": {
            "baseline": {"max_model_calls": 1, "max_repairs": 1},
            "agent": {"max_model_calls": max_calls, "max_repairs": 3},
            "context_chars": 32000,
            "max_output_tokens": 1800,
            "timeout_seconds": 180,
            "maximum_total_model_calls": len(tasks) * (1 + max_calls) if mode == "live" else 0,
        },
        "comparison_note": "Same model and tasks; baseline has one response, Agent has a larger explicit budget. This is an architecture comparison, not equal compute.",
        "context_policy": {
            "baseline": "Issue and bounded source Python context; one patch response; no test feedback",
            "agent": "Issue and tool-selected context; public tests readable; test-feedback iterations allowed",
        },
        "disclaimer": (
            "ENGINEERING ONLY: mock uses a hand-scripted fixture pattern, not model predictions; even a matching edit is excluded from real-model scores. All real-model repair metrics are null."
            if mode == "mock"
            else "Small synthetic benchmark; results do not establish real production or SWE-bench performance."
        ),
    }
    _save(output / "config.json", config)
    engine = Engine(settings)
    sandbox = Sandbox(timeout=settings.sandbox_timeout, image=settings.sandbox_image)
    records: list[dict[str, Any]] = []
    for item in tasks:
        task = root / "tasks" / item["id"]
        issue = (task / "issue.md").read_text(encoding="utf-8")
        for strategy in ("baseline", "agent"):
            started = time.monotonic()
            limit_calls = 1 if strategy == "baseline" else max_calls
            initial = engine.create(
                task / "repo",
                issue,
                mode=mode,
                strategy=strategy,
                limits={
                    "max_model_calls": limit_calls,
                    "max_tool_calls": max(6, limit_calls * 3),
                    "max_repairs": 1 if strategy == "baseline" else 3,
                    "timeout_seconds": 180,
                    "context_chars": 32000,
                    "max_output_tokens": 1800,
                },
                allow_paid=allow_paid,
            )
            state = engine.run(initial["id"])
            repaired = Workspace.open(settings.data_dir / "tasks" / initial["id"]).repo
            integrity = test_integrity(task / "repo", repaired)
            public = state.get("public_tests") or {"status": "not_run"}
            acceptance: dict[str, Any] = {
                "status": "not_measured",
                "reason": "mock engineering run",
            }
            if mode == "live" and not integrity:
                # Temporary evaluation copy is never handed to the model/Agent.
                with tempfile.TemporaryDirectory(prefix="repofix-eval-") as temporary:
                    stage = Path(temporary) / "repo"
                    shutil.copytree(
                        repaired,
                        stage,
                        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
                    )
                    acceptance_path = stage / "_acceptance" / "test_acceptance.py"
                    acceptance_path.parent.mkdir()
                    shutil.copy2(task / "hidden" / "test_acceptance.py", acceptance_path)
                    public = sandbox.run(stage, tests=["tests/test_public.py"])
                    acceptance = sandbox.run(stage, tests=["_acceptance/test_acceptance.py"])
            elif integrity:
                acceptance = {"status": "rejected", "reason": "test integrity violation"}
            measured = mode == "live" and (
                bool(integrity) or acceptance.get("status") in {"passed", "failed", "timeout"}
            )
            record = {
                "task_id": item["id"],
                "strategy": strategy,
                "mode": mode,
                "engine_task_id": initial["id"],
                "initial_version": item["initial_version"],
                "acceptance_sha256": json.loads((task / "meta.json").read_text(encoding="utf-8"))[
                    "acceptance_sha256"
                ],
                "category": item["category"],
                "status": state.get("status"),
                "summary": state.get("summary"),
                "error": state.get("error"),
                "model_errors": state.get("model_errors", 0),
                "candidate_proposed": bool(state.get("candidate_patch")),
                "test_integrity_errors": integrity,
                "public_tests": public,
                "independent_acceptance": acceptance,
                "repair_success": (
                    bool(
                        not integrity
                        and public.get("status") == "passed"
                        and acceptance.get("status") == "passed"
                    )
                    if measured
                    else None
                ),
                "wall_seconds": round(time.monotonic() - started, 6),
                "usage": state.get("usage", {}),
                "cost_usd": None,
                "failure_type": _failed_type(state, public, acceptance, integrity),
            }
            records.append(record)
            _save(output / "tasks" / f"{item['id']}-{strategy}.json", record)
            (output / "tasks" / f"{item['id']}-{strategy}.patch").write_text(
                state.get("candidate_patch") or "",
                encoding="utf-8",
            )
    metrics = {}
    for strategy in ("baseline", "agent"):
        selected = [record for record in records if record["strategy"] == strategy]
        verified = [record for record in selected if record["repair_success"] is not None]
        complete = mode == "live" and len(verified) == len(tasks)
        metrics[strategy] = {
            "configured_tasks": len(tasks),
            "independently_tested_tasks": len(verified),
            "repair_successes": sum(record["repair_success"] for record in verified)
            if complete
            else None,
            "repair_success_rate": sum(record["repair_success"] for record in verified) / len(tasks)
            if complete
            else None,
            "regression_passes": sum(
                record["public_tests"].get("status") == "passed" for record in selected
            )
            if complete
            else None,
            "real_model_metrics_measured": complete,
            "cost_usd": None,
            "observed_wall_seconds": round(sum(record["wall_seconds"] for record in selected), 6),
            "failure_types": {
                name: sum(record["failure_type"] == name for record in selected)
                for name in sorted(
                    {record["failure_type"] for record in selected if record["failure_type"]}
                )
            },
        }
    summary = {"config": config, "metrics": metrics, "records": records}
    _save(output / "summary.json", summary)
    (output / "README.md").write_text(
        "# Evaluation run\n\n"
        + config["disclaimer"]
        + "\n\n"
        + f"Split: {split}; {len(tasks)} configured tasks per strategy.\n\n"
        + "See summary.json for denominators, unavailable measurements, per-task outcomes and budgets. "
        + "Cost is unknown. Mock calls and durations are engineering observations only.\n",
        encoding="utf-8",
    )
    return summary
