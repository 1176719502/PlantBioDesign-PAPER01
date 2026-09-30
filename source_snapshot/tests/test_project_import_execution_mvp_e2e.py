from __future__ import annotations

import os
import sys
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_export_package_service import build_project_export_payload, build_project_export_zip
from services.project_import_dry_run_planner import build_project_import_dry_run_plan
from services.project_import_execution_gate_service import build_project_import_execution_gate_state
from services.project_import_execution_result_presenter import present_import_execution_result
from services.project_import_package_safety_checker import STATUS_BLOCKED, build_import_package_safety_check_report
from services.project_import_package_validator import validate_project_import_package
from services.project_import_service import execute_project_import_as_new_project
from tests.helpers.fake_streamlit import FakeStreamlit
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


def _payload(project_name: str = "Execution MVP Source") -> dict[str, Any]:
    return build_project_export_payload(
        project={
            "id": 1716,
            "name": project_name,
            "target_product": "Documentation target",
            "host": "Documentation host",
            "status": "draft",
            "description": "Execution MVP import fixture.",
        },
        steps=[
            {
                "id": 2716,
                "project_id": 1716,
                "step_order": 1,
                "step_name": "Recorded documentation step",
                "reaction_name": "Recorded conversion",
                "substrate": "Recorded substrate",
                "product": "Recorded product",
                "enzyme_name": "Recorded enzyme",
                "gene_name": "recorded_gene",
                "gene_sequence": "ATGAAATAA",
                "notes": "source documentation note",
            }
        ],
        expression_links=[{"id": 3716, "step_id": 2716, "design_id": 4716, "design_name": "Reference only"}],
        test_records=[{"id": 5716, "step_id": None, "sample_name": "Review observation", "yield_value": "not promoted"}],
        completeness_result={"score": 80, "status": "review", "missing_items": [], "step_summaries": []},
        review_signals=[{"related_step_id": 2716, "signal_type": "review"}],
        linked_tool_artifacts=[
            {
                "id": 6716,
                "created_at": "2026-06-06T10:00:00",
                "artifact_type": "lab_tools_sequence_export_preview",
                "source_module": "Lab Tools",
                "title": "Sequence Preview",
                "summary": "Documentation sequence summary only.",
                "boundary_label": "Documentation artifact / computational preview record only.",
                "project_id": 1716,
                "payload_json": {"raw_detail": "must not be restored"},
            }
        ],
        documentation_report="# Documentation report\nNo readiness claims.\n",
        exported_at="2026-06-06T10:00:00",
    )


def _zip_bytes(project_name: str = "Execution MVP Source") -> bytes:
    payload = _payload(project_name)
    payload["readme_boundary"] = payload["readme_boundary"].replace("wet-lab instructions", "wet-lab protocols")
    return build_project_export_zip(payload)


def _use_tmp_db(monkeypatch: Any) -> None:
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_import_service_dbs",
        "project_import_execution_mvp.sqlite",
    )
    import services.pathway_repository as pathway_repository
    import services.tool_artifact_service as tool_artifact_service

    monkeypatch.setattr(pathway_repository, "DB_PATH", str(db_path))
    monkeypatch.setattr(tool_artifact_service, "DB_PATH", str(db_path))


def test_project_import_execution_mvp_e2e_creates_openable_documentation_project(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.pathway_repository as pathway_repository

    package = _zip_bytes()
    validation_report = validate_project_import_package(package)
    safety_report = build_import_package_safety_check_report(package, local_project_reader=pathway_repository.list_pathway_projects)
    dry_run_plan = build_project_import_dry_run_plan(package)

    assert validation_report["is_valid"] is True
    assert safety_report["overall_status"] != STATUS_BLOCKED
    assert dry_run_plan["is_plan_available"] is True

    gate_before_confirmation = build_project_import_execution_gate_state(
        validation_report=validation_report,
        dry_run_plan=dry_run_plan,
        confirmation_checked=False,
    )
    assert gate_before_confirmation["can_enable_create_action"] is False

    gate_after_confirmation = build_project_import_execution_gate_state(
        validation_report=validation_report,
        dry_run_plan=dry_run_plan,
        confirmation_checked=True,
    )
    assert gate_after_confirmation["can_enable_create_action"] is True

    result = execute_project_import_as_new_project(package, enable_database_write=True)
    presented = present_import_execution_result({**result, "execution_status": "success" if result["execution_status"] == "completed" else result["execution_status"]})

    assert result["executed"] is True
    assert result["database_writes_performed"] is True
    assert result["created_project_id"] is not None
    assert result["created_counts"]["project"] == 1
    assert result["created_counts"]["pathway_steps"] == 1
    assert result["created_counts"]["documentation_snapshots"] == 1
    assert presented["execution_status"] == "success"
    assert presented["created_project_id"] == result["created_project_id"]

    created_project = pathway_repository.get_pathway_project(result["created_project_id"])
    listed_project_ids = {project["id"] for project in pathway_repository.list_pathway_projects()}
    steps = pathway_repository.list_pathway_steps(result["created_project_id"])

    assert created_project is not None
    assert created_project["id"] in listed_project_ids
    assert created_project["name"] == result["imported_project_name"]
    assert "documentation-only" in created_project["description"].lower()
    assert steps and steps[0]["project_id"] == result["created_project_id"]
    assert "documentation-only" in steps[0]["notes"].lower()

    rendered = repr({"result": result, "presented": presented}).lower()
    for forbidden in [
        "experiment-ready",
        "wet-lab success",
        "yield prediction result",
        "optimized pathway",
        "validated project",
        "readiness boost': true",
        "evidence boost': true",
    ]:
        assert forbidden not in rendered


def test_project_import_execution_mvp_rejects_without_final_confirmation() -> None:
    package = _zip_bytes("Unconfirmed Source")
    validation_report = validate_project_import_package(package)
    dry_run_plan = build_project_import_dry_run_plan(package)
    gate_state = build_project_import_execution_gate_state(
        validation_report=validation_report,
        dry_run_plan=dry_run_plan,
        confirmation_checked=False,
    )

    assert gate_state["can_enable_create_action"] is False
    assert "confirmation checkbox" in "\n".join(gate_state["disabled_reasons"]).lower()


def test_project_import_duplicate_detector_finds_existing_audit_payload(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.pathway_repository as pathway_repository
    import views.pathway_workspace_sections.import_preview_section as import_preview_section

    package = _zip_bytes("Duplicate Source")
    validation_report = validate_project_import_package(package)
    dry_run_plan = build_project_import_dry_run_plan(package)

    assert import_preview_section._find_existing_documentation_project_from_same_package(
        dry_run_plan,
        validation_report,
        dry_run_plan["package_fingerprint"],
    ) is None

    first_result = execute_project_import_as_new_project(package, enable_database_write=True)
    existing = import_preview_section._find_existing_documentation_project_from_same_package(
        dry_run_plan,
        validation_report,
        dry_run_plan["package_fingerprint"],
    )

    assert first_result["created_project_id"] is not None
    assert existing is not None
    assert existing["project_id"] == first_result["created_project_id"]
    assert existing["project_name"] == first_result["imported_project_name"]
    assert existing["matched_source_project_id"] == "1716"
    assert existing["matched_source_project_name"] == "duplicate source"
    assert existing["match_reason"] == "import audit payload"

    snapshots = pathway_repository.list_pathway_documentation_snapshots(first_result["created_project_id"])
    assert snapshots[0]["snapshot_payload"]["package_fingerprint"] == dry_run_plan["package_fingerprint"]


def test_project_import_duplicate_override_can_create_another_copy(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import views.pathway_workspace_sections.import_preview_section as import_preview_section

    package = _zip_bytes("Duplicate Override Source")
    validation_report = validate_project_import_package(package)
    dry_run_plan = build_project_import_dry_run_plan(package)

    first_result = execute_project_import_as_new_project(package, enable_database_write=True)
    assert first_result["created_project_id"] is not None
    existing = import_preview_section._find_existing_documentation_project_from_same_package(
        dry_run_plan,
        validation_report,
        dry_run_plan["package_fingerprint"],
    )
    assert existing is not None

    default_duplicate_gate = build_project_import_execution_gate_state(
        validation_report=validation_report,
        dry_run_plan=dry_run_plan,
        confirmation_checked=True,
    )
    default_duplicate_gate["can_enable_create_action"] = False
    default_duplicate_gate["disabled_reasons"] = [
        *list(default_duplicate_gate.get("disabled_reasons") or []),
        "A documentation-only project from this package appears to already exist; confirm another documentation-only copy before creation.",
    ]
    assert default_duplicate_gate["can_enable_create_action"] is False

    override_gate = build_project_import_execution_gate_state(
        validation_report=validation_report,
        dry_run_plan=dry_run_plan,
        confirmation_checked=True,
    )
    assert override_gate["can_enable_create_action"] is True
    second_result = execute_project_import_as_new_project(package, enable_database_write=True)

    assert second_result["created_project_id"] is not None
    assert second_result["created_project_id"] != first_result["created_project_id"]
    assert second_result["imported_project_name"].endswith("(2)")
    assert second_result["created_counts"]["project"] == 1


def test_blocked_no_go_state_never_calls_project_creation_or_writes(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.pathway_repository as pathway_repository
    import views.pathway_workspace_sections.import_preview_section as import_preview_section

    class UploadedZip:
        def getvalue(self) -> bytes:
            return _zip_bytes("Blocked Safety Source")

    fake_st = FakeStreamlit()
    fake_st.file_uploader_value = UploadedZip()
    fake_st.checkbox_values["project_import_create_new_documentation_project_confirmation"] = True
    fake_st.button_values["project_import_execute_create_new_documentation_project"] = True

    monkeypatch.setattr(import_preview_section, "st", fake_st)
    monkeypatch.setattr(import_preview_section, "build_import_package_safety_check_report", lambda *args, **kwargs: {"overall_status": STATUS_BLOCKED})

    called = {"count": 0}

    def _forbidden_create(*args: Any, **kwargs: Any) -> dict[str, Any]:
        called["count"] += 1
        raise AssertionError("blocked/no-go state must not execute project creation")

    monkeypatch.setattr(import_preview_section, "execute_project_import_as_new_project", _forbidden_create)

    import_preview_section.render_import_preview_section()

    assert called["count"] == 0
    assert fake_st.button_calls
    assert fake_st.button_calls[0]["disabled"] is True
    combined = "\n".join(fake_st.caption_messages + fake_st.error_messages)
    assert "Preview/review blocked for local documentation project creation." in combined
    assert "No database write was performed." in combined
    assert pathway_repository.list_pathway_projects() == []


def test_allowed_state_copy_is_explicitly_local_documentation_project_creation(monkeypatch: Any) -> None:
    import views.pathway_workspace_sections.import_preview_section as import_preview_section

    class UploadedZip:
        def getvalue(self) -> bytes:
            return _zip_bytes("Allowed Copy Source")

    fake_st = FakeStreamlit()
    fake_st.file_uploader_value = UploadedZip()
    fake_st.checkbox_values["project_import_create_new_documentation_project_confirmation"] = True

    monkeypatch.setattr(import_preview_section, "st", fake_st)

    import_preview_section.render_import_preview_section()

    combined = "\n".join(fake_st.caption_messages + fake_st.info_messages + fake_st.warning_messages)
    assert "Local documentation project creation allowed after explicit confirmation." in combined
    assert "This action can create a local documentation-only project from the reviewed package." in combined
    assert "It is not biological execution, validation, optimization, recommendation, or a wet-lab readiness judgment." in combined
    assert "Execution remains disabled in this build." not in combined
    assert "NO-GO" not in combined
