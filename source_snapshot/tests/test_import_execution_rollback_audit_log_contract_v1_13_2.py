from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DOC = ROOT / "docs" / "import_execution_rollback_audit_log_contract_v1_13_2.md"
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
THIS_TEST = Path(__file__).resolve()
THIS_TEST_AND_DOCS = (CONTRACT_DOC, THIS_TEST)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_rollback_audit_log_contract_document_exists() -> None:
    assert CONTRACT_DOC.exists()


def test_required_sections_exist() -> None:
    text = _read(CONTRACT_DOC)
    required_sections = [
        "Executive summary",
        "Baseline from V1.13.0 and V1.13.1",
        "Rollback record contract",
        "Audit log contract",
        "Failure recovery report contract",
        "User-visible vs developer-visible error separation",
        "Rollback status lifecycle",
        "Audit integrity and idempotency",
        "Non-goals",
        "Required test plan before implementation",
        "GO / NO-GO checklist",
    ]

    assert not [section for section in required_sections if section not in text]


def test_no_go_conclusion_exists() -> None:
    text = _read(CONTRACT_DOC)
    required_copy = [
        "V1.13.2 is a rollback and audit log contract only.",
        "Real import execution remains disabled / NO-GO.",
        "No rollback writer is implemented in this milestone.",
        "No audit log persistence is implemented in this milestone.",
        "No database writes are introduced.",
        "Current status: NO-GO for real import execution.",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_rollback_record_contract_fields_exist() -> None:
    text = _read(CONTRACT_DOC)
    required_fields = [
        "import_attempt_id",
        "package_fingerprint",
        "transaction_id",
        "failure_phase",
        "failure_reason_code",
        "user_visible_summary",
        "developer_diagnostic_detail",
        "affected_record_ids",
        "rollback_status",
        "recovery_report_id",
        "retry_allowed",
        "duplicate_prevention_key",
    ]

    assert not [field for field in required_fields if field not in text]


def test_audit_log_contract_fields_exist() -> None:
    text = _read(CONTRACT_DOC)
    required_fields = [
        "source_package_metadata",
        "selected_target_action",
        "preflight_summary_hash",
        "final_confirmation_token_id",
        "final_confirmation_timestamp",
        "actor_context",
        "mutation_phase_status",
        "execution_result_summary",
        "user_visible_report_id",
        "integrity_hash",
        "append-only",
    ]

    assert not [field for field in required_fields if field not in text]


def test_failure_recovery_report_content_exists() -> None:
    text = _read(CONTRACT_DOC)
    required_copy = [
        "safe_user_summary",
        "failed_phase",
        "what_was_not_changed",
        "retry_guidance",
        "support_diagnostic_reference",
        "report must avoid raw stack traces",
        "report must avoid raw payload_json display",
        "report must not certify or invalidate biological design",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_error_separation_content_exists() -> None:
    text = _read(CONTRACT_DOC)
    required_copy = [
        "user-visible summary",
        "developer diagnostic detail",
        "internal exception message",
        "raw payload reference",
        "support diagnostic reference",
        "users see safe summaries and recovery guidance",
        "developers may inspect diagnostics through controlled logs",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_rollback_lifecycle_content_exists() -> None:
    text = _read(CONTRACT_DOC)
    required_copy = [
        "not_started",
        "in_progress",
        "completed",
        "failed_requires_manual_review",
        "not_required_no_mutation_started",
        "failed rollback requires manual review before retry",
        "no partially visible imported project should exist without recovery status",
    ]

    assert not [copy for copy in required_copy if copy not in text]


def test_integrity_idempotency_and_non_goals_exist() -> None:
    text = _read(CONTRACT_DOC)
    required_copy = [
        "duplicate prevention key",
        "import attempt id",
        "transaction id",
        "integrity hash",
        "single-use confirmation token",
        "repeated click protection",
        "idempotent retry after rollback",
        "stale package rejection",
        "schema compatibility check",
        "no real import execution",
        "no rollback persistence implementation",
        "no audit log persistence implementation",
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

    assert not [copy for copy in required_copy if copy not in text]


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
