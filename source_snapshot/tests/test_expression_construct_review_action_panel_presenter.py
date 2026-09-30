from __future__ import annotations

import inspect
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.expression_construct_review_action_panel_presenter import (
    PANEL_BOUNDARY_NOTE,
    PANEL_NOTE,
    PANEL_STATUS_AVAILABLE,
    PANEL_STATUS_NOT_AVAILABLE,
    PANEL_TITLE,
    build_expression_construct_review_action_panel,
)


def _construct_section(**overrides) -> dict:
    data = {
        "summary_counts": {
            "review_gap_count": 1,
        },
        "construct_component_rows": [
            {"component_label": "Promoter row"},
            {"component_label": "CDS row"},
            {"component_label": "Terminator row"},
        ],
        "construct_component_review_summary": {
            "total_component_rows": 3,
            "rows_with_source_reference_context": 2,
            "rows_needing_manual_follow_up": 1,
        },
        "construct_component_manual_follow_up_readback": {
            "total_manual_follow_up_items": 1,
        },
        "review_gap_rows": [
            {"Gap type": "construct provenance", "Label": "Construct row"},
        ],
    }
    data.update(overrides)
    return data


def test_review_action_panel_builds_plain_rows_from_existing_payload() -> None:
    panel = build_expression_construct_review_action_panel(_construct_section())

    assert panel["status"] == PANEL_STATUS_AVAILABLE
    assert panel["panel_title"] == PANEL_TITLE
    assert panel["panel_note"] == PANEL_NOTE
    assert panel["boundary_notes"] == [PANEL_BOUNDARY_NOTE]
    assert panel["summary"] == {
        "row_count": 4,
        "missing_documentation_count": 2,
        "manual_follow_up_count": 1,
        "source_provenance_follow_up_count": 1,
    }

    rows_by_key = {row["key"]: row for row in panel["rows"]}
    assert list(rows_by_key) == [
        "missing_documentation",
        "needs_manual_follow_up",
        "source_provenance_review",
        "boundary_note",
    ]
    assert rows_by_key["missing_documentation"]["label"] == "Missing documentation"
    assert rows_by_key["missing_documentation"]["count"] == 2
    assert rows_by_key["needs_manual_follow_up"]["label"] == "Needs manual follow-up"
    assert rows_by_key["needs_manual_follow_up"]["count"] == 1
    assert rows_by_key["source_provenance_review"]["label"] == "Source/provenance review"
    assert rows_by_key["source_provenance_review"]["count"] == 1
    assert rows_by_key["boundary_note"]["label"] == "Boundary note"


def test_review_action_panel_uses_safe_empty_state_without_section() -> None:
    panel = build_expression_construct_review_action_panel(None)

    assert panel["status"] == PANEL_STATUS_NOT_AVAILABLE
    assert panel["summary"]["row_count"] == 4
    assert panel["summary"]["missing_documentation_count"] == 0
    assert panel["summary"]["manual_follow_up_count"] == 0
    assert all(isinstance(row, dict) for row in panel["rows"])


def test_review_action_panel_copy_is_bounded_and_has_no_write_behavior() -> None:
    source = inspect.getsource(build_expression_construct_review_action_panel)
    combined = f"{source}\n{build_expression_construct_review_action_panel(_construct_section())}".lower()

    forbidden = [
        "validated construct",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "optimized pathway",
        "yield prediction",
        "sequence output",
        "component selection",
    ]
    assert [phrase for phrase in forbidden if phrase in combined] == []
    assert "insert" not in source.lower()
    assert "update" not in source.lower()
    assert "delete" not in source.lower()
