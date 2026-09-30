from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import async_task_service as svc


class _FakeSessionState(dict):
    pass


def test_handle_task_submission_sets_common_submitted_state(monkeypatch):
    fake_state = _FakeSessionState(validation_task_progress=0, validation_task_detail="")
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    task_id = svc.handle_task_submission(
        "validation_task",
        response={"task_id": "task-1", "status": "queued"},
        fallback_status="queued",
        progress_map={"queued": 20, "unknown": 5},
        detail_builder=lambda status, poll_count: f"{status}-{poll_count}",
    )

    assert task_id == "task-1"
    assert fake_state["validation_task_id"] == "task-1"
    assert fake_state["validation_task_status"] == "queued"
    assert fake_state["validation_task_poll_enabled"] is True


def test_handle_task_active_poll_state_sets_result_and_error(monkeypatch):
    fake_state = _FakeSessionState(validation_task_result={"old": True}, validation_task_error="boom", validation_task_poll_enabled=False)
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    svc.handle_task_active_poll_state("validation_task")

    assert fake_state["validation_task_result"] is None
    assert fake_state["validation_task_error"] == ""
    assert fake_state["validation_task_poll_enabled"] is True


def test_handle_task_terminal_error_state_resets_runtime(monkeypatch):
    fake_state = _FakeSessionState(
        validation_task_status="started",
        validation_task_result={"old": True},
        validation_task_error="",
        validation_task_poll_enabled=True,
        validation_task_last_polled_at=5.0,
        validation_task_poll_count=2,
    )
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    svc.handle_task_terminal_error_state("validation_task", status="failed", error_text="bad")

    assert fake_state["validation_task_status"] == "failed"
    assert fake_state["validation_task_result"] is None
    assert fake_state["validation_task_error"] == "bad"
    assert fake_state["validation_task_poll_enabled"] is False
    assert fake_state["validation_task_poll_count"] == 0


def test_handle_task_non_polling_state_disables_polling(monkeypatch):
    fake_state = _FakeSessionState(validation_task_poll_enabled=True)
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    svc.handle_task_non_polling_state("validation_task", result={"x": 1}, error_text="warn")

    assert fake_state["validation_task_result"] == {"x": 1}
    assert fake_state["validation_task_error"] == "warn"
    assert fake_state["validation_task_poll_enabled"] is False


def test_handle_task_exception_state_sets_failed_metadata(monkeypatch):
    fake_state = _FakeSessionState(
        validation_task_progress=0,
        validation_task_detail="",
        validation_task_poll_enabled=True,
        validation_task_last_polled_at=5.0,
        validation_task_poll_count=2,
    )
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    svc.handle_task_exception_state(
        "validation_task",
        error=RuntimeError("boom"),
        failed_progress=100,
        failed_detail="failed detail",
    )

    assert fake_state["validation_task_status"] == "failed"
    assert fake_state["validation_task_error"] == "boom"
    assert fake_state["validation_task_progress"] == 100
    assert fake_state["validation_task_detail"] == "failed detail"
    assert fake_state["validation_task_poll_enabled"] is False


def test_handle_task_poll_update_returns_poll_count(monkeypatch):
    fake_state = _FakeSessionState(validation_task_poll_count=0, validation_task_progress=0, validation_task_detail="")
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    count = svc.handle_task_poll_update(
        "validation_task",
        status="started",
        now=12.0,
        progress_map={"started": 65, "unknown": 5},
        detail_builder=lambda status, poll_count: f"{status}-{poll_count}",
    )

    assert count == 1
    assert fake_state["validation_task_status"] == "started"
    assert fake_state["validation_task_progress"] == 65
    assert fake_state["validation_task_detail"] == "started-1"
