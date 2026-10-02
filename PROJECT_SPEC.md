# RepoFix-Lab v0.1 specification

Single-user, localhost tool for small Python repository snapshots. The deliverable is a model-driven tool loop with AST/BM25 evidence, protected patch application, Docker-only test execution, SQLite checkpoints, CLI/API/Web UI, and a frozen 15-task synthetic benchmark. Default mode is explicitly scripted mock; model accuracy cannot be inferred from mock runs.

## Acceptance

- Six validated tools; workspace copies are isolated; traversal/symlinks/secrets and test/config edits rejected.
- Model actions select tools from current evidence; tool/test errors return to the loop; calls/repair rounds/time/context bounded.
- Recover persisted execution after interruption without applying a patch twice; cancel and timeout tested.
- Docker tests use no network, nonroot, read-only mounts/rootfs, dropped capabilities and resource limits. No daemon means diagnosis remains usable with unavailable verification.
- CLI and localhost API/UI display task history, evidence, diff, public test outcomes, independent evaluation outcomes, and downloadable JSON/Markdown reports.
- 15 artificial tasks / 3 repos, frozen 6 development / 9 evaluation split; hidden tests/reference answers remain outside agent inputs; baseline and iterative evaluation implemented.
- Lint, type checking and tests executed; service/browser flow exercised with real screenshots; docs teach code/choices and honest resume claims.
- Live provider protocol is tested offline. Live provider end-to-end and model benchmark require an API key and explicit cost authorization; missing access is reported, never replaced by synthetic accuracy.
- GitHub publication needs the user's account and separate release authorization. Remote CI status is not inferred from local checks.

## Decisions

Use an explicit persisted state machine rather than LangGraph for v0.1: a small linear tool loop needs no graph dependency and checkpoints/side-effect boundaries are directly inspectable. A provider adapter speaks the documented Chat Completions function-calling protocol; provider compatibility is checked by a minimal explicit probe.

Plain static HTML/CSS/JS is served by FastAPI; no JavaScript build chain or CDN. SQLite stores durable state/events. Patches are exact-match structured replacements and cannot modify tests/config. The app owns trusted orchestration; only Docker executes candidate code.

## Boundaries

Python source/text, bounded file/repository sizes, local single process only. No promise of general repository support, production sandboxing or benchmark leadership. No remote pushes or batch paid inference without authorization.
