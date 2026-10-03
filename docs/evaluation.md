# Evaluation methodology

## What this benchmark measures

The bundled `synthetic-v0.1` set contains **15 self-authored, artificially seeded defects** in three small standard-library Python projects. It is not a public industrial benchmark and does not imply performance on production repositories. Public tests provide agent feedback; evaluator-owned hidden tests check additional requirements and regressions after the candidate is final.

| Project | Tasks | Development | Evaluation | Scope |
| --- | ---: | --- | --- | --- |
| `numberkit` / numeric | 5 | `numeric-01`, `numeric-02` | `numeric-03`–`numeric-05` | Boundaries, arithmetic, exceptions and cross-file numeric behavior |
| `textkit` / text | 5 | `text-01`, `text-02` | `text-03`–`text-05` | Text boundaries, invalid inputs and token interactions |
| `shopkit` / catalog | 5 | `catalog-01`, `catalog-02` | `catalog-03`–`catalog-05` | Money, inventory, cart totals and pagination |

The frozen rule is first two IDs per project for development and last three for evaluation: 6 development / 9 evaluation. Do not tune against the evaluation tasks and continue calling them unseen. All task sources, public tests, hidden tests and reference replacements were created for this repository and licensed MIT. Each manifest entry records the initial code version; fixture generation is reproducible.

## File separation

```text
benchmarks/tasks/<id>/
├── issue.md          # Issue provided to the agent
├── repo/             # Only this directory becomes the agent snapshot
│   ├── <package>/
│   └── tests/        # Public tests, immutable to agent tools
├── hidden/           # Evaluator-only acceptance tests
├── meta.json         # Answer/task metadata, outside the workspace
└── reference.json    # Reference exact replacements, outside the workspace
```

Model context receives the Issue and allowed tool observations from `repo/`. It cannot read parent directories through tools. The evaluator checks the reference fixtures independently as a dataset integrity check, not as an agent prediction. The hidden suite is placed into an evaluator-owned candidate copy only after agent execution. No hidden results are fed back to the agent, and the scored outcome comes from actual tests rather than string equality with the reference patch.

The benchmark is publicly readable in an open-source checkout; file separation prevents accidental inclusion in the agent's tools, not prior exposure of a hosted model to public data. It is too small and synthetic to support broad claims.

## Strategies and budgets

**Baseline** makes one generation with bounded source context and an `apply_patch` schema. It receives no retrieval or iterative test feedback. The evaluator/orchestrator tests the final candidate after the generation; verification does not become a second model turn.

**Agent** receives the Issue, tool schemas and recent observations. It can retrieve/read source, propose edits and inspect public test feedback until it finishes or reaches a limit.

Both use the same configured model, tasks, snapshot, tokenizer-free context character cap and output Token cap. Their call budgets intentionally differ, so this is a comparison of systems under recorded budgets, not a pure retrieval ablation with identical total inference effort.

| Limit | Baseline | Agent default |
| --- | ---: | ---: |
| Model calls per task | 1 | 12 |
| Maximum tool calls | 6; one patch-generation action | 36 |
| Repair rounds | one model response | 3 |
| Task timeout | 180 seconds | 180 seconds |
| Context characters | 32000 | 32000 |
| Output Tokens per call | 1800 | 1800 |

The actual configuration is saved with the run and each task. The evaluation CLI defaults to `--max-calls 12`; for a 9-task evaluation split, comparing both strategies has at most 9 × (1 + 12) = **117 model calls**, and at most **210600 requested output Tokens**. The evaluator derives tool limits as `max(6, max_calls × 3)`. Ordinary CLI repair tasks use 16 model / 12 tool calls by default; these are separate configurations. Input Tokens, provider-internal reasoning and failed-request billing depend on the provider; 32000 characters is not an exact Token ceiling. The two-call compatibility probe is a separate command. There is no automatic monetary cap, so inspect current pricing and provider account limits before granting `--allow-paid`.

## Commands

```sh
uv sync --locked
# Offline workflow exercise: no API bills, no model accuracy claim.
uv run repofix evaluate --mode mock --split dev --output work/mock-dev
uv run repofix evaluate --mode mock --split eval --output work/mock-eval

# Requires a built Docker sandbox image and explicit paid authorization.
uv run repofix model-check --allow-paid
# A selected development pilot: at most 1 + 8 = 9 task calls (probe is separate).
uv run repofix evaluate --mode live --split dev --task-id numeric-01 --max-calls 8 --output work/live-pilot --allow-paid
uv run repofix evaluate --mode live --split dev --output work/live-dev --max-calls 12 --allow-paid
# Freeze implementation/configuration after development, then run once on eval.
uv run repofix evaluate --mode live --split eval --output work/live-eval --max-calls 12 --allow-paid
```

Each `--output` is a fresh directory containing `config.json`, `summary.json`, per-task JSON/patch files and a run README; an existing summary is not overwritten. Repeat `--task-id` to select specific tasks in the chosen split; invalid, duplicate or empty selections are rejected before filesystem or provider side effects. The selected IDs and paired call budget are recorded. The Mock provider only scripts the dedicated pagination demo. It is not a solver for benchmark tasks, and may produce inappropriate tool selections under the one-shot baseline. Mock runs check integration and honest failure reporting; do not publish their success ratio as an LLM score.

## Metrics and unknowns

Save the per-task records and aggregate configuration together. Interpret these fields separately:

- **Repair success**: a real model candidate passes the complete public suite and independent hidden suite. Report passed / total, denominator and unmeasured cases explicitly.
- **Public/regression result**: suite status, exit code, complete-suite flag and raw bounded output. A missing environment is `unavailable`, not a passed test.
- **Calls and Tokens**: attempted model calls and provider-reported prompt/completion/total Tokens. If usage is missing or an error made totals incomplete, mark Tokens unknown rather than displaying zero as measured usage.
- **Time**: measured task elapsed seconds; record timeout budget and runtime environment.
- **Cost**: API-returned cost or Token totals × explicitly recorded contemporary prices. Otherwise `null` / unknown; do not fabricate a dollar total.

Per-response provider usage, including returned cached-input/reasoning details, is retained in `usage.responses` for pricing. Missing details remain unknown; the evaluator does not automatically turn partial usage into a billed dollar claim. The [live-validation guide](live-validation.zh-CN.md) records a dated official-price example and separate pilot/final-run budgets.
- **Failure category**: provider/protocol error, budget exhaustion, tool/policy error, public test failure, hidden test failure, unavailable verification or no candidate.

Ordinary tasks leave `independent_tests` at `not_run`. The evaluator's hidden result exists in evaluation output; it should not be inferred from `succeeded` in task state. An API response claiming “fixed” is not itself a measured repair.

## Current results

Real-provider end-to-end validation, real-model repair success, Token usage comparison and billed cost are **not yet measured**. API credentials and paid-batch authorization were not provided. Actual Docker engineering acceptance passes all ten checks both locally and on a GitHub Linux runner; this does not fill any real-model metric. Local validation and saved evidence are documented in [STATUS.md](../STATUS.md); the web screenshot demonstrates the actual interface in Mock mode.

Expected offline cases include: a correct scripted pagination diff with Docker verification `unavailable`, a strict path-policy rejection, a model output lacking a valid action and a loop ending at its configured call limit. These are documented behavioral examples, not invented benchmark successes. Refer to saved reports/test outputs for what actually occurred locally.

## Reporting a future live run

Record date, commit, model/base URL without credentials, all budgets, runtime versions, sandbox image, split, task IDs and output files. Report baseline and Agent results with equal denominators and separate unmeasured tasks. Include at least one concrete public/hidden failure case and the actual patch/trace. Avoid claims of improvement from a single small run without repeated trials and uncertainty; prioritize auditable evidence over a headline percentage.
