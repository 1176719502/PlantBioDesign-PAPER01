from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DOC = ROOT / "docs" / "import_execution_readiness_architecture_audit_v1_13_0.md"
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
THIS_TEST = Path(__file__).resolve()

UI_AND_HELPER_FILES = [
    ROOT / "views" / "PathwayWorkspace.py",
    ROOT / "services" / "project_import_execution_gate_service.py",
    ROOT / "services" / "project_import_execution_result_presenter.py",
    ROOT / "services" / "project_import_final_confirmation_gate_service.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_audit_document_exists() -> None:
    assert AUDIT_DOC.exists()


def test_required_sections_exist() -> None:
    text = _read(AUDIT_DOC)
    required_sections = [
        "Executive summary",
        "Current safe baseline",
        "Future import execution risk map",
        "Required architecture before implementation",
        "Required test matrix before implementation",
        "User-facing copy requirements",
        "GO / NO-GO checklist",
        "V1.13 implementation recommendation",
    ]

    assert not [section for section in required_sections if section not in text]


def test_no_go_conclusion_exists() -> None:
    text = _read(AUDIT_DOC)
    required_copy = [
        "V1.13.0 is an architecture audit only.",
        "Real import execution remains disabled / NO-GO.",
        "This document does not approve implementation.",
        "Current status: NO-GO for real import execution.",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_current_baseline_safety_copy_exists() -> None:
    text = _read(AUDIT_DOC)
    required_copy = [
        "read-only validation",
        "dry-run import plan",
        "no database writes by preview",
        "no project creation by preview",
        "no overwrite",
        "no merge",
        "no raw payload_json restoration",
        "execution disabled in this build",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_risk_map_coverage_exists() -> None:
    text = _read(AUDIT_DOC)
    required_risks = [
        "database mutation risk",
        "partial import failure risk",
        "duplicate project risk",
        "stale package / schema mismatch risk",
        "artifact linkage risk",
        "raw payload restoration risk",
        "rollback / recovery risk",
        "audit log risk",
        "user confusion risk",
        "boundary copy risk",
    ]

    assert not [risk for risk in required_risks if risk not in text]


def test_required_architecture_checklist_exists() -> None:
    text = _read(AUDIT_DOC)
    required_items = [
        "transaction or rollback strategy",
        "idempotency / duplicate prevention strategy",
        "audit log record",
        "post-import verification report",
        "user-visible recovery path",
        "final confirmation gate",
        "package schema compatibility check",
        "safe handling of linked documentation artifacts",
    ]

    assert not [item for item in required_items if item not in text]


def test_test_matrix_coverage_exists() -> None:
    text = _read(AUDIT_DOC)
    required_tests = [
        "transaction/rollback tests",
        "duplicate import tests",
        "stale package tests",
        "malformed package tests",
        "linked artifact tests",
        "audit log tests",
        "UI confirmation gate tests",
        "no database write tests for preview",
    ]

    assert not [test_name for test_name in required_tests if test_name not in text]


def test_import_safety_still_locked_in_ui() -> None:
    ui_source = _read(PATHWAY_WORKSPACE)
    forbidden_ui_terms = [
        "enable_database_write=True",
        "execute_project_import_as_new_project",
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready for execution",
    ]

    assert not [term for term in forbidden_ui_terms if term in ui_source]


def test_forbidden_database_execution_calls_absent_from_audit_document() -> None:
    audit_source = _read(AUDIT_DOC)
    forbidden_fragments = [
        "enable_database_write" + "=True",
        "execute_project_import" + "_as_new_project",
    ]

    assert not [fragment for fragment in forbidden_fragments if fragment in audit_source]


def test_forbidden_positive_misleading_claims_absent_from_ui_files() -> None:
    forbidden_claims = [
        "successful import",
        "validated import",
        "experiment-ready package",
        "production-ready package",
        "validated project",
        "optimized pathway",
        "yield prediction result",
        "wet-lab protocol generated",
    ]
    offenders: dict[str, list[str]] = {}

    for path in UI_AND_HELPER_FILES:
        if not path.exists():
            continue
        source = _read(path)
        found = [claim for claim in forbidden_claims if claim in source]
        if found:
            offenders[str(path.relative_to(ROOT))] = found

    assert offenders == {}
