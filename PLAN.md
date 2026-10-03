# Milestones and validation

1. Environment/spec/package setup — preserve prior files, resolve/lock dependencies.
2. Workspace/index/tools/sandbox — targeted AST/BM25, atomic patch and isolation tests.
3. Provider/state/store — protocol fixture tests, bounded loop, cancellation and crash recovery.
4. API/CLI/UI — exercise service, task submission/history/report and browser states.
5. Benchmark/evaluation — validate all artificial fixtures, development/evaluation separation and answer isolation; offline engineering run; live results only with authorized key.
6. Open-source/learning materials — docs, examples, CI/container recipe, source route, interview/exercises/resume; verify documentation commands.
7. Final integration — Ruff/format/mypy/pytest, clean-package install, real screenshot, reproducible archive, final status.

Validation failures are repaired before closing a milestone. STATUS.md records evidence and external dependencies.

## Milestone outcomes

1–4 completed and locally verified. 5 completed for fixture integrity and offline evaluation; live measurement awaits configured provider/budget and working Docker. 6 completed. 7 local checks, wheel installation and real browser flow passed; clean source archive extracted and all 15 frozen task hashes verified. The final API documentation correction passed 4 API tests and was checked on the running service.

At initial publication, external acceptance remained separate: neither live model quality nor Docker execution had been measured. GitHub publication and the first remote CI completed successfully; the subsequent Docker validation is recorded in milestone 9 and STATUS.md.

9. Post-publication external verification — real Docker acceptance completed on Windows/Docker Desktop and a GitHub Linux runner (10/10 each). The app image was actually built and its API/Mock diagnosis workflow exercised. Follow-up local checks pass 140 tests, remote checks pass 141; explicit skips are recorded. Live verification is prepared as a selected one-task paired pilot, but API credentials/model and monetary authorization are still required. No paid inference or live benchmark result is claimed.

8. Maintainer review gate — completed additional implementation audit, repaired four reproduced issues, added 15 regression cases and passed the final 119-test local run. The candidate and review steps are in RELEASE_REVIEW.zh-CN.md. The user explicitly authorized public publication on 2026-10-03; authentication, public repository creation, initial push and the first remote CI are complete. Remote Linux checks report 120 passed.
