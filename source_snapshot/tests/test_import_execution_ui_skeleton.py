from __future__ import annotations

from pathlib import Path

from services.project_import_execution_gate_service import (
    EXECUTION_DISABLED_REASON,
    build_project_import_execution_gate_state,
)

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
IMPORT_PREVIEW_SECTION = ROOT / "views" / "pathway_workspace_sections" / "import_preview_section.py"
GATE_SERVICE = ROOT / "services" / "project_import_execution_gate_service.py"

REQUIRED_UI_TERMS = [
    "Create New Documentation Project",
    "Create New Documentation Project is available only after package validation, safety review, dry-run planning, and explicit final confirmation.",
    "Execution creates a new documentation-only project only",
    "documentation-only",
    "read-only preview",
    "import as new project only",
    "no overwrite",
    "no merge",
    "no raw payload_json restoration",
    "no database writes",
    "does not import or modify any project",
]

REQUIRED_PREVIEW_TERMS = [
    "Pathway Workspace > Project Outputs > Import Preview",
    "documentation-only package inspection for validation and dry-run planning",
    "The preview step itself does not create a project",
    "read-only preview",
    "Dry-run import plan",
    "no database writes",
    "no project creation",
]

FORBIDDEN_DANGEROUS_LABELS = [
    "Import Project",
    "Execute Import",
    "Confirm Import",
    "Restore Project",
    "Merge Project",
    "Overwrite Project",
    "Import now",
    "Ready to import",
]


def _workspace_source() -> str:
    return PATHWAY_WORKSPACE.read_text(encoding="utf-8")


def _preview_section_source() -> str:
    return IMPORT_PREVIEW_SECTION.read_text(encoding="utf-8")


def _import_preview_source() -> str:
    source = _workspace_source()
    start = source.index("def _render_import_package_preview")
    end = source.index("def _safe_int", start)
    return source[start:end]


def test_ui_skeleton_required_copy_exists() -> None:
    content = _workspace_source()
    preview_section = _preview_section_source()
    gate_content = GATE_SERVICE.read_text(encoding="utf-8")
    combined = f"{content}\n{preview_section}\n{gate_content}"

    missing = [term for term in REQUIRED_UI_TERMS if term not in combined]

    assert not missing, "Missing gated skeleton UI terms: " + ", ".join(missing)


def test_forbidden_dangerous_button_labels_are_not_added() -> None:
    content = _workspace_source()

    for label in FORBIDDEN_DANGEROUS_LABELS:
        assert label not in content


def test_gating_helper_blocks_invalid_package() -> None:
    state = build_project_import_execution_gate_state(
        validation_report={"is_valid": False},
        dry_run_plan={"is_plan_available": True},
        confirmation_checked=True,
    )

    assert state["package_valid"] is False
    assert state["can_enable_create_action"] is False
    assert EXECUTION_DISABLED_REASON in state["disabled_reasons"]


def test_gating_helper_blocks_missing_dry_run_plan() -> None:
    state = build_project_import_execution_gate_state(
        validation_report={"is_valid": True},
        dry_run_plan={"is_plan_available": False},
        confirmation_checked=True,
    )

    assert state["dry_run_available"] is False
    assert state["can_enable_create_action"] is False
    assert EXECUTION_DISABLED_REASON in state["disabled_reasons"]


def test_gating_helper_blocks_unchecked_confirmation() -> None:
    state = build_project_import_execution_gate_state(
        validation_report={"is_valid": True},
        dry_run_plan={"is_plan_available": True},
        confirmation_checked=False,
    )

    assert state["confirmation_checked"] is False
    assert state["can_enable_create_action"] is False
    assert EXECUTION_DISABLED_REASON in state["disabled_reasons"]


def test_gating_helper_enables_create_action_when_all_visible_gates_pass() -> None:
    state = build_project_import_execution_gate_state(
        validation_report={"is_valid": True},
        dry_run_plan={"is_plan_available": True},
        confirmation_checked=True,
    )

    assert state["package_valid"] is True
    assert state["dry_run_available"] is True
    assert state["confirmation_checked"] is True
    assert state["execution_available_in_this_build"] is True
    assert state["can_show_gated_block"] is True
    assert state["can_enable_create_action"] is True
    assert EXECUTION_DISABLED_REASON not in state["disabled_reasons"]


def test_pathway_workspace_import_execution_safety() -> None:
    content = _workspace_source()
    preview_source = _import_preview_source()

    assert "enable_database_write=True" not in content
    assert "execute_project_import_as_new_project" not in content

    for repository_write_call in [
        "create_pathway_project(",
        "create_project(",
        "update_pathway_project(",
        "delete_pathway_project(",
        "restore_project(",
    ]:
        assert repository_write_call not in preview_source

    for unsafe_path in [
        "overwrite_project",
        "merge_project",
        "restore_raw_payload",
        "payload_json restoration path",
        "restore raw payload",
    ]:
        assert unsafe_path not in content.lower()


def test_preview_ui_keeps_read_only_dry_run_boundary() -> None:
    content = _workspace_source() + "\n" + _preview_section_source()

    for term in REQUIRED_PREVIEW_TERMS:
        assert term in content

    assert "This preview does not import or modify any project" in content
    assert "No database writes are performed" in content
    assert "documentation-only" in content
    assert "read-only preview" in content
    assert "no project creation" in content
    assert "no overwrite" in content
    assert "no merge" in content
    assert "does not certify experimental readiness" in content
    assert "does not predict yield" in content
    assert "does not optimize pathways" in content
    assert ("does not provide wet-lab protocols" in content) or ("does not provide wet-lab instructions" in content)
