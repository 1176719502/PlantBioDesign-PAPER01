"""Presenter helpers for the saved documentation artifact library workflow.

This module is UI-facing only. It does not change artifact persistence, import/export
services, pathway scoring, or experiment capabilities.
"""
from __future__ import annotations

from typing import Any


ARTIFACT_LIBRARY_SAFETY_COPY = (
    "Documentation artifacts are saved review records only. "
    "They do not certify experimental readiness. "
    "They do not predict yield. "
    "They do not optimize pathways. "
    "They do not provide wet-lab protocols. "
    "Linked artifacts are documentation records connected to a pathway project for traceability."
)

ARTIFACT_LIBRARY_WORKFLOW_COPY = (
    "Search saved documentation artifacts. "
    "Filter by artifact type. "
    "Filter by linked project. "
    "Show unlinked documentation artifacts. "
    "No saved documentation artifacts yet. "
    "No linked documentation artifacts for this project yet. "
    "Use tool pages to create documentation artifacts, then link them to a pathway project for traceability. "
    "Documentation artifacts are optional review records."
)

ARTIFACT_DETAIL_PREVIEW_COPY = (
    "Documentation record detail preview. "
    "Advanced record details are for traceability only. "
    "This record is a documentation record only. "
    "Detail fields include record type, created from, linked project, created timestamp, summary/preview, and boundary note."
)

ARTIFACT_DELETE_CONFIRMATION_COPY = (
    "This removes the saved documentation artifact only. "
    "It does not delete the linked pathway project. "
    "It does not certify or change experimental readiness. "
    "This action does not affect import/export package safety."
)

ARTIFACT_SAVE_SUCCESS_CONTEXT_COPY = (
    "Artifact saved as a documentation artifact. "
    "It can be reviewed in linked project context when a Pathway Project is selected. "
    "Linked records are visible from Pathway Workspace linked documentation artifacts. "
    "It is documentation-only and not validation, not prediction, not recommendation, not readiness approval, "
    "and not wet-lab protocol."
)

PROJECT_LINKED_ARTIFACT_BOUNDARY_COPY = (
    "Linked artifact = documentation record connected to a pathway project. "
    "Linked artifacts support traceability only. "
    "Linked artifacts remain review records only. "
    "Linked artifacts can be reviewed in linked project context from Pathway Workspace linked documentation artifacts. "
    "They are documentation references only and do not certify experimental readiness. "
    "They do not predict yield. "
    "They do not optimize pathways. "
    "They do not provide wet-lab protocols. "
    "They do not increase readiness or evidence score as experimental proof."
)


def normalize_artifact_text(value: Any) -> str:
    return str(value or "").strip()


def artifact_matches_search(artifact: dict[str, Any], query: str) -> bool:
    needle = normalize_artifact_text(query).lower()
    if not needle:
        return True
    haystack = " ".join(
        normalize_artifact_text(artifact.get(key))
        for key in ("artifact_type", "title", "source_module", "summary", "notes", "created_at")
    ).lower()
    return needle in haystack


def filter_documentation_artifacts(
    artifacts: list[dict[str, Any]],
    *,
    search_query: str = "",
    artifact_type: str | None = None,
    linked_project: str | int | None = None,
    show_unlinked: bool = False,
) -> list[dict[str, Any]]:
    """Filter an in-memory artifact list for the library UI without changing storage."""
    clean_type = normalize_artifact_text(artifact_type)
    clean_project = normalize_artifact_text(linked_project)
    filtered: list[dict[str, Any]] = []
    for artifact in artifacts:
        project_id = artifact.get("project_id")
        if clean_type and normalize_artifact_text(artifact.get("artifact_type")) != clean_type:
            continue
        if clean_project and normalize_artifact_text(project_id) != clean_project:
            continue
        if show_unlinked and project_id not in (None, ""):
            continue
        if not artifact_matches_search(artifact, search_query):
            continue
        filtered.append(artifact)
    return filtered


def artifact_library_empty_state(linked_project_scope: bool = False) -> str:
    if linked_project_scope:
        return (
            "No linked documentation artifacts for this project yet. "
            "Use tool pages to create documentation artifacts, then link them to a pathway project for traceability. "
            "Documentation artifacts are optional review records."
        )
    return (
        "No saved documentation artifacts yet. "
        "Use tool pages to create documentation artifacts, then link them to a pathway project for traceability. "
        "Documentation artifacts are optional review records."
    )


def artifact_save_success_message(artifact_id: int | str | None, project_id: int | str | None = None) -> str:
    """Return a consistent documentation-only success message for tool artifact saves."""
    linked_context = (
        f" Linked project context: Pathway Project {project_id}; review location: Pathway Workspace linked documentation artifacts."
        if project_id not in (None, "")
        else " No Pathway Project was linked; review it from Saved Documentation Artifacts or save another record with a project link."
    )
    return f"Saved documentation artifact #{artifact_id}. {ARTIFACT_SAVE_SUCCESS_CONTEXT_COPY}{linked_context}"


def artifact_detail_preview_labels() -> dict[str, str]:
    return {
        "heading": "Documentation record detail preview",
        "artifact_type": "Record type",
        "source_tool": "Created from",
        "linked_project": "linked project",
        "created_timestamp": "created timestamp",
        "summary_preview": "summary/preview",
        "raw_payload": "Advanced record details",
        "record_boundary": "This record is documentation-only.",
    }
