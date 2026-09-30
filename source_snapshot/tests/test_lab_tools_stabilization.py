import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.lab_tools_service import (
    BOUNDARY_COPY,
    cloning_preview_summary,
    lab_preview_artifact_payload,
    pcr_preview_summary,
    sequence_export_preview,
    virtual_gel_fragment_summary,
)


def test_lab_tools_boundary_copy_contains_required_documentation_only_language():
    assert "These tools create computational previews and documentation artifacts only." in BOUNDARY_COPY
    assert "They do not certify experimental readiness." in BOUNDARY_COPY
    assert "They do not predict yield." in BOUNDARY_COPY
    assert "They do not optimize pathways." in BOUNDARY_COPY
    assert "They do not provide wet-lab protocols." in BOUNDARY_COPY
    assert "They do not certify cloning, PCR, gel, or expression success." in BOUNDARY_COPY
    assert "Review primer and export decisions in Expression Wizard Step 5/Step 6." in BOUNDARY_COPY


def test_cloning_preview_summary_is_computational_and_includes_inputs():
    preview = cloning_preview_summary(
        insert_sequence="ATGCATGC",
        vector_name="pPreview",
        assembly_method="Gibson Assembly",
        insert_name="Reporter insert",
    )

    assert preview.status == "ok"
    assert preview.summary["insert_length_bp"] == 8
    assert preview.summary["vector"] == "pPreview"
    assert preview.summary["assembly_method"] == "Gibson Assembly"
    assert preview.summary["preview_type"] == "computational preview only"
    assert "wet-lab protocols" in preview.boundary


def test_pcr_preview_summary_reports_primer_target_and_amplicon_boundary():
    preview = pcr_preview_summary(
        template_sequence="ATGC" * 25,
        forward_primer="ATGCATGC",
        reverse_primer="GCATGCAT",
        forward_name="Fwd_A",
        reverse_name="Rev_A",
        expected_amplicon_length=64,
    )

    assert preview.status == "ok"
    assert preview.summary["forward_primer_name"] == "Fwd_A"
    assert preview.summary["reverse_primer_name"] == "Rev_A"
    assert preview.summary["target_length_bp"] == 100
    assert "64 bp" in preview.summary["expected_amplicon_summary"]
    assert "does not certify PCR or expression success" in preview.summary["does_not_certify"]


def test_virtual_gel_fragment_summary_provides_table_and_textual_preview():
    preview = virtual_gel_fragment_summary([500, "1000", 250, 0, "bad"])

    assert preview.status == "ok"
    assert preview.summary["fragment_count"] == 3
    assert preview.summary["fragment_sizes_bp"] == [1000, 500, 250]
    assert preview.summary["fragment_table"][0] == {"Fragment": 1, "Size (bp)": 1000}
    assert preview.summary["textual_gel_preview"] == "1000 bp | 500 bp | 250 bp"


def test_sequence_export_preview_generates_documentation_artifacts():
    fasta = sequence_export_preview(sequence="ATGCATGC", name="construct_a", fmt="FASTA")
    gbk = sequence_export_preview(sequence="ATGCATGC", name="construct_a", fmt="GenBank (GBK)")
    plain = sequence_export_preview(sequence="ATGCATGC", name="construct_a", fmt="Plain Text")

    assert fasta.status == "ok"
    assert fasta.summary["artifact_preview"].startswith(">construct_a\nATGCATGC")
    assert "LOCUS" in gbk.summary["artifact_preview"]
    assert plain.summary["artifact_preview"] == "ATGCATGC"
    assert fasta.summary["preview_type"] == "documentation artifact"
    assert "Step 6 export review rules" in fasta.summary["does_not_bypass"]


def test_lab_tools_preview_helpers_handle_invalid_or_empty_input():
    assert cloning_preview_summary(insert_sequence="---").status == "invalid_input"
    assert pcr_preview_summary(
        template_sequence="ATGC",
        forward_primer="",
        reverse_primer="GCAT",
    ).status == "invalid_input"
    assert virtual_gel_fragment_summary([0, -10, "bad"]).status == "invalid_input"
    assert sequence_export_preview(sequence="", fmt="FASTA").status == "invalid_input"


def test_lab_tools_preview_artifact_payload_is_documentation_only():
    preview = sequence_export_preview(sequence="ATGCATGC", name="construct_a", fmt="FASTA")

    payload = lab_preview_artifact_payload(
        preview,
        preview_kind="sequence_export",
        inputs={"format": "FASTA"},
    )

    assert payload["artifact_type"] == "lab_tools_sequence_export_preview"
    assert payload["title"] == "Sequence Export Preview"
    assert payload["source_module"] == "Lab Tools"
    assert payload["summary"]["sequence_length_bp"] == 8
    assert payload["summary"]["preview_type"] == "documentation artifact"
    assert payload["boundary_label"]
    assert "wet-lab protocols" in payload["boundary_copy"]
    assert lab_preview_artifact_payload(preview, preview_kind="unknown") == {}


def test_lab_tools_artifact_ui_copy_and_delete_warning_exist():
    page = open(os.path.join(ROOT, "views", "LabTools.py"), encoding="utf-8").read()

    assert "No saved documentation artifacts yet." in page
    assert "Record type" in page
    assert "Source module" in page
    assert "Cloning preview record" in page
    assert "Readable payload summary" in page
    assert "readable_payload_summary" in page
    assert "Advanced raw payload preview" in page
    assert "Advanced: view raw documentation record table" in page
    assert "raw_payload_preview" in page
    assert "Payload summary truncated for readability." in page
    assert "expanded=False" in page
    assert "max_chars=2000" in page
    assert "Delete record" in page
    assert "This removes the saved documentation record only." in page
    assert "Generate or review a cloning preview, then use Save current cloning preview record" in page
    assert "Saved documentation records are documentation-only review records." in page
    assert "not experimental conclusions" in page
    assert "not yield prediction" in page
    assert "not pathway optimization" in page
    assert "delete_tool_artifact" in page
    assert "Save Documentation Artifact" not in page
    assert "Filter by artifact_type" not in page
    assert "Filter by source_module" not in page
    assert "文档伪影" not in page
    assert "st.json" not in page
    assert "def _payload_summary" not in page
