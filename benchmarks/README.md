# Synthetic benchmark v0.1

All code, issues, injected bugs and tests in this directory were authored for
RepoFix-Lab and released under the repository's MIT license. These tasks are
deliberately small, artificial engineering fixtures. They are not production
incidents, SWE-bench tasks, or evidence of employability by themselves.

There are **15 tasks across 3 Python projects**: `numberkit`, `textkit` and
`shopkit`. Each project contributes five snapshots with exactly one injected
bug. Cases cover boundaries, invalid-input exceptions, arithmetic, and calls
across files. Public tests reproduce the reported bug and check basic regression
behavior; separate acceptance tests probe additional inputs.

`manifest.json` freezes the split: `*-01` and `*-02` are development tasks (6);
`*-03`, `*-04`, and `*-05` are evaluation tasks (9). `initial_version` and
`source_sha256` in metadata identify exact original snapshots. Do not tune on
evaluation task results and then present them as untouched holdout performance.

Each task has:

- `repo/`: the only directory handed to the Agent; source and public tests.
- `issue.md`: user-facing reproduction and expected behavior.
- `meta.json`: author metadata and snapshot hashes, outside the Agent workspace.
- `hidden/test_acceptance.py`: evaluator-only acceptance tests.
- `reference.json`: author patch, never supplied to the Agent or mock provider.

The public GitHub repository contains acceptance tests and author answers to
make reproduction and educational review possible. They are "hidden" from the
Agent's bounded task directory, not secret from a human browsing GitHub.
This protects the implemented evaluation protocol from accidental answer
leakage; it does not establish adversarial robustness against malicious code
that introspects pytest at runtime.

## Run

From a source checkout:

```sh
repofix evaluate --mode mock --split dev --output work/eval-mock
```

Mock follows a hand-scripted pagination fixture pattern. A matching edit in a
benchmark remains scripted engineering evidence, not a model prediction. A mock
benchmark run checks the orchestration and records failures/unavailable tests;
**all real-model repair metrics remain null**. It is not a repair accuracy run.

For real measurement first build the Docker test image, configure the API key
locally, verify model tool compatibility, and review the explicit budget:

```sh
repofix evaluate --mode live --split dev --output work/eval-live-dev --max-calls 8 --allow-paid
```

This runs both strategies on the same tasks and model. The baseline receives
the issue and bounded source context, one response, and no test feedback. The
Agent retrieves its own context, can read public tests, and receives at most `--max-calls`
responses and three repair rounds. With 6 tasks and 8 Agent responses, the
upper bound is 54 model requests; this is a call cap, not a USD spending cap.
The context policies and budgets differ by design. Report both differences with
any comparison; this measures the complete engineering workflow rather than
isolating retrieval or feedback as a single causal factor.
Token counts come from the actual provider; absent counts and monetary costs
remain unknown. Check your provider price and budget before authorizing a run.

The evaluator copies only `repo/` into the Agent task directory. After execution,
it checks that public tests were preserved, then copies the result to a separate
temporary staging directory, adds the independent acceptance suite, and runs
public and acceptance suites in Docker. No host fallback exists. The Agent does
not receive hidden suite content or feedback. Added/modified pytest control
files and changed public tests reject the repair. A fully measured repair
requires both suites to pass; missing Docker leaves accuracy unmeasured.

Results contain run config, exact task IDs/versions, per-task JSON and patches,
model usage, elapsed time, failure category, configured denominator and tested
denominator. Reuse a fresh output directory for each run. Neither evaluation
results nor model credentials belong in a source commit unless reviewed.

## Author validation

`tests/test_benchmarks.py` verifies fixture hashes, frozen split, every original
bug's public reproduction, and every reference patch against both public and
acceptance tests. Those development checks run only this self-authored fixture
set on the host; they do not invoke the Agent or run user-submitted repositories.

The delivered [author validation record](../reports/fixture-validation.json)
records 15 reproduced bugs and 15 author reference patches passing both suites,
with source, issue and acceptance hashes. These counts validate fixture quality;
they are **not model repair outcomes**. Rerun the tests to revalidate a checkout.

`generate_fixtures.py` documents how the artificial release was authored. Running
it rewrites the fixture release. Do not regenerate or format fixture source in
the middle of a measured run; keep release hashes stable.
