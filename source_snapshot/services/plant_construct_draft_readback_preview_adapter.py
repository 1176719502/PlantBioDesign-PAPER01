from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


PREVIEW_STATUS_AVAILABLE = "construct_draft_readback_preview_available"
PREVIEW_STATUS_EMPTY = "construct_draft_readback_preview_empty"
PREVIEW_TITLE = "Plant Construct Draft Readback Preview"
NOT_PROVIDED = "not provided"
BOUNDARY_NOTE = (
    "Documentation-only and manual-review-only preview. It preserves the R331 "
    "construct draft readback for review discussion without creating biological "
    "build content, component choices, sequences, procedure steps, forecasts, "
    "certifications, or downstream-use judgments."
)
EMPTY_STATE_LINE = "No readable construct draft readback payload was supplied."
MANUAL_REVIEW_LINE = "Manual review required."


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_text(item) for item in value if _text(item)]
    return []


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _bool_text(value: Any) -> str:
    return "yes" if value is True else "no" if value is False else NOT_PROVIDED


def _markdown_cell(value: Any, fallback: str = NOT_PROVIDED) -> str:
    clean = _text(value, fallback)
    return clean.replace("\\", "\\\\").replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def _markdown_list(title: str, rows: Sequence[str]) -> list[str]:
    lines = [f"## {title}"]
    if rows:
        lines.extend(f"- {_markdown_cell(row)}" for row in rows)
    else:
        lines.append(f"- {NOT_PROVIDED}")
    return lines


def _slot_rows(readback: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rows = readback.get("slot_rows")
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)):
        return []

    rows: list[dict[str, Any]] = []
    for raw_row in raw_rows:
        row = _mapping(raw_row)
        if not row:
            continue
        display_label = _text(row.get("display_label")) or _text(row.get("slot_name"), "Draft slot")
        missing_reason = _text(row.get("missing_reason"))
        recorded_value = _text(row.get("value"))
        if not recorded_value:
            recorded_value = missing_reason or NOT_PROVIDED
        rows.append(
            {
                "slot_name": _text(row.get("slot_name"), NOT_PROVIDED),
                "display_label": display_label,
                "role": _text(row.get("role"), "draft slot"),
                "status": _text(row.get("status"), NOT_PROVIDED),
                "recorded_value": recorded_value,
                "missing_reason": missing_reason or NOT_PROVIDED,
                "source_ids": _unique([*_as_list(row.get("source_ids")), *_as_list(row.get("supporting_source_ids"))]),
                "evidence_ids": _unique([*_as_list(row.get("evidence_ids")), *_as_list(row.get("evidence_source_ids"))]),
                "manual_review_required": row.get("manual_review_required") is not False,
                "safe_status_text": _text(row.get("safe_status_text"), MANUAL_REVIEW_LINE),
            }
        )
    return rows


def _review_counts(readback: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    status_counts: dict[str, int] = {}
    for row in rows:
        status = _text(row.get("status")).casefold()
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "slot_count": len(rows),
        "present_slot_count": _int(readback.get("present_slot_count")) or status_counts.get("present", 0),
        "missing_slot_count": _int(readback.get("missing_slot_count")) or status_counts.get("missing", 0),
        "needs_source_count": _int(readback.get("needs_source_count")) or status_counts.get("needs_source", 0),
        "needs_confirmation_count": _int(readback.get("needs_confirmation_count"))
        or status_counts.get("needs_confirmation", 0),
        "warning_count": len(_as_list(readback.get("warnings"))),
        "review_item_count": len(_as_list(readback.get("review_items"))),
    }


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _source_reference_lines(readback: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list[str]:
    source_ids: list[str] = []
    evidence_ids: list[str] = []
    source_ids.extend(_as_list(readback.get("source_ids")))
    evidence_ids.extend(_as_list(readback.get("evidence_source_ids")))
    for row in rows:
        source_ids.extend(_as_list(row.get("source_ids")))
        evidence_ids.extend(_as_list(row.get("evidence_ids")))
    return [
        f"Source IDs: {', '.join(_unique(source_ids)) if source_ids else NOT_PROVIDED}",
        f"Evidence IDs: {', '.join(_unique(evidence_ids)) if evidence_ids else NOT_PROVIDED}",
    ]


def _missing_reason_lines(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for row in rows:
        status = _text(row.get("status")).casefold()
        reason = _text(row.get("missing_reason"))
        if status in {"missing", "needs_source"} or (reason and reason != NOT_PROVIDED):
            lines.append(f"{_text(row.get('display_label'), 'Draft slot')}: {reason or NOT_PROVIDED}")
    return lines


def _summary_lines(readback: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list[str]:
    draft_status = _text(readback.get("draft_status"), "unreported")
    route_label = _text(readback.get("route_source_label"), "unlabeled route")
    plant_context = _text(readback.get("plant_host_or_context"), "unreported plant context")
    manual_review_state = MANUAL_REVIEW_LINE if readback.get("manual_review_required") is not False else "Manual review state not reported."
    return [
        f"Draft readback source: {route_label}.",
        f"Plant host/context: {plant_context}.",
        f"Draft status: {draft_status}.",
        manual_review_state,
        f"Draft slots shown: {len(rows)}.",
        "External review discussion candidate.",
    ]


def _slot_table_markdown(rows: Sequence[Mapping[str, Any]]) -> str:
    headers = [
        "Slot",
        "Role",
        "Status",
        "Recorded value or gap",
        "Missing reason",
        "Source IDs",
        "Evidence IDs",
        "Manual review",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    if not rows:
        lines.append("| not provided |  |  |  |  |  |  |  |")
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(row.get("display_label")),
                    _markdown_cell(row.get("role")),
                    _markdown_cell(row.get("status")),
                    _markdown_cell(row.get("recorded_value")),
                    _markdown_cell(row.get("missing_reason")),
                    _markdown_cell(", ".join(_as_list(row.get("source_ids")))),
                    _markdown_cell(", ".join(_as_list(row.get("evidence_ids")))),
                    _markdown_cell(_bool_text(row.get("manual_review_required"))),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _build_markdown(
    *,
    summary_lines: Sequence[str],
    slot_rows: Sequence[Mapping[str, Any]],
    missing_reason_lines: Sequence[str],
    source_reference_lines: Sequence[str],
    review_counts: Mapping[str, int],
    warning_lines: Sequence[str],
    is_empty: bool,
) -> str:
    count_lines = [f"{key}: {value}" for key, value in review_counts.items()]
    lines = [
        f"# {PREVIEW_TITLE}",
        "",
        f"**Boundary:** {BOUNDARY_NOTE}",
        "",
        "## Preview State",
        f"- Status: {PREVIEW_STATUS_EMPTY if is_empty else PREVIEW_STATUS_AVAILABLE}",
        f"- Empty state: {_bool_text(is_empty)}",
        "",
        *_markdown_list("Summary", list(summary_lines)),
        "",
        "## Draft Slots",
        _slot_table_markdown(slot_rows),
        "",
        *_markdown_list("Missing Reasons", list(missing_reason_lines)),
        "",
        *_markdown_list("Source And Evidence References", list(source_reference_lines)),
        "",
        *_markdown_list("Review Counts", count_lines),
        "",
        *_markdown_list("Warnings", list(warning_lines)),
        "",
    ]
    return "\n".join(lines)


def _empty_preview(reason: str) -> dict[str, Any]:
    warning_lines = [_text(reason, EMPTY_STATE_LINE)]
    review_counts = {
        "slot_count": 0,
        "present_slot_count": 0,
        "missing_slot_count": 0,
        "needs_source_count": 0,
        "needs_confirmation_count": 0,
        "warning_count": len(warning_lines),
        "review_item_count": 1,
    }
    summary_lines = [EMPTY_STATE_LINE, MANUAL_REVIEW_LINE]
    preview = {
        "status": PREVIEW_STATUS_EMPTY,
        "is_empty": True,
        "title": PREVIEW_TITLE,
        "boundary_note": BOUNDARY_NOTE,
        "summary_lines": summary_lines,
        "slot_rows": [],
        "missing_reason_lines": [],
        "source_reference_lines": [f"Source IDs: {NOT_PROVIDED}", f"Evidence IDs: {NOT_PROVIDED}"],
        "review_counts": review_counts,
        "warning_lines": warning_lines,
    }
    preview["markdown"] = _build_markdown(
        summary_lines=summary_lines,
        slot_rows=[],
        missing_reason_lines=[],
        source_reference_lines=preview["source_reference_lines"],
        review_counts=review_counts,
        warning_lines=warning_lines,
        is_empty=True,
    )
    return preview


def build_plant_construct_draft_readback_preview(readback_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build a deterministic documentation-only preview from an R331 readback payload."""
    readback = _mapping(readback_payload)
    if not readback:
        return _empty_preview("Invalid or empty construct draft readback payload.")

    readback_status = _text(readback.get("readback_status")).casefold()
    rows = _slot_rows(readback)
    blocked_or_empty = readback_status.endswith("_empty") or "blocked" in _text(readback.get("draft_status")).casefold()
    if blocked_or_empty or not rows:
        warnings = _as_list(readback.get("warnings"))
        reason = warnings[0] if warnings else "Construct draft readback is empty or blocked."
        empty = _empty_preview(reason)
        empty["warning_lines"] = warnings or empty["warning_lines"]
        empty["review_counts"]["warning_count"] = len(empty["warning_lines"])
        empty["markdown"] = _build_markdown(
            summary_lines=empty["summary_lines"],
            slot_rows=[],
            missing_reason_lines=[],
            source_reference_lines=empty["source_reference_lines"],
            review_counts=empty["review_counts"],
            warning_lines=empty["warning_lines"],
            is_empty=True,
        )
        return empty

    warning_lines = _as_list(readback.get("warnings"))
    missing_reason_lines = _missing_reason_lines(rows)
    source_reference_lines = _source_reference_lines(readback, rows)
    review_counts = _review_counts(readback, rows)
    review_counts["warning_count"] = len(warning_lines)
    summary_lines = _summary_lines(readback, rows)
    markdown = _build_markdown(
        summary_lines=summary_lines,
        slot_rows=rows,
        missing_reason_lines=missing_reason_lines,
        source_reference_lines=source_reference_lines,
        review_counts=review_counts,
        warning_lines=warning_lines,
        is_empty=False,
    )
    return {
        "status": PREVIEW_STATUS_AVAILABLE,
        "is_empty": False,
        "title": PREVIEW_TITLE,
        "boundary_note": BOUNDARY_NOTE,
        "summary_lines": summary_lines,
        "slot_rows": rows,
        "missing_reason_lines": missing_reason_lines,
        "source_reference_lines": source_reference_lines,
        "review_counts": review_counts,
        "warning_lines": warning_lines,
        "markdown": markdown,
    }
