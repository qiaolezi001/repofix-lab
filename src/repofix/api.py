"""Local-only API, single worker and static UI; background state survives restart."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from repofix.config import DEMO_ISSUE, Settings, demo_source
from repofix.engine import Engine
from repofix.models import TERMINAL, TaskRequest
from repofix.providers import ProviderError
from repofix.reports import markdown, public_state
from repofix.sandbox import Sandbox


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = engine or Engine(settings)
    jobs: dict[asyncio.Task, str] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine.store.recover_startup()
        yield
        for task_id in list(jobs.values()):
            engine.cancel(task_id)  # to_thread cancellation alone cannot stop its worker.
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)

    # Built-in Swagger/Redoc load CDN scripts that conflict with the offline CSP.
    # Keep the machine-readable schema and the bundled local UI.
    app = FastAPI(
        title="RepoFix-Lab", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.state.engine = engine
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"]
    )

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if request.headers.get("sec-fetch-site") == "cross-site" or (
                origin and origin != f"{request.url.scheme}://{request.headers.get('host', '')}"
            ):
                return JSONResponse(
                    {"detail": "Cross-origin mutation is blocked."}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        )
        return response

    def lookup(task_id: str):
        try:
            return engine.get(task_id)
        except KeyError:
            raise HTTPException(404, "Unknown task") from None

    def launch(task_id: str) -> None:
        job = asyncio.create_task(asyncio.to_thread(engine.run, task_id))
        jobs[job] = task_id
        job.add_done_callback(lambda done: jobs.pop(done, None))

    @app.get("/api/health")
    def health():
        return {
            "mode": "live" if settings.api_key and settings.model else "mock",
            "model": settings.model or "scripted-pagination-demo",
            "docker": Sandbox(image=settings.sandbox_image).available(),
            "demo_path": str(demo_source()),
            "version": "0.1.0",
        }

    @app.get("/api/demo")
    def demo():
        return {"source": str(demo_source()), "issue": DEMO_ISSUE}

    @app.get("/api/tasks")
    def tasks():
        return [public_state(s) for s in engine.list_tasks()]

    @app.post("/api/tasks", status_code=202)
    async def submit(body: TaskRequest):
        try:
            state = await asyncio.to_thread(
                engine.create,
                body.source,
                body.issue,
                body.mode,
                body.strategy,
                body.limits.model_dump(),
                body.allow_paid,
            )
        except (ValueError, OSError, ProviderError) as exc:
            raise HTTPException(400, str(exc)) from None
        launch(state["id"])
        return public_state(state)

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str):
        return public_state(lookup(task_id))

    @app.post("/api/tasks/{task_id}/cancel")
    def cancel(task_id: str):
        lookup(task_id)
        return public_state(engine.cancel(task_id))

    @app.post("/api/tasks/{task_id}/resume", status_code=202)
    async def resume(task_id: str):
        state = lookup(task_id)
        if state["status"] in TERMINAL:
            raise HTTPException(409, "Terminal tasks cannot be resumed; create a new task.")
        launch(task_id)
        return public_state(state)

    @app.get("/api/tasks/{task_id}/report")
    def report(task_id: str, format: Literal["md", "json"] = "md"):
        state = lookup(task_id)
        headers = {"Content-Disposition": f'attachment; filename="{task_id}.{format}"'}
        if format == "json":
            return JSONResponse(public_state(state), headers=headers)
        return Response(markdown(state), media_type="text/markdown; charset=utf-8", headers=headers)

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static, check_dir=False), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static / "index.html")

    return app
