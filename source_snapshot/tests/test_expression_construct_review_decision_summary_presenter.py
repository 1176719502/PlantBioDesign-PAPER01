from __future__ import annotations

import inspect
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.expression_construct_review_decision_summary_presenter import (
    REVIEW_FRAME_NOTE,
    REVIEW_STATUS_MISSING,
    REVIEW_STATUS_NEEDS_FOLLOW_UP,
    REVIEW_STATUS_REVIEWABLE,
    build_expression_construct_review_decision_summary,
)


def _construct_section(**overrides) -> dict:
    data = {
        "summary_counts": {
            "construct_profile_count": 1,
            "cassette_count": 1,
            "cassette_part_count": 3,
            "review_gap_count": 2,
        },
        "construct_component_rows": [
            {"component_label": "Promoter row"},
            {"component_label": "CDS row"},
            {"component_label": "Terminator row"},
        ],
        "construct_component_review_summary": {
            "total_component_rows": 3,
            "rows_with_source_reference_context": 2,
            "rows_missing_source_reference_context": 1,
            "rows_needing_manual_follow_up": 1,
        },
        "construct_component_manual_follow_up_readback": {
            "total_manual_follow_up_items": 1,
        },
        "boundary_notes": [
            "Documentation-only construct review context.",
        ],
    }
    data.update(overrides)
    return data


def test_review_decision_summary_reflects_existing_review_payload() -> None:
    summary = build_expression_construct_review_decision_summary(_construct_section())

    assert summary["status"] == "AVAILABLE"
    assert summary["review_summary_status"] == REVIEW_STATUS_NEEDS_FOLLOW_UP
    assert summary["documented_slots_count"] == 3
    assert summary["missing_slots_count"] == 1
    assert summary["manual_follow_up_count"] == 1
    assert summary["source_provenance_coverage_count"] == 2
    assert summary["source_provenance_coverage_label"] == "Source/provenance recorded"
    assert summary["review_summary_note"] == REVIEW_FRAME_NOTE
    assert summary["boundary_notes"] == ["Documentation-only construct review context."]


def test_review_decision_summary_uses_safe_empty_state_when_no_section_is_available() -> None:
    summary = build_expression_construct_review_decision_summary(None)

    assert summary["status"] == "NOT_AVAILABLE"
    assert summary["review_summary_status"] == REVIEW_STATUS_MISSING
    assert summary["documented_slots_count"] == 0
    assert summary["missing_slots_count"] == 0
    assert summary["manual_follow_up_count"] == 0
    assert summary["warnings"]


def test_review_decision_summary_is_pure_python_and_bounded() -> None:
    source = inspect.getsource(build_expression_construct_review_decision_summary)
    combined = "\n".join(
        [
            source,
            str(build_expression_construct_review_decision_summary(_construct_section())),
        ]
    ).lower()

    forbidden = [
        "validated construct",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "optimized pathway",
        "yield prediction",
        "wet-lab readiness",
        "biological recommendation",
        "build-ready",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []
    assert REVIEW_STATUS_REVIEWABLE in {"Reviewable", "Needs manual follow-up", "Missing documentation"}
