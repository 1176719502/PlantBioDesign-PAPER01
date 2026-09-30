from __future__ import annotations

from pathlib import Path

from services.project_import_execution_result_presenter import present_import_execution_result

ROOT = Path(__file__).resolve().parents[1]
PRESENTER = ROOT / "services" / "project_import_execution_result_presenter.py"


def _flatten_display_model(value: object) -> str:
    return str(value)


def test_success_output_contains_created_project_summary_and_audit() -> None:
    model = present_import_execution_result(
        {
            "execution_status": "success",
            "created_project_id": "proj-123",
            "imported_project_name": "Imported documentation project",
            "created_counts": {"linked_artifacts": 2, "review_records": 1},
            "audit_summary": {"dry_run_plan_id": "plan-1"},
        }
    )

    assert model["execution_status"] == "success"
    assert model["created_project_id"] == "proj-123"
    assert model["imported_project_name"] == "Imported documentation project"
    assert model["created_counts"] == {"linked_artifacts": 2, "review_records": 1}
    assert model["audit_summary"] == {"dry_run_plan_id": "plan-1"}


def test_failed_output_contains_errors_warnings_and_limited_rollback_note() -> None:
    model = present_import_execution_result(
        {
            "execution_status": "failed",
            "errors": ["write gate rejected"],
            "warnings": ["review dry-run plan"],
            "created_counts": {},
        }
    )

    assert model["execution_status"] == "failed"
    assert "write gate rejected" in model["errors"]
    assert "review dry-run plan" in model["warnings"]
    assert "limited rollback note" in model["limited_rollback_note"]


def test_partial_failure_output_contains_required_failure_and_audit_fields() -> None:
    model = present_import_execution_result(
        {
            "execution_status": "partial_failure",
            "errors": ["artifact import failed"],
            "warnings": ["some records were not created"],
            "created_counts": {"review_records": 3},
            "audit_summary": {"created_before_failure": True},
        }
    )

    assert model["execution_status"] == "partial_failure"
    assert "artifact import failed" in model["errors"]
    assert "some records were not created" in model["warnings"]
    assert model["created_counts"] == {"review_records": 3}
    assert "limited rollback note" in model["limited_rollback_note"]
    assert model["audit_summary"] == {"created_before_failure": True}


def test_blocked_preflight_output_contains_reasons_and_no_write_boundaries() -> None:
    model = present_import_execution_result(
        {
            "execution_status": "blocked_preflight",
            "blocking_reasons": ["valid package required", "dry-run plan available"],
        }
    )
    flattened = _flatten_display_model(model)

    assert model["execution_status"] == "blocked_preflight"
    assert "valid package required" in model["blocking_reasons"]
    assert "dry-run plan available" in model["blocking_reasons"]
    assert "No database writes are performed." in flattened
    assert "no project created" in flattened


def test_disabled_output_contains_disabled_message() -> None:
    model = present_import_execution_result({"execution_status": "disabled_in_this_build"})
    flattened = _flatten_display_model(model)

    assert model["execution_status"] == "disabled_in_this_build"
    assert "Execution remains disabled in this build." in flattened
    assert "No database writes are performed." in flattened
    assert "This preview does not import or modify any project." in flattened


def test_unknown_status_is_not_treated_as_success() -> None:
    model = present_import_execution_result({"execution_status": "unexpected_status"})

    assert model["execution_status"] != "success"
    assert model["execution_status"] in {"failed", "blocked_preflight"}


def test_all_supported_statuses_include_documentation_only_boundary() -> None:
    for status in ["success", "failed", "partial_failure", "blocked_preflight", "disabled_in_this_build"]:
        model = present_import_execution_result({"execution_status": status})

        assert "documentation-only" in model["documentation_only_boundary"]


def test_all_supported_statuses_include_no_readiness_or_evidence_boost_statement() -> None:
    for status in ["success", "failed", "partial_failure", "blocked_preflight", "disabled_in_this_build"]:
        model = present_import_execution_result({"execution_status": status})

        statement = model["no_readiness_or_evidence_boost_statement"]
        assert "no readiness boost" in statement
        assert "no evidence boost" in statement


def test_presenter_file_does_not_enable_database_writes_or_call_execution() -> None:
    source = PRESENTER.read_text(encoding="utf-8")

    assert "enable_database_write=True" not in source
    assert "execute_project_import_as_new_project" not in source


def test_presenter_file_does_not_import_repository_or_database() -> None:
    source = PRESENTER.read_text(encoding="utf-8")

    forbidden = [
        "import repository",
        "from repository",
        "import database",
        "from database",
        "ProjectRepository",
        "pathway_repository",
    ]

    assert [term for term in forbidden if term in source] == []
