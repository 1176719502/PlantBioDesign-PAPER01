from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import streamlit as st


DetailBuilder = Callable[[str, int], str]


def _key(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def initialize_task_state(prefix: str, *, defaults: dict[str, Any]) -> None:
    """Initialize Streamlit session state keys for an async task prefix."""
    for suffix, value in defaults.items():
        st.session_state.setdefault(_key(prefix, suffix), value)


def reset_task_runtime_state(prefix: str) -> None:
    """Reset only polling/runtime metadata while preserving task payload fields."""
    st.session_state[_key(prefix, "poll_enabled")] = False
    st.session_state[_key(prefix, "last_polled_at")] = 0.0
    st.session_state[_key(prefix, "poll_count")] = 0


def reset_task_state(prefix: str, *, reset_values: dict[str, Any]) -> None:
    """Reset the entire task state to explicit values."""
    for suffix, value in reset_values.items():
        st.session_state[_key(prefix, suffix)] = value
    reset_task_runtime_state(prefix)


def normalize_status(status: str | None, fallback: str = "unknown") -> str:
    return str(status or fallback).strip().lower()


def build_task_detail(status: str | None, poll_count: int, detail_map: dict[str, str], active_statuses: Iterable[str]) -> str:
    normalized = normalize_status(status)
    detail = detail_map.get(normalized, detail_map.get("unknown", "Task status is being checked."))
    if normalized in set(active_statuses) and poll_count > 0:
        return f"{detail} Poll cycle {poll_count}."
    return detail


def build_task_progress(status: str | None, progress_map: dict[str, int]) -> int:
    normalized = normalize_status(status)
    return progress_map.get(normalized, progress_map.get("unknown", 0))


def mark_task_submitted(
    prefix: str,
    *,
    task_id: str,
    status: str,
    progress_map: dict[str, int],
    detail_builder: DetailBuilder,
) -> None:
    normalized = normalize_status(status, fallback="queued")
    st.session_state[_key(prefix, "id")] = task_id
    st.session_state[_key(prefix, "status")] = normalized
    st.session_state[_key(prefix, "result")] = None
    st.session_state[_key(prefix, "error")] = ""
    st.session_state[_key(prefix, "poll_enabled")] = True
    st.session_state[_key(prefix, "last_polled_at")] = 0.0
    st.session_state[_key(prefix, "poll_count")] = 0
    progress_key = _key(prefix, "progress")
    detail_key = _key(prefix, "detail")
    if progress_key in st.session_state:
        st.session_state[progress_key] = build_task_progress(normalized, progress_map)
    if detail_key in st.session_state:
        st.session_state[detail_key] = detail_builder(normalized, 0)


def mark_task_polled(
    prefix: str,
    *,
    status: str,
    now: float,
    progress_map: dict[str, int] | None = None,
    detail_builder: DetailBuilder | None = None,
) -> int:
    normalized = normalize_status(status)
    poll_count = int(st.session_state.get(_key(prefix, "poll_count")) or 0) + 1
    st.session_state[_key(prefix, "status")] = normalized
    st.session_state[_key(prefix, "last_polled_at")] = now
    st.session_state[_key(prefix, "poll_count")] = poll_count
    if progress_map is not None and _key(prefix, "progress") in st.session_state:
        st.session_state[_key(prefix, "progress")] = build_task_progress(normalized, progress_map)
    if detail_builder is not None and _key(prefix, "detail") in st.session_state:
        st.session_state[_key(prefix, "detail")] = detail_builder(normalized, poll_count)
    return poll_count


def should_poll_task(prefix: str, *, active_statuses: set[str], now: float, min_interval_seconds: float = 1.0) -> bool:
    if not st.session_state.get(_key(prefix, "poll_enabled")):
        return False

    status = normalize_status(st.session_state.get(_key(prefix, "status")) or "idle")
    if status not in active_statuses:
        reset_task_runtime_state(prefix)
        return False

    last_polled_at = float(st.session_state.get(_key(prefix, "last_polled_at")) or 0.0)
    return (now - last_polled_at) >= min_interval_seconds
