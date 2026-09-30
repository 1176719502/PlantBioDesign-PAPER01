from __future__ import annotations

from typing import Any

import streamlit as st

from core.session_keys import SK
from services import expression_construct_presenter as presenter


def current_step2_component_context_readback() -> dict[str, Any] | None:
    """Return current-session Step 2 Component Library context without saving it."""
    ds = st.session_state.get(SK.DESIGN_SESSION)
    host = _text(getattr(ds, "host", ""))
    if not host:
        return None

    tag = _text(getattr(ds, "tag", ""))
    elements = getattr(ds, "elements", {})
    rules: dict[str, Any] = {}
    try:
        from core.expression_frame_builder import get_host_rules

        loaded_rules = get_host_rules(host)
        rules = loaded_rules if isinstance(loaded_rules, dict) else {}
    except Exception:
        rules = {}

    return presenter.build_step2_component_context_readback(
        host=host,
        tag=tag,
        rules=rules,
        elements=elements if isinstance(elements, dict) else {},
    )


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback
