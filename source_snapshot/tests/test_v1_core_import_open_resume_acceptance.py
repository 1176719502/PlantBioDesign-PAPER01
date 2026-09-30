from __future__ import annotations

import os
import sys
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_export_package_service import build_project_export_payload, build_project_export_zip
from services.project_import_dry_run_planner import build_project_import_dry_run_plan
from services.project_import_package_validator import validate_project_import_package
from services.project_import_service import execute_project_import_as_new_project
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


FORBIDDEN_COPY = [
    "successful import",
    "project imported",
    "ready for execution",
    "experiment-ready",
    "production-ready",
    "validated construct",
    "optimized pathway",
    "yield prediction",
]


def _use_temp_database(monkeypatch: Any) -> None:
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_import_service_dbs",
        "v1_core_import_open_resume_acceptance.sqlite",
    )
    import services.pathway_repository as pathway_repository
    import services.tool_artifact_service as tool_artifact_service

    monkeypatch.setattr(pathway_repository, "DB_PATH", str(db_path))
    monkeypatch.setattr(tool_artifact_service, "DB_PATH", str(db_path))


def _valid_project_export_package_zip(project_name: str = "V1 Core Acceptance Source") -> bytes:
    payload = build_project_export_payload(
        project={
            "id": 91001,
            "name": project_name,
            "target_product": "Acceptance documentation target",
            "host": "Acceptance documentation host",
            "status": "draft",
            "description": "V1 core acceptance fixture for import/open/resume coverage.",
        },
        steps=[
            {
                "id": 91011,
                "project_id": 91001,
                "step_order": 1,
                "step_name": "Acceptance documentation step",
                "reaction_name": "Acceptance review conversion",
                "substrate": "Acceptance substrate",
                "product": "Acceptance product",
                "enzyme_name": "Acceptance enzyme",
                "gene_name": "acceptance_gene",
                "gene_sequence": "ATGAAATAA",
                "organism_source": "Acceptance organism",
                "notes": "Source note remains documentation-only.",
            }
        ],
        expression_links=[
            {
                "id": 91021,
                "project_id": 91001,
                "step_id": 91011,
                "design_id": 91031,
                "design_name": "Acceptance expression reference",
            }
        ],
        test_records=[
            {
                "id": 91041,
                "project_id": 91001,
                "step_id": None,
                "sample_name": "Acceptance review observation",
                "measured_product": "Acceptance product",
                "yield_value": "summary only",
                "notes": "Review summary only.",
            }
        ],
        completeness_result={"score": 20, "status": "review", "missing_items": ["review required"], "step_summaries": []},
        review_signals=[{"related_step_id": 91011, "signal_type": "review", "message": "Documentation review only."}],
        linked_tool_artifacts=[
            {
                "id": 91051,
                "created_at": "2026-06-09T10:00:00",
                "artifact_type": "lab_tools_sequence_export_preview",
                "source_module": "Lab Tools",
                "title": "Acceptance sequence preview",
                "summary": "Acceptance computational preview summary only.",
                "boundary_label": "Documentation artifact / computational preview record only.",
                "project_id": 91001,
                "payload_json": {"raw_detail": "must remain summarized"},
            }
        ],
        documentation_report="# Acceptance documentation report\nReview-only package fixture.\n",
        exported_at="2026-06-09T10:00:00",
    )
    payload["readme_boundary"] = payload["readme_boundary"].replace("wet-lab instructions", "wet-lab protocols")
    return build_project_export_zip(payload)


def test_duplicate_detector_does_not_match_same_source_project_name_only(monkeypatch: Any) -> None:
    _use_temp_database(monkeypatch)
    import views.pathway_workspace_sections.import_preview_section as import_preview_section

    first_package = _valid_project_export_package_zip(project_name="Same Name Demo")
    first_result = execute_project_import_as_new_project(first_package, enable_database_write=True)
    assert first_result["created_project_id"] is not None

    second_package = _valid_project_export_package_zip(project_name="Same Name Demo")
    second_validation_report = validate_project_import_package(second_package)
    second_dry_run_plan = build_project_import_dry_run_plan(second_package)
    second_dry_run_plan["source_project_id"] = "B"
    second_validation_report["source_project_id"] = "B"
    second_package_fingerprint = "different-package-fingerprint-for-source-project-b"

    existing = import_preview_section._find_existing_documentation_project_from_same_package(
        second_dry_run_plan,
        second_validation_report,
        second_package_fingerprint,
    )

    assert second_dry_run_plan["source_project_name"] == "Same Name Demo"
    assert second_dry_run_plan["source_project_id"] == "B"
    assert second_package_fingerprint != build_project_import_dry_run_plan(first_package)["package_fingerprint"]
    assert existing is None


def test_v1_core_import_open_resume_acceptance(monkeypatch: Any) -> None:
    _use_temp_database(monkeypatch)
    import services.pathway_repository as pathway_repository
    import views.pathway_workspace_sections.import_preview_section as import_preview_section

    package = _valid_project_export_package_zip()
    validation_report = validate_project_import_package(package)
    dry_run_plan = build_project_import_dry_run_plan(package)

    assert validation_report["is_valid"] is True
    assert dry_run_plan["is_plan_available"] is True

    result = execute_project_import_as_new_project(package, enable_database_write=True)

    assert result["created_project_id"] is not None
    assert result["imported_project_name"] == "Imported - V1 Core Acceptance Source"
    assert result["created_counts"] == {
        "project": 1,
        "pathway_steps": 1,
        "linked_tool_artifact_summaries": 1,
        "test_record_summaries": 1,
        "documentation_snapshots": 1,
    }

    created_project = pathway_repository.get_pathway_project(result["created_project_id"])
    assert created_project["id"] == result["created_project_id"]
    assert created_project["name"] == result["imported_project_name"]
    assert created_project["status"] == "draft"
    assert "documentation-only" in created_project["description"].lower()

    resume_payload = {
        "acceptance_marker": "manual documentation snapshot payload persists",
        "created_project_id": result["created_project_id"],
        "created_counts": result["created_counts"],
        "source_project_name": result["source_project_name"],
        "raw_payload_restored": False,
        "readiness_or_evidence_boosted": False,
    }
    snapshot_ok, snapshot_message, snapshot_id = pathway_repository.create_pathway_documentation_snapshot(
        project_id=result["created_project_id"],
        snapshot_title="V1 Core acceptance resume snapshot",
        snapshot_note="Acceptance test snapshot for open/resume persistence.",
        snapshot_payload=resume_payload,
        report_config={"source": "test_v1_core_import_open_resume_acceptance"},
        generated_markdown_text="Acceptance resume documentation snapshot.",
        include_generated_markdown=True,
        schema_version="v1_core_acceptance_test",
    )
    assert snapshot_ok is True, snapshot_message
    assert snapshot_id is not None

    snapshots = pathway_repository.list_pathway_documentation_snapshots(result["created_project_id"])
    persisted_snapshot = next(snapshot for snapshot in snapshots if snapshot["id"] == snapshot_id)
    assert persisted_snapshot["snapshot_payload"] == resume_payload

    existing = import_preview_section._find_existing_documentation_project_from_same_package(
        dry_run_plan,
        validation_report,
        dry_run_plan["package_fingerprint"],
    )
    assert existing is not None
    assert existing["project_id"] == result["created_project_id"]
    assert existing["project_name"] == result["imported_project_name"]
    assert existing["matched_source_project_id"] == "91001"
    assert existing["matched_source_project_name"] == "v1 core acceptance source"
    assert existing["match_reason"] == "import audit payload"

    override_result = execute_project_import_as_new_project(package, enable_database_write=True)
    assert override_result["created_project_id"] is not None
    assert override_result["created_project_id"] != result["created_project_id"]
    assert override_result["imported_project_name"] == "Imported - V1 Core Acceptance Source (2)"
    assert override_result["created_counts"]["project"] == 1

    rendered_result_copy = repr({"first_result": result, "override_result": override_result}).casefold()
    assert not [copy for copy in FORBIDDEN_COPY if copy in rendered_result_copy]
