from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from services.tool_artifact_library_presenter import (
    PROJECT_LINKED_ARTIFACT_BOUNDARY_COPY,
    artifact_library_empty_state,
)
from services.tool_artifact_service import list_tool_artifacts

LINKED_TOOL_ARTIFACT_BOUNDARY_COPY = PROJECT_LINKED_ARTIFACT_BOUNDARY_COPY
LINKED_TOOL_ARTIFACT_REVIEW_CONTEXT_COPY = (
    "Use this section to review saved tool outputs in the active pathway project context. "
    "Artifact summaries show what was saved, where it came from, and whether it is linked to this project. "
    "Structure analysis artifacts and other tool artifacts are local documentation review context only. "
    "They are not validation, not prediction, not recommendation, not readiness approval, and not wet-lab protocol."
)


def _linked_tool_artifact_rows(project_id: int | str | None) -> list[dict[str, Any]]:
    artifacts = list_tool_artifacts(project_id=project_id)
    return [
        {
            "created_at": artifact.get("created_at", ""),
            "artifact_type": artifact.get("artifact_type", ""),
            "title": artifact.get("title", ""),
            "source_module": artifact.get("source_module", ""),
            "summary": artifact.get("summary", ""),
            "linked_project_context": f"Pathway Project {project_id}",
            "review_location": "Pathway Workspace / Linked Documentation Artifacts",
            "boundary_label": artifact.get("boundary_label", ""),
        }
        for artifact in artifacts
    ]


def render_linked_artifacts_section(project_id: int | str | None) -> None:
    st.subheader("Linked Documentation Artifacts")
    st.caption(LINKED_TOOL_ARTIFACT_BOUNDARY_COPY)
    st.caption(
        "Linked artifacts are documentation records connected to a pathway project for traceability. "
        "They remain review records only and do not increase readiness or evidence score as experimental proof. "
        "Review location: Pathway Workspace linked documentation artifacts."
    )
    st.caption(
        "Documentation artifacts and computational previews are for traceability only: this section does not certify experimental readiness, "
        "does not predict yield, does not optimize pathways, and does not provide wet-lab protocols."
    )
    st.caption(LINKED_TOOL_ARTIFACT_REVIEW_CONTEXT_COPY)
    rows = _linked_tool_artifact_rows(project_id)
    if not rows:
        st.info(artifact_library_empty_state(linked_project_scope=True))
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
