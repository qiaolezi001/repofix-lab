# Contributing

RepoFix-Lab is a small local-first Python repair workbench. Start with [PROJECT_SPEC.md](PROJECT_SPEC.md) and the [architecture](docs/architecture.md), then open an issue describing the observable behavior and a minimal reproduction. Include repository size, Python version, mode, verification status and a redacted report; never include API credentials or private source code.

## Development

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repofix
uv run pytest
```

The standard tests run without network, model keys or Docker. Stubbed sandbox results establish orchestration behavior, not actual Docker execution. To exercise container verification, build `Dockerfile.sandbox` and run the demo. Avoid executing benchmark candidate code directly on your host.

Keep PRs focused and explain the user-visible effect, test evidence and limitations. Add meaningful failure-path tests for changes to tools, budgets, persistence or verification. For UI-only changes, include actual browser screenshots and check keyboard use, narrow screens and error states. Do not replace the working interface with staged images.

## Project invariants

- Repository/Issue contents are untrusted data, not instructions to override orchestration policy.
- Agent tools cannot modify tests, configuration, reference answers or the immutable baseline.
- Hidden acceptance tests and reference patches never enter model context or task workspaces.
- Only Docker runs candidate code. An unavailable test environment must remain visible in results.
- Candidate generation, public-suite pass and independent evaluation have separate claims.
- `mock` is deliberately scripted; do not add benchmark answers to it.
- API credentials and actual secrets must be excluded from committed files, task state and logs.
- Paid probes or evaluations require explicit authorization and visible resource budgets.

## Benchmark changes

The v0.1 split is frozen. Put new tasks in a separately versioned set rather than tuning against the existing evaluation set and continuing to label it unseen. Record task provenance, seeded defect, public/hidden coverage and split rules. All bundled fixtures are original MIT-licensed code; include the exact source and compatible license when adding third-party material.

## Reporting security issues

Before a maintainer contact is configured, avoid posting secrets or weaponized exploit details in a public issue. Report a short description and ask the maintainer for a private channel. This local educational prototype does not promise production containment or authenticated multi-user operation.
