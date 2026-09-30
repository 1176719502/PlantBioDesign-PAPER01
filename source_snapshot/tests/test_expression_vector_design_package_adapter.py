from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.expression_cassette_slot_rows_presenter import build_expression_cassette_slot_rows_presenter
from services.expression_vector_design_package_adapter import (
    DEFAULT_PACKAGE_STATUS,
    PACKAGE_TYPE,
    build_expression_vector_design_package_preview,
)


def test_adapter_returns_stable_package_preview_structure() -> None:
    preview = build_expression_vector_design_package_preview(
        package_title="crtI expression vector documentation preview",
        source_commit_or_version="test-commit",
        target_record={
            "target_name": "crtI",
            "cds_or_protein_value": "crtI CDS record",
            "source_reference": "Manual source note",
            "review_status": "documented",
        },
        host_record={
            "host_system": "E. coli BL21(DE3) context",
            "source_reference": "Host notebook",
            "review_status": "documented",
        },
        vector_backbone_record={
            "backbone_name": "pET backbone context",
            "source_reference": "Backbone source note",
            "review_status": "documented",
        },
        cassette_rows=[
            {
                "promoter_label": "T7 promoter context",
                "gene_label": "crtI insert context",
                "terminator_label": "T7 terminator context",
                "source_reference": "Cassette notebook",
                "review_status": "documented",
            }
        ],
        sequence_basic_checks=[
            {
                "check_name": "Length",
                "recorded_value": "1482 bp",
                "review_status": "documented",
                "source_reference": "Read-only sequence check row",
            }
        ],
    )

    assert list(preview) == [
        "package_identity",
        "target_summary",
        "host_summary",
        "cassette_slot_rows",
        "cassette_slot_rows_presenter",
        "vector_backbone_summary",
        "sequence_basic_checks",
        "provenance_summary",
        "gap_follow_up_summary",
        "package_limitations",
    ]
    assert preview["package_identity"]["package_type"] == PACKAGE_TYPE
    assert preview["package_identity"]["package_title"] == "crtI expression vector documentation preview"
    assert preview["package_identity"]["source_commit_or_version"] == "test-commit"
    assert preview["target_summary"]["target_name"] == "crtI"
    assert preview["target_summary"]["cds_or_protein_value"] == "crtI CDS record"
    assert preview["host_summary"]["host_or_system"] == "E. coli BL21(DE3) context"
    assert preview["vector_backbone_summary"]["vector_or_backbone_name"] == "pET backbone context"
    assert preview["sequence_basic_checks"][0]["check_name"] == "Length"


def test_adapter_reuses_cassette_slot_rows_presenter_output() -> None:
    kwargs = {
        "target_record": {
            "recorded_value": "lacZ target record",
            "source_reference": "Manual target source",
            "review_status": "documented",
        },
        "host_record": {
            "recorded_value": "Documented host context",
            "source_reference": "Host notebook",
            "review_status": "documented",
        },
        "cassette_part_rows": [
            {
                "part_role": "promoter",
                "part_label": "Recorded promoter",
                "source_reference": "Promoter source note",
                "review_status": "documented",
            }
        ],
    }

    expected_presenter = build_expression_cassette_slot_rows_presenter(**kwargs)
    preview = build_expression_vector_design_package_preview(**kwargs)

    assert preview["cassette_slot_rows"] == expected_presenter["rows"]
    assert preview["cassette_slot_rows_presenter"]["summary"] == expected_presenter["summary"]
    assert preview["cassette_slot_rows_presenter"]["slot_order"] == expected_presenter["slot_order"]


def test_missing_source_provenance_is_collected_into_gap_follow_up_summary() -> None:
    preview = build_expression_vector_design_package_preview(
        target_record={
            "target_name": "Target from local note",
            "review_status": "documented",
        },
        cassette_part_rows=[
            {
                "part_role": "promoter",
                "part_label": "Promoter label without source",
                "review_status": "documented",
            }
        ],
    )

    gaps = preview["gap_follow_up_summary"]
    combined = " ".join(str(row) for row in gaps)

    assert preview["target_summary"]["review_status"] == "needs source"
    assert any(row["section"] == "target" and row["review_status"] == "needs source" for row in gaps)
    assert "cassette slot: Promoter" in combined
    assert "record source/provenance context" in combined


def test_package_identity_includes_deterministic_md5_and_identity_payload() -> None:
    first = build_expression_vector_design_package_preview(
        package_title="Stable identity preview",
        source_commit_or_version="abc123",
        target_record={"target_name": "Target A", "source_reference": "Source A"},
        host_record={"host_system": "Host A", "source_reference": "Host source"},
        vector_backbone_record={"backbone_name": "Backbone A", "source_reference": "Backbone source"},
    )
    second = build_expression_vector_design_package_preview(
        package_title="Stable identity preview",
        source_commit_or_version="abc123",
        target_record={"target_name": "Target A", "source_reference": "Source A"},
        host_record={"host_system": "Host A", "source_reference": "Host source"},
        vector_backbone_record={"backbone_name": "Backbone A", "source_reference": "Backbone source"},
    )
    changed = build_expression_vector_design_package_preview(
        package_title="Stable identity preview",
        source_commit_or_version="abc123",
        target_record={"target_name": "Target B", "source_reference": "Source A"},
        host_record={"host_system": "Host A", "source_reference": "Host source"},
        vector_backbone_record={"backbone_name": "Backbone A", "source_reference": "Backbone source"},
    )

    identity = first["package_identity"]

    assert identity["identity_payload"]["package_type"] == PACKAGE_TYPE
    assert identity["identity_payload"]["package_title"] == "Stable identity preview"
    assert identity["checksum_algorithm"] == "MD5"
    assert len(identity["md5"]) == 32
    assert identity["package_id"] == f"md5:{identity['md5']}"
    assert first["package_identity"]["md5"] == second["package_identity"]["md5"]
    assert first["package_identity"]["md5"] != changed["package_identity"]["md5"]


def test_package_limitations_state_documentation_only_non_goals() -> None:
    preview = build_expression_vector_design_package_preview()
    limitations = " ".join(preview["package_limitations"]).casefold()

    assert "documentation-only" in limitations
    assert "does not generate a final vector sequence" in limitations
    assert "does not provide protocol steps" in limitations
    assert "does not output codon-rewritten sequences" in limitations
    assert "does not recommend promoters" in limitations
    assert "does not claim experimental validation" in limitations


def test_output_avoids_positive_recommendation_validation_readiness_and_generation_claims() -> None:
    preview = build_expression_vector_design_package_preview(
        target_record={"target_name": "Target record", "source_reference": "Manual source note"},
        host_record={"host_system": "Host context", "source_reference": "Host source"},
        vector_backbone_record={"backbone_name": "Backbone context", "source_reference": "Backbone source"},
    )
    combined = str(preview).casefold()

    forbidden = [
        "recommended",
        "best promoter",
        "best host",
        "best vector",
        "validated construct",
        "build-ready",
        "ready-to-clone",
        "ready for execution",
        "wet-lab protocol",
        "cloning protocol",
        "yield prediction",
        "experimentally validated",
        "experiment-ready",
        "production-ready",
        "final vector generated",
        "generated final vector",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_minimal_empty_input_returns_safe_draft_needs_review_structure() -> None:
    preview = build_expression_vector_design_package_preview()

    assert preview["package_identity"]["package_status"] == DEFAULT_PACKAGE_STATUS
    assert preview["target_summary"]["target_name"] == "Not recorded"
    assert preview["host_summary"]["host_or_system"] == "Not recorded"
    assert preview["vector_backbone_summary"]["vector_or_backbone_name"] == "Not recorded"
    assert preview["sequence_basic_checks"][0]["review_status"] == "not assessed"
    assert preview["gap_follow_up_summary"]
    assert preview["cassette_slot_rows"]
