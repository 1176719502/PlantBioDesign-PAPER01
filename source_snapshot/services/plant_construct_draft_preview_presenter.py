from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


PRESENTER_STATUS_AVAILABLE = "construct_draft_preview_presenter_available"
PRESENTER_STATUS_EMPTY = "construct_draft_preview_presenter_empty"
PAGE_TITLE = "Plant Construct Draft Preview"
SUBTITLE = "UI-safe presenter for read-only construct draft review."
NOT_PROVIDED = "not provided"
MANUAL_REVIEW_REQUIRED_TEXT = "manual review required"
DEFAULT_BOUNDARY = (
    "Read-only construct draft preview for source and manual review. It preserves "
    "draft slots, source identifiers, evidence identifiers, missing reasons, review "
    "counts, and warnings without creating final construct content or downstream-use "
    "judgments."
)
EMPTY_STATE_MESSAGE = "No readable construct draft preview payload was supplied."


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


def _bool(value: Any, fallback: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    return fallback


def _count(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _review_counts(preview: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    raw_counts = _mapping(preview.get("review_counts"))
    status_counts: dict[str, int] = {}
    for row in rows:
        status = _text(row.get("status")).casefold()
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "slot_count": _count(raw_counts.get("slot_count"), len(rows)),
        "present_slot_count": _count(raw_counts.get("present_slot_count"), status_counts.get("present", 0)),
        "missing_slot_count": _count(raw_counts.get("missing_slot_count"), status_counts.get("missing", 0)),
        "needs_source_count": _count(raw_counts.get("needs_source_count"), status_counts.get("needs_source", 0)),
        "needs_confirmation_count": _count(
            raw_counts.get("needs_confirmation_count"),
            status_counts.get("needs_confirmation", 0),
        ),
        "warning_count": _count(raw_counts.get("warning_count"), len(_as_list(preview.get("warning_lines")))),
        "review_item_count": _count(raw_counts.get("review_item_count"), len(_as_list(preview.get("review_items")))),
    }


def _slot_rows(preview: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rows = preview.get("slot_rows")
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)):
        return []

    rows: list[dict[str, Any]] = []
    for raw_row in raw_rows:
        row = _mapping(raw_row)
        if not row:
            continue
        explicit_value = _text(row.get("value")) if "value" in row else ""
        rows.append(
            {
                "display_label": _text(row.get("display_label"), _text(row.get("slot_name"), "Draft slot")),
                "slot_name": _text(row.get("slot_name"), NOT_PROVIDED),
                "role": _text(row.get("role"), "draft slot"),
                "status": _text(row.get("status"), NOT_PROVIDED),
                "safe_status_text": _text(row.get("safe_status_text"), MANUAL_REVIEW_REQUIRED_TEXT),
                "value": explicit_value,
                "source_ids": _unique([*_as_list(row.get("source_ids")), *_as_list(row.get("supporting_source_ids"))]),
                "evidence_ids": _unique([*_as_list(row.get("evidence_ids")), *_as_list(row.get("evidence_source_ids"))]),
                "missing_reason": _text(row.get("missing_reason")),
                "manual_review_required": _bool(row.get("manual_review_required"), True),
            }
        )
    return rows


def _missing_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for row in rows:
        status = _text(row.get("status")).casefold()
        reason = _text(row.get("missing_reason"))
        if status in {"missing", "needs_source"} or reason:
            missing.append(
                {
                    "display_label": _text(row.get("display_label"), "Draft slot"),
                    "slot_name": _text(row.get("slot_name"), NOT_PROVIDED),
                    "status": _text(row.get("status"), NOT_PROVIDED),
                    "missing_reason": reason or NOT_PROVIDED,
                    "manual_review_required": _bool(row.get("manual_review_required"), True),
                }
            )
    return missing


def _evidence_summary(preview: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    source_ids: list[str] = []
    evidence_ids: list[str] = []
    source_ids.extend(_as_list(preview.get("source_ids")))
    evidence_ids.extend(_as_list(preview.get("evidence_ids")))
    evidence_ids.extend(_as_list(preview.get("evidence_source_ids")))
    for row in rows:
        source_ids.extend(_as_list(row.get("source_ids")))
        evidence_ids.extend(_as_list(row.get("evidence_ids")))
    return {
        "source_ids": _unique(source_ids),
        "evidence_ids": _unique(evidence_ids),
        "source_count": len(_unique(source_ids)),
        "evidence_count": len(_unique(evidence_ids)),
        "note": "Identifiers are displayed as supplied; no evidence is inferred.",
    }


def _status_badges(preview: Mapping[str, Any], review_counts: Mapping[str, int]) -> list[dict[str, str]]:
    draft_status = _text(preview.get("draft_status"), NOT_PROVIDED)
    manual_review = "yes" if _bool(preview.get("manual_review_required"), True) else "no"
    return [
        {"label": "Preview status", "value": _text(preview.get("status"), PRESENTER_STATUS_AVAILABLE), "tone": "neutral"},
        {"label": "Draft status", "value": draft_status, "tone": "neutral"},
        {"label": "Manual review", "value": manual_review, "tone": "attention" if manual_review == "yes" else "neutral"},
        {"label": "Missing fields", "value": str(review_counts.get("missing_slot_count", 0)), "tone": "attention"},
        {"label": "Warnings", "value": str(review_counts.get("warning_count", 0)), "tone": "attention"},
    ]


def _empty_presenter(reason: str) -> dict[str, Any]:
    warning = _text(reason, EMPTY_STATE_MESSAGE)
    review_counts = {
        "slot_count": 0,
        "present_slot_count": 0,
        "missing_slot_count": 0,
        "needs_source_count": 0,
        "needs_confirmation_count": 0,
        "warning_count": 1,
        "review_item_count": 0,
    }
    return {
        "status": PRESENTER_STATUS_EMPTY,
        "page_title": PAGE_TITLE,
        "subtitle": SUBTITLE,
        "draft_summary_card": {
            "draft_id": "",
            "draft_status": "",
            "manual_review_required": True,
            "safety_boundary": DEFAULT_BOUNDARY,
            "summary_lines": [EMPTY_STATE_MESSAGE],
            "review_counts": review_counts,
        },
        "status_badges": [
            {"label": "Preview status", "value": PRESENTER_STATUS_EMPTY, "tone": "attention"},
            {"label": "Manual review", "value": "yes", "tone": "attention"},
        ],
        "slot_table": {"columns": _slot_table_columns(), "rows": [], "row_count": 0},
        "evidence_summary": {
            "source_ids": [],
            "evidence_ids": [],
            "source_count": 0,
            "evidence_count": 0,
            "note": "Identifiers are displayed as supplied; no evidence is inferred.",
        },
        "missing_fields_section": {"rows": [], "manual_review_required": True},
        "review_items_section": {"items": [], "review_item_count": 0, "manual_review_required": True},
        "warnings_section": {"warnings": [warning], "warning_count": 1},
        "empty_state": {"is_empty": True, "reason": warning, "manual_review_required": True},
    }


def _slot_table_columns() -> list[str]:
    return [
        "display_label",
        "slot_name",
        "role",
        "status",
        "safe_status_text",
        "value",
        "source_ids",
        "evidence_ids",
        "missing_reason",
        "manual_review_required",
    ]


def build_plant_construct_draft_preview_presenter(preview_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Convert an R332 preview payload into deterministic UI-safe presenter sections."""
    preview = _mapping(preview_payload)
    if not preview:
        return _empty_presenter("Invalid or empty construct draft preview payload.")

    rows = _slot_rows(preview)
    status = _text(preview.get("status"))
    is_empty = preview.get("is_empty") is True or status.endswith("_empty")
    if is_empty or not rows:
        warnings = _as_list(preview.get("warning_lines")) or _as_list(preview.get("warnings"))
        reason = warnings[0] if warnings else "Construct draft preview is empty or blocked."
        empty = _empty_presenter(reason)
        empty["warnings_section"] = {"warnings": warnings or [reason], "warning_count": len(warnings or [reason])}
        empty["draft_summary_card"]["draft_id"] = _text(preview.get("draft_id"))
        empty["draft_summary_card"]["draft_status"] = _text(preview.get("draft_status"))
        empty["draft_summary_card"]["manual_review_required"] = _bool(preview.get("manual_review_required"), True)
        empty["draft_summary_card"]["safety_boundary"] = _text(
            preview.get("safety_boundary"),
            _text(preview.get("boundary_note"), DEFAULT_BOUNDARY),
        )
        return empty

    review_counts = _review_counts(preview, rows)
    manual_review_required = _bool(preview.get("manual_review_required"), any(row["manual_review_required"] for row in rows))
    missing_rows = _missing_rows(rows)
    review_items = _as_list(preview.get("review_items"))
    warnings = _as_list(preview.get("warning_lines")) or _as_list(preview.get("warnings"))
    evidence_summary = _evidence_summary(preview, rows)
    safety_boundary = _text(preview.get("safety_boundary"), _text(preview.get("boundary_note"), DEFAULT_BOUNDARY))

    return {
        "status": PRESENTER_STATUS_AVAILABLE,
        "page_title": PAGE_TITLE,
        "subtitle": SUBTITLE,
        "draft_summary_card": {
            "draft_id": _text(preview.get("draft_id")),
            "draft_status": _text(preview.get("draft_status"), NOT_PROVIDED),
            "manual_review_required": manual_review_required,
            "safety_boundary": safety_boundary,
            "summary_lines": _as_list(preview.get("summary_lines")),
            "review_counts": review_counts,
        },
        "status_badges": _status_badges(preview, review_counts),
        "slot_table": {"columns": _slot_table_columns(), "rows": rows, "row_count": len(rows)},
        "evidence_summary": evidence_summary,
        "missing_fields_section": {"rows": missing_rows, "manual_review_required": manual_review_required},
        "review_items_section": {
            "items": review_items,
            "review_item_count": review_counts.get("review_item_count", len(review_items)),
            "manual_review_required": manual_review_required,
        },
        "warnings_section": {"warnings": warnings, "warning_count": len(warnings)},
        "empty_state": {"is_empty": False, "reason": "", "manual_review_required": manual_review_required},
    }
