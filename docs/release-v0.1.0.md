# RepoFix-Lab v0.1.0

RepoFix-Lab is a single-user local workbench that turns an Issue in a small Python repository into code evidence, a candidate patch and an auditable verification report.

This first release includes:

- Python AST passages and BM25 retrieval with file, symbol, line and snapshot citations.
- Six validated tools for listing, searching, reading, patching, testing and diff export; isolated snapshots and protected tests.
- A bounded model/tool feedback loop, SQLite checkpoints, cancellation and receipt-based patch recovery.
- CLI, FastAPI and a lightweight browser interface with execution traces and Markdown/JSON reports.
- A scripted offline pagination demo and a Chat Completions tool-calling adapter.
- Docker-only task verification with no network and resource limits; unavailable verification remains explicit.
- Fifteen self-authored synthetic tasks across three projects, frozen into 6 development / 9 evaluation tasks, plus one-shot and iterative evaluation strategies.
- MIT licensing, reproducible dependency locking, CI configuration, architecture notes and learning materials.

Local validation on Windows with Python 3.11.9 and uv 0.12.13: **119 tests passed, 1 skipped**. Ruff lint/format and mypy passed. The skipped test requires Windows symlink-creation privileges; junction handling was tested separately. Actual Mock browser flows and a clean wheel installation were exercised. See [STATUS.md](../STATUS.md) for evidence and the scope of each check.

The first [GitHub Actions run](https://github.com/qiaolezi001/repofix-lab/actions/runs/37058013447) also passed on Ubuntu with Python 3.12: **120 passed**, including the symlink case unavailable on the Windows host. Remote Ruff lint/format and mypy checks passed.

**Measurement limits:** Mock demonstrates engineering flow only. Real-model repair accuracy, online provider compatibility and API cost have not been measured. The local Docker engine was unreachable, so no sandbox image/container execution was verified; container command/cleanup and trusted runner behavior were tested offline. Remote CI validates offline engineering behavior, not model quality or container execution.

The prototype supports small, dependency-free Python snapshots and defaults to localhost. It is not a production service or a security guarantee against hostile Python. Candidate generation, complete public-test verification and independent acceptance are separate outcomes. Reference-fixture validation is dataset authoring evidence, not a model score.

Start with `uv sync --locked`, then `uv run repofix demo` or `uv run repofix serve`. Build `Dockerfile.sandbox` before attempting container verification; review provider prices and explicitly authorize live calls before running a real-model probe or evaluation.
