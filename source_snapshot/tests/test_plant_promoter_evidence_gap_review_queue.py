# -*- coding: utf-8 -*-
from __future__ import annotations

from services import plant_promoter_evidence_gap_review_queue as queue


def _complete_view_model() -> dict[str, object]:
    return {
        "profile_rows": [
            {
                "part_id": "plant-promoter-complete",
                "display_name": "Complete promoter record",
                "plant_clade": "monocot",
                "species_label": "Zea mays (maize)",
                "promoter_type": "source-recorded promoter context",
                "sequence_availability": "metadata-only sequence context",
            }
        ],
        "evidence_rows": [
            {
                "part_id": "plant-promoter-complete",
                "promoter_label": "Complete promoter record",
                "tissue_context": "root",
                "source_database": "Fixture source",
                "curation_status": "metadata reviewed",
                "review_note": "Documentation review captured.",
            }
        ],
        "rows_needing_review": [],
        "context_readback_rows": [
            {
                "promoter_label": "Complete promoter record",
                "catalog_context": "Complete promoter record",
                "metadata_gap": "No metadata gap recorded",
            }
        ],
    }


def test_empty_input_returns_safe_empty_state() -> None:
    result = queue.build_plant_promoter_evidence_gap_review_queue({})

    assert result["summary_counts"] == {
        "profile_count": 0,
        "queue_item_count": 0,
        "category_count": 0,
    }
    assert result["queue_item_rows"] == []
    assert result["category_counts"]["source_provenance_gap"] == 0
    assert "Supports documentation review and human curation only." in result["boundary_notes"]


def test_complete_record_produces_no_gap_items() -> None:
    result = queue.build_plant_promoter_evidence_gap_review_queue(_complete_view_model())

    assert result["summary_counts"]["queue_item_count"] == 0
    assert result["queue_item_rows"] == []


def test_missing_source_tissue_species_review_and_metadata_create_expected_categories() -> None:
    result = queue.build_plant_promoter_evidence_gap_review_queue(
        {
            "profile_rows": [
                {
                    "part_id": "plant-promoter-gap",
                    "display_name": "Gap-heavy promoter",
                    "plant_clade": "other / not specified",
                    "species_label": "No species context recorded",
                    "promoter_type": "",
                    "sequence_availability": "",
                }
            ],
            "evidence_rows": [
                {
                    "part_id": "plant-promoter-gap",
                    "promoter_label": "Gap-heavy promoter",
                    "tissue_context": "No tissue context recorded",
                    "source_database": "No source database recorded",
                    "curation_status": "No curation status recorded",
                    "review_note": "",
                }
            ],
            "rows_needing_review": [
                {
                    "part_id": "plant-promoter-gap",
                    "display_name": "Gap-heavy promoter",
                    "tissue_context": "No tissue context recorded",
                    "curation_status": "No curation status recorded",
                    "review_note": "Needs documentation follow-up.",
                }
            ],
            "context_readback_rows": [
                {
                    "promoter_label": "Gap-heavy promoter",
                    "catalog_context": "Gap-heavy promoter",
                    "metadata_gap": "species context metadata gap; tissue evidence context metadata gap",
                }
            ],
        }
    )

    categories = [row["category"] for row in result["queue_item_rows"]]

    assert categories == [
        "source_provenance_gap",
        "tissue_context_gap",
        "species_or_clade_context_gap",
        "review_status_gap",
        "metadata_gap",
        "documentation_follow_up",
    ]
    assert result["category_counts"] == {
        "source_provenance_gap": 1,
        "tissue_context_gap": 1,
        "species_or_clade_context_gap": 1,
        "review_status_gap": 1,
        "metadata_gap": 1,
        "documentation_follow_up": 1,
    }
    assert result["queue_item_rows"][0]["queue_item_id"] == "plant-promoter-gap::source_provenance_gap"


def test_output_order_is_deterministic_across_multiple_profiles() -> None:
    result = queue.build_plant_promoter_evidence_gap_review_queue(
        {
            "profile_rows": [
                {
                    "part_id": "b-promoter",
                    "display_name": "Beta promoter",
                    "plant_clade": "monocot",
                    "species_label": "Zea mays (maize)",
                },
                {
                    "part_id": "a-promoter",
                    "display_name": "Alpha promoter",
                    "plant_clade": "monocot",
                    "species_label": "No species context recorded",
                },
            ],
            "evidence_rows": [],
            "rows_needing_review": [],
            "context_readback_rows": [],
        }
    )

    assert [row["queue_item_id"] for row in result["queue_item_rows"][:4]] == [
        "a-promoter::source_provenance_gap",
        "b-promoter::source_provenance_gap",
        "a-promoter::tissue_context_gap",
        "b-promoter::tissue_context_gap",
    ]


def test_boundary_notes_keep_negative_safety_language() -> None:
    combined = "\n".join(queue.BOUNDARY_NOTES).lower()
    forbidden = [
        "best promoter",
        "recommended promoter",
        "validated promoter",
        "ranked promoter",
        "scored promoter",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
