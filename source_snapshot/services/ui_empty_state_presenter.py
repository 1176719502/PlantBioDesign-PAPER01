"""Shared UI-facing empty, error, and boundary copy for primary pages.

This module contains copy only. It does not change business logic, persistence,
import/export behavior, calculations, schema, or pathway project state.
"""
from __future__ import annotations


GLOBAL_EMPTY_ERROR_COPY = (
    "Enter input to generate a documentation preview. "
    "No saved documentation artifacts yet. "
    "No matching documentation records found. "
    "No linked documentation artifacts for this project yet. "
    "No active pathway project selected. "
    "No saved design snapshots found. "
    "No reference records found. "
    "Use the filters or search box to narrow documentation records. "
    "This page creates documentation records only. "
    "This preview does not certify experimental readiness. "
    "Review the input and try again."
)

TOOL_BOUNDARY_COPY = (
    "This check is a computational preview only. "
    "This result is documentation-only and for traceability only. "
    "Documentation artifacts are review records only. "
    "This does not certify experimental readiness. "
    "This does not predict yield. "
    "This does not optimize pathways. "
    "This does not provide wet-lab protocols. "
    "This does not validate folding. "
    "This does not validate function. "
    "This does not validate expression. "
    "This does not certify cloning success. "
    "This does not certify PCR success. "
    "This does not certify gel success. "
    "This does not certify expression success."
)

PAGE_EMPTY_STATE_COPY = {
    "lab_tools": (
        "Enter input to generate a documentation preview. "
        "No saved documentation artifacts yet. "
        "This page creates documentation records only. "
        "This review-only preview does not certify cloning success, PCR success, gel success, or expression success. "
        "This does not provide wet-lab protocols."
    ),
    "structure_analysis": (
        "Enter structure or protein input to generate a documentation preview. "
        "This check is a computational preview only. "
        "This does not validate folding. "
        "This does not validate function. "
        "This does not validate expression. "
        "This does not certify experimental readiness."
    ),
    "sequence_tools": (
        "Enter input to generate a documentation preview. "
        "No saved documentation artifacts yet. "
        "This page creates documentation records only. "
        "This does not certify experimental readiness. "
        "This does not predict yield. "
        "This does not optimize pathways."
    ),
    "codon_usage_preview": (
        "Enter a sequence to generate a preview. "
        "Codon Usage Preview. "
        "This documentation-only preview does not optimize sequence. "
        "This does not predict expression or yield."
    ),
    "parts_registry": (
        "No reference records found. "
        "Use search or filters to narrow reference records. "
        "Reference records are documentation aids only. "
        "This does not certify experimental readiness."
    ),
    "design_library": (
        "No saved design snapshots found. "
        "Saved design = wizard snapshot. "
        "Loading a saved design restores wizard inputs and outputs. "
        "Loading a saved design does not automatically create or select a pathway project."
    ),
    "data_saved_documentation_artifacts": (
        "No saved documentation artifacts yet. "
        "No matching documentation records found. "
        "Search saved documentation artifacts. "
        "Filter by artifact type. "
        "Filter by linked project. "
        "Documentation artifacts are saved review records only."
    ),
    "pathway_projects": (
        "Create or select a pathway documentation workspace. "
        "No pathway documentation projects found. "
        "Selecting a pathway project makes it the active project for Pathway Workspace. "
        "Pathway project = documentation workspace. "
        "Active project = currently selected pathway documentation workspace. "
        "This does not certify experimental readiness."
    ),
    "pathway_workspace": (
        "No active pathway project selected. "
        "Pathway Workspace shows one documentation project at a time. "
        "No linked documentation artifacts for this project yet. "
        "Project export/import preview remains documentation-only/read-only. "
        "Import Preview stays read-only, and any allowed create-as-new action is limited to local documentation-only project creation."
    ),
}


def all_ui_empty_state_copy() -> str:
    """Return combined UI copy for static tests and lightweight presenters."""
    return " ".join([GLOBAL_EMPTY_ERROR_COPY, TOOL_BOUNDARY_COPY, *PAGE_EMPTY_STATE_COPY.values()])
