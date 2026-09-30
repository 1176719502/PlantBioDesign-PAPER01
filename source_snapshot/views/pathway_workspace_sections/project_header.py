from __future__ import annotations

from typing import Any, Callable

import streamlit as st


def _render_project_concept_help() -> None:
    with st.expander("Project concepts", expanded=False):
        st.caption("Saved design = wizard snapshot")
        st.caption("Pathway project = documentation workspace")
        st.caption("Active project = currently selected pathway documentation workspace")
        st.caption("Linked artifact = documentation record connected to a pathway project")


def render_project_header(project: dict[str, Any], change_page: Callable[[str], None]) -> None:
    top_col, action_col = st.columns([4, 1], gap="small")
    with top_col:
        st.title(project.get("name") or "Pathway Workspace")
        st.caption(
            "Documentation-only workspace for pathway steps, test records, linked design records, review signals, "
            "and local traceability. It does not predict yield, optimize production, or certify experimental readiness."
        )
        st.caption(
            "This Pathway workflow is documentation-only. Active project means the currently selected pathway "
            "documentation workspace."
        )
        st.caption("Project identity is shown for review records and computational previews only.")
        _render_project_concept_help()
    with action_col:
        if st.button("Back to Projects", use_container_width=True):
            change_page("Pathway Projects")

    c1, c2, c3 = st.columns(3, gap="small")
    with c1:
        st.markdown("**Target product**")
        st.markdown(project.get("target_product") or "Not set")
    with c2:
        st.markdown("**Host / chassis**")
        st.markdown(project.get("host") or "Not set")
    with c3:
        st.markdown("**Status**")
        st.markdown(project.get("status") or "draft")
    if project.get("description"):
        st.caption(project["description"])
