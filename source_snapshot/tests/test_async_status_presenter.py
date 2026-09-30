from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.async_status_presenter import build_async_status_presenter


def test_build_async_status_presenter_for_step4_includes_result_ready():
    session_state = {
        "primer_task_id": "task-123",
        "primer_task_error": "",
        "primer_task_poll_count": 4,
        "primer_task_result": {"results": [1]},
        "primer_task_poll_enabled": True,
    }

    presenter = build_async_status_presenter(
        "primer_task",
        title="Primer async task",
        status="finished",
        progress_builder=lambda status: 100,
        detail_builder=lambda status, poll_count: f"{status}-{poll_count}",
        session_state=session_state,
        include_result_ready=True,
    )

    assert presenter["title"] == "Primer async task"
    assert presenter["status"] == "finished"
    assert presenter["progress"] == 100
    assert presenter["detail"] == "finished-4"
    assert presenter["task_id"] == "task-123"
    assert presenter["poll_count"] == 4
    assert presenter["poll_enabled"] is True
    assert presenter["result_ready"] is True


def test_build_async_status_presenter_for_step5_uses_session_defaults():
    session_state = {
        "validation_task_id": "",
        "validation_task_error": "boom",
        "validation_task_poll_count": 0,
        "validation_task_result": None,
        "validation_task_poll_enabled": False,
    }

    presenter = build_async_status_presenter(
        "validation_task",
        title="Validation task",
        status="failed",
        progress_builder=lambda status: 100,
        detail_builder=lambda status, poll_count: "Validation failed.",
        session_state=session_state,
    )

    assert presenter["title"] == "Validation task"
    assert presenter["status"] == "failed"
    assert presenter["progress"] == 100
    assert presenter["detail"] == "Validation failed."
    assert presenter["task_id"] == ""
    assert presenter["error_text"] == "boom"
    assert presenter["poll_count"] == 0
    assert presenter["poll_enabled"] is False
    assert "result_ready" not in presenter
