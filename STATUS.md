# Validation status — v0.1.0

Validated on 2026-10-03 (Asia/Shanghai), Windows, Python 3.11.9, uv 0.12.13, with additional GitHub Linux checks and actual Docker execution. Implementation is ready for local use and source review. Real-model validation below is pending; this is not a claim of model accuracy or production readiness. The initial release checks and subsequent follow-up checks are recorded separately.

## Checks actually executed

| Check | Result |
| --- | --- |
| Full `uv run pytest -q` | **119 passed, 1 skipped**, 28.83 seconds after pre-publication fixes |
| Skipped test | Host lacks symlink-creation privilege; Windows junction detection separately tested |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed |
| `uv run mypy src/repofix` | Passed, 14 source modules |
| HTTP model protocol fixture | Two-call tool/result exchange tested with MockTransport; no network inference |
| Recovery/cancellation | Crash after patch write, duplicate replay, stale checkpoint cancellation, setup lease release, worker shutdown and budgets tested |
| Verification guards | Missing JUnit, empty/skipped suites, collection errors and test mutation rejected in trusted wrapper tests |
| Synthetic fixture authoring | 15 initial bugs reproduced; 15 author reference patches pass public and independent tests; **not model predictions** |
| Benchmark pipeline | 9 evaluation tasks × 2 strategies = 18 mock records; real-model scores and cost are null |
| Actual browser | Microsoft Edge: submit demo, evidence, diff, keyboard tabs, report download, error state and 390px no-overflow layout; zero page script errors |
| Clean installation | Built sdist/wheel, installed wheel in a separate environment outside checkout; packaged demo and 15 benchmark tasks present; demo produces real evidence/patch |
| Final API/documentation correction | OpenAPI schema served locally; CDN Swagger/Redoc pages disabled to retain offline CSP. All 4 API tests rerun and passed; running service UI and schema returned HTTP 200 |
| Source release archive | 257 tracked files including review checklist and release notes; all 15 frozen fixture snapshots retain exact hashes after extraction; local runtime/cache/secret files excluded |
| Actual GitHub Actions | [First successful remote run](https://github.com/qiaolezi001/repofix-lab/actions/runs/37058013447), commit `f61b5e5b8fce5eabfb1ddddf9ee4fccb4b36c809`; Ubuntu/Python 3.12, **120 passed**, Ruff/format/mypy passed |
| Follow-up local checks | **140 passed, 2 skipped** in 43.88 seconds; Ruff/format/mypy passed. Opt-in container suite and Windows symlink privilege skipped |
| Follow-up remote checks | [Actual Linux checks](https://github.com/qiaolezi001/repofix-lab/actions/runs/37096982058), commit `2d4ddf264ed8750887c893fb4714d2ba2ac9af9d`; **141 passed, 1 skipped**, 9.43 seconds; Ruff/format/mypy passed. Docker acceptance runs in its own workflow |
| Actual remote Docker | [Container run](https://github.com/qiaolezi001/repofix-lab/actions/runs/37096982053), same commit; **10/10 checks passed**, 12.856 seconds, Docker 28.0.4; JSON artifact downloaded and inspected |
| Actual local Docker | **10/10 checks passed**, 32.922 seconds, Docker 29.6.2; observed container limits, tests and cleanup recorded |
| Actual app container | Built and started nonroot application image; localhost UI/schema, Mock task, evidence/diff/report and removal of container/data volume passed. Tests unavailable as documented: no Docker socket/CLI inside app image |
| Browser after Docker setup | Real Edge UI task **succeeded**, public tests **3/3 passed**, 5 code evidence entries, no page errors; screenshots and demo reports refreshed in Mock mode |

One dependency deprecation warning in Starlette's HTTPX-based test client remains; tests pass. This is not an application runtime failure.

## Execution evidence

- `reports/browser-validation.json` and `docs/assets/{home,demo,mobile}.png`: actual browser captures in **mock mode**.
- `reports/demo/`: actual mock task report and exported patch. Public tests pass 3/3 in Docker; independent tests were not run.
- `reports/fixture-validation.json`: authoring-only trusted host validation with fixture hashes; not an Agent benchmark.
- `reports/mock-eval/`: paired offline pipeline records/configuration; model performance deliberately unmeasured.
- `reports/validation.json`: machine-readable release checks.
- `reports/docker-validation.json`: downloaded remote artifact with actual container outcomes and inspect/cleanup evidence.
- `reports/docker-local-validation.json`: actual Windows-host/Linux-container acceptance.
- `reports/docker-app-validation.json`: actual application-container/API smoke run in Mock mode.

## Remaining external verification

**Real provider:** no model API key/model is configured. Protocol contract tests pass offline; no online compatibility probe, real repair task or paid batch benchmark has run. Configure environment variables locally, review provider pricing, run the explicitly authorized two-call probe and one selected development task before deciding on a batch budget. See `docs/live-validation.zh-CN.md` for the proposed 11-request pilot and dated official pricing. A no-key HTTP 401 connectivity response does not establish inference compatibility.

## GitHub publication

Published with the maintainer's authorization at <https://github.com/qiaolezi001/repofix-lab>, public visibility, default branch `main`. The initial push and first remote CI completed successfully on 2026-10-03 (Asia/Shanghai). The Windows symlink test that was skipped locally executes on the Linux runner. The offline checks use no paid model credentials; the separate Docker workflow now verifies actual container execution, with no real-model accuracy claim. The published `v0.1.0` tag/archive remain immutable; these follow-up additions are on `main`.

## Product boundaries

Small dependency-free Python snapshots only; UTF-8 `.py`/`.md`, 500 files, 256 KiB per file, 8 MiB total. Tests/configs are protected, patches cannot create files. Single-user/single-server process, localhost by default. Docker isolation and hidden fixture staging are defense in depth, not a guarantee against hostile Python or sandbox escapes. Uniform LF/CRLF is preserved; mixed endings require exact-match edits.

The live baseline uses one generation; iterative Agent has a larger recorded budget and selected context/test feedback. Comparisons cannot isolate retrieval as the only cause. Open-source fixture answers are public to humans but excluded from the Agent's tool workspace.

## Maintainer next steps

Read `docs/guide.zh-CN.md`, then the source route and three exercises in `docs/learning.zh-CN.md`. Check `docs/publishing.md` for the concrete source-release steps. Resume/model-quality claims should be based on the maintainer's own understanding and measured live results.

## Publication gate

The maintainer reviewed the candidate and explicitly authorized public GitHub publication on 2026-10-03. The reviewed scope is in `RELEASE_REVIEW.zh-CN.md`. GitHub authentication succeeded as `qiaolezi001`, and the public repository was created and pushed. Publication authorization does not include paid model evaluation.

## Follow-up Docker validation completed (2026-10-03)

The maintainer requested real Docker and live-model validation after publication. A separate `docker-verification` workflow builds the sandbox and executes actual containers, retaining a JSON artifact. All ten checks pass remotely and locally: failing original tests, a tool-applied passing patch, skipped/empty/early-exit/mutated-test rejection, observed isolation limits, timeout/cancellation cleanup and the **mock** Agent end-to-end flow. The original two tests fail before the patch and both pass after it; the dedicated demo's three public tests pass. No fixture result is an LLM success-rate measurement.

Local Docker Desktop 4.84.0 originally failed while accessing a stale AF_UNIX `dockerInference` socket. WSL probes ran successfully, ruling out an unavailable WSL runtime. Direct socket rename failed; after confirming no backend process remained, the runtime-only `%LOCALAPPDATA%/Docker/run` directory was moved to the sibling `run.validation-backup-20261003`. Desktop recreated the runtime directory and its Linux daemon started. Images/volumes/settings were preserved; the backup was retained. The first sandbox build encountered a PyPI TLS EOF; a build-only explicit proxy resolved it without disabling TLS or enabling networking in candidate containers. The app build similarly required separate host-CLI and container proxy addresses; the corrected actual build and API smoke pass.

The new task-ID selection supports a bounded one-task paired live pilot. Provider response usage details are retained for subsequent pricing, and an explicit opt-in model proxy is supported. Local follow-up checks pass: **140 passed, 2 skipped** in 43.88 seconds; Ruff/format and mypy pass. The skips are the opt-in real Docker suite and Windows symlink privilege. A no-key GET to the OpenAI model-list endpoint times out on a direct connection and returns HTTP 401 through the explicit proxy; **zero inference requests** were made.

No API key/model is configured and no paid-run budget has been granted. Live compatibility and model-effectiveness results remain **not measured**.

## Additional pre-publication review completed

The requested review reproduced and repaired four issues: final verification now resumes before model budget checks; patch attempts invalidate earlier test results even if a result receipt fails after source replacement; staging/receipt I/O failures clean temporary files and allow safe retries; Windows fixture self-checks use a real empty pytest config with explicit collection boundaries instead of the NUL device. The initial review run caught one fixture collection failure; the corrected whole-project run passes all 119 executable tests. Fifteen additional regression cases cover these behaviors. All 22 benchmark, 30 Engine and 35 tool tests passed in targeted runs; the tool run also had the same one permission-dependent skip. The rebuilt wheel was reinstalled and exercised outside the checkout, and the current service passed the real browser demo again.
