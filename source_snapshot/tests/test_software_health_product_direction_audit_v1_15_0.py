from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DOC = ROOT / "docs" / "software_health_product_direction_audit_v1_15_0.md"
TEST_FILE = ROOT / "tests" / "test_software_health_product_direction_audit_v1_15_0.py"


def _audit_text() -> str:
    return AUDIT_DOC.read_text(encoding="utf-8")


def test_v1_15_0_audit_document_exists() -> None:
    assert AUDIT_DOC.exists()


def test_v1_15_0_audit_document_required_sections_exist() -> None:
    text = _audit_text()
    required_sections = [
        "Executive summary",
        "Current MVP health",
        "Main workflow risk review",
        "State management risk review",
        "SQLite and persistence risk review",
        "Heavy file maintainability review",
        "Test coverage review",
        "Product direction recommendation",
        "Recommended roadmap",
        "GO / NO-GO summary",
    ]
    for section in required_sections:
        assert section in text


def test_v1_15_0_audit_current_health_conclusions_exist() -> None:
    text = _audit_text()
    required_phrases = [
        "Current software health: MVP usable with known stability risks.",
        "Expression Wizard",
        "DesignSession",
        "Saved design immutable ID",
        "Import Package Safety Check Report",
        "read-only safety checks",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_v1_15_0_audit_risk_review_coverage_exists() -> None:
    text = _audit_text()
    required_phrases = [
        "st.session_state",
        "bare string session keys",
        "SK.ACTIVE_",
        "widget state",
        "transient task state",
        "SQLite",
        "project_history",
        "sequences",
        "services/design_saver.py",
        "services/pathway_repository.py",
        "views/PathwayWorkspace.py",
        "views/wizard_steps/step4_cloning_primers.py",
        "views/wizard_steps/step6_export.py",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_v1_15_0_audit_product_direction_is_explicit() -> None:
    text = _audit_text()
    required_phrases = [
        "local BioDesign project workspace",
        "documentation",
        "traceability",
        "read-only safety checks",
        "review reports",
        "project quality management",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_v1_15_0_audit_non_recommended_directions_are_explicit() -> None:
    text = _audit_text()
    required_phrases = [
        "automated wet-lab protocol platform",
        "yield prediction tool",
        "autonomous pathway optimizer",
        "one-click experimental readiness certifier",
        "real import execution before rollback/audit/idempotency implementation",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_v1_15_0_audit_roadmap_exists() -> None:
    text = _audit_text()
    required_phrases = [
        "V1.15.1 Main Workflow Manual UI Smoke Checklist",
        "V1.15.2 Project Review Report MVP",
        "V1.15.3 Project Quality Dashboard MVP",
        "V1.15.4 PathwayWorkspace Decomposition Plan",
        "V1.16.0 Repository Boundary Stabilization",
        "V1.17.0 Controlled Import Execution only if prerequisites are met",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_v1_15_0_audit_go_no_go_summary_exists() -> None:
    text = _audit_text()
    required_phrases = [
        "Real import execution: NO-GO.",
        "Major new biological capability expansion: NO-GO until core workflow stability improves.",
        "Project review/reporting features: GO.",
        "Project quality dashboard: GO.",
        "Large DB migration: NO-GO until repository boundary audit is complete.",
        "Wet-lab protocol generation: NO-GO.",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_v1_15_0_audit_changes_do_not_enable_import_execution() -> None:
    combined_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (AUDIT_DOC, TEST_FILE)
    )
    forbidden_phrases = [
        "enable_database_write" + "=True",
        "execute_project_import" + "_as_new_project",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined_text
