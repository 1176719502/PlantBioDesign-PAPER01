from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.expression_cassette_slot_rows_presenter import (
    SAFETY_BOUNDARY_NOTE,
    SLOT_ORDER,
    build_expression_cassette_slot_rows,
    build_expression_cassette_slot_rows_presenter,
)


def _row(rows: list[dict[str, str]], slot_key: str) -> dict[str, str]:
    return next(row for row in rows if row["slot_key"] == slot_key)


def test_returns_expression_vector_first_slot_order() -> None:
    rows = build_expression_cassette_slot_rows()

    assert [row["slot_key"] for row in rows] == SLOT_ORDER
    assert [row["slot_label"] for row in rows[:4]] == [
        "Target Gene / CDS / Protein",
        "Sequence Source / Provenance",
        "Expression Host",
        "Promoter",
    ]
    assert rows[-1]["slot_label"] == "Gap / Follow-up Review"
    assert all(row["safety_boundary_note"] == SAFETY_BOUNDARY_NOTE for row in rows)


def test_minimal_input_returns_stable_read_only_rows() -> None:
    presenter = build_expression_cassette_slot_rows_presenter(
        target_record={
            "recorded_value": "crtI CDS documentation record",
            "source_reference": "Notebook target source",
            "review_status": "documented",
        },
        host_record={
            "recorded_value": "E. coli BL21(DE3) documentation context",
            "source_reference": "Host note",
            "review_status": "documented",
        },
        cassette_rows=[
            {
                "promoter_label": "T7 promoter context",
                "gene_label": "crtI insert context",
                "terminator_label": "T7 terminator context",
                "source_reference": "Cassette notebook",
                "provenance_note": "Recorded for traceability review.",
                "review_status": "documented",
            }
        ],
        construct_profile={
            "plasmid_backbone": "pET backbone context",
            "source_reference": "Backbone source note",
            "review_status": "documented",
        },
        sequence_check_record={
            "length": 1482,
            "gc_percent": "52.0%",
            "frame_status": "read-only frame check recorded",
            "review_status": "documented",
        },
    )

    rows = presenter["rows"]

    assert presenter["columns"][0] == "slot_key"
    assert presenter["slot_order"] == SLOT_ORDER
    assert presenter["summary"]["total_slot_rows"] == len(SLOT_ORDER)
    assert _row(rows, "target_gene_cds_protein")["recorded_value"] == "crtI CDS documentation record"
    assert _row(rows, "expression_host")["recorded_value"] == "E. coli BL21(DE3) documentation context"
    assert _row(rows, "promoter")["recorded_value"] == "T7 promoter context"
    assert _row(rows, "cds_insert")["recorded_value"] == "crtI insert context"
    assert _row(rows, "terminator_polya")["recorded_value"] == "T7 terminator context"
    assert _row(rows, "sequence_basic_checks")["recorded_value"] == (
        "length: 1482; GC: 52.0%; frame: read-only frame check recorded"
    )


def test_missing_source_provenance_becomes_manual_review_gap() -> None:
    rows = build_expression_cassette_slot_rows(
        target_record={
            "recorded_value": "Target sequence pasted from local note",
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

    target_row = _row(rows, "target_gene_cds_protein")
    promoter_row = _row(rows, "promoter")
    source_row = _row(rows, "sequence_source_provenance")
    follow_up_row = _row(rows, "gap_follow_up_review")

    assert target_row["review_status"] == "needs source"
    assert promoter_row["review_status"] == "needs source"
    assert "record source/provenance context" in promoter_row["gap_or_follow_up"]
    assert source_row["review_status"] == "needs source"
    assert "manual follow-up item" in follow_up_row["recorded_value"]
    assert "needs source" in follow_up_row["notes"]


def test_missing_optional_slots_are_optional_not_errors() -> None:
    rows = build_expression_cassette_slot_rows(
        target_record={
            "recorded_value": "lacZ target record",
            "source_reference": "Manual source note",
        },
        host_record={
            "recorded_value": "Documented host context",
            "source_reference": "Host notebook",
        },
        cassette_part_rows=[
            {
                "part_role": "promoter",
                "part_label": "Recorded promoter",
                "source_reference": "Promoter source note",
            },
            {
                "part_role": "cds",
                "part_label": "Recorded CDS",
                "source_reference": "CDS source note",
            },
        ],
        construct_profile={
            "plasmid_backbone": "Recorded backbone context",
            "source_reference": "Backbone notebook",
        },
    )

    optional_keys = [
        "rbs_kozak_5utr",
        "signal_peptide",
        "fusion_tag",
        "linker",
        "terminator_polya",
        "selectable_marker_reporter",
    ]

    for key in optional_keys:
        row = _row(rows, key)
        assert row["recorded_value"] == "Not provided"
        assert row["review_status"] == "optional / not provided"
        assert row["gap_or_follow_up"] == "Optional slot not provided in current documentation input."


def test_vector_backbone_is_documentation_context_not_assembled_output() -> None:
    rows = build_expression_cassette_slot_rows(
        construct_profile={
            "plasmid_backbone": "pUC-derived backbone context",
            "source_reference": "Backbone source record",
            "provenance_note": "Manual backbone provenance note.",
            "review_status": "documented",
        }
    )

    backbone_row = _row(rows, "vector_backbone")
    combined = " ".join(backbone_row.values()).casefold()

    assert backbone_row["slot_group"] == "vector/context"
    assert backbone_row["recorded_value"] == "pUC-derived backbone context"
    assert backbone_row["review_status"] == "documented"
    assert "assemble" in backbone_row["safety_boundary_note"]
    assert "final vector sequence" not in combined
    assert "ready-to-clone" not in combined
    assert "build-ready" not in combined


def test_consumes_component_library_step2_and_construct_style_rows() -> None:
    rows = build_expression_cassette_slot_rows(
        component_library_rows=[
            {
                "asset_type": "marker_metadata",
                "display_name": "Kanamycin marker documentation record",
                "asset_id": "marker-001",
                "provenance_status": "source review needed",
                "review_status": "needs review",
                "human_review_notes": "Review source record before package citation.",
            }
        ],
        step2_context_rows=[
            {
                "key": "translation_initiation_context",
                "step2_value": "Shine-Dalgarno context",
                "asset_label": "RBS documentation record",
                "asset_id": "rbs-001",
                "source_provenance_review": "source review needed",
                "record_review_status": "needs review",
            }
        ],
        cassette_part_rows=[
            {
                "part_role": "signal_peptide",
                "part_label": "PelB signal peptide context",
                "source_catalog": "Local Design Asset Catalog",
                "source_record_id": "signal-001",
                "review_metadata_status": "documented",
            },
            {
                "component_category": "tag",
                "component_label": "His6 tag context",
                "source_reference": "Tag source note",
                "review_status": "documented",
            },
        ],
    )

    assert _row(rows, "selectable_marker_reporter")["recorded_value"] == (
        "Kanamycin marker documentation record"
    )
    assert _row(rows, "rbs_kozak_5utr")["recorded_value"] == "RBS documentation record"
    assert _row(rows, "signal_peptide")["recorded_value"] == "PelB signal peptide context"
    assert _row(rows, "fusion_tag")["recorded_value"] == "His6 tag context"
    assert _row(rows, "component_source")["recorded_value"].endswith("component source/provenance row(s) recorded")


def test_presenter_copy_avoids_recommendation_optimization_validation_protocol_and_readiness_claims() -> None:
    output = build_expression_cassette_slot_rows_presenter(
        target_record={
            "recorded_value": "Target record",
            "source_reference": "Manual source note",
            "review_status": "documented",
        },
        cassette_part_rows=[
            {
                "part_role": "promoter",
                "part_label": "Recorded promoter",
                "source_reference": "Promoter source note",
                "review_status": "documented",
            }
        ],
    )
    combined = str(output).casefold()

    forbidden = [
        "optimized",
        "recommended",
        "validated",
        "best promoter",
        "best host",
        "best vector",
        "build-ready",
        "ready-to-clone",
        "ready for execution",
        "wet-lab protocol",
        "cloning protocol",
        "yield prediction",
        "experimentally validated",
        "experiment-ready",
        "production-ready",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
    assert "documentation-only" in combined
    assert "manual review" in combined
