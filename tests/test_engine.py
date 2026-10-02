import json
import time

import pytest

from repofix.config import DEMO_ISSUE, Settings, demo_source
from repofix.engine import Engine
from repofix.models import Reply
from repofix.providers import MockProvider, ProviderError, tool_reply


class FakeSandbox:
    """No submitted Python is executed; unit-test the orchestrator contract only."""

    def run(self, repo, tests=None, cancel_event=None):
        return {
            "status": "passed",
            "exit_code": 0,
            "output": "unit-test stub",
            "duration_seconds": 0.01,
            "complete_suite": tests is None,
        }


class MissingSandbox(FakeSandbox):
    def run(self, repo, tests=None, cancel_event=None):
        return {
            "status": "unavailable",
            "exit_code": None,
            "output": "Docker unavailable",
            "duration_seconds": 0,
            "complete_suite": tests is None,
        }


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "state")


def test_mock_produces_isolated_candidate_and_claims(settings):
    before = (demo_source() / "pagination.py").read_bytes()
    engine = Engine(settings, sandbox=FakeSandbox())
    task = engine.create(demo_source(), DEMO_ISSUE)
    state = engine.run(task["id"])
    assert state["status"] == "succeeded"
    assert state["public_tests"]["complete_suite"]
    assert state["independent_tests"]["status"] == "not_run"
    assert state["usage"]["mock"] and state["usage"]["cost_usd"] is None
    assert state["repairs"] == 1 and state["evidence"]
    assert "+ 1" in state["candidate_patch"]
    assert (demo_source() / "pagination.py").read_bytes() == before


def test_missing_docker_never_claims_success(settings):
    engine = Engine(settings, sandbox=MissingSandbox())
    state = engine.run(engine.create(demo_source(), DEMO_ISSUE)["id"])
    assert state["status"] == "completed"
    assert state["candidate_patch"]
    assert state["public_tests"]["status"] == "unavailable"


def test_recovery_after_patch_write_does_not_apply_twice(settings):
    class SimulatedCrash(BaseException):
        pass

    def crash(state, result):
        if state["pending"]["name"] == "apply_patch":
            raise SimulatedCrash()

    original = Engine(settings, sandbox=FakeSandbox(), after_tool=crash)
    task = original.create(demo_source(), DEMO_ISSUE)
    with pytest.raises(SimulatedCrash):
        original.run(task["id"])
    assert original.get(task["id"])["status"] == "interrupted"
    restored = Engine(settings, sandbox=FakeSandbox())
    state = restored.run(task["id"])
    assert state["status"] == "succeeded"
    assert state["repairs"] == 1
    assert state["tool_calls"] == 4


def test_budget_terminates_loop(settings):
    engine = Engine(settings, sandbox=FakeSandbox())
    state = engine.run(engine.create(demo_source(), DEMO_ISSUE, limits={"max_tool_calls": 2})["id"])
    assert state["status"] == "failed" and state["error"] == "tool_limit"
    assert not state["candidate_patch"]


def test_cancel_queued_task(settings):
    engine = Engine(settings, sandbox=FakeSandbox())
    task = engine.create(demo_source(), DEMO_ISSUE)
    engine.cancel(task["id"])
    assert engine.run(task["id"])["status"] == "cancelled"


def test_timeout_and_terminal_idempotency(settings):
    class SlowMock(MockProvider):
        def complete(self, *args, **kwargs):
            time.sleep(1.05)
            return super().complete(*args, **kwargs)

    engine = Engine(settings, provider=SlowMock(), sandbox=FakeSandbox())
    state = engine.run(
        engine.create(demo_source(), DEMO_ISSUE, limits={"timeout_seconds": 1})["id"]
    )
    assert state["status"] == "timed_out"
    assert engine.run(state["id"])["usage"] == state["usage"]


def test_live_requires_explicit_consent(settings):
    engine = Engine(settings)
    with pytest.raises(ValueError, match="allow-paid"):
        engine.create(demo_source(), DEMO_ISSUE, mode="live")


def test_model_error_is_bounded(settings):
    class Broken:
        def complete(self, *args, **kwargs):
            raise ProviderError("provider is unavailable")

    engine = Engine(settings, provider=Broken(), sandbox=FakeSandbox())
    state = engine.run(engine.create(demo_source(), DEMO_ISSUE)["id"])
    assert state["status"] == "failed"
    assert state["usage"]["model_calls"] == 2


def test_baseline_is_one_model_generation(settings):
    class OnePatch:
        def complete(self, *args, **kwargs):
            return tool_reply(
                "apply_patch",
                {
                    "edits": [
                        {
                            "path": "pagination.py",
                            "old": "start = (page - 1) * page_size + 1",
                            "new": "start = (page - 1) * page_size",
                        }
                    ]
                },
                0,
                "Single generation patch.",
            )

    engine = Engine(settings, provider=OnePatch(), sandbox=FakeSandbox())
    state = engine.run(engine.create(demo_source(), DEMO_ISSUE, strategy="baseline")["id"])
    assert state["status"] == "succeeded"
    assert state["usage"]["model_calls"] == 1


def test_test_failure_is_observed_and_repaired(settings):
    class Feedback:
        def complete(self, messages, *args, **kwargs):
            results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
            steps = [
                (
                    "apply_patch",
                    {
                        "edits": [
                            {
                                "path": "pagination.py",
                                "old": "page_size + 1",
                                "new": "page_size + 2",
                            }
                        ]
                    },
                ),
                ("run_tests", {}),
                (
                    "apply_patch",
                    {
                        "edits": [
                            {"path": "pagination.py", "old": "page_size + 2", "new": "page_size"}
                        ]
                    },
                ),
                ("run_tests", {}),
            ]
            if len(results) == 2:
                assert results[-1]["data"]["status"] == "failed"
            if len(results) < len(steps):
                name, args = steps[len(results)]
                return tool_reply(name, args, len(results), "Fixture feedback step")
            return Reply({"role": "assistant", "content": "Done"}, summary="Done")

    class FeedbackSandbox(FakeSandbox):
        def run(self, repo, tests=None, cancel_event=None):
            result = super().run(repo, tests, cancel_event)
            if "page_size + 2" in (repo / "pagination.py").read_text():
                result.update(status="failed", exit_code=1, output="assert first page == [10,20]")
            return result

    engine = Engine(settings, provider=Feedback(), sandbox=FeedbackSandbox())
    state = engine.run(engine.create(demo_source(), DEMO_ISSUE)["id"])
    assert state["status"] == "succeeded" and state["repairs"] == 2


def test_large_export_is_complete_not_tool_preview(settings, tmp_path):
    source = tmp_path / "large-source"
    (source / "tests").mkdir(parents=True)
    old = 'VALUE = "' + "a" * 26000 + '"\n'
    new = 'VALUE = "' + "b" * 26000 + '"\n'
    (source / "value.py").write_text(old)
    (source / "tests" / "test_value.py").write_text("def test_exists():\n    assert True\n")

    class LargePatch:
        def complete(self, *args, **kwargs):
            return tool_reply(
                "apply_patch",
                {"edits": [{"path": "value.py", "old": old, "new": new}]},
                0,
                "Large fixture patch",
            )

    engine = Engine(settings, provider=LargePatch(), sandbox=FakeSandbox())
    state = engine.run(
        engine.create(source, "Replace VALUE in the source", strategy="baseline")["id"]
    )
    assert state["status"] == "succeeded"
    assert len(state["candidate_patch"]) > 48000
    assert "+" + new.strip() in state["candidate_patch"]


@pytest.mark.parametrize("bad", [None, -1, "100", True])
def test_invalid_usage_stays_unknown(bad):
    state = {
        "usage": {
            "tokens_known": True,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    }
    Engine._record_usage(state, {"prompt_tokens": bad, "completion_tokens": 2, "total_tokens": 3})
    assert state["usage"]["tokens_known"] is False
    assert state["usage"]["total_tokens"] == 0


def test_context_includes_tool_schemas_before_model_call(settings):
    engine = Engine(settings, sandbox=FakeSandbox())
    state = engine.run(
        engine.create(demo_source(), DEMO_ISSUE, limits={"context_chars": 3000})["id"]
    )
    assert state["status"] == "failed"
    assert state["usage"]["model_calls"] == 0
    assert "context budget" in state["error"]


def test_cancel_cannot_overwrite_a_fresh_worker_checkpoint(settings, monkeypatch):
    engine = Engine(settings, sandbox=FakeSandbox())
    task = engine.create(demo_source(), DEMO_ISSUE)
    real_get = engine.get
    first = True

    def racing_get(task_id):
        nonlocal first
        snapshot = real_get(task_id)
        if first:
            first = False
            newer = dict(
                snapshot, status="running", pending={"receipt_id": "fresh-intent"}, tool_calls=7
            )
            assert engine.store.claim(task_id, "other-worker")
            engine.store.save(newer, "other-worker")
        return snapshot

    monkeypatch.setattr(engine, "get", racing_get)
    state = engine.cancel(task["id"])
    assert state["cancel_requested"]
    assert state["pending"] == {"receipt_id": "fresh-intent"}
    assert state["tool_calls"] == 7 and state["status"] == "running"


def test_rechecks_terminal_state_after_worker_claim(settings, monkeypatch):
    engine = Engine(settings, sandbox=FakeSandbox())
    task = engine.create(demo_source(), DEMO_ISSUE)
    real_claim = engine.store.claim

    def claim_after_finish(task_id, owner):
        completed = engine.get(task_id)
        completed.update(status="completed", phase="done", tool_calls=7)
        engine.store.save(completed)
        return real_claim(task_id, owner)

    monkeypatch.setattr(engine.store, "claim", claim_after_finish)
    state = engine.run(task["id"])
    assert state["status"] == "completed" and state["tool_calls"] == 7
    assert state["usage"]["model_calls"] == 0


def test_active_test_cancellation_is_observed(settings):
    class CancellingSandbox(FakeSandbox):
        def run(self, repo, tests=None, cancel_event=None):
            cancel_event.store.cancel(cancel_event.task_id)
            return {
                "status": "cancelled",
                "exit_code": None,
                "output": "fixture cancel",
                "duration_seconds": 0,
            }

    engine = Engine(settings, sandbox=CancellingSandbox())
    state = engine.run(engine.create(demo_source(), DEMO_ISSUE)["id"])
    assert state["status"] == "cancelled" and state["usage"]["model_calls"] == 4


def test_setup_failure_releases_lease(settings):
    engine = Engine(settings)
    task = engine.create(demo_source(), DEMO_ISSUE)
    (settings.data_dir / "tasks" / task["id"] / "baseline" / "pagination.py").write_text("tampered")
    state = engine.run(task["id"])
    assert state["status"] == "failed"
    assert engine.store.claim(task["id"], "new-owner")


def test_mock_baseline_respects_the_patch_only_contract(settings):
    engine = Engine(settings, sandbox=FakeSandbox())
    state = engine.run(engine.create(demo_source(), DEMO_ISSUE, strategy="baseline")["id"])
    assert state["status"] == "succeeded"
    assert state["usage"]["model_calls"] == 1
    assert state["verification_calls"] == 1 and state["tool_calls"] == 2


@pytest.mark.parametrize("limits", [{}, {"max_model_calls": 1}])
def test_final_verification_resume_does_not_generate_another_baseline_patch(settings, limits):
    class VerificationCrash(BaseException):
        pass

    class CrashBeforeResult(FakeSandbox):
        def __init__(self):
            self.calls = 0

        def run(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise VerificationCrash()
            return super().run(*args, **kwargs)

    sandbox = CrashBeforeResult()
    engine = Engine(settings, sandbox=sandbox)
    task = engine.create(demo_source(), DEMO_ISSUE, strategy="baseline", limits=limits)
    with pytest.raises(VerificationCrash):
        engine.run(task["id"])
    interrupted = engine.get(task["id"])
    assert interrupted["phase"] == "verifying" and interrupted["pending"] is None
    assert interrupted["verification_pending"]["result_recorded"] is False
    restored = Engine(settings, sandbox=sandbox)
    state = restored.run(task["id"])
    assert state["status"] == "succeeded"
    assert state["usage"]["model_calls"] == 1 and state["repairs"] == 1
    assert state["tool_calls"] == 3 and state["verification_calls"] == 2
    assert sandbox.calls == 2 and state["verification_pending"] is None


@pytest.mark.parametrize(
    ("test_status", "terminal_status"),
    [("passed", "succeeded"), ("failed", "failed"), ("unavailable", "completed")],
)
def test_recorded_final_verification_result_survives_crash_without_repeating_work(
    settings, monkeypatch, test_status, terminal_status
):
    class VerificationCrash(BaseException):
        pass

    class RecordedResult(FakeSandbox):
        def __init__(self):
            self.calls = 0

        def run(self, *args, **kwargs):
            self.calls += 1
            result = super().run(*args, **kwargs)
            result["status"] = test_status
            return result

    sandbox = RecordedResult()
    engine = Engine(settings, sandbox=sandbox)
    task = engine.create(
        demo_source(), DEMO_ISSUE, strategy="baseline", limits={"max_model_calls": 1}
    )
    checkpoint = engine._checkpoint

    def crash_after_recording(state, owner, kind="", data=None):
        checkpoint(state, owner, kind, data)
        if kind == "verification_result":
            raise VerificationCrash()

    monkeypatch.setattr(engine, "_checkpoint", crash_after_recording)
    with pytest.raises(VerificationCrash):
        engine.run(task["id"])
    assert engine.get(task["id"])["verification_pending"]["result_recorded"] is True
    state = Engine(settings, sandbox=sandbox).run(task["id"])
    assert state["status"] == terminal_status
    assert state["public_tests"]["status"] == test_status
    assert state["usage"]["model_calls"] == 1
    assert state["tool_calls"] == 2 and state["verification_calls"] == 1
    assert sandbox.calls == 1 and state["verification_pending"] is None


def test_final_verification_retry_requires_remaining_tool_budget(settings):
    class VerificationCrash(BaseException):
        pass

    class AlwaysCrashes(FakeSandbox):
        def __init__(self):
            self.calls = 0

        def run(self, *args, **kwargs):
            self.calls += 1
            raise VerificationCrash()

    sandbox = AlwaysCrashes()
    engine = Engine(settings, sandbox=sandbox)
    task = engine.create(
        demo_source(),
        DEMO_ISSUE,
        strategy="baseline",
        limits={"max_model_calls": 1, "max_tool_calls": 2},
    )
    with pytest.raises(VerificationCrash):
        engine.run(task["id"])
    state = Engine(settings, sandbox=sandbox).run(task["id"])
    assert state["status"] == "failed" and state["error"] == "tool_limit"
    assert state["usage"]["model_calls"] == 1 and state["tool_calls"] == 2
    assert sandbox.calls == 1 and state["public_tests"]["status"] == "not_run"


@pytest.mark.parametrize("stop", ["cancelled", "timed_out"])
def test_final_verification_resume_obeys_cancellation_and_remaining_time(settings, stop):
    class VerificationCrash(BaseException):
        pass

    class InterruptedVerification(FakeSandbox):
        def __init__(self):
            self.calls = 0

        def run(self, *args, **kwargs):
            self.calls += 1
            if stop == "timed_out":
                time.sleep(1.05)
            raise VerificationCrash()

    sandbox = InterruptedVerification()
    engine = Engine(settings, sandbox=sandbox)
    task = engine.create(
        demo_source(),
        DEMO_ISSUE,
        strategy="baseline",
        limits={"max_model_calls": 1, "timeout_seconds": 1},
    )
    with pytest.raises(VerificationCrash):
        engine.run(task["id"])
    if stop == "cancelled":
        engine.cancel(task["id"])
    state = Engine(settings, sandbox=sandbox).run(task["id"])
    assert state["status"] == stop and state["usage"]["model_calls"] == 1
    assert sandbox.calls == 1 and state["public_tests"]["status"] == "not_run"


def test_receipt_failure_after_source_change_cannot_reuse_previous_passing_tests(
    settings, monkeypatch
):
    import repofix.tools

    original_write = repofix.tools.atomic_json
    patch_results = 0

    def fail_second_patch_receipt(path, data):
        nonlocal patch_results
        if path.name.endswith(".result.json") and data.get("name") == "apply_patch":
            patch_results += 1
            if patch_results == 2:
                raise OSError("simulated receipt persistence failure")
        return original_write(path, data)

    monkeypatch.setattr(repofix.tools, "atomic_json", fail_second_patch_receipt)

    class PatchThenBreak:
        def complete(self, messages, *args, **kwargs):
            results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
            steps = [
                (
                    "apply_patch",
                    {
                        "edits": [
                            {"path": "pagination.py", "old": "page_size + 1", "new": "page_size"}
                        ]
                    },
                ),
                ("run_tests", {}),
                (
                    "apply_patch",
                    {
                        "edits": [
                            {
                                "path": "pagination.py",
                                "old": "start = (page - 1) * page_size",
                                "new": "start = (page - 1) * page_size + 2",
                            }
                        ]
                    },
                ),
            ]
            if len(results) == 2:
                assert results[-1]["data"]["status"] == "passed"
            if len(results) < len(steps):
                name, arguments = steps[len(results)]
                return tool_reply(name, arguments, len(results), "Receipt failure fixture")
            assert results[-1]["ok"] is False
            assert results[-1]["error"]["code"] == "IO_ERROR"
            return Reply({"role": "assistant", "content": "Done"}, summary="Done")

    class ActualContentSandbox(FakeSandbox):
        def __init__(self):
            self.calls = 0

        def run(self, repo, tests=None, cancel_event=None):
            self.calls += 1
            result = super().run(repo, tests, cancel_event)
            if "page_size + 2" in (repo / "pagination.py").read_text():
                result.update(status="failed", exit_code=1, output="Wrong page offset")
            return result

    sandbox = ActualContentSandbox()
    engine = Engine(settings, provider=PatchThenBreak(), sandbox=sandbox)
    state = engine.run(engine.create(demo_source(), DEMO_ISSUE)["id"])
    assert state["status"] == "failed" and state["public_tests"]["status"] == "failed"
    assert state["repairs"] == 1 and sandbox.calls == 2
    assert "page_size + 2" in state["candidate_patch"]
    assert state["verification_calls"] == 1
