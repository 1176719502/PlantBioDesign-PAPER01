from __future__ import annotations

from typing import Callable

import streamlit as st


def _render_project_concept_help() -> None:
    with st.expander("Project concepts", expanded=False):
        st.caption("Saved design = wizard snapshot")
        st.caption("Pathway project = documentation workspace")
        st.caption("Active project = currently selected pathway documentation workspace")
        st.caption("Linked artifact = documentation record connected to a pathway project")


def render_no_active_project_empty_state(change_page: Callable[[str], None]) -> None:
    st.title("Pathway Workspace")
    st.subheader("No active pathway project selected")
    st.info(
        "Pathway Workspace shows one documentation project at a time. "
        "Choose an existing pathway project or create a new one to continue."
    )
    st.caption(
        "Saved designs are wizard snapshots. pathway projects are documentation workspaces. "
        "Loading a saved design does not automatically select a pathway project."
    )
    st.caption(
        "This workspace is documentation-only and does not certify experimental readiness. "
        "Import Preview stays read-only, and any allowed create-as-new action is limited to local "
        "documentation-only project creation."
    )
    _render_project_concept_help()
    st.markdown("**Next steps**")
    st.caption("- Go to Pathway Projects to create or load a project.")
    st.caption("- Use Design Library to load a saved wizard snapshot.")
    st.caption("- Link wizard outputs to a pathway project when you want traceability.")
    st.caption("- Select a pathway documentation workspace before reviewing documentation-only records.")
    if st.button("Go to Pathway Projects", type="primary"):
        change_page("Pathway Projects")
