from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.component_library_slot_browse_presenter import (
    MANUAL_FOLLOW_UP_NEEDED,
    SLOT_BROWSE_EMPTY_STATE,
    SLOT_LABELS,
    SOURCE_PROVENANCE_MISSING_STATUS,
    build_component_library_slot_browse_presenter,
)


def _record(
    asset_id: str,
    asset_type: str,
    display_name: str,
    *,
    provenance_status: str = "source reviewed",
    review_status: str = "human reviewed",
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "display_name": display_name,
        "aliases": [],
        "short_description": "Documentation-only component record.",
        "organism_or_source_context": "local expression context",
        "sequence_available": False,
        "source_notes": "Local source note.",
        "provenance_status": provenance_status,
        "version_context": "seed v2.6",
        "review_status": review_status,
        "human_review_notes": "Manual review note.",
        "tags": [asset_type],
        "documentation_boundary_note": "Documentation-only metadata record for review and traceability.",
    }


def test_slot_browse_presenter_exposes_plant_expression_context_labels() -> None:
    presenter = build_component_library_slot_browse_presenter(
        [
            _record("prom-1", "promoter", "Promoter documentation record"),
            _record("rbs-1", "rbs_5utr", "RBS / UTR documentation record"),
            _record("cds-1", "cds_target", "CDS target documentation record"),
            _record("sig-1", "signal_peptide", "Signal peptide documentation record"),
            _record("tag-1", "tag", "Fusion tag documentation record"),
            _record("term-1", "terminator", "Terminator documentation record"),
            _record("marker-1", "marker_metadata", "Selectable marker documentation record"),
            _record("backbone-1", "plasmid_backbone", "Vector backbone documentation record"),
            _record("host-1", "host_chassis_context_note", "Host context documentation record"),
            _record("transit-1", "transit_peptide", "Transit peptide documentation record"),
            _record("targeting-1", "subcellular_targeting", "Subcellular targeting documentation record"),
            _record("tissue-1", "tissue_context", "Tissue context documentation record"),
            _record("mode-1", "expression_mode", "Expression mode documentation record"),
            _record("source-1", "literature_source_note", "Source note documentation record"),
        ]
    )

    assert "Component records by plant expression construct context" == presenter["title"]
    assert "plant-expression-construct context" in presenter["intro"]
    assert "documentation-only review" in presenter["intro"]
    for label in (
        "Plant promoter context",
        "RBS / Kozak / UTR",
        "CDS / Insert",
        "Signal peptide",
        "Transit peptide",
        "Subcellular targeting",
        "Fusion Tag / Linker",
        "Terminator context",
        "Selectable Marker / Reporter",
        "Vector / backbone context",
        "Plant species / host context",
        "Tissue / organ / expression compartment",
        "Expression mode",
        "Source / Provenance",
        "Manual Follow-up",
    ):
        assert label in SLOT_LABELS
        assert any(row["Slot"] == label for row in presenter["rows"])
    assert presenter["summary"]["slot_rows_with_records"] == 14


def test_slot_browse_marks_missing_source_as_manual_follow_up_not_recommendation() -> None:
    presenter = build_component_library_slot_browse_presenter(
        [
            _record(
                "prom-2",
                "promoter",
                "Promoter needing source review",
                provenance_status="",
                review_status="human review needed",
            )
        ],
        selected_slot_label="Plant promoter context",
    )

    row = presenter["rows"][0]
    assert row["Slot"] == "Plant promoter context"
    assert row["Record count"] == "1"
    assert SOURCE_PROVENANCE_MISSING_STATUS in row["Source/provenance status"]
    assert MANUAL_FOLLOW_UP_NEEDED in row["Manual follow-up"]
    joined = " ".join(str(value) for value in row.values()).casefold()
    for phrase in ("best promoter", "best host", "best vector", "optimized sequence", "validated construct"):
        assert phrase not in joined


def test_slot_browse_treats_source_review_needed_as_source_follow_up() -> None:
    presenter = build_component_library_slot_browse_presenter(
        [
            _record(
                "host-2",
                "host_chassis_context_note",
                "Host context needing source review",
                provenance_status="source review needed",
                review_status="human reviewed",
            )
        ],
        selected_slot_label="Plant species / host context",
    )

    row = presenter["rows"][0]
    assert SOURCE_PROVENANCE_MISSING_STATUS in row["Source/provenance status"]
    assert MANUAL_FOLLOW_UP_NEEDED in row["Manual follow-up"]
    assert presenter["summary"]["source_follow_up_slot_count"] == 1


def test_slot_browse_empty_state_is_clear_when_no_records_exist() -> None:
    presenter = build_component_library_slot_browse_presenter([])

    assert presenter["rows"] == []
    assert presenter["empty_state"] == SLOT_BROWSE_EMPTY_STATE
    assert "No component records are available yet" in presenter["empty_state"]
    assert "plant expression construct review" in presenter["empty_state"]


def test_slot_browse_filter_limits_rows_to_selected_slot() -> None:
    presenter = build_component_library_slot_browse_presenter(
        [
            _record("prom-3", "promoter", "Promoter documentation record"),
            _record("cds-3", "cds_target", "CDS documentation record"),
        ],
        selected_slot_label="CDS / Insert",
    )

    assert [row["Slot"] for row in presenter["rows"]] == ["CDS / Insert"]
    assert presenter["rows"][0]["Records"] == "CDS documentation record"


def test_slot_browse_filter_accepts_new_all_plant_context_label() -> None:
    presenter = build_component_library_slot_browse_presenter(
        [
            _record("prom-4", "promoter", "Promoter documentation record"),
            _record("mode-4", "expression_mode", "Expression mode documentation record"),
        ],
        selected_slot_label="All plant expression construct contexts",
    )

    assert len(presenter["rows"]) == len(SLOT_LABELS)
    assert any(row["Slot"] == "Plant promoter context" for row in presenter["rows"])
    assert any(row["Slot"] == "Expression mode" for row in presenter["rows"])


def test_slot_browse_boundary_excludes_plant_readiness_or_prediction_claims() -> None:
    presenter = build_component_library_slot_browse_presenter(
        [_record("target-1", "subcellular_targeting", "Subcellular targeting documentation record")]
    )

    boundary = presenter["boundary_note"].casefold()
    assert "does not choose" in boundary
    assert "validate plant lines" in boundary
    assert "certify construct readiness" in boundary
    assert "predict outcomes" in boundary
