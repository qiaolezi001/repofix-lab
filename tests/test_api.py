import threading
import time

from fastapi.testclient import TestClient

from repofix.api import create_app
from repofix.config import DEMO_ISSUE, Settings, demo_source
from repofix.engine import Engine
from repofix.providers import MockProvider


class OfflineSandbox:
    def run(self, repo, tests=None, cancel_event=None):
        return {
            "status": "unavailable",
            "output": "Test stub: Docker not available",
            "exit_code": None,
            "duration_seconds": 0,
            "complete_suite": tests is None,
        }


def test_api_submission_history_reports_and_validation(tmp_path):
    settings = Settings(data_dir=tmp_path / "state")
    with TestClient(create_app(settings, Engine(settings, sandbox=OfflineSandbox()))) as client:
        response = client.post(
            "/api/tasks", json={"source": str(demo_source()), "issue": DEMO_ISSUE}
        )
        assert response.status_code == 202
        task_id = response.json()["id"]
        for _ in range(100):
            task = client.get(f"/api/tasks/{task_id}").json()
            if task["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        assert task["status"] == "completed", task
        assert "messages" not in task and "pending" not in task
        assert task["candidate_patch"] and task["evidence"]
        assert client.get("/api/tasks").json()[0]["id"] == task_id
        report = client.get(f"/api/tasks/{task_id}/report?format=md")
        assert report.status_code == 200 and "SCRIPTED MOCK" in report.text
        assert "Independent acceptance: **not_run**" in report.text
        assert client.get(f"/api/tasks/{task_id}/report?format=json").json()["mode"] == "mock"
        assert client.post(f"/api/tasks/{task_id}/resume").status_code == 409
        assert client.get("/api/tasks/missing").status_code == 404
        assert (
            client.post(
                "/api/tasks",
                json={
                    "source": str(demo_source()),
                    "issue": DEMO_ISSUE,
                    "limits": {"max_tool_calls": "12"},
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/tasks",
                json={"source": str(demo_source()), "issue": DEMO_ISSUE, "mode": "live"},
            ).status_code
            == 400
        )


def test_local_origin_guard(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        schema = client.get("/openapi.json")
        assert schema.status_code == 200 and "/api/tasks" in schema.json()["paths"]
        assert client.get("/docs").status_code == 404
        response = client.post(
            "/api/tasks",
            headers={"Origin": "https://untrusted.example"},
            json={"source": str(demo_source()), "issue": DEMO_ISSUE},
        )
        assert response.status_code == 403
        assert client.get("/api/demo", headers={"Host": "untrusted.example"}).status_code == 400


def test_startup_marks_abandoned_task_as_interrupted(tmp_path):
    settings = Settings(data_dir=tmp_path)
    engine = Engine(settings, sandbox=OfflineSandbox())
    state = engine.create(demo_source(), DEMO_ISSUE)
    state["status"] = "running"
    engine.store.save(state)
    with TestClient(create_app(settings, engine)) as client:
        assert client.get(f"/api/tasks/{state['id']}").json()["status"] == "interrupted"


def test_shutdown_cooperatively_stops_the_worker(tmp_path):
    started = threading.Event()
    settings = Settings(data_dir=tmp_path)

    class SlowProvider(MockProvider):
        def complete(self, *args, **kwargs):
            started.set()
            time.sleep(0.15)
            return super().complete(*args, **kwargs)

    engine = Engine(settings, provider=SlowProvider(), sandbox=OfflineSandbox())
    with TestClient(create_app(settings, engine)) as client:
        task = client.post(
            "/api/tasks", json={"source": str(demo_source()), "issue": DEMO_ISSUE}
        ).json()
        assert started.wait(timeout=3)
    assert engine.get(task["id"])["status"] == "cancelled"
    assert engine.get(task["id"])["usage"]["model_calls"] == 1
