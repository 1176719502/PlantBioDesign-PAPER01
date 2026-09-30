from __future__ import annotations

import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_export_package_service import build_project_export_payload, build_project_export_zip
from services.project_import_dry_run_planner import build_project_import_dry_run_plan


SERVICE_FILE = Path(ROOT) / "services" / "project_import_dry_run_planner.py"
DESIGN_DOC = Path(ROOT) / "docs" / "project_import_package_design.md"


def _payload() -> dict:
    return build_project_export_payload(
        project={"id": 5, "name": "Terpene Pathway", "target_product": "Demo Product", "host": "E.coli", "status": "draft"},
        steps=[
            {"id": 10, "project_id": 5, "step_order": 1, "step_name": "First step", "gene_sequence": "ATGAAATAA"},
            {"id": 11, "project_id": 5, "step_order": 2, "step_name": "Second step", "gene_sequence": "ATGCCCTAA"},
        ],
        expression_links=[
            {"id": 100, "step_id": 10, "design_id": 77, "design_name": "Linked design A"},
            {"id": 101, "step_id": 11, "design_id": 78, "design_name": "Linked design B"},
        ],
        test_records=[
            {"id": 200, "step_id": 10, "sample_name": "Step observation"},
            {"id": 201, "step_id": None, "sample_name": "Project observation"},
        ],
        completeness_result={"score": 80, "status": "partial", "missing_items": [], "step_summaries": []},
        review_signals=[],
        linked_tool_artifacts=[
            {
                "created_at": "2026-06-02T10:00:00",
                "artifact_type": "protein_structure_analysis",
                "source_module": "Structure Analysis",
                "title": "Structure Preview",
                "summary": "Documentation preview summary",
                "boundary_label": "Documentation artifact / computational preview record only.",
                "project_id": 5,
                "payload_json": {"sequence_properties": {"length": 120}},
            },
            {
                "created_at": "2026-06-02T10:10:00",
                "artifact_type": "codon_analysis",
                "source_module": "Lab Tools",
                "title": "Codon Preview",
                "summary": "Documentation codon summary",
                "boundary_label": "Documentation artifact / computational preview record only.",
                "project_id": 5,
                "payload_json": {"gc_content": 0.5},
            },
        ],
        documentation_report="# Pathway Documentation Report\n",
        exported_at="2026-06-02T10:00:00",
    )


def _zip_with_removed_file(filename: str) -> bytes:
    base_zip = build_project_export_zip(_payload())
    buffer = BytesIO()
    with zipfile.ZipFile(BytesIO(base_zip), "r") as source, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            if name == filename:
                continue
            target.writestr(name, source.read(name))
    return buffer.getvalue()


def test_valid_export_zip_produces_available_dry_run_plan() -> None:
    plan = build_project_import_dry_run_plan(build_project_export_zip(_payload()))

    assert plan["is_plan_available"] is True
    assert plan["is_valid_package"] is True
    assert plan["proposed_project_name"].startswith("Imported - ")
    assert plan["import_mode"] == "import_as_new_project_only"
    assert plan["read_only"] is True
    assert plan["database_writes_performed"] is False


def test_counts_are_derived_from_package_contents() -> None:
    plan = build_project_import_dry_run_plan(build_project_export_zip(_payload()))

    assert plan["would_create"]["project"] == 1
    assert plan["would_create"]["pathway_steps"] == 2
    assert plan["would_create"]["linked_tool_artifact_summaries"] == 2
    assert plan["would_create"]["linked_expression_design_references"] == 2
    assert plan["would_create"]["test_record_summaries"] == 2


def test_invalid_package_does_not_produce_plan() -> None:
    plan = build_project_import_dry_run_plan(_zip_with_removed_file("manifest.json"))

    assert plan["is_plan_available"] is False
    assert plan["is_valid_package"] is False
    assert plan["errors"]
    assert plan["would_create"] == {}


def test_id_remapping_required_flags_all_true() -> None:
    plan = build_project_import_dry_run_plan(build_project_export_zip(_payload()))

    assert plan["id_remapping_required"]["project_id"] is True
    assert plan["id_remapping_required"]["pathway_step_ids"] is True
    assert plan["id_remapping_required"]["linked_tool_artifact_ids"] is True
    assert plan["id_remapping_required"]["test_record_ids"] is True


def test_plan_boundary_copy_contains_required_safety_language() -> None:
    plan = build_project_import_dry_run_plan(build_project_export_zip(_payload()))
    boundary = plan["boundary_statement"]

    assert "documentation-only" in boundary
    assert "does not certify experimental readiness" in boundary
    assert "does not predict yield" in boundary
    assert "does not optimize pathways" in boundary
    assert "does not provide wet-lab protocols" in boundary
    assert "computational previews" in boundary
    assert "review records only" in boundary


def test_no_raw_payload_restoration() -> None:
    plan = build_project_import_dry_run_plan(build_project_export_zip(_payload()))
    rendered = repr(plan)

    assert "payload_json" not in rendered
    assert "linked_tool_artifact_summaries" in plan["would_create"]
    assert "readable_payload_summary" not in rendered


def test_read_only_static_guard() -> None:
    source = SERVICE_FILE.read_text(encoding="utf-8")
    forbidden_terms = [
        "create_project",
        "update_project",
        "delete_project",
        "insert",
        "update",
        "delete",
        "commit",
        "sqlite",
    ]

    assert not [term for term in forbidden_terms if term in source]


def test_design_doc_includes_v17_dry_run_planner_notes() -> None:
    content = DESIGN_DOC.read_text(encoding="utf-8").lower()

    assert "v1.7 dry-run planner" in content
    assert "read-only" in content
    assert "does not execute import" in content
    assert "does not write database" in content
    assert "import as new project" in content
    assert "id remapping required" in content
    assert "no overwrite" in content
    assert "no merge" in content
