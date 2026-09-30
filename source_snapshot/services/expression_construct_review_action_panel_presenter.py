from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.expression_construct_review_decision_summary_presenter import (
    REVIEW_FRAME_NOTE,
    REVIEW_STATUS_MISSING,
    REVIEW_STATUS_NEEDS_FOLLOW_UP,
    build_expression_construct_review_decision_summary,
)
from services.project_output_boundary_copy import PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE


PANEL_TITLE = "Review action panel"
PANEL_STATUS_AVAILABLE = "AVAILABLE"
PANEL_STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"
PANEL_NOTE = (
    "Read-only documentation review actions from the current construct review payload; "
    "manual review remains responsible for interpretation."
)
PANEL_BOUNDARY_NOTE = (
    "Review actions are documentation follow-up cues only. "
    f"{PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE}"
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or [] if isinstance(row, Mapping)]


def _int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _status_for_count(count: int, active_status: str, empty_status: str) -> str:
    return active_status if count > 0 else empty_status


def _row(
    *,
    key: str,
    label: str,
    status: str,
    count: int,
    review_action: str,
    source: str,
    boundary_note: str = PANEL_BOUNDARY_NOTE,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "count": count,
        "review_action": review_action,
        "source": source,
        "boundary_note": boundary_note,
    }


def build_expression_construct_review_action_panel(
    construct_section: Mapping[str, Any] | None,
    documentation_review_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build read-only review action rows from existing construct review payloads."""
    section = _mapping(construct_section)
    summary = _mapping(documentation_review_summary)
    if not summary:
        summary = build_expression_construct_review_decision_summary(section)

    summary_counts = _mapping(section.get("summary_counts"))
    review_gap_rows = _rows(section.get("review_gap_rows"))
    missing_slots_count = _int(summary.get("missing_slots_count"), 0)
    manual_follow_up_count = _int(summary.get("manual_follow_up_count"), 0)
    documented_slots_count = _int(summary.get("documented_slots_count"), 0)
    source_coverage_count = _int(summary.get("source_provenance_coverage_count"), 0)
    review_gap_count = _int(summary_counts.get("review_gap_count"), len(review_gap_rows))
    source_gap_count = max(documented_slots_count - source_coverage_count, 0)

    rows = [
        _row(
            key="missing_documentation",
            label="Missing documentation",
            status=_status_for_count(
                missing_slots_count + review_gap_count,
                REVIEW_STATUS_MISSING,
                "No missing documentation count visible in current payload",
            ),
            count=missing_slots_count + review_gap_count,
            review_action=(
                "Review existing construct documentation rows and record missing source/provenance "
                "or review-note context where appropriate."
            ),
            source="documentation_review_summary + review_gap_rows",
        ),
        _row(
            key="needs_manual_follow_up",
            label="Needs manual follow-up",
            status=_status_for_count(
                manual_follow_up_count,
                REVIEW_STATUS_NEEDS_FOLLOW_UP,
                "No manual follow-up count visible in current payload",
            ),
            count=manual_follow_up_count,
            review_action=(
                "Use existing manual follow-up rows to decide what a human reviewer should inspect next."
            ),
            source="construct_component_manual_follow_up_readback",
        ),
        _row(
            key="source_provenance_review",
            label="Source/provenance review",
            status=_status_for_count(
                source_gap_count,
                REVIEW_STATUS_NEEDS_FOLLOW_UP,
                "Source/provenance count visible in current payload",
            ),
            count=source_gap_count,
            review_action=(
                "Check recorded source/reference and provenance fields before using the package as review notes."
            ),
            source="construct_component_review_summary",
        ),
        _row(
            key="boundary_note",
            label="Boundary note",
            status="Review boundary visible",
            count=1,
            review_action=str(summary.get("review_summary_note") or REVIEW_FRAME_NOTE),
            source="documentation_review_summary",
            boundary_note=PANEL_BOUNDARY_NOTE,
        ),
    ]

    return {
        "status": PANEL_STATUS_AVAILABLE if section else PANEL_STATUS_NOT_AVAILABLE,
        "panel_title": PANEL_TITLE,
        "panel_note": PANEL_NOTE,
        "review_summary_status": summary.get("review_summary_status") or REVIEW_STATUS_MISSING,
        "rows": rows,
        "summary": {
            "row_count": len(rows),
            "missing_documentation_count": missing_slots_count + review_gap_count,
            "manual_follow_up_count": manual_follow_up_count,
            "source_provenance_follow_up_count": source_gap_count,
        },
        "boundary_notes": [PANEL_BOUNDARY_NOTE],
    }
