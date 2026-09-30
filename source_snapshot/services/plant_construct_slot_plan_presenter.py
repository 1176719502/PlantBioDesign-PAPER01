from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_text,
)


PAGE_TITLE = "Plant Construct Slot Plan Readback"
SUBTITLE = "Documentation-only slot plan summary for manual review."
BOUNDARY_NOTICE = (
    "Documentation-only construct slot plan presenter for manual review. It formats existing "
    "slot plan readback data without choosing components, generating constructs, generating "
    "sequences, computing route metrics, or judging wet-lab use state."
)
EMPTY_STATE_MESSAGE = (
    "No construct slot plan rows are available. Build or provide a slot plan readback before "
    "using this presenter for manual documentation review."
)

PRESENTER_KEYS: tuple[str, ...] = (
    "page_title",
    "subtitle",
    "summary_card",
    "compatibility_card",
    "slot_rows",
    "gap_rows",
    "blocked_output_rows",
    "boundary_notice",
    "markdown_snapshot",
    "empty_state",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = _text(item)
            if text and text not in seen:
                result.append(text)
                seen.add(text)
        return result
    text = _text(value)
    return [text] if text else []


def _slot_rows(readback: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(_mapping_list(readback.get("slot_rows")), start=1):
        rows.append(
            {
                "row_id": f"slot-plan-{index:02d}",
                "slot_id": _text(row.get("slot_id")),
                "slot_type": _text(row.get("slot_type")),
                "module_id": _text(row.get("module_id")),
                "module_label": _text(row.get("module_label")),
                "required_or_optional": _text(row.get("required_or_optional")),
                "expected_evidence_type": _text(row.get("expected_evidence_type")),
                "current_evidence_status": _text(row.get("current_evidence_status")),
                "gap_reason": _text(row.get("gap_reason")),
                "manual_review_state": _text(row.get("manual_review_state")),
            }
        )
    return rows


def _gap_rows(slot_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for row in slot_rows:
        evidence_status = _text(row.get("current_evidence_status"))
        manual_review_state = _text(row.get("manual_review_state"))
        if "missing" not in evidence_status and "required" not in manual_review_state:
            continue
        gaps.append(
            {
                "row_id": f"gap-{len(gaps) + 1:02d}",
                "slot_id": _text(row.get("slot_id")),
                "module_label": _text(row.get("module_label")) or "Missing module card",
                "gap_reason": _text(row.get("gap_reason")),
                "manual_review_state": manual_review_state or "manual_review_required",
            }
        )
    return gaps


def _blocked_output_rows(readback: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for output in _string_list(readback.get("blocked_output_categories")):
        rows.append(
            {
                "row_id": f"blocked-output-{len(rows) + 1:02d}",
                "blocked_output_category": output,
                "reason": "Shown only as a documentation boundary reminder.",
            }
        )
    return rows


def _summary_card(readback: Mapping[str, Any], slot_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    requirement_counts = Counter(_text(row.get("required_or_optional")) for row in slot_rows)
    evidence_counts = Counter(_text(row.get("current_evidence_status")) for row in slot_rows)
    review_counts = Counter(_text(row.get("manual_review_state")) for row in slot_rows)
    return {
        "slot_plan_status": _text(readback.get("slot_plan_status")),
        "route_template_id": _text(readback.get("route_template_id")),
        "canonical_route_template_id": _text(readback.get("canonical_route_template_id")),
        "slot_row_count": len(slot_rows),
        "required_slot_count": requirement_counts.get("required", 0),
        "optional_slot_count": requirement_counts.get("optional", 0),
        "missing_evidence_row_count": sum(
            count for status, count in evidence_counts.items() if "missing" in status
        ),
        "manual_review_row_count": sum(
            count for status, count in review_counts.items() if "required" in status
        ),
    }


def _compatibility_card(readback: Mapping[str, Any]) -> dict[str, Any]:
    compatibility = _as_mapping(readback.get("compatibility"))
    return {
        "requested_route_id": _text(compatibility.get("requested_route_id")),
        "resolved_canonical_route_id": _text(compatibility.get("resolved_canonical_route_id")),
        "resolved_legacy_route_id": _text(compatibility.get("resolved_legacy_route_id")),
        "alias_status": _text(compatibility.get("alias_status")),
        "is_alias": bool(compatibility.get("is_alias")),
        "route_template_found": bool(compatibility.get("route_template_found")),
        "note": "Compatibility aliases are metadata only and do not imply biological suitability.",
    }


def _empty_presenter() -> dict[str, Any]:
    return {
        "page_title": PAGE_TITLE,
        "subtitle": SUBTITLE,
        "summary_card": {
            "slot_plan_status": "",
            "route_template_id": "",
            "canonical_route_template_id": "",
            "slot_row_count": 0,
            "required_slot_count": 0,
            "optional_slot_count": 0,
            "missing_evidence_row_count": 0,
            "manual_review_row_count": 0,
        },
        "compatibility_card": {},
        "slot_rows": [],
        "gap_rows": [],
        "blocked_output_rows": [],
        "boundary_notice": BOUNDARY_NOTICE,
        "markdown_snapshot": "",
        "empty_state": {"is_empty": True, "message": EMPTY_STATE_MESSAGE},
    }


def format_construct_slot_plan_markdown(presenter: Mapping[str, Any]) -> str:
    """Format a compact Markdown snapshot from presenter output."""
    summary = _as_mapping(presenter.get("summary_card"))
    compatibility = _as_mapping(presenter.get("compatibility_card"))
    slot_rows = _mapping_list(presenter.get("slot_rows"))
    gap_rows = _mapping_list(presenter.get("gap_rows"))
    lines = [
        "# Plant Construct Slot Plan Readback Snapshot",
        "",
        BOUNDARY_NOTICE,
        "This snapshot is review text only. It does not save records, export packages, or create construct outputs.",
        "",
        "## Summary",
        f"- slot plan status: {summary.get('slot_plan_status') or 'NOT_AVAILABLE'}",
        f"- route template ID: {summary.get('route_template_id') or 'NOT_AVAILABLE'}",
        f"- canonical route template ID: {summary.get('canonical_route_template_id') or 'NOT_AVAILABLE'}",
        f"- slot rows: {summary.get('slot_row_count', 0)}",
        f"- required slots: {summary.get('required_slot_count', 0)}",
        f"- optional slots: {summary.get('optional_slot_count', 0)}",
        f"- rows needing evidence notes: {summary.get('missing_evidence_row_count', 0)}",
        f"- rows needing manual review: {summary.get('manual_review_row_count', 0)}",
        "",
        "## Compatibility metadata",
        f"- requested route ID: {compatibility.get('requested_route_id') or 'NOT_AVAILABLE'}",
        f"- alias status: {compatibility.get('alias_status') or 'NOT_AVAILABLE'}",
        f"- route template found: {compatibility.get('route_template_found', False)}",
        f"- note: {compatibility.get('note') or 'Compatibility metadata only.'}",
        "",
        "## Slot rows",
    ]
    if slot_rows:
        for row in slot_rows:
            lines.append(
                "- "
                f"{row.get('slot_id') or 'slot'} | "
                f"{row.get('module_label') or 'Missing module card'} | "
                f"{row.get('required_or_optional') or 'manual review'} | "
                f"{row.get('current_evidence_status') or 'manual review required'}"
            )
    else:
        lines.append(f"- {EMPTY_STATE_MESSAGE}")

    lines.extend(["", "## Gap rows"])
    if gap_rows:
        for row in gap_rows:
            lines.append(
                "- "
                f"{row.get('slot_id') or 'slot'}: "
                f"{row.get('gap_reason') or 'manual documentation review needed'}"
            )
    else:
        lines.append("- No slot gap rows are currently available.")

    lines.extend(["", "## Boundary note", f"- {BOUNDARY_NOTICE}", ""])
    markdown = normalize_generated_output_text("\n".join(lines))
    assert_no_misleading_generated_claims(markdown, context="construct slot plan presenter")
    return markdown


def present_construct_slot_plan_readback(readback: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return deterministic plain readback sections for an existing construct slot plan."""
    source = readback if isinstance(readback, Mapping) else {}
    if not source:
        return _empty_presenter()

    slot_rows = _slot_rows(source)
    presented = _empty_presenter()
    presented.update(
        {
            "summary_card": _summary_card(source, slot_rows),
            "compatibility_card": _compatibility_card(source),
            "slot_rows": slot_rows,
            "gap_rows": _gap_rows(slot_rows),
            "blocked_output_rows": _blocked_output_rows(source),
            "empty_state": {"is_empty": not bool(slot_rows), "message": "" if slot_rows else EMPTY_STATE_MESSAGE},
        }
    )
    presented["markdown_snapshot"] = format_construct_slot_plan_markdown(presented)
    return {key: presented[key] for key in PRESENTER_KEYS}
