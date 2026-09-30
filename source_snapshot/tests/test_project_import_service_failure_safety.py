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


APPROVED_WRITE_APIS = [
    "create_pathway_project",
    "create_pathway_step",
    "create_tool_artifact",
    "create_pathway_documentation_snapshot",
]
BOUNDARY_PHRASES = [
    "documentation-only",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not provide wet-lab protocols",
]


def _payload(project_name: str = "Failure Safety Source") -> dict[str, Any]:
    return build_project_export_payload(
        project={
            "id": 101,
            "name": project_name,
            "target_product": "Demo product",
            "host": "Demo host",
            "status": "draft",
            "description": "Failure safety fixture.",
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
            }
        ],
        documentation_report="# Documentation report\nNo readiness claims.\n",
        exported_at="2026-06-02T10:00:00",
    )


def _valid_zip_bytes() -> bytes:
    return build_project_export_zip(_payload())


def _invalid_zip_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(BytesIO(_valid_zip_bytes()), "r") as source, zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for name in source.namelist():
            if name != "manifest.json":
                target.writestr(name, source.read(name))
    return buffer.getvalue()


def _use_tmp_db(monkeypatch: Any) -> None:
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_import_service_dbs",
        "import_failure_safety.sqlite",
    )
    import services.pathway_repository as pathway_repository
    import services.tool_artifact_service as tool_artifact_service

    monkeypatch.setattr(pathway_repository, "DB_PATH", str(db_path))
    monkeypatch.setattr(tool_artifact_service, "DB_PATH", str(db_path))


def _assert_not_completed_failure(result: dict[str, Any]) -> None:
    assert result["execution_status"] in ["failed", "partial_failure", "rejected"]
    assert result["execution_status"] != "completed"
    assert result["executed"] is False
    assert result["errors"]
    for phrase in BOUNDARY_PHRASES:
        assert phrase in result["boundary_statement"].lower()


def test_project_creation_failure_stops_before_downstream_writes(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.project_import_service as import_service

    calls = {"steps": 0, "artifacts": 0, "snapshots": 0}

    def fail_create_project(**_kwargs: Any) -> tuple[bool, str, None]:
        raise RuntimeError("project creation failed")

    monkeypatch.setattr(import_service, "create_pathway_project", fail_create_project)
    monkeypatch.setattr(import_service, "create_pathway_step", lambda **_kwargs: calls.__setitem__("steps", calls["steps"] + 1))
    monkeypatch.setattr(import_service, "create_tool_artifact", lambda **_kwargs: calls.__setitem__("artifacts", calls["artifacts"] + 1))
    monkeypatch.setattr(
        import_service,
        "create_pathway_documentation_snapshot",
        lambda **_kwargs: calls.__setitem__("snapshots", calls["snapshots"] + 1),
    )

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=True)

    assert result["execution_status"] in ["failed", "rejected"]
    assert result["executed"] is False
    assert result["created_project_id"] is None
    assert result["database_writes_performed"] is False
    assert result["errors"]
    assert result["created_counts"]["project"] == 0
    assert calls == {"steps": 0, "artifacts": 0, "snapshots": 0}


def test_pathway_step_creation_failure_reports_partial_without_completed(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.project_import_service as import_service

    def fail_create_step(**_kwargs: Any) -> tuple[bool, str, None]:
        raise RuntimeError("step creation failed")

    monkeypatch.setattr(import_service, "create_pathway_step", fail_create_step)

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=True)

    _assert_not_completed_failure(result)
    assert result["created_project_id"] is not None
    assert result["created_counts"]["project"] == 1
    assert result["created_counts"]["pathway_steps"] < 1
    assert "limited rollback" in "\n".join(result["warnings"]).lower()


def test_linked_tool_artifact_failure_reports_summary_failure_without_payload_restoration(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.project_import_service as import_service

    def fail_create_artifact(**_kwargs: Any) -> tuple[bool, str, None]:
        raise RuntimeError("artifact write failed")

    monkeypatch.setattr(import_service, "create_tool_artifact", fail_create_artifact)

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=True)
    rendered = repr(result).lower()

    _assert_not_completed_failure(result)
    assert "artifact summary failure" in "\n".join(result["warnings"]).lower()
    assert "limited rollback" in "\n".join(result["warnings"]).lower()
    assert "raw_payload_restored': true" not in rendered
    assert "payload_json" not in rendered


def test_documentation_snapshot_failure_reports_audit_failure_without_completed(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.project_import_service as import_service

    def fail_create_snapshot(**_kwargs: Any) -> tuple[bool, str, None]:
        raise RuntimeError("audit snapshot failed")

    monkeypatch.setattr(import_service, "create_pathway_documentation_snapshot", fail_create_snapshot)

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=True)

    _assert_not_completed_failure(result)
    assert result["created_counts"]["documentation_snapshots"] == 0
    assert "audit snapshot failure" in "\n".join(result["warnings"]).lower()


def test_invalid_package_rejects_before_any_approved_write(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.project_import_service as import_service

    calls: list[str] = []
    for api_name in APPROVED_WRITE_APIS:
        monkeypatch.setattr(import_service, api_name, lambda *args, _api_name=api_name, **kwargs: calls.append(_api_name))

    result = execute_project_import_as_new_project(_invalid_zip_bytes(), enable_database_write=True)

    assert result["executed"] is False
    assert result["execution_status"] == "rejected"
    assert result["database_writes_performed"] is False
    assert result["created_counts"] == {
        "project": 0,
        "pathway_steps": 0,
        "linked_tool_artifact_summaries": 0,
        "test_record_summaries": 0,
        "documentation_snapshots": 0,
    }
    assert result["errors"]
    assert calls == []


def test_write_disabled_path_never_calls_approved_write_apis(monkeypatch: Any) -> None:
    import services.project_import_service as import_service

    calls: list[str] = []
    for api_name in APPROVED_WRITE_APIS:
        monkeypatch.setattr(import_service, api_name, lambda *args, _api_name=api_name, **kwargs: calls.append(_api_name))

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=False)

    assert result["executed"] is False
    assert result["execution_status"] == "write_disabled"
    assert result["database_writes_performed"] is False
    assert calls == []


def test_failure_boundary_copy_does_not_boost_readiness_or_evidence(monkeypatch: Any) -> None:
    _use_tmp_db(monkeypatch)
    import services.project_import_service as import_service

    monkeypatch.setattr(import_service, "create_pathway_step", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("step failed")))

    result = execute_project_import_as_new_project(_valid_zip_bytes(), enable_database_write=True)
    boundary = result["boundary_statement"].lower()

    for phrase in BOUNDARY_PHRASES:
        assert phrase in boundary
    assert result["execution_status"] != "completed"


def test_static_service_guard_remains_valid_for_failure_safety_scope() -> None:
    service_source = SERVICE_FILE.read_text(encoding="utf-8").lower()
    ui_source = PATHWAY_WORKSPACE.read_text(encoding="utf-8")
    forbidden_service_terms = [
        "overwrite existing",
        "merge into existing",
        "update_project",
        "delete_project",
        "insert(",
        "update(",
        "delete(",
        "commit(",
        "executemany(",
        "sqlite",
        "raw payload restoration",
        "restore raw payload",
    ]
    forbidden_ui_controls = ["Import Project", "Create Imported Project", "Confirm Import", "Execute Import"]

    assert not [term for term in forbidden_service_terms if term in service_source]
    assert not [control for control in forbidden_ui_controls if control in ui_source]
