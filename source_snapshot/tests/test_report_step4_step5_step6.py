from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from views.wizard_steps.step4_cloning_primers import build_step4_assembly_plan_summary
from views.wizard_steps.step5_validation import PRIMER_HIGH_RISK_CODE, PRIMER_REVIEW_CODE
from services.report_service import (
    _build_step4_assembly_plan_summary,
    generate_report_content,
    render_markdown_report,
    EXPORT_FORMAT_DETAILS,
    SEQUENCE_VERIFICATION_BLAST_NO_HITS_MESSAGE,
    SEQUENCE_VERIFICATION_LOCAL_NO_HITS_MESSAGE,
    SEQUENCE_VERIFICATION_NO_RESULT_MESSAGE,
    SEQUENCE_VERIFICATION_STALE_REPORT_MESSAGE,
    SEQUENCE_VERIFICATION_UNAVAILABLE_MESSAGE,
)
from services.validation_summary_service import build_validation_run_state


def _base_session() -> DesignSession:
    sequence = "ATG" + ("GCC" * 20) + "TAA"
    return DesignSession(
        step=6,
        gene_name="DemoGene",
        original_seq=sequence,
        optimized_seq=sequence,
        host="E.coli BL21(DE3)",
        tag="No tag",
        elements={
            "promoter_name": "T7",
            "rbs_name": "Strong RBS",
            "terminator_name": "rrnB T1",
        },
        frame={
            "success": True,
            "final_sequence": sequence,
            "total_length": len(sequence),
            "gc_content": 51.2,
            "vector_suggestion": "pET-28a",
            "parts": [
                {"name": "Promoter", "type": "promoter", "seq": "TTGACA"},
                {"name": "CDS", "type": "CDS", "seq": sequence},
            ],
        },
        cloning_method="Gibson Assembly",
        step4_plan_summary={
            "selected_overlap_len": 24,
            "selected_target_tm": 60.0,
            "best_plan_summary": "Review summary recorded the overlap/Tm combination shown for primer option comparison.",
            "structured_results": [
                {
                    "name": "Design 1",
                    "quality_grade": "Recommended",
                    "quality_score": 92,
                    "product_size": 180,
                    "target_tm": 60.0,
                    "tm_gap": 0.5,
                    "hetero_dimer_risk": "Low",
                    "quality_reasons": ["Balanced primer Tm."],
                    "pair_warnings": [],
                }
            ],
        },
    )


def test_report_carries_step4_step5_step6_for_recommended_case():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "FragA",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Fwd Anneal Tm (°C)": 60.0,
            "Rev Anneal Tm (°C)": 60.2,
            "Fwd Arm (bp)": 24,
            "Rev Arm (bp)": 24,
            "Quality Grade": "Recommended",
            "Quality Reasons": ["Balanced primer Tm.", "No major warning triggered."],
            "Warnings": [],
        }
    ]
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()

    state = build_validation_run_state(ds)
    report = generate_report_content(ds)
    md = render_markdown_report(report)

    assert report["primer_quality"]["quality_grade"] == "Recommended"
    assert report["primer_quality"]["selected_overlap"] == 24
    assert report["primer_quality"]["selected_target_tm"] == 60.0
    assert report["step4_assembly_plan_summary"]["assembly_method"] == "Gibson Assembly"
    assert report["step4_assembly_plan_summary"]["insert_length"] == len(ds.optimized_seq)
    assert report["step4_assembly_plan_summary"]["expected_product_size"] == 180
    assert report["step4_assembly_plan_summary"]["final_construct_length"] == len(ds.frame["final_sequence"])
    assert report["step4_assembly_plan_summary"]["host"] == "E.coli BL21(DE3)"
    assert report["step4_assembly_plan_summary"]["vector_backbone"] == "pET-28a"
    assert report["step4_assembly_plan_summary"]["vector_backbone_name"] == "pET-28a"
    assert report["step4_assembly_plan_summary"]["backbone_source"] == ""
    assert report["step4_assembly_plan_summary"]["primer_count"] == 2
    assert report["step4_assembly_plan_summary"]["forward_primer_count"] == 1
    assert report["step4_assembly_plan_summary"]["reverse_primer_count"] == 1
    assert report["step4_assembly_plan_summary"]["warning_count"] == 0
    assert report["step4_assembly_plan_summary"]["readiness_status"] == "Available for review"
    assert report["step4_assembly_plan_summary"]["readiness_reasons"]
    assert report["step4_assembly_plan_summary"]["warning_level"] == "none"
    assert report["step4_assembly_plan_summary"]["selected_overlap"] == 24
    assert report["step4_assembly_plan_summary"]["selected_overlap_len"] == 24
    assert "context_signature" in report["step4_assembly_plan_summary"]
    assert "context_signature_status" in report["step4_assembly_plan_summary"]
    assert "Active review option: Pass-range (review value 92)" in report["step4_assembly_plan_summary"]["quality_summary"]
    assert report["step4_assembly_plan_summary"]["best_plan_summary"] == "Review summary recorded the overlap/Tm combination shown for primer option comparison."
    assert report["validation_results"]["primer_risk_summary"]["recommended_count"] == 1
    assert state["status"] == "completed_passed"
    assert report["validation_results"]["final_conclusion"]["status"] == "passed"
    assert report["export_recommendation"]["recommendation"] == "Documentation Export Available"
    assert report["step_alignment"]["step4"]["status"] == "Recommended"
    assert report["step_alignment"]["step4"]["assembly_plan"] == report["step4_assembly_plan_summary"]
    assert report["step_alignment"]["step5"]["status"] == "passed"
    assert report["step_alignment"]["step6"]["status"] == "Documentation Export Available"
    assert report["export_formats"]["recommended_primary_format"] in {"fasta", "genbank"}
    assert any(item["format"] == "fasta" and item["available"] for item in report["export_formats"]["available_formats"])
    assert any(item["format"] == "genbank" and item["available"] for item in report["export_formats"]["available_formats"])
    png_format = next(item for item in report["export_formats"]["available_formats"] if item["format"] == "png")
    png_format_text = f"{png_format['label']} {png_format['use_case']}".lower()
    assert png_format["label"] == "Construct/cassette map preview PNG"
    assert "documentation map preview image" in png_format_text
    assert png_format["filename"] == "DemoGene_plasmid_map.png"
    assert "plasmid map" not in png_format_text
    assert "validated plasmid" not in png_format_text
    assert "sequence verified" not in png_format_text
    assert "cloning-ready" not in png_format_text
    assert "wet-lab ready" not in png_format_text
    assert "optimized vector" not in png_format_text
    assert "recommended plasmid" not in png_format_text
    assert "guaranteed expression" not in png_format_text
    assert "experimental success" not in png_format_text
    assert "primer_design_summary" not in report
    assert "validation_summary" not in report
    assert "validation" not in report
    assert "## 3. Primer design summary" in md
    assert "### Assembly plan summary" in md
    assert "| Assembly method | Gibson Assembly |" in md
    assert "| Insert length | 66 bp |" in md
    assert "| Expected product size | 180 bp |" in md
    assert "| Final construct length | 66 bp |" in md
    assert "| Host | E.coli BL21(DE3) |" in md
    assert "| Vector / backbone name | pET-28a |" in md
    assert "| Backbone source | — |" in md
    assert "| Vector / backbone | pET-28a |" in md
    assert "| Primer count | 2 |" in md
    assert "| Warning count | 0 |" in md
    assert "| Review status | Available for review |" in md
    assert "| Warning level | none |" in md
    assert "- Review plan summary: Review summary recorded the overlap/Tm combination shown for primer option comparison." in md
    assert "| Review plan summary | Review summary recorded the overlap/Tm combination shown for primer option comparison. |" in md
    assert "Best plan summary" not in md
    assert "## 4. Validation summary" in md
    assert "### Export formats" in md
    assert "Construct/cassette map preview PNG" in md
    assert "DemoGene_plasmid_map.png" in md
    assert "Documentation map preview image" in md
    assert "## 6. Step alignment" in md
    assert "## 7. Sequence Verification Summary" in md
    assert SEQUENCE_VERIFICATION_NO_RESULT_MESSAGE in md
    assert "Documentation Export Available" in md


def test_step4_and_report_helpers_share_canonical_assembly_summary():
    ds = _base_session()
    ds.primer_context_signature = ds.current_primer_context_signature()
    ds.primers = [
        {
            "Fragment Name": "FragA",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Recommended",
            "Quality Reasons": ["Balanced primer Tm."],
            "Warnings": [],
        }
    ]

    step4_summary = build_step4_assembly_plan_summary(ds)
    report_summary = _build_step4_assembly_plan_summary(ds)

    assert step4_summary == report_summary
    assert step4_summary["selected_overlap"] == 24
    assert step4_summary["selected_overlap_len"] == 24
    assert step4_summary["context_signature"] == ds.current_primer_context_signature()
    assert step4_summary["context_signature_status"] == "Current"
    assert set(step4_summary).issuperset(
        {
            "assembly_method",
            "insert_length",
            "expected_product_size",
            "final_construct_length",
            "host",
            "vector_backbone",
            "vector_backbone_name",
            "backbone_source",
            "primer_count",
            "forward_primer_count",
            "reverse_primer_count",
            "warning_count",
            "quality_summary",
            "best_plan_summary",
            "selected_overlap",
            "selected_target_tm",
            "tried_combinations",
            "stale_status",
            "context_signature",
            "readiness_status",
            "readiness_reasons",
            "warning_level",
        }
    )
    assert step4_summary["readiness_status"] == "Available for review"
    assert step4_summary["warning_level"] == "none"


def test_assembly_plan_readiness_marks_warning_case_for_review():
    ds = _base_session()
    ds.primer_context_signature = ds.current_primer_context_signature()
    ds.primers = [
        {
            "Fragment Name": "FragRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Usable with Risk",
            "Warnings": ["Moderate cross-dimer risk between primers."],
        }
    ]

    summary = build_step4_assembly_plan_summary(ds)

    assert summary["readiness_status"] == "Needs Review"
    assert summary["warning_level"] == "warning"
    assert summary["readiness_reasons"]


def test_assembly_plan_readiness_blocks_missing_primers():
    ds = _base_session()
    ds.primers = []

    summary = build_step4_assembly_plan_summary(ds)

    assert summary["readiness_status"] == "Blocked"
    assert summary["warning_level"] == "blocker"
    assert summary["readiness_reasons"]


def test_assembly_plan_readiness_blocks_stale_primers():
    ds = _base_session()
    ds.primer_context_signature = "stale-signature"
    ds.primers = [
        {
            "Fragment Name": "FragStale",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Recommended",
            "Warnings": [],
        }
    ]

    summary = build_step4_assembly_plan_summary(ds)

    assert summary["readiness_status"] == "Blocked"
    assert summary["warning_level"] == "blocker"
    assert summary["readiness_reasons"]


def test_report_carries_risk_summary_and_review_required_case():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "FragRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Fwd Anneal Tm (°C)": 58.0,
            "Rev Anneal Tm (°C)": 60.0,
            "Fwd Arm (bp)": 20,
            "Rev Arm (bp)": 20,
            "Quality Grade": "Usable with Risk",
            "Quality Reasons": ["Annealing Tm is slightly offset from target (60.0°C)."],
            "Warnings": ["Moderate cross-dimer risk between primers."],
        }
    ]
    ds.validation_results = [
        {"severity": "warning", "code": PRIMER_REVIEW_CODE, "title": "Primer quality review recommended", "why": "Review-level primer risk carried over.", "fix": "Review Step 4."}
    ]
    ds.validation_context_signature = ds.current_validation_context_signature()

    report = generate_report_content(ds)
    md = render_markdown_report(report)

    assert report["primer_quality"]["quality_grade"] == "Usable with Risk"
    assert report["primer_quality"]["pair_warnings"]
    assert report["validation_results"]["primer_risk_summary"]["affected_fragments"] == ["FragRisk"]
    assert report["validation_results"]["primer_risk_summary"]["top_risk_reasons"]
    assert report["validation_results"]["final_conclusion"]["status"] == "review_required"
    assert report["export_recommendation"]["recommendation"] == "Export with Review Required"
    assert "Affected fragments: FragRisk" in md
    assert "Export with Review Required" in md


def test_report_carries_high_risk_and_not_recommended_case():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "FragHighRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Fwd Anneal Tm (°C)": 55.0,
            "Rev Anneal Tm (°C)": 66.0,
            "Fwd Arm (bp)": 18,
            "Rev Arm (bp)": 18,
            "Quality Grade": "Not Recommended",
            "Quality Reasons": ["High cross-dimer risk between primers (8 bp complementarity)."],
            "Warnings": ["High cross-dimer risk between primers (8 bp complementarity)."],
        }
    ]
    ds.validation_results = [
        {"severity": "warning", "code": PRIMER_HIGH_RISK_CODE, "title": "High-risk primer pair(s) detected", "why": "Step 4 marked 1 primer pair as Not Recommended.", "fix": "Return to Step 4 to review primer design before export."},
        {"severity": "info", "code": "PASS", "title": "All validation checks passed", "why": "No biological logic errors detected.", "fix": "Proceed after primer review."},
    ]
    ds.validation_context_signature = ds.current_validation_context_signature()

    report = generate_report_content(ds)
    md = render_markdown_report(report)

    assert report["primer_quality"]["quality_grade"] == "Not Recommended"
    assert report["validation_results"]["primer_risk_summary"]["not_recommended_count"] == 1
    assert report["validation_results"]["final_conclusion"]["status"] == "high_risk_primer_review"
    assert report["export_recommendation"]["recommendation"] == "Review blocked by unresolved risk signals"
    assert report["export_recommendation"]["primer_high_risk_count"] == 1
    assert "High cross-dimer risk between primers" in md
    assert "Review blocked by unresolved risk signals" in md


def test_report_keeps_step4_step5_step6_fields_consistent_without_duplication():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "FragConsistent",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Fwd Anneal Tm (°C)": 58.5,
            "Rev Anneal Tm (°C)": 59.0,
            "Fwd Arm (bp)": 22,
            "Rev Arm (bp)": 22,
            "Quality Grade": "Usable with Risk",
            "Quality Reasons": ["Annealing Tm is slightly offset from target (60.0°C)."],
            "Warnings": ["Moderate cross-dimer risk between primers."],
        }
    ]
    ds.validation_results = [
        {"severity": "warning", "code": PRIMER_REVIEW_CODE, "title": "Primer quality review recommended", "why": "Review-level primer risk carried over.", "fix": "Review Step 4."},
        {"severity": "info", "code": "PASS", "title": "All validation checks passed", "why": "No biological logic errors detected.", "fix": "Proceed after review."},
    ]
    ds.validation_context_signature = ds.current_validation_context_signature()

    report = generate_report_content(ds)
    primer_risk = report["validation_results"]["primer_risk_summary"]
    step_alignment = report["step_alignment"]

    assert set(report).issuperset({"primer_quality", "validation_results", "export_recommendation", "export_formats", "step_alignment"})
    assert "primer_design_summary" not in report
    assert "validation_summary" not in report
    assert "validation" not in report
    assert primer_risk["recommended_count"] == report["primer_quality"]["risk_summary"]["recommended"]
    assert primer_risk["usable_with_risk_count"] == report["primer_quality"]["risk_summary"]["usable_with_risk"]
    assert primer_risk["not_recommended_count"] == report["primer_quality"]["risk_summary"]["not_recommended"]
    assert primer_risk["affected_fragments"] == report["export_recommendation"]["affected_fragments"]
    assert step_alignment["step4"]["risk_counts"] == report["primer_quality"]["risk_summary"]
    assert step_alignment["step4"]["assembly_plan"] == report["step4_assembly_plan_summary"]
    assert step_alignment["step5"]["affected_fragments"] == report["export_recommendation"]["affected_fragments"]
    assert step_alignment["step6"]["recommendation"] == report["export_recommendation"]["recommendation"]
    assert step_alignment["step6"]["available_formats"] == report["export_formats"]["available_formats"]
    assert report["validation_results"]["final_conclusion"]["status"] == "review_required"
    assert report["export_recommendation"]["recommendation"] == "Export with Review Required"


def test_report_step6_uses_active_primer_quality_even_when_validation_has_no_primer_issue():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "ActiveHighRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Not Recommended",
            "Quality Reasons": ["High primer interaction risk."],
            "Warnings": [],
        }
    ]
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()

    report = generate_report_content(ds)

    assert report["primer_quality"]["quality_grade"] == "Not Recommended"
    assert report["validation_results"]["final_conclusion"]["status"] == "passed"
    assert report["export_recommendation"]["recommendation"] == "Review blocked by unresolved risk signals"
    assert report["export_recommendation"]["primer_high_risk_count"] == 1
    assert report["export_recommendation"]["primer_action_required_count"] == 1
    assert report["step_alignment"]["step4"]["status"] == "Not Recommended"
    assert report["step_alignment"]["step4"]["readiness_status"] == "Blocked"
    assert report["step4_assembly_plan_summary"]["readiness_status"] == "Blocked"
    assert report["step_alignment"]["step6"]["status"] == "Review blocked by unresolved risk signals"



    ds = _base_session()
    ds.primers = []
    ds.validation_results = []

    report = generate_report_content(ds)
    formats = {item["format"]: item for item in report["export_formats"]["available_formats"]}

    assert set(EXPORT_FORMAT_DETAILS).issubset({"markdown", "fasta", "genbank", "png"})
    assert formats["fasta"]["label"] == "FASTA Sequence (.fasta)"
    assert formats["fasta"]["filename"].endswith(".fasta")
    assert formats["fasta"]["available"] is True
    assert formats["genbank"]["label"] == "GenBank Record (.gb)"
    assert formats["genbank"]["filename"].endswith(".gb")
    assert formats["genbank"]["available"] is True
    assert report["step_alignment"]["step6"]["recommended_primary_format"] in {"fasta", "genbank"}
    assert report["report_presenter"]["summary_cards"][2]["status_text"] == report["export_recommendation"]["recommendation"]
    assert report["report_presenter"]["cards_by_step"]["step4"]["step_key"] == "step4"
    assert report["report_presenter"]["cards_by_step"]["step4"]["title"] == "Step 4 · Assembly plan"
    step4_metrics = {item["label"]: item["value"] for item in report["report_presenter"]["cards_by_step"]["step4"]["metrics"]}
    assert step4_metrics["Review status"] == "Blocked"
    assert step4_metrics["Assembly method"] == "Gibson Assembly"
    assert step4_metrics["Primer count"] == "0"
    assert step4_metrics["Warnings"] == "0"
    assert report["report_presenter"]["cards_by_step"]["step5"]["step_key"] == "step5"
    assert report["report_presenter"]["cards_by_step"]["step6"]["step_key"] == "step6"
    assert report["report_presenter"]["alignment_rows"][0]["Section"] == report["step_alignment"]["step4"]["section_title"]


def test_report_export_formats_follow_canonical_export_payload_when_features_exist_without_parts():
    ds = _base_session()
    ds.frame = {
        "success": True,
        "final_sequence": ds.original_seq,
        "total_length": len(ds.original_seq),
        "gc_content": 51.2,
        "vector_suggestion": "pET-28a",
        "parts": [],
        "features": [
            {"name": "Promoter", "type": "promoter", "start": 1, "end": 6},
            {"name": "CDS", "type": "CDS", "start": 7, "end": len(ds.original_seq)},
        ],
    }
    ds.primers = []
    ds.validation_results = []

    report = generate_report_content(ds)
    formats = {item["format"]: item for item in report["export_formats"]["available_formats"]}

    assert formats["fasta"]["available"] is True
    assert formats["genbank"]["available"] is True
    assert report["export_formats"]["recommended_primary_format"] == "genbank"


def test_usable_with_risk_without_warnings_maps_to_needs_review_not_ready():
    ds = _base_session()
    ds.primer_context_signature = ds.current_primer_context_signature()
    ds.primers = [
        {
            "Fragment Name": "FragRiskNoWarning",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Usable with Risk",
            "Warnings": [],
        }
    ]

    summary = build_step4_assembly_plan_summary(ds)

    assert summary["readiness_status"] == "Needs Review"
    assert summary["warning_level"] == "warning"


def test_documentation_only_export_status_under_not_recommended():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "FragHighRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Not Recommended",
            "Warnings": [],
        }
    ]
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()

    report = generate_report_content(ds)
    available_formats = [item for item in report["export_formats"]["available_formats"] if item["available"]]

    assert report["export_recommendation"]["recommendation"] == "Review blocked by unresolved risk signals"
    assert available_formats
    assert all(item["status"] == "documentation_only" for item in available_formats)
    assert all(item["display_status"] == "Available for documentation" for item in available_formats)
    assert all("documentation-only" in item["reason"] for item in available_formats)
    assert "documentation only" in report["report_presenter"]["report_download"]["help"]


def _verification_payload(ds: DesignSession, *, source: str = "Local Parts Registry", status: str = "completed") -> dict:
    return {
        "status": status,
        "query": {"length": len(ds.final_sequence), "hash": __import__("hashlib").sha256(ds.final_sequence.encode("utf-8")).hexdigest()},
        "database": {"source": source},
        "adapter_name": "local-parts-registry" if source == "Local Parts Registry" else "imported-blast-tsv",
        "top_hit": {
            "accession": "PART-001" if source == "Local Parts Registry" else "BLAST123",
            "description": "Fixture verification hit",
            "percent_identity": 99.5,
            "coverage": 96.0,
            "e_value": "1e-40",
            "match_type": "exact_match" if source == "Local Parts Registry" else "blast_hit",
        } if status == "completed" else None,
        "hits": [],
        "warnings": [{"code": "INFORMATIONAL_ONLY", "message": "Review only.", "severity": "info"}],
        "timestamp": "2026-01-01T00:00:00Z",
        "disclaimer": "Sequence verification is informational only. It does not certify experimental readiness.",
    }


def test_completed_local_registry_verification_enters_report_preview_and_markdown():
    ds = _base_session()
    payload = _verification_payload(ds, source="Local Parts Registry")

    report = generate_report_content(ds, verification_result=payload)
    md = render_markdown_report(report)
    rows = {row["label"]: row["value"] for row in report["report_presenter"]["sequence_verification"]["rows"]}

    assert report["report_presenter"]["sequence_verification"]["included"] is True
    assert rows["Verification source"] == "Local Parts Registry"
    assert rows["Status"] == "completed"
    assert rows["Top hit accession"] == "PART-001"
    assert rows["Percent identity"] == "99.50%"
    assert rows["Coverage"] == "96.00%"
    assert rows["E-value"] == "1e-40"
    assert rows["Match type"] == "exact_match"
    assert "## 7. Sequence Verification Summary" in md
    assert "| Verification source | Local Parts Registry |" in md
    assert "| Top hit accession | PART-001 |" in md


def test_completed_imported_blast_verification_enters_report_preview():
    ds = _base_session()
    payload = _verification_payload(ds, source="Imported BLAST TSV")

    report = generate_report_content(ds, verification_result=payload)
    rows = {row["label"]: row["value"] for row in report["report_presenter"]["sequence_verification"]["rows"]}

    assert report["report_presenter"]["sequence_verification"]["included"] is True
    assert rows["Verification source"] == "Imported BLAST TSV"
    assert rows["Top hit accession"] == "BLAST123"
    assert rows["Match type"] == "blast_hit"


def test_no_verification_result_shows_no_attached_result_message():
    ds = _base_session()

    report = generate_report_content(ds, verification_result=None, include_session_verification=False)
    md = render_markdown_report(report)

    assert report["sequence_verification"]["included"] is False
    assert report["sequence_verification"]["message"] == SEQUENCE_VERIFICATION_NO_RESULT_MESSAGE
    assert SEQUENCE_VERIFICATION_NO_RESULT_MESSAGE in md


def test_stale_verification_result_is_not_included_in_current_report():
    ds = _base_session()
    payload = _verification_payload(ds)
    payload["query"]["hash"] = "stale-hash"

    report = generate_report_content(ds, verification_result=payload)
    md = render_markdown_report(report)

    assert report["sequence_verification"]["included"] is False
    assert report["sequence_verification"]["is_stale"] is True
    assert report["sequence_verification"]["message"] == SEQUENCE_VERIFICATION_STALE_REPORT_MESSAGE
    assert SEQUENCE_VERIFICATION_STALE_REPORT_MESSAGE in md
    assert "PART-001" not in md


def test_no_hit_wording_is_source_specific_in_report():
    ds = _base_session()
    blast_payload = _verification_payload(ds, source="Imported BLAST TSV", status="no_hits")
    local_payload = _verification_payload(ds, source="Local Parts Registry", status="no_hits")
    placeholder_payload = _verification_payload(ds, source="Placeholder verification adapter", status="unavailable")

    blast_report = generate_report_content(ds, verification_result=blast_payload)
    local_report = generate_report_content(ds, verification_result=local_payload)
    placeholder_report = generate_report_content(ds, verification_result=placeholder_payload)

    assert blast_report["sequence_verification"]["message"] == SEQUENCE_VERIFICATION_BLAST_NO_HITS_MESSAGE
    assert local_report["sequence_verification"]["message"] == SEQUENCE_VERIFICATION_LOCAL_NO_HITS_MESSAGE
    assert placeholder_report["sequence_verification"]["message"] == SEQUENCE_VERIFICATION_UNAVAILABLE_MESSAGE


def test_verification_report_section_preserves_step5_step6_recommendation_and_session_safety_fields():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "FragHighRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Not Recommended",
            "Warnings": [],
        }
    ]
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()
    validation_before = list(ds.validation_results)
    context_before = ds.validation_context_signature

    report_without_verification = generate_report_content(ds, verification_result=None)
    report_with_verification = generate_report_content(ds, verification_result=_verification_payload(ds))

    assert report_with_verification["step_alignment"]["step5"]["status"] == report_without_verification["step_alignment"]["step5"]["status"]
    assert report_with_verification["step_alignment"]["step6"]["status"] == "Review blocked by unresolved risk signals"
    assert report_with_verification["export_recommendation"] == report_without_verification["export_recommendation"]
    assert ds.validation_results == validation_before
    assert ds.validation_context_signature == context_before
