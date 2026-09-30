from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN_DOC = ROOT / "docs" / "import_execution_duplicate_stale_package_safety_tests_v1_13_3.md"
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
THIS_TEST = Path(__file__).resolve()
THIS_TEST_AND_DOCS = (DESIGN_DOC, THIS_TEST)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_duplicate_stale_package_safety_design_document_exists() -> None:
    assert DESIGN_DOC.exists()


def test_required_sections_exist() -> None:
    text = _read(DESIGN_DOC)
    required_sections = [
        "Executive summary",
        "Baseline from V1.13.0 to V1.13.2",
        "Duplicate import safety scenarios",
        "Stale package safety scenarios",
        "Schema mismatch safety scenarios",
        "Repeated confirmation click protection",
        "Idempotent retry after rollback",
        "Package identity and fingerprint test contract",
        "Expected failure report copy",
        "Required automated test matrix before implementation",
        "Non-goals",
        "GO / NO-GO checklist",
    ]

    assert not [section for section in required_sections if section not in text]


def test_no_go_conclusion_exists() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "V1.13.3 is a safety test design document only.",
        "Real import execution remains disabled / NO-GO.",
        "No duplicate detection implementation is added in this milestone.",
        "No stale package rejection implementation is added in this milestone.",
        "No schema mismatch enforcement implementation is added in this milestone.",
        "No database writes are introduced.",
        "Current status: NO-GO for real import execution.",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_duplicate_safety_scenarios_exist() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "same package imported twice",
        "same package retried after rollback",
        "same project identity already exists",
        "same package fingerprint with different file name",
        "repeated user action from double click",
        "repeated browser refresh submission",
        "concurrent import attempt with same package fingerprint",
        "duplicate prevention key collision handling",
        "tests must prevent duplicate project creation",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_stale_package_scenarios_exist() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "package generated from older application version",
        "package generated before current schema compatibility level",
        "package missing required manifest metadata",
        "package with stale project snapshot timestamp",
        "package with stale linked artifact references",
        "unsupported exporter version",
        "future unsupported package version",
        "stale package rejection must not mutate database",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_schema_mismatch_scenarios_exist() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "manifest schema version mismatch",
        "missing required manifest fields",
        "incompatible pathway step structure",
        "incompatible linked documentation artifact structure",
        "incompatible review record structure",
        "corrupted package manifest",
        "invalid package checksum or integrity hash",
        "schema mismatch must fail before mutation",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_repeated_click_and_retry_content_exists() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "single-use confirmation token",
        "token already used",
        "token expired",
        "token mismatched with preflight snapshot",
        "repeated click while transaction is in progress",
        "browser refresh after confirmation",
        "confirmation token replay attack",
        "retry after completed rollback",
        "retry after rollback failure requiring manual review",
        "retry after linked artifact failure",
        "failed rollback requires manual review before retry",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_package_identity_contract_exists() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "package fingerprint",
        "duplicate prevention key",
        "package schema version",
        "exporter version",
        "manifest integrity hash",
        "source project id",
        "source project name",
        "package created timestamp",
        "linked artifact ids",
        "preflight summary hash",
        "final confirmation token id",
        "import attempt id",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_failure_report_and_non_goals_exist() -> None:
    text = _read(DESIGN_DOC)
    required_copy = [
        "safe_user_summary",
        "failed safety check",
        "what_was_not_changed",
        "retry guidance",
        "support diagnostic reference",
        "no raw stack trace",
        "no raw payload_json display",
        "no claim of successful import",
        "no claim of validated import",
        "no real import execution",
        "no duplicate detection implementation",
        "no stale package rejection implementation",
        "no schema mismatch enforcement implementation",
        "no database write implementation",
        "no UI execution button",
        "no overwrite",
        "no merge",
        "no biological validation",
        "no experimental readiness certification",
        "no yield prediction",
        "no pathway optimization",
        "no wet-lab protocols",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_ui_safety_still_locked_while_design_can_name_forbidden_terms() -> None:
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
