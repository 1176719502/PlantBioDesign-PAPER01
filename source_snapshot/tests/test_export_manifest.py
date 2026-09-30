from __future__ import annotations

import copy
import hashlib
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from services.export_recommendation_service import build_export_recommendation
from services.report_service import generate_report_content
from services.validation_summary_service import (
    PRIMER_HIGH_RISK_CODE,
    PRIMER_REVIEW_CODE,
    build_validation_run_state,
)
from components.export_manager import (
    build_design_session_export_base_payload,
    build_export_manifest,
    build_export_manifest_payload,
)


def _base_session() -> DesignSession:
    sequence = "ATG" + ("GCC" * 12) + "TAA"
    return DesignSession(
        step=6,
        gene_name="Demo Gene",
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
            "gc_content": 52.4,
            "vector_suggestion": "pET-28a",
            "parts": [
                {"name": "T7", "type": "promoter", "seq": "ATG"},
                {"name": "Target Gene (CDS)", "type": "CDS", "seq": sequence[3:]},
            ],
        },
        cloning_method="Gibson Assembly",
    )


def _build_manifest(ds: DesignSession, verification_result: dict | None = None) -> dict:
    export_payload = build_design_session_export_base_payload(ds)
    validation_state = build_validation_run_state(ds)
    recommendation = build_export_recommendation(
        ds.validation_results or [],
        ds.primers or [],
        export_payload["sequence"],
        validation_complete=validation_state["is_complete"],
    )
    report = generate_report_content(
        ds,
        verification_result=verification_result,
        include_session_verification=False,
    )
    delivery_ready = (
        export_payload["has_sequence"]
        and validation_state["is_complete"]
        and not validation_state["is_stale"]
        and not validation_state["is_running"]
        and not validation_state["is_failed"]
        and validation_state["critical_count"] == 0
        and recommendation["recommendation"] == "Documentation Export Available"
    )
    return build_export_manifest(
        export_payload=export_payload,
        report=report,
        validation_state=validation_state,
        export_recommendation=recommendation,
        delivery_ready=delivery_ready,
    )


def test_manifest_includes_schema_sequence_checksum_and_serializes():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "FragA",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Recommended",
        }
    ]
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()

    manifest = _build_manifest(ds)
    payload = build_export_manifest_payload(manifest, "Demo_Gene")

    assert manifest["schema_version"] == "bds.export_manifest.v0.4"
    assert manifest["platform"] == "BioDesign Studio"
    assert manifest["sequence_length_bp"] == len(ds.frame["final_sequence"])
    assert manifest["sequence_sha256"] == hashlib.sha256(ds.frame["final_sequence"].encode("utf-8")).hexdigest()
    assert manifest["coordinate_system"] == "Biological feature coordinates use 1-based inclusive positions."
    assert payload["file_name"] == "Demo_Gene_export_manifest.json"
    assert payload["mime"] == "application/json"
    json.dumps(manifest, ensure_ascii=False, sort_keys=True, default=str)
    json.loads(payload["data"])


def test_manifest_artifact_filenames_match_existing_export_payload_and_report():
    ds = _base_session()
    ds.primers = [{"Fragment Name": "FragA", "Quality Grade": "Recommended"}]
    ds.validation_context_signature = ds.current_validation_context_signature()

    export_payload = build_design_session_export_base_payload(ds)
    manifest = _build_manifest(ds)
    artifact_files = {item["format"]: item["filename"] for item in manifest["artifacts"]}

    assert artifact_files["fasta"] == export_payload["payloads"]["fasta"]["file_name"]
    assert artifact_files["genbank"] == export_payload["payloads"]["genbank"]["file_name"]
    assert artifact_files["markdown"] == export_payload["report_filename"]
    assert artifact_files["png"] == export_payload["png_filename"]
    assert artifact_files["png"] == "Demo_Gene_plasmid_map.png"


def test_manifest_png_artifact_uses_documentation_preview_wording():
    ds = _base_session()
    ds.primers = [{"Fragment Name": "FragA", "Quality Grade": "Recommended"}]
    ds.validation_context_signature = ds.current_validation_context_signature()

    manifest = _build_manifest(ds)
    png_artifact = next(item for item in manifest["artifacts"] if item["format"] == "png")
    png_text = json.dumps(png_artifact, ensure_ascii=False, sort_keys=True).lower()

    assert png_artifact["label"] == "Construct/cassette map preview PNG"
    assert png_artifact["filename"] == "Demo_Gene_plasmid_map.png"
    assert "documentation map preview image" in png_text
    assert "sequence validation" in png_text
    assert "cloning feasibility verification" in png_text
    assert "plasmid map" not in png_text
    assert "validated plasmid" not in png_text
    assert "sequence verified" not in png_text
    assert "cloning-ready" not in png_text
    assert "wet-lab ready" not in png_text
    assert "optimized vector" not in png_text
    assert "recommended plasmid" not in png_text
    assert "guaranteed expression" not in png_text
    assert "experimental success" not in png_text


def test_manifest_marks_review_required_as_documentation_only():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "FragRisk",
            "Quality Grade": "Usable with Risk",
            "Warnings": ["Moderate cross-dimer risk between primers."],
        }
    ]
    ds.validation_results = [
        {
            "severity": "warning",
            "code": PRIMER_REVIEW_CODE,
            "title": "Primer quality review recommended",
        }
    ]
    ds.validation_context_signature = ds.current_validation_context_signature()

    manifest = _build_manifest(ds)

    assert manifest["export_recommendation"]["recommendation"] == "Export with Review Required"
    assert manifest["export_recommendation"]["documentation_only"] is True
    assert manifest["primer_risk_summary"]["usable_with_risk_count"] == 1


def test_manifest_preserves_not_recommended_as_documentation_only():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "FragHighRisk",
            "Quality Grade": "Not Recommended",
            "Warnings": ["High cross-dimer risk between primers."],
        }
    ]
    ds.validation_results = [
        {
            "severity": "warning",
            "code": PRIMER_HIGH_RISK_CODE,
            "title": "High-risk primer pair detected",
        }
    ]
    ds.validation_context_signature = ds.current_validation_context_signature()

    manifest = _build_manifest(ds)

    assert manifest["export_recommendation"]["recommendation"] == "Review blocked by unresolved risk signals"
    assert manifest["export_recommendation"]["documentation_only"] is True
    assert manifest["export_recommendation"]["ready_for_downstream_handoff"] is False
    assert manifest["primer_risk_summary"]["not_recommended_count"] == 1


def test_manifest_avoids_certification_or_approval_language():
    ds = _base_session()
    ds.primers = [{"Fragment Name": "FragA", "Quality Grade": "Recommended"}]
    ds.validation_context_signature = ds.current_validation_context_signature()

    manifest_text = json.dumps(_build_manifest(ds), ensure_ascii=False, sort_keys=True, default=str).lower()

    assert "certified" not in manifest_text
    assert "approved" not in manifest_text
    assert "certification" not in manifest_text
    assert "approval" not in manifest_text
    assert "experiment-ready" not in manifest_text


def test_manifest_generation_does_not_mutate_design_session_fields():
    ds = _base_session()
    ds.primers = [{"Fragment Name": "FragA", "Quality Grade": "Recommended"}]
    ds.validation_context_signature = ds.current_validation_context_signature()
    before = copy.deepcopy(ds.__dict__)

    _build_manifest(ds)

    assert ds.__dict__ == before


def test_manifest_represents_absent_sequence_verification_summary():
    ds = _base_session()
    ds.primers = [{"Fragment Name": "FragA", "Quality Grade": "Recommended"}]
    ds.validation_context_signature = ds.current_validation_context_signature()

    manifest = _build_manifest(ds)
    summary = manifest["sequence_verification_summary"]

    assert summary["included"] is False
    assert summary["is_stale"] is False
    assert summary["source"] == "Not configured"
    assert summary["status"] == "not_run"
    assert "No sequence verification result" in summary["message"]


def test_manifest_represents_present_sequence_verification_summary():
    ds = _base_session()
    ds.primers = [{"Fragment Name": "FragA", "Quality Grade": "Recommended"}]
    ds.validation_context_signature = ds.current_validation_context_signature()
    verification_result = {
        "status": "hit",
        "source": "Local Parts Registry",
        "adapter_name": "Local Registry",
        "query": {
            "length": len(ds.frame["final_sequence"]),
            "signature": hashlib.sha256(ds.frame["final_sequence"].encode("utf-8")).hexdigest(),
        },
        "top_hit": {
            "accession": "LOCAL-001",
            "description": "Demo local construct",
            "percent_identity": 99.5,
            "coverage": 98.0,
            "e_value": "1e-20",
            "match_type": "similarity",
        },
        "warnings": [{"code": "REVIEW", "message": "Manual review recommended."}],
        "disclaimer": "Local verification only.",
    }

    manifest = _build_manifest(ds, verification_result=verification_result)
    summary = manifest["sequence_verification_summary"]

    assert summary["included"] is True
    assert summary["is_stale"] is False
    assert summary["source"] == "Local Parts Registry"
    assert summary["status"] == "hit"
    assert summary["top_hit"]["accession"] == "LOCAL-001"
    assert summary["warnings"]
