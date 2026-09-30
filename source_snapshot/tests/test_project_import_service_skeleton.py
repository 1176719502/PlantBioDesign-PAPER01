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
from services.project_import_service import execute_project_import_as_new_project, prepare_project_import

ROOT_PATH = Path(ROOT)
SERVICE_FILE = ROOT_PATH / "services" / "project_import_service.py"
PATHWAY_WORKSPACE = ROOT_PATH / "views" / "PathwayWorkspace.py"


def _payload() -> dict[str, Any]:
    return build_project_export_payload(
        project={
            "id": 51,
            "name": "Service Skeleton Project",
            "target_product": "Demo product",
            "host": "Demo host",
            "status": "draft",
            "description": "Import service skeleton fixture.",
        },
        steps=[
            {
                "id": 61,
                "project_id": 51,
                "step_order": 1,
                "step_name": "Recorded step",
                "reaction_name": "A to B",
                "substrate": "A",
                "product": "B",
                "enzyme_name": "Demo enzyme",
                "gene_name": "demo_gene",
                "gene_sequence": "ATGAAATAA",
            }
        ],
        expression_links=[{"id": 71, "step_id": 61, "design_id": 81, "design_name": "Design reference"}],
        test_records=[{"id": 91, "step_id": None, "sample_name": "Project observation"}],
        completeness_result={"score": 50, "status": "partial", "missing_items": [], "step_summaries": []},
        review_signals=[],
        linked_tool_artifacts=[
            {
                "created_at": "2026-06-02T10:00:00",
                "artifact_type": "codon_analysis",
                "source_module": "Lab Tools",
                "title": "Codon Preview",
                "summary": "Documentation codon summary",
                "boundary_label": "Documentation artifact / computational preview record only.",
                "project_id": 51,
                "payload_json": {"gc_content": 0.5},
            }
        ],
        documentation_report="# Documentation report\n",
        exported_at="2026-06-02T10:00:00",
    )


def _valid_zip_bytes() -> bytes:
    return build_project_export_zip(_payload())


def _zip_with_removed_file(filename: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(BytesIO(_valid_zip_bytes()), "r") as source, zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for name in source.namelist():
            if name != filename:
                target.writestr(name, source.read(name))
    return buffer.getvalue()


def test_prepare_project_import_with_valid_export_zip() -> None:
    result = prepare_project_import(_valid_zip_bytes())

    assert result["operation"] == "prepare_import"
    assert result["is_valid_package"] is True
    assert result["is_plan_available"] is True
    assert result["can_execute_import"] is False
    assert result["execution_status"] == "not_implemented"
    assert result["read_only"] is True
    assert result["database_writes_performed"] is False
    assert result["dry_run_plan"]
    assert result["dry_run_plan"]["is_plan_available"] is True


def test_prepare_project_import_with_invalid_zip() -> None:
    result = prepare_project_import(_zip_with_removed_file("manifest.json"))

    assert result["is_valid_package"] is False
    assert result["is_plan_available"] is False
    assert result["can_execute_import"] is False
    assert result["execution_status"] == "not_implemented"
    assert result["read_only"] is True
    assert result["database_writes_performed"] is False
    assert result["dry_run_plan"]["is_plan_available"] is False
    assert result["validation_report"]["errors"]


def test_execute_project_import_as_new_project_defaults_to_no_write() -> None:
    result = execute_project_import_as_new_project(_valid_zip_bytes())

    assert result["executed"] is False
    assert result["execution_status"] in {"not_implemented", "write_disabled", "rejected"}
    assert result["created_project_id"] is None
    assert result["read_only"] is True
    assert result["database_writes_performed"] is False
    assert result["created_counts"]["project"] == 0


def test_service_boundary_copy_safe() -> None:
    result = prepare_project_import(_valid_zip_bytes())
    boundary = result["boundary_statement"]

    for phrase in [
        "documentation-only",
        "read-only",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
        "computational previews",
        "review records only",
        "no database writes are performed",
        "real import is not implemented",
    ]:
        assert phrase in boundary.lower()


def test_static_write_guard_uses_only_approved_repository_apis() -> None:
    source = SERVICE_FILE.read_text(encoding="utf-8").lower()
    approved_terms = [
        "create_pathway_project",
        "create_pathway_step",
        "create_pathway_test_record",
        "create_tool_artifact",
        "create_pathway_documentation_snapshot",
    ]
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
    assert "create_pathway_test_record" not in source or "create_pathway_test_record" in approved_terms
    assert not [term for term in forbidden_terms if term in source]


def test_no_ui_import_controls() -> None:
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
