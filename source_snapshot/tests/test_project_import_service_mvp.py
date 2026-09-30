from __future__ import annotations

import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_export_package_service import build_project_export_payload, build_project_export_zip
from services.project_import_service import execute_project_import_as_new_project
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path

ROOT_PATH = Path(ROOT)
SERVICE_FILE = ROOT_PATH / "services" / "project_import_service.py"
PATHWAY_WORKSPACE = ROOT_PATH / "views" / "PathwayWorkspace.py"


def _payload(project_name: str = "MVP Import Source") -> dict[str, Any]:
    return build_project_export_payload(
        project={
            "id": 101,
            "name": project_name,
            "target_product": "Demo product",
            "host": "Demo host",
            "status": "draft",
            "description": "MVP import fixture.",
        },
        steps=[
            {
                "id": 201,
                "project_id": 101,
                "step_order": 1,
                "step_name": "Recorded step",
                "reaction_name": "A to B",
                "substrate": "A",
                "product": "B",
                "enzyme_name": "Demo enzyme",
                "gene_name": "demo_gene",
                "gene_sequence": "ATGAAATAA",
                "notes": "source note",
            }
        ],
        expression_links=[{"id": 301, "step_id": 201, "design_id": 401, "design_name": "Design reference"}],
        test_records=[{"id": 501, "step_id": None, "sample_name": "Project observation", "yield_value": "not promoted"}],
        completeness_result={"score": 95, "status": "complete", "missing_items": [], "step_summaries": []},
        review_signals=[{"related_step_id": 201, "signal_type": "review"}],
        linked_tool_artifacts=[
            {
                "id": 601,
                "created_at": "2026-06-02T10:00:00",
                "artifact_type": "lab_tools_sequence_export_preview",
                "source_module": "Lab Tools",
                "title": "Sequence Preview",
                "summary": "Documentation sequence summary",
                "boundary_label": "Documentation artifact / computational preview record only.",
                "project_id": 101,
                "payload_json": {"sequence_count": 1, "developer_only": "must not restore raw payload"},
            }
        ],
        documentation_report="# Documentation report\nNo readiness claims.\n",
        exported_at="2026-06-02T10:00:00",
    )


def _valid_zip_bytes(project_name: str = "MVP Import Source") -> bytes:
    return build_project_export_zip(_payload(project_name))


def _zip_with_removed_file(filename: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(BytesIO(_valid_zip_bytes()), "r") as source, zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for name in source.namelist():
            if name != filename:
                target.writestr(name, source.read(name))
    return buffer.getvalue()


def _use_tmp_db(monkeypatch: Any) -> Path:
    db_path = repo_local_sqlite_db_path(".pytest_tmp_r82_import_service_dbs", "import_mvp.sqlite")
    import services.pathway_repository as pathway_repository
    import services.tool_artifact_service as tool_artifact_service

    monkeypatch.setattr(pathway_repository, "DB_PATH", str(db_path))
    monkeypatch.setattr(tool_artifact_service, "DB_PATH", str(db_path))
    return db_path


def test_default_execute_remains_not_executed() -> None:
    result = execute_project_import_as_new_project(_valid_zip_bytes())

    assert result["executed"] is False
    assert result["database_writes_performed"] is False
    assert result["execution_status"] in ["not_implemented", "write_disabled", "rejected"]
    assert result["created_project_id"] is None


def test_valid_package_imports_as_new_project_only_when_enabled(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=True)

    assert result["executed"] is True
    assert result["created_project_id"] is not None
    assert result["created_counts"]["project"] == 1
    assert result["imported_project_name"].startswith("Imported -")
    assert result["database_writes_performed"] is True


def test_invalid_package_rejected_without_database_writes(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)

    result = execute_project_import_as_new_project(_zip_with_removed_file("README_BOUNDARY.txt"), enable_database_write=True)

    assert result["executed"] is False
    assert result["database_writes_performed"] is False
    assert result["created_project_id"] is None
    assert result["execution_status"] == "rejected"


def test_duplicate_project_name_creates_distinct_import_without_overwrite(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)

    first = execute_project_import_as_new_project(_valid_zip_bytes("Duplicate Source"), enable_database_write=True)
    second = execute_project_import_as_new_project(_valid_zip_bytes("Duplicate Source"), enable_database_write=True)

    assert first["created_project_id"] != second["created_project_id"]
    assert first["imported_project_name"] == "Imported - Duplicate Source"
    assert second["imported_project_name"] == "Imported - Duplicate Source (2)"


def test_linked_tool_artifacts_imported_as_sanitized_summaries_only(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.tool_artifact_service as tool_artifact_service

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=True)
    artifacts = tool_artifact_service.list_tool_artifacts(project_id=result["created_project_id"])

    assert result["created_counts"]["linked_tool_artifact_summaries"] == 1
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact["project_id"] == result["created_project_id"]
    assert artifact["source_module"] == "Lab Tools"
    assert artifact["artifact_type"] == "lab_tools_sequence_export_preview"
    assert artifact["payload_json"]["raw_payload_restored"] is False
    assert "payload_json" not in artifact["payload_json"]
    assert "readable_payload_summary" in artifact["payload_json"]
    assert "boundary_label" in artifact["payload_json"]


def test_imported_pathway_steps_are_remapped_and_documentation_only(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.pathway_repository as pathway_repository

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=True)
    steps = pathway_repository.list_pathway_steps(result["created_project_id"])

    assert result["created_counts"]["pathway_steps"] == 1
    assert len(steps) == 1
    assert steps[0]["id"] != 201
    assert steps[0]["project_id"] == result["created_project_id"]
    assert "documentation-only" in steps[0]["notes"].lower()
    assert result["id_remapping_summary"]["pathway_step_ids"]["201"] == steps[0]["id"]


def test_test_record_summaries_do_not_boost_readiness_or_evidence(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.pathway_repository as pathway_repository

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=True)
    test_records = pathway_repository.list_pathway_test_records(result["created_project_id"])
    snapshots = pathway_repository.list_pathway_documentation_snapshots(result["created_project_id"])

    assert result["created_counts"]["test_record_summaries"] == 1
    assert test_records == []
    assert snapshots[0]["snapshot_payload"]["readiness_or_evidence_boosted"] is False


def test_import_audit_summary_created_with_required_boundary(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.pathway_repository as pathway_repository

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=True)
    snapshots = pathway_repository.list_pathway_documentation_snapshots(result["created_project_id"])
    boundary = result["boundary_statement"].lower()

    assert result["created_counts"]["documentation_snapshots"] == 1
    assert snapshots
    assert result["source_project_name"] == "MVP Import Source"
    assert result["imported_project_name"] == "Imported - MVP Import Source"
    for phrase in [
        "documentation-only",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
        "imported linked artifacts remain computational previews / review records only",
    ]:
        assert phrase in boundary


def test_static_approved_write_api_guard() -> None:
    source = SERVICE_FILE.read_text(encoding="utf-8").lower()
    forbidden_terms = [
        "update_project",
        "delete_project",
        "merge",
        "overwrite",
        "insert(",
        "update(",
        "delete(",
        "commit(",
        "executemany(",
        "sqlite",
    ]

    assert "create_pathway_project" in source
    assert "create_pathway_step" in source
    assert "create_tool_artifact" in source
    assert "create_pathway_documentation_snapshot" in source
    assert not [term for term in forbidden_terms if term in source]


def test_ui_remains_unchanged_without_import_controls() -> None:
    source = PATHWAY_WORKSPACE.read_text(encoding="utf-8")
    forbidden_controls = [
        "Import Project",
        "Create Imported Project",
        "Confirm Import",
        "Execute Import",
        "Merge Project",
        "Overwrite Project",
    ]

    assert not [control for control in forbidden_controls if control in source]
