from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
EMPTY_STATE = ROOT / "views" / "pathway_workspace_sections" / "empty_state.py"
PROJECT_HEADER = ROOT / "views" / "pathway_workspace_sections" / "project_header.py"


def _source() -> str:
    return PATHWAY_WORKSPACE.read_text(encoding="utf-8")


def _workspace_and_extracted_layout_source() -> str:
    return "\n".join(
        [
            PATHWAY_WORKSPACE.read_text(encoding="utf-8"),
            EMPTY_STATE.read_text(encoding="utf-8"),
            PROJECT_HEADER.read_text(encoding="utf-8"),
        ]
    )


def test_pathway_workspace_empty_state_copy_is_present() -> None:
    source = _workspace_and_extracted_layout_source()

    required_copy = [
        "No active pathway project selected",
        "Pathway Workspace shows one documentation project at a time.",
        "Choose an existing pathway project or create a new one to continue.",
        "Saved designs are wizard snapshots",
        "pathway projects are documentation workspaces",
        "Loading a saved design does not automatically select a pathway project",
        "documentation-only",
        "does not certify experimental readiness",
        "Go to Pathway Projects",
        "Design Library",
        "traceability",
    ]

    missing = [item for item in required_copy if item not in source]
    assert not missing


def test_project_concept_explanation_copy_is_present() -> None:
    source = _workspace_and_extracted_layout_source()

    required_copy = [
        "Saved design = wizard snapshot",
        "Pathway project = documentation workspace",
        "Active project = currently selected pathway documentation workspace",
        "Linked artifact = documentation record connected to a pathway project",
    ]

    missing = [item for item in required_copy if item not in source]
    assert not missing


def test_existing_import_safety_still_locked_in_pathway_workspace_ui() -> None:
    source = _source()

    forbidden_copy = [
        "enable_database_write=True",
        "execute_project_import_as_new_project",
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready for execution",
    ]

    present = [item for item in forbidden_copy if item in source]
    assert not present


def test_existing_active_workspace_import_preview_copy_still_present() -> None:
    source = _source()

    required_copy = [
        "Import Execution Preflight Review",
        "Import Execution Result Preview",
        "Create New Documentation Project is available only after package validation, safety review, dry-run planning, and explicit final confirmation.",
        "No database writes are performed by preview and safety checks.",
        "This preview does not import or modify any project.",
    ]

    missing = [item for item in required_copy if item not in source]
    assert not missing
