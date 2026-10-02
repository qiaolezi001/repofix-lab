# Publishing on GitHub

The local repository is prepared for review. No GitHub account, remote repository or public push is implied by local generation. Publish only after the maintainer has reviewed the source, artifacts and license and explicitly authorized the release.

## Suggested repository metadata

- Name: `repofix-lab`
- Description: `Evidence-backed Python issue repair agent with AST/BM25 retrieval, isolated tests, durable checkpoints, and reproducible evaluation.`
- Topics: `agent`, `llm`, `code-repair`, `python`, `fastapi`, `tool-calling`, `bm25`, `evaluation`, `developer-tools`
- First release: `v0.1.0` — local workflow and synthetic benchmark, real-model metrics not yet measured.

Do not add a passing CI badge until its remote run actually passes. Do not claim production readiness, model accuracy, integration with unspecified providers or performance improvements without evidence.

## Review before release

1. Read [STATUS.md](../STATUS.md), run the locked install and local checks, and reproduce the Mock UI flow.
2. Confirm that no API credentials, private source, `.repofix/` task data or personal paths appear in tracked files/artifacts. `.gitignore` is a first filter, not a secret audit. Check report and screenshot content manually.
3. Keep demonstration material clearly labeled **MOCK / no live model evaluation**. Public-test unavailability must remain visible.
4. Confirm ownership of the self-authored code, preserve dependency licenses and adjust the contributor copyright line if desired.
5. Verify Docker separately and record actual outcomes. If not verified, preserve that limitation in release notes.
6. Review resume descriptions against the maintainer's actual contributions, commits and measured results.

## After account and release authorization

Run these commands yourself, or authorize Codex to run them against your account. Replace the GitHub URL with your chosen repository. These instructions do not execute a remote publication.

```sh
git init
git add .
git diff --cached --stat
git diff --cached
git commit -m "Initial RepoFix-Lab v0.1 implementation"
git branch -M main
git remote add origin https://github.com/YOUR_ACCOUNT/repofix-lab.git
git push -u origin main
```

Create an empty GitHub repository before adding the remote. If Git is already initialized, inspect its status/remotes rather than overwriting existing configuration. Check GitHub Actions after the push, fix any remote-specific failures, then add a correct badge and a release tag. Attach every published PR to the relevant Codex chat if it was created during work here.

## Suggested initial release notes

```text
RepoFix-Lab v0.1.0 is a single-user local workbench for small Python repositories.
It provides evidence retrieval, six validated tools, durable execution, a scripted
offline demo, Docker-only public verification, and a frozen synthetic evaluation
set (15 tasks across 3 projects, 6 development / 9 evaluation).

The mock provider demonstrates engineering flow only. Real-model repair accuracy,
live provider compatibility and billed cost remain unmeasured unless supported
by the release's attached run artifacts. Docker verification requires a separate
locally built sandbox image. See STATUS.md for actual checks and limitations.
```

After a real run, replace the unmeasured statement only with the exact model, configuration and linked results. Keep failed cases, cost unknowns and unverified environments visible.
