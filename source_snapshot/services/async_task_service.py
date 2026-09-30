from __future__ import annotations

from typing import Any

import streamlit as st

from services.task_polling_service import mark_task_polled, mark_task_submitted, reset_task_runtime_state


def handle_task_submission(
    prefix: str,
    *,
    response: dict[str, Any],
    fallback_status: str,
    progress_map: dict[str, int],
    detail_builder,
) -> str:
    """Store the common submitted-task state and return the task id."""
    task_id = str(response.get("task_id") or "").strip()
    status = str(response.get("status") or fallback_status).strip().lower()
    mark_task_submitted(
        prefix,
        task_id=task_id,
        status=status,
        progress_map=progress_map,
        detail_builder=detail_builder,
    )
    return task_id


def handle_task_active_poll_state(prefix: str) -> None:
    """Apply the common state for queued/started/deferred task payloads."""
    st.session_state[f"{prefix}_result"] = None
    st.session_state[f"{prefix}_error"] = ""
    st.session_state[f"{prefix}_poll_enabled"] = True


def handle_task_terminal_error_state(prefix: str, *, status: str, error_text: str) -> None:
    """Apply the common state for failed/not-found task payloads."""
    st.session_state[f"{prefix}_status"] = status
    st.session_state[f"{prefix}_result"] = None
    st.session_state[f"{prefix}_error"] = error_text or f"Task returned status: {status}."
    reset_task_runtime_state(prefix)


def handle_task_non_polling_state(prefix: str, *, result: dict[str, Any] | None, error_text: str) -> None:
    """Apply the common state for non-active, non-terminal task payloads."""
    st.session_state[f"{prefix}_result"] = result
    st.session_state[f"{prefix}_error"] = error_text
    st.session_state[f"{prefix}_poll_enabled"] = False


def handle_task_exception_state(
    prefix: str,
    *,
    error: Exception,
    failed_status: str = "failed",
    failed_progress: int | None = None,
    failed_detail: str | None = None,
) -> None:
    """Apply the common exception fallback for task polling."""
    st.session_state[f"{prefix}_status"] = failed_status
    st.session_state[f"{prefix}_result"] = None
    st.session_state[f"{prefix}_error"] = str(error)
    if failed_progress is not None and f"{prefix}_progress" in st.session_state:
        st.session_state[f"{prefix}_progress"] = failed_progress
    if failed_detail is not None and f"{prefix}_detail" in st.session_state:
        st.session_state[f"{prefix}_detail"] = failed_detail
    reset_task_runtime_state(prefix)


def handle_task_poll_update(
    prefix: str,
    *,
    status: str,
    now: float,
    progress_map: dict[str, int] | None = None,
    detail_builder=None,
) -> int:
    """Apply the common post-poll bookkeeping and return poll count."""
    return mark_task_polled(
        prefix,
        status=status,
        now=now,
        progress_map=progress_map,
        detail_builder=detail_builder,
    )
