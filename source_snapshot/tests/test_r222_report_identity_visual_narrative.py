from __future__ import annotations

import os
import re
import sys
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from services.pathway_report_service import generate_pathway_markdown_report
from services.project_review_report_service import build_project_review_report
from services.report_service import generate_report_content, render_markdown_report


UNSAFE_CLAIMS = [
    "guaranteed expression",
    "yield " + "prediction",
    "wet-lab readiness",
    "experimental validation conclusion",
    "automatic " + "optimization",
    "automatic " + "conservation",
    "validated " + "construct",
    "production" + "-ready",
    "experiment" + "-ready",
    "ready for execution",
    "replacement of expert/company review",
]


def _assert_md5(value: str) -> None:
    assert re.fullmatch(r"[0-9a-f]{32}", value)


def _assert_safe_batch_copy(text: str) -> None:
    lowered = text.lower()
    assert [phrase for phrase in UNSAFE_CLAIMS if phrase in lowered] == []
    assert "documentation-only" in lowered


def _design_session() -> DesignSession:
    sequence = "ATG" + ("GCC" * 16) + "TAA"
    ds = DesignSession(
        step=6,
        gene_name="ReportIdentityCase",
        original_seq=sequence,
        optimized_seq=sequence,
        host="E.coli BL21(DE3)",
        tag="No tag",
        elements={
            "promoter_name": "T7 documentation record",
            "rbs_name": "RBS documentation record",
            "terminator_name": "Terminator documentation record",
        },
        frame={
            "success": True,
            "final_sequence": sequence,
            "total_length": len(sequence),
            "gc_content": 51.2,
            "vector_suggestion": "pET documentation context",
        },
        cloning_method="Gibson Assembly",
    )
    ds.primers = [
        {
            "Fragment Name": "FragA",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Usable with Risk",
            "Warnings": ["Manual review cue retained."],
        }
    ]
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()
    return ds


def test_expression_design_report_includes_identity_qr_payload_and_visual_narrative() -> None:
    report = generate_report_content(_design_session(), include_session_verification=False)
    markdown = render_markdown_report(report)
    identity = report["report_identity"]

    _assert_md5(identity["md5_checksum"])
    assert "BioDesign Studio report QR verification payload" in identity["qr_payload_text"]
    assert "Checksum algorithm: MD5" in identity["qr_payload_text"]
    assert "MD5 checksum:" in identity["qr_payload_text"]
    assert "QR dependency note: Payload-only QR preview" in identity["qr_payload_text"]
    assert "Report identity and QR verification preview" in markdown
    assert "Report visual narrative" in markdown
    assert "Target intent -> Expression system candidate -> Construct/component records" in markdown
    assert "Evidence/provenance review -> Codon/conservation status -> Review gaps -> Handoff package" in markdown
    assert "Manual/company review remains responsible" in markdown
    _assert_safe_batch_copy(f"{identity}\n{markdown}")


def test_pathway_markdown_report_includes_identity_qr_payload_and_workflow_narrative() -> None:
    markdown = generate_pathway_markdown_report(
        project={
            "id": 222,
            "name": "R222 report identity pathway",
            "target_product": "Documentation target",
            "host": "Recorded host context",
            "status": "draft",
            "description": "Teacher-readable documentation report.",
        },
        steps=[
            {
                "id": 1,
                "step_order": 1,
                "step_name": "Record context",
                "enzyme_name": "Recorded enzyme context",
                "gene_name": "recorded_gene",
                "organism_source": "Recorded organism context",
            }
        ],
        expression_links=[{"id": 10, "step_id": 1, "design_name": "Linked design record"}],
        test_records=[],
        completeness_result={"score": 66, "status": "In Progress", "missing_items": ["Add source context."]},
        suggestions=[],
        generated_at=datetime(2026, 6, 26, 10, 30, 0),
    )

    assert "## Report identity and QR verification preview" in markdown
    assert "Report/package ID: pathway-report:222" in markdown
    assert "Checksum algorithm: MD5" in markdown
    assert "MD5 checksum:" in markdown
    assert "QR payload status: PAYLOAD_ONLY" in markdown
    assert "## Report visual narrative" in markdown
    assert "Pathway steps 1; linked designs 1; review signals 0." in markdown
    assert "Human/company review should resolve missing documentation fields" in markdown
    _assert_safe_batch_copy(markdown)


def test_project_review_report_and_detailed_draft_standardize_identity_and_narrative(monkeypatch) -> None:
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [],
    )

    report = build_project_review_report(
        {
            "id": 222,
            "name": "R222 project review report",
            "target_product": "Documentation target",
            "status": "draft",
            "description": "Project review report identity example.",
            "pathway_steps": [{"id": 1, "step_order": 1, "step_name": "Record context"}],
        }
    )

    identity = report["report_identity"]
    detailed = report["detailed_documentation_report_draft"]
    _assert_md5(identity["md5_checksum"])
    assert identity["report_or_package_id"].startswith("md5:")
    assert identity["md5_checksum"] in report["markdown"]
    assert "BioDesign Studio report QR verification payload" in report["markdown"]
    assert "## Report visual narrative" in report["markdown"]
    assert "## Report identity and QR verification preview" in detailed["markdown"]
    assert "Target intent -> Expression system candidate -> Construct/component records" in detailed["markdown"]
    assert "Human/company review should resolve missing source/provenance context" in identity["qr_payload_text"]
    assert "This report identity block is documentation-only." in report["markdown"]
    _assert_safe_batch_copy(f"{report['markdown']}\n{detailed['markdown']}")
