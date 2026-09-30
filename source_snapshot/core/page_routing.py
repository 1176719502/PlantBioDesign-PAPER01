"""Small helpers for Streamlit page/query-parameter reconciliation."""
from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from typing import Any


def _query_value(value: Any) -> str:
    """Return a normalized single query-param value."""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def resolve_page_from_query(
    query_params: MutableMapping[str, Any],
    all_pages: Iterable[str],
    *,
    default_page: str,
) -> str | None:
    """Return the valid page requested by query params, or ``None``."""
    requested_page = _query_value(query_params.get("page"))
    if requested_page and requested_page in set(all_pages):
        return requested_page
    return None


def reconcile_selected_page_from_query(
    session_state: MutableMapping[str, Any],
    query_params: MutableMapping[str, Any],
    all_pages: Iterable[str],
    *,
    selected_page_key: str,
    default_page: str,
) -> str:
    """Synchronize selected page state with a valid direct URL route."""
    page_set = set(all_pages)
    requested_page = resolve_page_from_query(
        query_params,
        page_set,
        default_page=default_page,
    )
    current_page = _query_value(session_state.get(selected_page_key))

    if requested_page:
        session_state[selected_page_key] = requested_page
        return requested_page

    if current_page in page_set:
        return current_page

    session_state[selected_page_key] = default_page
    return default_page
