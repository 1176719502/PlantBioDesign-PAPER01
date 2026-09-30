from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import task_polling_service as svc


class _FakeSessionState(dict):
    pass


def test_initialize_task_state_sets_defaults(monkeypatch):
    fake_state = _FakeSessionState()
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    svc.initialize_task_state(
        "primer_task",
        defaults={"id": "", "status": "idle", "poll_enabled": False},
    )

    assert fake_state["primer_task_id"] == ""
    assert fake_state["primer_task_status"] == "idle"
    assert fake_state["primer_task_poll_enabled"] is False


def test_reset_task_runtime_state_clears_polling_fields(monkeypatch):
    fake_state = _FakeSessionState(
        primer_task_poll_enabled=True,
        primer_task_last_polled_at=123.0,
        primer_task_poll_count=7,
    )
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    svc.reset_task_runtime_state("primer_task")

    assert fake_state["primer_task_poll_enabled"] is False
    assert fake_state["primer_task_last_polled_at"] == 0.0
    assert fake_state["primer_task_poll_count"] == 0


def test_mark_task_submitted_sets_common_state(monkeypatch):
    fake_state = _FakeSessionState(validation_task_progress=0, validation_task_detail="")
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    svc.mark_task_submitted(
        "validation_task",
        task_id="task-123",
        status="queued",
        progress_map={"queued": 20, "unknown": 5},
        detail_builder=lambda status, poll_count: f"{status}-{poll_count}",
    )

    assert fake_state["validation_task_id"] == "task-123"
    assert fake_state["validation_task_status"] == "queued"
    assert fake_state["validation_task_poll_enabled"] is True
    assert fake_state["validation_task_poll_count"] == 0
    assert fake_state["validation_task_progress"] == 20
    assert fake_state["validation_task_detail"] == "queued-0"


def test_mark_task_polled_updates_progress_and_count(monkeypatch):
    fake_state = _FakeSessionState(validation_task_poll_count=1, validation_task_progress=0, validation_task_detail="")
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    count = svc.mark_task_polled(
        "validation_task",
        status="started",
        now=42.0,
        progress_map={"started": 65, "unknown": 5},
        detail_builder=lambda status, poll_count: f"{status}-{poll_count}",
    )

    assert count == 2
    assert fake_state["validation_task_status"] == "started"
    assert fake_state["validation_task_last_polled_at"] == 42.0
    assert fake_state["validation_task_poll_count"] == 2
    assert fake_state["validation_task_progress"] == 65
    assert fake_state["validation_task_detail"] == "started-2"


def test_should_poll_task_respects_interval_and_active_status(monkeypatch):
    fake_state = _FakeSessionState(
        primer_task_poll_enabled=True,
        primer_task_status="queued",
        primer_task_last_polled_at=10.0,
        primer_task_poll_count=3,
    )
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    assert svc.should_poll_task("primer_task", active_statuses={"queued", "started"}, now=10.5, min_interval_seconds=1.0) is False
    assert svc.should_poll_task("primer_task", active_statuses={"queued", "started"}, now=11.1, min_interval_seconds=1.0) is True


def test_should_poll_task_resets_runtime_for_inactive_status(monkeypatch):
    fake_state = _FakeSessionState(
        primer_task_poll_enabled=True,
        primer_task_status="finished",
        primer_task_last_polled_at=10.0,
        primer_task_poll_count=3,
    )
    monkeypatch.setattr(svc.st, "session_state", fake_state)

    assert svc.should_poll_task("primer_task", active_statuses={"queued", "started"}, now=11.1, min_interval_seconds=1.0) is False
    assert fake_state["primer_task_poll_enabled"] is False
    assert fake_state["primer_task_last_polled_at"] == 0.0
    assert fake_state["primer_task_poll_count"] == 0
