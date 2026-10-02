"""Report claims derive from tool outcomes, never model prose."""

import json
from typing import Any


def public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in state.items() if key not in {"messages", "pending", "source"}
    }


def markdown(state: dict[str, Any]) -> str:
    public = state["public_tests"]
    independent = state.get("independent_tests", {"status": "not_run"})
    evidence = (
        "\n".join(
            f"- `{e['path']}:{e.get('start_line', 1)}` — {e.get('symbol', 'source')} "
            f"(snapshot `{e.get('version', state['workspace_version'])[:12]}`)"
            for e in state["evidence"]
        )
        or "No source evidence collected."
    )
    return f"""# RepoFix-Lab task {state["id"]}

Mode: **{state["mode"]}** · Strategy: **{state["strategy"]}** · Status: **{state["status"]}**

{"**SCRIPTED MOCK: demonstrates engineering, not model accuracy.**" if state["mode"] == "mock" else "Live provider run; synthetic benchmark results have limited scope."}

## Claims supported by execution

- Candidate patch: {"produced" if state["candidate_patch"] else "not produced"}
- Public tests: **{public.get("status", "not_run")}**, complete suite: {public.get("complete_suite", False)}
- Independent acceptance: **{independent.get("status", "not_run")}**
- Real model benchmark accuracy: **not measured** in this task report.

## Issue

{state["issue"]}

## Agent summary (provider-generated, not a verification claim)

{state["summary"]}

## Evidence

{evidence}

## Candidate diff

```diff
{state["candidate_patch"] or "(none)"}
```

## Public verification

```json
{json.dumps(public, ensure_ascii=False, indent=2)}
```

## Usage

```json
{json.dumps(state["usage"], indent=2)}
```

Tool calls: {state["tool_calls"]} · Applied repair rounds: {state["repairs"]}

## Effective budgets

```json
{json.dumps(state["limits"], indent=2)}
```

## Execution events

```json
{json.dumps(state["events"], ensure_ascii=False, indent=2)}
```

Error: {state.get("error") or "none"}
"""
