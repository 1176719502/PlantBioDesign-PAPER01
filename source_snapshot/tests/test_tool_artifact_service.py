import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import services.tool_artifact_service as artifact_service
from services.lab_tools_service import cloning_preview_summary, lab_preview_artifact_payload
from services.protein_structure_analysis_service import structure_analysis_artifact_payload


def _use_temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "tool_artifacts.db"
    monkeypatch.setattr(artifact_service, "DB_PATH", str(db_path))
    return db_path


def test_create_list_get_and_delete_tool_artifact(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    ok, message, artifact_id = artifact_service.create_tool_artifact(
        artifact_type="lab_tools_cloning_preview",
        title="Cloning Preview",
        source_module="Lab Tools",
        summary="Insert: 8 bp",
        payload_json={"preview_status": "ok"},
        boundary_label=artifact_service.TOOL_ARTIFACT_BOUNDARY_LABEL,
        notes="reviewed",
    )

    assert ok is True
    assert message == "Tool documentation artifact created."
    assert isinstance(artifact_id, int)

    rows = artifact_service.list_tool_artifacts()
    assert len(rows) == 1
    assert rows[0]["artifact_id"] == artifact_id
    assert rows[0]["artifact_type"] == "lab_tools_cloning_preview"
    assert rows[0]["payload_json"] == {"preview_status": "ok"}
    assert rows[0]["project_id"] is None
    assert rows[0]["boundary_label"] == artifact_service.TOOL_ARTIFACT_BOUNDARY_LABEL

    detail = artifact_service.get_tool_artifact(artifact_id)
    assert detail["title"] == "Cloning Preview"
    assert detail["project_id"] is None
    assert detail["notes"] == "reviewed"

    deleted, delete_message = artifact_service.delete_tool_artifact(artifact_id)
    assert deleted is True
    assert delete_message == "Tool documentation artifact deleted."
    assert artifact_service.get_tool_artifact(artifact_id) == {}


def test_invalid_and_empty_artifact_handling(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    assert artifact_service.create_tool_artifact(
        artifact_type="not_supported",
        title="Bad",
        source_module="Lab Tools",
        summary="Bad",
        payload_json={"x": 1},
    ) == (False, "Invalid artifact type.", None)

    ok, message, artifact_id = artifact_service.create_tool_artifact(
        artifact_type="lab_tools_pcr_preview",
        title="",
        source_module="Lab Tools",
        summary="PCR",
        payload_json={"x": 1},
    )
    assert (ok, message, artifact_id) == (False, "Artifact title is required.", None)

    ok, message, artifact_id = artifact_service.create_tool_artifact(
        artifact_type="lab_tools_pcr_preview",
        title="PCR",
        source_module="Lab Tools",
        summary="",
        payload_json={"x": 1},
    )
    assert (ok, message, artifact_id) == (False, "Artifact summary is required.", None)

    ok, message, artifact_id = artifact_service.create_tool_artifact(
        artifact_type="lab_tools_pcr_preview",
        title="PCR",
        source_module="Lab Tools",
        summary="PCR",
        payload_json={},
    )
    assert (ok, message, artifact_id) == (False, "Artifact payload is required.", None)
    assert artifact_service.list_tool_artifacts() == []
    assert artifact_service.get_tool_artifact("bad") == {}


def test_create_and_list_tool_artifacts_by_project_id(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    ok, _, linked_id = artifact_service.create_tool_artifact(
        artifact_type="lab_tools_pcr_preview",
        title="Linked PCR Preview",
        source_module="Lab Tools",
        summary="Linked summary",
        payload_json={"preview_status": "ok"},
        project_id=42,
    )
    assert ok is True
    ok, _, global_id = artifact_service.create_tool_artifact(
        artifact_type="protein_structure_analysis",
        title="Global Structure Preview",
        source_module="Structure Analysis",
        summary="Global summary",
        payload_json={"preview_status": "ok"},
    )
    assert ok is True

    linked_rows = artifact_service.list_tool_artifacts(project_id=42)
    assert [row["artifact_id"] for row in linked_rows] == [linked_id]
    assert linked_rows[0]["project_id"] == 42
    assert artifact_service.get_tool_artifact(linked_id)["project_id"] == 42
    assert artifact_service.get_tool_artifact(global_id)["project_id"] is None
    assert artifact_service.list_tool_artifacts(project_id=999) == []


def test_lab_tools_preview_artifact_payload_contains_boundary_and_summary():
    preview = cloning_preview_summary(
        insert_sequence="ATGCATGC",
        vector_name="pPreview",
        assembly_method="Gibson Assembly",
        insert_name="Reporter insert",
    )

    payload = lab_preview_artifact_payload(preview, preview_kind="cloning", inputs={"source": "test"})

    assert payload["artifact_type"] == "lab_tools_cloning_preview"
    assert payload["source_module"] == "Lab Tools"
    assert payload["summary"]["insert_length_bp"] == 8
    assert payload["inputs"] == {"source": "test"}
    assert payload["boundary_label"] == artifact_service.TOOL_ARTIFACT_BOUNDARY_LABEL
    assert "wet-lab protocols" in payload["boundary_copy"]


def test_structure_analysis_artifact_payload_contains_properties_source_and_boundary():
    payload = structure_analysis_artifact_payload(
        protein_sequence="ACDE",
        structure_source={"ok": "true", "source": "RCSB PDB", "pdb_id": "6LU7"},
    )

    assert payload["artifact_type"] == "protein_structure_analysis"
    assert payload["source_module"] == "Structure Analysis"
    assert payload["sequence_properties"]["ok"] is True
    assert payload["sequence_properties"]["length"] == 4
    assert payload["structure_source"]["pdb_id"] == "6LU7"
    assert payload["boundary_label"] == artifact_service.TOOL_ARTIFACT_BOUNDARY_LABEL
    assert "does not validate folding" in payload["boundary_copy"]


def test_artifact_type_and_source_module_filtering(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    records = (
        ("lab_tools_pcr_preview", "Lab Tools"),
        ("lab_tools_sequence_export_preview", "Lab Tools"),
        ("protein_structure_analysis", "Structure Analysis"),
    )
    for artifact_type, source_module in records:
        ok, _, _ = artifact_service.create_tool_artifact(
            artifact_type=artifact_type,
            title=artifact_type,
            source_module=source_module,
            summary="summary",
            payload_json={"artifact_type": artifact_type, "boundary_copy": "documentation-only summary"},
        )
        assert ok is True

    rows = artifact_service.list_tool_artifacts("protein_structure_analysis")
    assert len(rows) == 1
    assert rows[0]["artifact_type"] == "protein_structure_analysis"

    lab_rows = artifact_service.list_tool_artifacts(source_module="Lab Tools")
    assert len(lab_rows) == 2
    assert {row["source_module"] for row in lab_rows} == {"Lab Tools"}

    combined = artifact_service.list_tool_artifacts(
        artifact_type="lab_tools_sequence_export_preview",
        source_module="Lab Tools",
    )
    assert len(combined) == 1
    assert combined[0]["artifact_type"] == "lab_tools_sequence_export_preview"


def test_list_empty_state_constant_and_payload_summary_are_documentation_only():
    import views.LabTools as lab_tools_page
    import views.StructureAnalysis as structure_page

    assert lab_tools_page.ARTIFACT_EMPTY_STATE == "No saved documentation artifacts yet."
    assert structure_page.ARTIFACT_EMPTY_STATE == "No saved documentation artifacts yet."

    combined_boundary_copy = "\n".join(
        [lab_tools_page.ARTIFACT_BOUNDARY_COPY, structure_page.ARTIFACT_BOUNDARY_COPY]
    )
    for required_phrase in [
        "documentation-only",
        "documentation records",
        "review records",
        "not experimental conclusions",
        "not yield prediction",
        "not pathway optimization",
        "not wet-lab protocols",
    ]:
        assert required_phrase in combined_boundary_copy

    payload = {
        "title": "PCR Preview",
        "artifact_type": "lab_tools_pcr_preview",
        "source_module": "Lab Tools",
        "summary": {
            "forward_primer_name": "FWD-1",
            "reverse_primer_name": "REV-1",
            "target_length_bp": 120,
            "preview_type": "computational preview only",
        },
        "boundary_copy": "documentation-only review record; not wet-lab protocols.",
        "raw": "x" * 3000,
    }
    summary_rows = artifact_service.readable_payload_summary(payload)
    summary_text = "\n".join(f"{label}: {value}" for label, value in summary_rows)
    assert "Forward primer: FWD-1" in summary_text
    assert "Reverse primer: REV-1" in summary_text
    assert "Target length: 120 bp" in summary_text
    assert "computational preview only" in summary_text
    assert "xxxxxxxxxxxxxxxx" not in summary_text

    raw_preview, truncated = artifact_service.raw_payload_preview(payload, max_chars=1500)
    assert truncated is True
    assert len(raw_preview) <= 1500
