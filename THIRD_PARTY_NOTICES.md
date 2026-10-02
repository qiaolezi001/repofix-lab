# Third-party dependencies and references

RepoFix-Lab source and all artificial fixtures are MIT licensed. It does not vendor the packages below. Their licenses continue to apply independently. Versions and license expressions below were read from installed distribution metadata for this validated lockfile; transitive dependency versions are recorded in `uv.lock`.

| Direct dependency | Validated version | License |
| --- | --- | --- |
| FastAPI | 0.142.2 | MIT |
| Pydantic | 2.13.5 | MIT |
| HTTPX | 0.28.1 | BSD-3-Clause |
| Uvicorn | 0.54.0 | BSD-3-Clause |
| pytest (development) | 9.1.1 | MIT |
| Ruff (development) | 0.16.10 | MIT |
| mypy (development) | 1.20.2 | MIT |
| Playwright (development) | 1.63.0 | Apache-2.0 |

The sandbox Dockerfile separately pins pytest 9.1.1 on Python 3.12. Its execution was not verified on the authoring machine because the Docker daemon was unavailable. The app Docker image uses the frozen `uv.lock` and uv 0.12.13. Base images and installed packages retain their own notices; no base image is bundled in this repository.

Implementation references reviewed during development:

- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)
- [Pydantic strict validation](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- [Docker container run controls](https://docs.docker.com/reference/cli/docker/container/run/)
- [OpenAI function calling protocol](https://developers.openai.com/api/docs/guides/function-calling)
- [pytest configuration and collection roots](https://docs.pytest.org/en/stable/reference/customize.html)

The BM25 implementation and orchestration source were authored for this project, rather than copied from a third-party repository. Benchmark answers, issues, fixtures and tests were authored together and are explicitly labeled synthetic. Project generation was assisted by Codex; maintainer responsibilities and learning exercises are in `docs/learning.zh-CN.md`.
