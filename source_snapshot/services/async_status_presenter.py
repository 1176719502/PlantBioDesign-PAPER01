from __future__ import annotations

from typing import Any, Callable


ProgressBuilder = Callable[[str], int]
DetailBuilder = Callable[[str, int], str]


def build_async_status_presenter(
    prefix: str,
    *,
    title: str,
    status: str,
    progress_builder: ProgressBuilder,
    detail_builder: DetailBuilder,
    session_state: dict[str, Any],
    include_result_ready: bool = False,
) -> dict[str, Any]:
    """Build a UI-friendly async task status presenter from session state."""
    task_id = str(session_state.get(f"{prefix}_id") or "")
    task_error = str(session_state.get(f"{prefix}_error") or "")
    poll_count = int(session_state.get(f"{prefix}_poll_count") or 0)
    result_payload = session_state.get(f"{prefix}_result")
    poll_enabled = bool(session_state.get(f"{prefix}_poll_enabled"))

    presenter: dict[str, Any] = {
        "title": title,
        "status": status,
        "progress": progress_builder(status),
        "detail": detail_builder(status, poll_count),
        "task_id": task_id,
        "error_text": task_error,
        "poll_count": poll_count,
        "poll_enabled": poll_enabled,
    }
    if include_result_ready:
        presenter["result_ready"] = bool(status == "finished" and result_payload)
    return presenter
