from __future__ import annotations

import json
import os
import sys
import zipfile
from io import BytesIO

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_export_package_service import (
    README_BOUNDARY_TEXT,
    build_project_export_contents_preview,
    build_project_export_filename,
    build_project_export_manifest,
    build_project_export_payload,
    build_project_export_zip,
)


def _project() -> dict:
    return {
        "id": 5,
        "name": "Terpene Pathway",
        "target_product": "Demo Product",
        "host": "E.coli",
        "status": "draft",
        "description": "Documentation package demo.",
    }


def _steps() -> list[dict]:
    return [
        {
            "id": 10,
            "project_id": 5,
            "step_order": 1,
            "step_name": "First step",
            "reaction_name": "Demo reaction",
            "gene_name": "demo_gene",
            "gene_sequence": "ATGAAACCCTAA",
        }
    ]


def _expression_links() -> list[dict]:
    return [{"id": 100, "step_id": 10, "design_id": 77, "design_name": "Linked design", "primer_risk_status": "low"}]


def _test_records() -> list[dict]:
    return [{"id": 200, "step_id": 10, "sample_name": "Observation"}, {"id": 201, "step_id": None, "sample_name": "Project note"}]


def _review_signals() -> list[dict]:
    return [{"signal_type": "missing_test_records", "priority": "info", "related_step_id": 10}]


def _completeness() -> dict:
    return {"score": 88, "status": "partial", "missing_items": ["one"], "step_summaries": []}


def _tool_artifacts() -> list[dict]:
    return [
        {
            "created_at": "2026-06-02T10:00:00",
            "artifact_type": "protein_structure_analysis",
            "source_module": "Structure Analysis",
            "title": "Structure Preview",
            "summary": "Documentation preview summary",
            "boundary_label": "Documentation artifact / computational preview record only.",
            "project_id": 5,
            "payload_json": {
                "artifact_type": "protein_structure_analysis",
                "sequence_properties": {"length": 120, "molecular_weight": 12345},
                "structure_source": {"source": "PDB", "pdb_id": "1ABC"},
                "huge_raw_field": "x" * 5000,
            },
        }
    ]


def test_export_manifest_contains_required_fields():
    manifest = build_project_export_manifest(_project(), exported_at="2026-06-02T10:00:00")

    required_fields = {
        "package_version",
        "exported_at",
        "app_context",
        "project_id",
        "project_name",
        "boundary_statement",
        "included_sections",
    }
    assert required_fields <= set(manifest)
    assert manifest["package_version"]
    assert manifest["exported_at"] == "2026-06-02T10:00:00"
    assert manifest["app_context"] == "Pathway Workspace Project Export Package"
    assert manifest["project_id"] == 5
    assert manifest["project_name"] == "Terpene Pathway"
    assert "does not certify experimental readiness" in manifest["boundary_statement"]
    assert manifest["included_sections"] == [
        "manifest.json",
        "project_summary.json",
        "pathway_steps.json",
        "test_records_summary.json",
        "linked_expression_designs.json",
        "linked_tool_artifacts.json",
        "documentation_report.md",
        "README_BOUNDARY.txt",
    ]


def test_export_payload_contains_expected_sections():
    payload = build_project_export_payload(
        project=_project(),
        steps=_steps(),
        expression_links=_expression_links(),
        test_records=_test_records(),
        completeness_result=_completeness(),
        review_signals=_review_signals(),
        linked_tool_artifacts=_tool_artifacts(),
        documentation_report="# Pathway Documentation Report\n",
        exported_at="2026-06-02T10:00:00",
    )

    assert payload["project_summary"]["project_name"] == "Terpene Pathway"
    assert payload["pathway_steps"][0]["sequence_recorded"] is True
    assert "linked_tool_artifacts" in payload
    assert payload["documentation_report"] == "# Pathway Documentation Report\n"
    assert "documentation-only" in payload["readme_boundary"]


def test_project_export_contents_preview_contains_expected_sections_and_artifact_count():
    preview = build_project_export_contents_preview(_tool_artifacts())

    assert preview["sections"] == [
        "Project summary",
        "Pathway steps",
        "Test records summary",
        "Linked expression designs",
        "Linked tool artifacts: 1",
        "Documentation report",
        "Boundary README",
    ]
    assert preview["linked_tool_artifacts_count"] == 1
    assert "documentation-only" in preview["boundary_summary"]
    assert "review and traceability only" in preview["boundary_summary"]


def test_project_export_contents_preview_shows_zero_linked_tool_artifacts():
    preview = build_project_export_contents_preview([])

    assert "Linked tool artifacts: 0" in preview["sections"]
    assert preview["linked_tool_artifacts_count"] == 0


def test_project_export_contents_preview_does_not_change_payload_or_zip_structure():
    kwargs = {
        "project": _project(),
        "steps": _steps(),
        "expression_links": _expression_links(),
        "test_records": _test_records(),
        "completeness_result": _completeness(),
        "review_signals": _review_signals(),
        "linked_tool_artifacts": _tool_artifacts(),
        "documentation_report": "# Report\n",
        "exported_at": "2026-06-02T10:00:00",
    }
    payload_before = build_project_export_payload(**kwargs)
    zip_before = build_project_export_zip(payload_before)

    preview = build_project_export_contents_preview(kwargs["linked_tool_artifacts"])
    payload_after = build_project_export_payload(**kwargs)
    zip_after = build_project_export_zip(payload_after)

    assert preview["linked_tool_artifacts_count"] == 1
    assert payload_after == payload_before
    assert zip_after == zip_before
    with zipfile.ZipFile(BytesIO(zip_after), "r") as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "project_summary.json",
            "pathway_steps.json",
            "test_records_summary.json",
            "linked_expression_designs.json",
            "linked_tool_artifacts.json",
            "documentation_report.md",
            "README_BOUNDARY.txt",
        }


def test_linked_tool_artifacts_export_uses_readable_payload_summary_without_raw_payload():
    payload = build_project_export_payload(
        project=_project(),
        steps=_steps(),
        expression_links=_expression_links(),
        test_records=_test_records(),
        completeness_result=_completeness(),
        review_signals=_review_signals(),
        linked_tool_artifacts=_tool_artifacts(),
        documentation_report="# Report\n",
    )

    artifact = payload["linked_tool_artifacts"]["linked_tool_artifacts"][0]
    artifact_dump = json.dumps(artifact)
    assert artifact["readable_payload_summary"]
    assert {item["label"] for item in artifact["readable_payload_summary"]} >= {"Sequence length", "Structure source", "PDB ID"}
    assert "payload_json" not in artifact
    assert "developer_payload_preview" not in artifact
    if "developer_payload_preview" in artifact:
        assert len(str(artifact["developer_payload_preview"])) <= 1000
    assert "huge_raw_field" not in artifact_dump
    assert "x" * 1000 not in artifact_dump
    assert len(artifact_dump) < 3000


def test_export_package_zip_contains_expected_files_valid_json_and_boundary_text():
    payload = build_project_export_payload(
        project=_project(),
        steps=_steps(),
        expression_links=_expression_links(),
        test_records=_test_records(),
        completeness_result=_completeness(),
        review_signals=_review_signals(),
        linked_tool_artifacts=_tool_artifacts(),
        documentation_report="# Report\n",
    )
    zip_bytes = build_project_export_zip(payload)

    expected_files = {
        "manifest.json",
        "project_summary.json",
        "pathway_steps.json",
        "test_records_summary.json",
        "linked_expression_designs.json",
        "linked_tool_artifacts.json",
        "documentation_report.md",
        "README_BOUNDARY.txt",
    }
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as archive:
        names = set(archive.namelist())
        assert names == expected_files
        parsed_json = {
            name: json.loads(archive.read(name).decode("utf-8"))
            for name in names
            if name.endswith(".json")
        }
        readme = archive.read("README_BOUNDARY.txt").decode("utf-8")

    assert set(parsed_json) == {name for name in expected_files if name.endswith(".json")}
    assert parsed_json["manifest.json"]["project_id"] == 5
    assert parsed_json["project_summary.json"]["completeness_score"] == 88
    assert parsed_json["linked_tool_artifacts.json"]["linked_tool_artifacts"][0]["readable_payload_summary"]
    for phrase in [
        "documentation-only",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
        "computational previews",
        "review records only",
    ]:
        assert phrase in readme
    assert readme == README_BOUNDARY_TEXT


def test_export_payload_does_not_change_completeness_evidence_or_review_signal_inputs():
    project = _project()
    steps = _steps()
    expression_links = _expression_links()
    test_records = _test_records()
    completeness = _completeness()
    review_signals = _review_signals()
    before = json.dumps([project, steps, expression_links, test_records, completeness, review_signals], sort_keys=True)

    payload = build_project_export_payload(
        project=project,
        steps=steps,
        expression_links=expression_links,
        test_records=test_records,
        completeness_result=completeness,
        review_signals=review_signals,
        linked_tool_artifacts=_tool_artifacts(),
        documentation_report="# Report\n",
    )

    after = json.dumps([project, steps, expression_links, test_records, completeness, review_signals], sort_keys=True)
    assert after == before
    assert payload["project_summary"]["completeness_score"] == completeness["score"]
    assert payload["project_summary"]["documentation_status"] == completeness["status"]
    assert payload["pathway_steps"][0]["step_id"] == steps[0]["id"]
    assert payload["pathway_steps"][0]["review_signal_count"] == len(review_signals)
    assert payload["test_records_summary"]["project_level_test_records_summary"]["count"] == 1
    assert payload["test_records_summary"]["step_associated_test_records_summary"]["count"] == 1


def test_project_export_filename_is_safe_and_semantic():
    filename = build_project_export_filename(
        {"name": "Terpene Project / Weird: Name!* with spaces"},
        exported_at="2026-06-02T10:00:00",
    )

    assert filename.startswith("pathway_project_export_terpene_project_weird_name_with_spaces_")
    assert filename.endswith(".zip")
    assert "project_export" in filename
    assert " " not in filename
    assert all(character.islower() or character.isdigit() or character in "_." for character in filename)
    assert not any(character in filename for character in r'<>:"/\\|?*')
