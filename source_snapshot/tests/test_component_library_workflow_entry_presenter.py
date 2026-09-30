from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.component_library_workflow_entry_presenter import (
    ALL_FOLLOWUP_FILTER,
    ALL_SLOT_FILTER,
    ALL_SOURCE_FILTER,
    ALL_TYPE_FILTER,
    FOLLOWUP_NEEDED,
    SOURCE_NEEDS_REVIEW,
    SOURCE_RECORDED,
    WORKFLOW_ENTRY_COLUMNS,
    build_component_library_workflow_entry_presenter,
    build_component_library_workflow_entry_rows,
    filter_component_library_workflow_entry_rows,
)


def _record(
    asset_id: str,
    asset_type: str,
    display_name: str,
    *,
    provenance_status: str = "source reviewed",
    review_status: str = "human reviewed",
    source_notes: str = "Recorded source/provenance note.",
    human_review_notes: str = "Recorded review note.",
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "display_name": display_name,
        "short_description": "Documentation-only component record.",
        "organism_or_source_context": "plant expression context",
        "sequence_available": False,
        "source_notes": source_notes,
        "provenance_status": provenance_status,
        "version_context": "seed v2.7",
        "review_status": review_status,
        "human_review_notes": human_review_notes,
        "tags": [asset_type],
        "documentation_boundary_note": "Documentation-only metadata record for review and traceability.",
    }


def test_workflow_entry_summary_counts_registry_and_workflow_records() -> None:
    presenter = build_component_library_workflow_entry_presenter(
        [
            _record("prom-1", "promoter", "Promoter source record"),
            _record(
                "cds-1",
                "cds_target",
                "CDS source record needing review",
                provenance_status="source review needed",
                review_status="human review needed",
            ),
        ],
        saved_registry_record_count=3,
    )

    summary = presenter["summary"]
    assert summary["total_records"] == 5
    assert summary["workflow_records"] == 2
    assert summary["saved_registry_records"] == 3
    assert summary["records_with_source_provenance"] == 1
    assert summary["records_needing_source_provenance_review"] == 1
    assert summary["records_needing_manual_review"] == 1
    assert summary["slot_group_count"] == 2
    assert summary["filtered_records"] == 2


def test_workflow_entry_filters_by_slot_type_source_and_followup_state() -> None:
    rows = build_component_library_workflow_entry_rows(
        [
            _record("prom-2", "promoter", "Recorded promoter source record"),
            _record(
                "term-2",
                "terminator",
                "Terminator source record needing review",
                provenance_status="source review needed",
                review_status="human review needed",
            ),
        ]
    )

    filtered = filter_component_library_workflow_entry_rows(
        rows,
        slot="Terminator context",
        component_type="terminator",
        source_status=SOURCE_NEEDS_REVIEW,
        followup_status=FOLLOWUP_NEEDED,
    )

    assert [row["Component label"] for row in filtered] == ["Terminator source record needing review"]
    assert filter_component_library_workflow_entry_rows(
        rows,
        slot=ALL_SLOT_FILTER,
        component_type=ALL_TYPE_FILTER,
        source_status=ALL_SOURCE_FILTER,
        followup_status=ALL_FOLLOWUP_FILTER,
    ) == rows


def test_workflow_entry_surfaces_missing_provenance_and_followup_cards() -> None:
    presenter = build_component_library_workflow_entry_presenter(
        [
            _record(
                "host-1",
                "host_chassis_context_note",
                "Host context missing source note",
                provenance_status="source review needed",
                review_status="human review needed",
                source_notes="",
                human_review_notes="source_review_required",
            )
        ],
        source_status=SOURCE_NEEDS_REVIEW,
        followup_status=FOLLOWUP_NEEDED,
    )

    assert presenter["filtered_rows"][0]["Slot"] == "Plant species / host context"
    assert presenter["filtered_rows"][0]["Source/provenance status"] == SOURCE_NEEDS_REVIEW
    assert presenter["filtered_rows"][0]["Follow-up status"] == FOLLOWUP_NEEDED
    assert presenter["cards"][0]["Component label"] == "Host context missing source note"
    assert presenter["slot_groups"] == [
        {
            "Slot": "Plant species / host context",
            "Record count": "1",
            "Source/provenance review": "1",
            "Manual review": "1",
        }
    ]


def test_workflow_entry_full_detail_rows_remain_accessible() -> None:
    presenter = build_component_library_workflow_entry_presenter(
        [_record("tag-1", "tag", "Tag/linker documentation record")],
    )

    row = presenter["rows"][0]
    assert presenter["columns"] == WORKFLOW_ENTRY_COLUMNS
    assert row["Slot"] == "Fusion Tag / Linker"
    assert row["Record ID"] == "tag-1"
    assert row["Source/provenance status"] == SOURCE_RECORDED
    assert row["Review status"] == "human reviewed"
    assert row["Source/provenance detail"] == "Recorded source/provenance note."
    assert row["Short description"] == "Documentation-only component record."
    assert row["Documentation boundary"] == "Documentation-only metadata record for review and traceability."


def test_workflow_entry_visible_copy_avoids_forbidden_claims() -> None:
    presenter = build_component_library_workflow_entry_presenter(
        [_record("source-1", "literature_source_note", "Source note record")]
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
        " ".join(("wet-lab", "readiness")),
        " ".join(("proven", "construct")),
        " ".join(("validated", "pathway")),
    ]
    for phrase in forbidden:
        assert phrase not in text

    assert "documentation-only component library entry view" in text
    assert "manual review" in text
