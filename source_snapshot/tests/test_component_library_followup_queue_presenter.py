from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.component_library_followup_queue_presenter import (
    FOLLOWUP_QUEUE_BOUNDARY_NOTE,
    build_component_library_followup_queue_presenter,
    filter_followup_queue_rows,
    followup_queue_filter_options,
)


def test_followup_queue_flags_missing_source_evidence_review_deferred_and_boundary_rows() -> None:
    presenter = build_component_library_followup_queue_presenter(
        [
            {
                "asset_id": "asset-001",
                "asset_type": "promoter",
                "display_name": "Promoter source note",
                "missing_metadata_fields": ["source_label"],
                "review_status": "human review needed",
                "human_review_notes": "Confirm source citation before citing this design record.",
            }
        ]
    )

    rows = presenter["rows"]
    followup_types = [row["Follow-up type"] for row in rows]

    assert "Missing source/provenance" in followup_types
    assert "Missing evidence/reference" not in followup_types
    assert "Needs manual review" in followup_types
    assert "Deferred field" in followup_types
    assert "Boundary note" in followup_types
    assert all(row["Manual review"] == "Needs manual review" for row in rows)
    assert all(row["Boundary note"] == FOLLOWUP_QUEUE_BOUNDARY_NOTE for row in rows)

    summary = presenter["summary"]
    assert summary["total_followup_rows"] == len(rows)
    assert summary["components_with_followup"] == 1
    assert summary["records_with_followup"] == 1
    assert summary["followup_type_counts"]["Missing source/provenance"] == 1
    assert summary["followup_type_counts"]["Deferred field"] == 1
    assert summary["component_type_counts"] == {"promoter": len(rows)}
    assert summary["missing_source_provenance_count"] == 1
    assert summary["missing_evidence_reference_count"] == 0
    assert summary["needs_manual_review_count"] == followup_types.count("Needs manual review")
    assert summary["deferred_field_count"] == 1
    assert summary["boundary_note_count"] == 1
    assert {
        "Summary group": "Follow-up type",
        "Group value": "Missing source/provenance",
        "Rows": 1,
    } in summary["summary_rows"]
    assert {
        "Summary group": "Component type",
        "Group value": "promoter",
        "Rows": len(rows),
    } in summary["summary_rows"]


def test_followup_queue_uses_existing_readback_action_rows_without_persistence() -> None:
    presenter = build_component_library_followup_queue_presenter(
        [],
        construct_component_rows=[
            {
                "component_label": "Cassette component reference",
                "component_category": "terminator",
                "component_reference_label": "",
                "sequence_availability_status": "Sequence availability not recorded",
                "review_metadata_status": "Review metadata gap",
                "cassette_label": "Cassette A",
            }
        ],
    )

    rows = presenter["rows"]

    assert rows == [
        {
            "Component label": "Cassette component reference",
            "Component ID": "No source/reference context recorded",
            "Component type": "construct component reference",
            "Follow-up type": "Needs manual review",
            "Follow-up detail": (
                "Review next: record source/provenance identity and record review status "
                "in the existing review surface."
            ),
            "Manual review": "Needs manual review",
            "Boundary note": FOLLOWUP_QUEUE_BOUNDARY_NOTE,
        }
    ]
    assert presenter["summary"]["total_followup_rows"] == 1
    assert presenter["summary"]["records_with_followup"] == 1
    assert presenter["summary"]["component_type_counts"] == {"construct component reference": 1}
    assert presenter["summary"]["needs_manual_review_count"] == 1
    assert presenter["summary"]["missing_source_provenance_count"] == 0
    assert presenter["columns"] == [
        "Component label",
        "Component ID",
        "Component type",
        "Follow-up type",
        "Follow-up detail",
        "Manual review",
        "Boundary note",
    ]


def test_followup_queue_empty_state_for_recorded_context() -> None:
    presenter = build_component_library_followup_queue_presenter(
        [
            {
                "asset_id": "asset-002",
                "asset_type": "cds_target",
                "display_name": "CDS source note",
                "source_label": "Local Design Asset Catalog",
                "source_reference": "Project source note",
                "evidence_summary": "Recorded evidence/reference context for documentation review.",
                "review_status": "Source/reference metadata recorded for documentation review",
            }
        ]
    )

    assert presenter["rows"] == []
    assert presenter["summary"]["total_followup_rows"] == 0
    assert presenter["summary"]["summary_rows"] == []
    assert presenter["summary"]["component_type_counts"] == {}
    assert presenter["empty_state"].startswith("No Component Library source/provenance follow-up rows")


def test_followup_queue_filter_options_are_derived_from_existing_rows() -> None:
    rows = [
        {"Follow-up type": "Needs manual review", "Component type": "promoter"},
        {"Follow-up type": "Missing source/provenance", "Component type": "promoter"},
        {"Follow-up type": "Boundary note", "Component type": "terminator"},
        {"Follow-up type": "", "Component type": ""},
    ]

    options = followup_queue_filter_options(rows)

    assert options == {
        "followup_types": ["Boundary note", "Missing source/provenance", "Needs manual review"],
        "component_types": ["promoter", "terminator"],
    }


def test_followup_queue_filters_by_followup_type_and_component_type_without_mutating_rows() -> None:
    rows = [
        {"Follow-up type": "Needs manual review", "Component type": "promoter", "Component label": "A"},
        {"Follow-up type": "Boundary note", "Component type": "promoter", "Component label": "B"},
        {"Follow-up type": "Needs manual review", "Component type": "terminator", "Component label": "C"},
    ]

    filtered = filter_followup_queue_rows(
        rows,
        followup_types=["Needs manual review"],
        component_types=["promoter"],
    )

    assert filtered == [{"Follow-up type": "Needs manual review", "Component type": "promoter", "Component label": "A"}]
    assert filtered[0] is not rows[0]
    assert filter_followup_queue_rows(rows, followup_types=[], component_types=[]) == rows


def test_followup_queue_presenter_includes_filter_payload_and_filtered_empty_state() -> None:
    presenter = build_component_library_followup_queue_presenter(
        [
            {
                "asset_id": "asset-003",
                "asset_type": "terminator",
                "display_name": "Terminator source note",
                "missing_metadata_fields": ["source_reference"],
                "review_status": "human review needed",
            }
        ]
    )

    assert presenter["filter_options"]["followup_types"] == [
        "Boundary note",
        "Deferred field",
        "Missing source/provenance",
        "Needs manual review",
    ]
    assert presenter["filter_options"]["component_types"] == ["terminator"]
    assert presenter["filter_empty_state"].startswith("No follow-up rows match the current read-only filters")


def test_followup_queue_copy_avoids_forbidden_user_visible_phrases() -> None:
    presenter = build_component_library_followup_queue_presenter(
        [{"asset_type": "source_reference", "display_name": "Unidentified source note"}]
    )
    text = str(presenter).casefold()

    forbidden = [
        " ".join(("successful", "import")),
        " ".join(("project", "imported")),
        " ".join(("ready", "for", "execution")),
        "-".join(("experiment", "ready")),
        "-".join(("production", "ready")),
        " ".join(("validated", "construct")),
        " ".join(("optimized", "pathway")),
        " ".join(("yield", "prediction")),
        "-".join(("lab", "ready")),
        " ".join(("wet-lab", "ready")),
        " ".join(("proven", "construct")),
        " ".join(("validated", "pathway")),
    ]
    for phrase in forbidden:
        assert phrase not in text

    assert "documentation-only follow-up queue" in text
    assert "not a biology-use recommendation, validation claim, optimization claim, or wet-lab use judgment" in text
    assert "does not recommend or select components" in text
