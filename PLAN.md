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

External acceptance remains separate: no live model quality or Docker container execution claim. GitHub publication and the first remote CI completed successfully; see STATUS.md and reports/validation.json for actual evidence.

8. Maintainer review gate — completed additional implementation audit, repaired four reproduced issues, added 15 regression cases and passed the final 119-test local run. The candidate and review steps are in RELEASE_REVIEW.zh-CN.md. The user explicitly authorized public publication on 2026-10-03; authentication, public repository creation, initial push and the first remote CI are complete. Remote Linux checks report 120 passed.
