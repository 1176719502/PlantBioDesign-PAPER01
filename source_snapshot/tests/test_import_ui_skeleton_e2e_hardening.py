from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from services.project_import_execution_gate_service import (
    EXECUTION_DISABLED_REASON,
    build_project_import_execution_gate_state,
)

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
GATE_SERVICE = ROOT / "services" / "project_import_execution_gate_service.py"


PATHWAY_EXECUTION_FORBIDDEN_TERMS = [
    "create_project(",
    "insert_project",
    "update_project",
    "delete_project",
    "repository.write",
    "repo.write",
    "ProjectRepository",
    "Import Project",
    "Execute Import",
    "Confirm Import",
    "Import now",
    "Ready to import",
    "Restore Project",
    "Merge Project",
    "Overwrite Project",
]

REQUIRED_SKELETON_COPY = [
    "Create New Documentation Project",
    "Create New Documentation Project is available only after package validation, safety review, dry-run planning, and explicit final confirmation.",
    "Execution creates a new documentation-only project only",
    "This checkbox is the final confirmation gate before documentation project creation.",
    "does not import or modify any project",
    "No project creation is performed.",
    "documentation-only",
    "read-only preview",
    "import as new project only",
    "no overwrite",
    "no merge",
    "no raw payload_json restoration",
    "no database writes",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not provide wet-lab protocols",
    "computational previews",
    "review records only",
]

HIDDEN_WRITE_PATH_FORBIDDEN_TERMS = [
    "database write",
    "repository write",
    "raw payload restore",
    "overwrite project",
    "merge project",
]

REQUIRED_PREVIEW_COPY = [
    "read-only preview",
    "dry-run import plan",
    "no database writes",
    "does not import or modify any project",
    "No database writes are performed.",
    "No project creation is performed.",
    "Documentation project creation requires all explicit gates.",
]

DANGEROUS_POSITIVE_CLAIMS = [
    "experiment-ready",
    "production-ready",
    "validated import",
    "validated project",
    "successful import",
    "ready to import",
    "optimized pathway",
    "yield prediction result",
    "wet-lab protocol generated",
]

SAFE_NEGATED_OR_DISABLED_PHRASES = [
    "no database writes",
    "No database writes",
    "Database writes performed",
    "database_writes_performed",
    "No project creation",
    "does not provide wet-lab protocols",
    "does not import or modify any project",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "Execution is intentionally disabled in this build.",
    "restores raw payload_json",
    "overwrites, restores raw payload_json, or writes to the database",
    "no raw payload_json restoration",
    "no overwrite",
    "no merge",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _pathway_workspace_source() -> str:
    return _read(PATHWAY_WORKSPACE)


def _gate_service_source() -> str:
    return _read(GATE_SERVICE)


def _import_preview_source() -> str:
    source = _pathway_workspace_source()
    start = source.index("def _render_import_dry_run_plan")
    end = source.index("def _safe_int", start)
    return source[start:end]


def _combined_skeleton_source() -> str:
    return f"{_import_preview_source()}\n{_gate_service_source()}"


def _without_allowed_safety_copy(source: str) -> str:
    scrubbed = source
    for phrase in SAFE_NEGATED_OR_DISABLED_PHRASES:
        scrubbed = scrubbed.replace(phrase, "")
    return scrubbed


def test_pathway_workspace_has_no_import_execution_entrypoint_or_dangerous_labels() -> None:
    source = _pathway_workspace_source()

    forbidden = [term for term in PATHWAY_EXECUTION_FORBIDDEN_TERMS if term in source]

    assert forbidden == []


def test_skeleton_safety_copy_still_present_in_ui_and_gate_helper() -> None:
    source = _combined_skeleton_source()
    lower_source = source.lower()

    missing = [term for term in REQUIRED_SKELETON_COPY if term.lower() not in lower_source]

    assert missing == []


@pytest.mark.parametrize(
    ("validation_report", "dry_run_plan", "confirmation_checked", "expected_show_block"),
    [
        ({"is_valid": False}, {"is_plan_available": False}, False, False),
        ({"is_valid": True}, {"is_plan_available": False}, False, False),
        ({"is_valid": True}, {"is_plan_available": True}, False, True),
        ({"is_valid": True}, {"is_plan_available": True}, True, True),
    ],
)
def test_gating_helper_enables_create_action_only_when_all_gates_pass(
    validation_report: dict[str, Any],
    dry_run_plan: dict[str, Any],
    confirmation_checked: bool,
    expected_show_block: bool,
) -> None:
    state = build_project_import_execution_gate_state(
        validation_report=validation_report,
        dry_run_plan=dry_run_plan,
        confirmation_checked=confirmation_checked,
    )

    expected_enabled = bool(validation_report["is_valid"] and dry_run_plan["is_plan_available"] and confirmation_checked)
    assert state["execution_available_in_this_build"] is True
    assert state["can_enable_create_action"] is expected_enabled
    assert (EXECUTION_DISABLED_REASON in state["disabled_reasons"]) is (not expected_enabled)
    assert state["can_show_gated_block"] is expected_show_block


def test_gating_helper_only_shows_gated_block_for_valid_package_with_dry_run_plan() -> None:
    for package_valid in [False, True]:
        for dry_run_available in [False, True]:
            state = build_project_import_execution_gate_state(
                validation_report={"is_valid": package_valid},
                dry_run_plan={"is_plan_available": dry_run_available},
                confirmation_checked=True,
            )

            assert state["can_show_gated_block"] is (package_valid and dry_run_available)
            assert state["can_enable_create_action"] is (package_valid and dry_run_available)


def test_ui_skeleton_and_gate_helper_have_no_hidden_write_path() -> None:
    sources = {
        PATHWAY_WORKSPACE: _import_preview_source(),
        GATE_SERVICE: _gate_service_source(),
    }

    violations: list[str] = []
    for path, source in sources.items():
        scrubbed_source = _without_allowed_safety_copy(source).lower()
        for term in HIDDEN_WRITE_PATH_FORBIDDEN_TERMS:
            if term.lower() in scrubbed_source:
                violations.append(f"{path.relative_to(ROOT)} contains {term!r}")

    assert violations == []


def test_existing_project_import_package_preview_remains_read_only() -> None:
    source = _import_preview_source()
    lower_source = source.lower()

    missing = [term for term in REQUIRED_PREVIEW_COPY if term.lower() not in lower_source]

    assert missing == []


def test_no_dangerous_positive_claims_in_ui_skeleton_or_gate_helper() -> None:
    scrubbed_source = _without_allowed_safety_copy(_combined_skeleton_source()).lower()

    present = [claim for claim in DANGEROUS_POSITIVE_CLAIMS if claim in scrubbed_source]

    assert present == []
