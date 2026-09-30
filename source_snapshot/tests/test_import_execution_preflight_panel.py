from __future__ import annotations

from pathlib import Path
from typing import Any

from services.project_import_execution_gate_service import build_project_import_execution_gate_state

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
GATE_SERVICE = ROOT / "services" / "project_import_execution_gate_service.py"

REQUIRED_PREFLIGHT_COPY = [
    "Import Execution Preflight Review",
    "preflight review",
    "Execution creates a new documentation project only after explicit final confirmation.",
    "does not overwrite, merge, restore raw payload_json, or modify existing projects",
    "does not certify experimental readiness, predict yield, optimize pathways, or provide wet-lab protocols",
    "valid package required",
    "validator is_valid=True",
    "dry-run plan available",
    "dry-run plan does not write database",
    "import as new project only",
    "no overwrite",
    "no merge",
    "no raw payload_json restoration",
    "no original id restoration",
    "no executable content restoration",
    "documentation-only",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not provide wet-lab protocols",
    "computational previews",
    "review records only",
    "limited rollback note",
    "audit summary required before future execution",
    "explicit confirmation checkbox required before execution branch",
]

FORBIDDEN_EXECUTION_TERMS = [
    "create_project(",
    "insert_project",
    "update_project",
    "delete_project",
    "repository.write",
    "repo.write",
    "ProjectRepository",
]

FORBIDDEN_DANGEROUS_LABELS = [
    "Import Project",
    "Execute Import",
    "Confirm Import",
    "Import now",
    "Ready to import",
    "Ready for execution",
    "real import execution enabled",
    "successful import",
    "production-ready package",
    "experiment-ready package",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _combined_preflight_source() -> str:
    return f"{_read(PATHWAY_WORKSPACE)}\n{_read(GATE_SERVICE)}"


def _build_state(
    *,
    package_valid: bool,
    dry_run_available: bool,
    confirmation_checked: bool = False,
) -> dict[str, Any]:
    return build_project_import_execution_gate_state(
        validation_report={"is_valid": package_valid},
        dry_run_plan={"is_plan_available": dry_run_available},
        confirmation_checked=confirmation_checked,
    )


def test_preflight_copy_exists() -> None:
    source = _combined_preflight_source()

    missing = [term for term in REQUIRED_PREFLIGHT_COPY if term not in source]

    assert missing == []


def test_helper_blocks_preflight_for_invalid_package() -> None:
    state = _build_state(package_valid=False, dry_run_available=True, confirmation_checked=True)

    assert state["preflight_panel_available"] is False
    assert "valid package required" in state["preflight_blocking_reasons"]
    assert state["can_enable_create_action"] is False
    assert state["execution_available_in_this_build"] is True
    assert state["final_confirmation_required"] is True


def test_helper_blocks_preflight_for_missing_dry_run_plan() -> None:
    state = _build_state(package_valid=True, dry_run_available=False, confirmation_checked=True)

    assert state["preflight_panel_available"] is False
    assert "dry-run plan available" in state["preflight_blocking_reasons"]
    assert state["can_enable_create_action"] is False
    assert state["execution_available_in_this_build"] is True
    assert state["final_confirmation_required"] is True


def test_helper_shows_preflight_for_valid_package_with_dry_run_plan() -> None:
    state = _build_state(package_valid=True, dry_run_available=True, confirmation_checked=False)

    assert state["preflight_panel_available"] is True
    assert state["preflight_blocking_reasons"] == []
    assert state["preflight_items"]
    assert state["can_enable_create_action"] is False
    assert state["execution_available_in_this_build"] is True
    assert state["final_confirmation_required"] is True


def test_confirmation_enables_create_action_only_after_visible_gates_pass() -> None:
    unchecked = _build_state(package_valid=True, dry_run_available=True, confirmation_checked=False)
    checked = _build_state(package_valid=True, dry_run_available=True, confirmation_checked=True)

    assert unchecked["can_enable_create_action"] is False
    assert checked["can_enable_create_action"] is True
    assert unchecked["execution_available_in_this_build"] is True
    assert checked["execution_available_in_this_build"] is True


def test_no_execution_path_in_preflight_sources() -> None:
    sources = {
        PATHWAY_WORKSPACE: _read(PATHWAY_WORKSPACE),
        GATE_SERVICE: _read(GATE_SERVICE),
    }

    violations: list[str] = []
    for path, source in sources.items():
        for term in FORBIDDEN_EXECUTION_TERMS:
            if term in source:
                violations.append(f"{path.relative_to(ROOT)} contains {term!r}")

    assert violations == []


def test_dangerous_labels_absent() -> None:
    source = _combined_preflight_source()

    present = [label for label in FORBIDDEN_DANGEROUS_LABELS if label in source]

    assert present == []
