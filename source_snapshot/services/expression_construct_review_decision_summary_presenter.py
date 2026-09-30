from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.project_output_boundary_copy import PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE


PAGE_TITLE = "Documentation review summary"
REVIEW_STATUS_REVIEWABLE = "Reviewable"
REVIEW_STATUS_NEEDS_FOLLOW_UP = "Needs manual follow-up"
REVIEW_STATUS_MISSING = "Missing documentation"
REVIEW_FRAME_NOTE = (
    "Review-only documentation handoff review; not a downstream-use assessment. "
    f"{PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE}"
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return []


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _review_status(
    *,
    documented_slots_count: int,
    missing_slots_count: int,
    manual_follow_up_count: int,
) -> str:
    if documented_slots_count <= 0:
        return REVIEW_STATUS_MISSING
    if missing_slots_count > 0 or manual_follow_up_count > 0:
        return REVIEW_STATUS_NEEDS_FOLLOW_UP
    return REVIEW_STATUS_REVIEWABLE


def build_expression_construct_review_decision_summary(
    construct_section: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Summarize the existing construct review payload without changing review logic."""
    section = _mapping(construct_section)
    summary_counts = _mapping(section.get("summary_counts"))
    component_summary = _mapping(section.get("construct_component_review_summary"))
    follow_up_summary = _mapping(section.get("construct_component_manual_follow_up_readback"))
    component_rows = [row for row in section.get("construct_component_rows") or [] if isinstance(row, dict)]

    documented_slots_count = _int(
        component_summary.get("total_component_rows"),
        len(component_rows),
    )
    source_coverage_count = _int(
        component_summary.get("rows_with_source_reference_context"),
        0,
    )
    missing_slots_count = max(documented_slots_count - source_coverage_count, 0)
    manual_follow_up_count = _int(
        follow_up_summary.get("total_manual_follow_up_items"),
        _int(component_summary.get("rows_needing_manual_follow_up"), 0),
    )

    boundary_notes = _unique([_text(note) for note in _text_list(section.get("boundary_notes"))])
    warnings = _unique([_text(section.get("message"))]) if _text(section.get("message")) else []

    review_status = _review_status(
        documented_slots_count=documented_slots_count,
        missing_slots_count=missing_slots_count,
        manual_follow_up_count=manual_follow_up_count,
    )

    if review_status == REVIEW_STATUS_MISSING and not warnings:
        warnings.append("No construct documentation rows are currently visible in the report payload.")
    elif review_status == REVIEW_STATUS_NEEDS_FOLLOW_UP and not warnings:
        warnings.append("Manual follow-up is still recorded in the current report payload.")

    return {
        "status": "AVAILABLE" if section else "NOT_AVAILABLE",
        "summary_title": PAGE_TITLE,
        "review_summary_status": review_status,
        "review_summary_note": REVIEW_FRAME_NOTE,
        "documented_slots_count": documented_slots_count,
        "missing_slots_count": missing_slots_count,
        "manual_follow_up_count": manual_follow_up_count,
        "source_provenance_coverage_count": source_coverage_count,
        "source_provenance_coverage_label": (
            "Source/provenance recorded" if source_coverage_count > 0 else "Missing documentation"
        ),
        "boundary_notes": boundary_notes,
        "warnings": warnings,
        "summary_counts": {
            "construct_profile_count": _int(summary_counts.get("construct_profile_count"), 0),
            "cassette_count": _int(summary_counts.get("cassette_count"), 0),
            "cassette_part_count": _int(summary_counts.get("cassette_part_count"), 0),
            "review_gap_count": _int(summary_counts.get("review_gap_count"), 0),
        },
    }
