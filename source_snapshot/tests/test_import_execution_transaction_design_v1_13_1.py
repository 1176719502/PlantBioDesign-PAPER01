from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN_DOC = ROOT / "docs" / "import_execution_transaction_design_v1_13_1.md"
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
THIS_TEST = Path(__file__).resolve()
THIS_TEST_AND_DOCS = (DESIGN_DOC, THIS_TEST)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_transaction_design_document_exists() -> None:
    assert DESIGN_DOC.exists()


def test_required_sections_exist() -> None:
    text = _read(DESIGN_DOC)
    required_sections = [
        "Executive summary",
        "Baseline from V1.13.0",
        "Transaction boundary proposal",
        "Database mutation phases",
        "Rollback and recovery requirements",
        "Idempotency and duplicate prevention",
        "Audit log requirements",
        "Non-goals",
        "Required test plan before implementation",
        "GO / NO-GO checklist",
    ]

    assert not [section for section in required_sections if section not in text]


def test_no_go_conclusion_exists() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "V1.13.1 is a transaction design document only.",
        "Real import execution remains disabled / NO-GO.",
        "No execution service is implemented in this milestone.",
        "No database writes are introduced.",
        "Current status: NO-GO for real import execution.",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_transaction_boundary_content_exists() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "explicit execution service boundary",
        "single transaction boundary",
        "no UI direct database mutation",
        "no partial commit without recovery record",
        "final confirmation token",
        "execution result",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_mutation_phases_are_complete_and_not_implemented() -> None:
    text = _read(DESIGN_DOC)
    required_phases = [
        "phase 0: package validation already passed",
        "phase 1: execution preflight snapshot",
        "phase 2: duplicate/idempotency check",
        "phase 3: create pathway documentation project",
        "phase 4: create pathway steps / review records",
        "phase 5: link documentation artifacts safely",
        "phase 6: write audit log",
        "phase 7: post-import verification report",
        "phase 8: commit or rollback",
        "not implemented in V1.13.1",
    ]

    assert not [phase for phase in required_phases if phase not in text]


def test_rollback_and_recovery_content_exists() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "rollback on any write failure",
        "rollback on linked artifact failure",
        "rollback on audit log failure",
        "no partially visible imported project without recovery status",
        "recovery report",
        "retry safety after rollback",
        "no duplicate project creation on retry",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_idempotency_and_audit_content_exists() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "package fingerprint",
        "import attempt id",
        "duplicate import detection",
        "stale package rejection",
        "schema compatibility check",
        "repeated click protection",
        "confirmation token single-use design",
        "mutation phase status",
        "rollback status",
        "user-visible report id",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_non_goals_and_safety_boundary_exist() -> None:
    text = _read(DESIGN_DOC)
    required_non_goals = [
        "no real import execution",
        "no database write implementation",
        "no UI execution button",
        "no overwrite",
        "no merge",
        "no raw payload_json restoration",
        "no biological validation",
        "no experimental readiness certification",
        "no yield prediction",
        "no pathway optimization",
        "no wet-lab protocols",
    ]

    assert not [item for item in required_non_goals if item not in text]


def test_ui_safety_still_locked_while_docs_can_name_forbidden_terms() -> None:
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

    combined_design_text = "\n".join(_read(path) for path in THIS_TEST_AND_DOCS)
    assert "no real import execution" in combined_design_text
    assert "Current status: NO-GO for real import execution." in combined_design_text
