# -*- coding: utf-8 -*-
from __future__ import annotations

from services.project_review_follow_up_index import build_project_review_follow_up_index


def test_empty_inputs_return_safe_empty_state() -> None:
    index = build_project_review_follow_up_index({}, {})

    assert index["status"] == "NOT_AVAILABLE"
    assert index["summary"]["total_follow_up_items"] == 0
    assert index["summary"]["source_section_counts"] == {
        "candidate_evidence": 0,
        "plant_promoter_catalog": 0,
    }
    assert index["rows"] == []
    assert "manual documentation review and triage only" in index["boundary_notes"][0].lower()
    assert "Review next: open existing review surfaces for candidate evidence" in index["empty_state_message"]


def test_candidate_only_queue_is_aggregated() -> None:
    index = build_project_review_follow_up_index(
        {
            "summary": {
                "queue_item_count": 2,
                "category_counts": {
                    "Documentation gap": 1,
                    "Human review follow-up": 1,
                },
            },
            "rows": [
                {
                    "queue_item_id": "candidate-review-001-01",
                    "candidate_label": "Candidate A",
                    "category_label": "Documentation gap",
                    "issue": "Documentation review remains available for confirmation.",
                    "human_follow_up": "Confirm the recorded documentation context during manual review if needed.",
                    "source_context": "Plant Promoter Catalog / PP-001",
                },
                {
                    "queue_item_id": "candidate-review-002-review",
                    "candidate_label": "Candidate B",
                    "category_label": "Human review follow-up",
                    "issue": "Records needing manual follow-up",
                    "human_follow_up": "Review the current documentation context and record a human review note.",
                    "source_context": "Plant Promoter Catalog / PP-002",
                },
            ],
        },
        {},
    )

    assert index["status"] == "AVAILABLE"
    assert index["summary"]["total_follow_up_items"] == 2
    assert index["summary"]["source_section_counts"]["candidate_evidence"] == 2
    assert index["summary"]["category_counts"]["Documentation gap"] == 1
    assert index["rows"][0]["follow_up_id"].startswith("candidate_evidence::")


def test_promoter_only_queue_is_aggregated() -> None:
    index = build_project_review_follow_up_index(
        {},
        {
            "summary_counts": {
                "queue_item_count": 2,
            },
            "category_counts": {
                "source_provenance_gap": 1,
                "documentation_follow_up": 1,
            },
            "rows": [
                {
                    "queue_item_id": "plant-promoter-001::source_provenance_gap",
                    "promoter_label": "Promoter A",
                    "category": "source_provenance_gap",
                    "issue": "Source/provenance gap remains visible for this promoter record.",
                    "human_follow_up": "Add or confirm source database or accession context for documentation review.",
                    "source_context": "No source context recorded",
                },
                {
                    "queue_item_id": "plant-promoter-001::documentation_follow_up",
                    "promoter_label": "Promoter A",
                    "category": "documentation_follow_up",
                    "issue": "Documentation follow-up remains open for source or metadata review.",
                    "human_follow_up": "Use the queue as a human curation checklist only.",
                    "source_context": "No source context recorded",
                },
            ],
        },
    )

    assert index["summary"]["total_follow_up_items"] == 2
    assert index["summary"]["source_section_counts"]["plant_promoter_catalog"] == 2
    assert index["summary"]["category_counts"]["documentation_follow_up"] == 1
    assert all(row["source_section"] == "plant_promoter_catalog" for row in index["rows"])


def test_placeholder_source_context_is_not_presented_as_manual_review_context() -> None:
    index = build_project_review_follow_up_index(
        {
            "summary": {"queue_item_count": 1},
            "rows": [
                {
                    "queue_item_id": "candidate-review-placeholder",
                    "candidate_label": "Candidate placeholder",
                    "category_label": "Source/provenance gap",
                    "issue": "Missing source/provenance details",
                    "human_follow_up": "Record source context.",
                    "source_context": "Unknown",
                }
            ],
        },
        {
            "summary_counts": {"queue_item_count": 1},
            "rows": [
                {
                    "queue_item_id": "promoter-placeholder::source_provenance_gap",
                    "promoter_label": "Promoter placeholder",
                    "category": "source_provenance_gap",
                    "issue": "Source/provenance gap remains visible for this promoter record.",
                    "human_follow_up": "Record provenance.",
                    "source_context": "N/A",
                }
            ],
        },
    )

    assert [row["manual_review_context"] for row in index["rows"]] == [
        "No source context recorded",
        "No source context recorded",
    ]


def test_combined_index_is_deterministic() -> None:
    index = build_project_review_follow_up_index(
        {
            "summary": {"queue_item_count": 1, "category_counts": {"Human review follow-up": 1}},
            "rows": [
                {
                    "queue_item_id": "candidate-review-001-review",
                    "candidate_label": "Zulu candidate",
                    "category_label": "Human review follow-up",
                    "issue": "Records needing manual follow-up",
                    "human_follow_up": "Review context.",
                    "source_context": "Catalog Z / Z-001",
                }
            ],
        },
        {
            "summary_counts": {"queue_item_count": 2},
            "category_counts": {
                "documentation_follow_up": 1,
                "source_provenance_gap": 1,
            },
            "rows": [
                {
                    "queue_item_id": "alpha-promoter::documentation_follow_up",
                    "promoter_label": "Alpha promoter",
                    "category": "documentation_follow_up",
                    "issue": "Documentation follow-up remains open for source or metadata review.",
                    "human_follow_up": "Checklist only.",
                    "source_context": "No source context recorded",
                },
                {
                    "queue_item_id": "alpha-promoter::source_provenance_gap",
                    "promoter_label": "Alpha promoter",
                    "category": "source_provenance_gap",
                    "issue": "Source/provenance gap remains visible for this promoter record.",
                    "human_follow_up": "Record provenance.",
                    "source_context": "No source context recorded",
                },
            ],
        },
    )

    assert [
        (row["source_section"], row["item_label"], row["category"])
        for row in index["rows"]
    ] == [
        ("candidate_evidence", "Zulu candidate", "Human review follow-up"),
        ("plant_promoter_catalog", "Alpha promoter", "documentation_follow_up"),
        ("plant_promoter_catalog", "Alpha promoter", "source_provenance_gap"),
    ]
