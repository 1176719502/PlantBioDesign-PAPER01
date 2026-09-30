from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


READBACK_STATUS_READY = "construct_draft_readback_created"
READBACK_STATUS_EMPTY = "construct_draft_readback_empty"

SLOT_STATUS_PRESENT = "present"
SLOT_STATUS_MISSING = "missing"
SLOT_STATUS_NEEDS_SOURCE = "needs_source"
SLOT_STATUS_NEEDS_CONFIRMATION = "needs_confirmation"
SLOT_STATUS_NOT_APPLICABLE = "not_applicable"

SAFE_STATUS_TEXT = {
    SLOT_STATUS_PRESENT: "source-backed field; manual review required",
    SLOT_STATUS_MISSING: "missing required slot; manual review required",
    SLOT_STATUS_NEEDS_SOURCE: "missing source; manual review required",
    SLOT_STATUS_NEEDS_CONFIRMATION: "needs confirmation; manual review required",
    SLOT_STATUS_NOT_APPLICABLE: "not applicable for this draft readback",
}

READBACK_BOUNDARY = (
    "Construct draft readback is a read-only summary for source and manual review. "
    "It preserves draft slots and missing fields without creating final sequences, "
    "assembly instructions, automatic component choices, biological forecasts, or "
    "downstream-use approval."
)

DEFAULT_REVIEW_ITEM = "Manual review required before any downstream interpretation."


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        clean = _text(value)
        if clean:
            return clean
    return ""


def _display_label(slot_name: str) -> str:
    labels = {
        "cds_payload_gene_or_enzyme": "CDS / payload / gene or enzyme",
        "selectable_marker": "Selectable marker",
        "vector_backbone": "Vector backbone",
        "plant_host_context": "Plant host/context",
    }
    return labels.get(slot_name, slot_name.replace("_", " ").title())


def _safe_status_text(status: str) -> str:
    return SAFE_STATUS_TEXT.get(status, "needs confirmation; manual review required")


def _slot_status(slot: Mapping[str, Any]) -> str:
    raw = _text(slot.get("status")).casefold()
    if raw in SAFE_STATUS_TEXT:
        return raw
    if "needs_source" in raw or "needs source" in raw or "missing source" in raw:
        return SLOT_STATUS_NEEDS_SOURCE
    if "needs_confirmation" in raw or "needs confirmation" in raw or "manual review" in raw:
        return SLOT_STATUS_NEEDS_CONFIRMATION
    if "not_applicable" in raw or "not applicable" in raw:
        return SLOT_STATUS_NOT_APPLICABLE
    if "present" in raw or "confirmed" in raw:
        return SLOT_STATUS_PRESENT
    if "missing" in raw:
        return SLOT_STATUS_MISSING
    return SLOT_STATUS_NEEDS_CONFIRMATION if slot else SLOT_STATUS_MISSING


def _manual_review_required(draft: Mapping[str, Any], slot_rows: Sequence[Mapping[str, Any]]) -> bool:
    if draft.get("manual_review_required") is False:
        return any(row.get("manual_review_required") for row in slot_rows)
    return True


def _empty_payload(reason: str) -> dict[str, Any]:
    return {
        "readback_status": READBACK_STATUS_EMPTY,
        "draft_id": "",
        "route_source_label": "",
        "plant_host_or_context": "",
        "goal_type": "",
        "route_type": "",
        "draft_status": "",
        "manual_review_required": True,
        "safety_boundary": READBACK_BOUNDARY,
        "summary_lines": [
            "Construct draft readback unavailable.",
            "Manual review required before any downstream interpretation.",
        ],
        "slot_rows": [],
        "missing_slot_count": 0,
        "present_slot_count": 0,
        "needs_source_count": 0,
        "needs_confirmation_count": 0,
        "evidence_source_ids": [],
        "warnings": [reason],
        "review_items": [DEFAULT_REVIEW_ITEM],
    }


def _slot_rows(draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_slots = draft.get("construct_slots")
    if not isinstance(raw_slots, Sequence) or isinstance(raw_slots, (str, bytes, bytearray)):
        return []

    rows: list[dict[str, Any]] = []
    for raw_slot in raw_slots:
        slot = _mapping(raw_slot)
        if not slot:
            continue
        slot_name = _first_text(slot.get("slot_name"), slot.get("slot"))
        status = _slot_status(slot)
        row = {
            "slot_name": slot_name,
            "role": _text(slot.get("role")) or "draft slot",
            "status": status,
            "value": _text(slot.get("value")),
            "source_ids": _unique([*_as_list(slot.get("source_ids")), *_as_list(slot.get("supporting_source_ids"))]),
            "evidence_ids": _unique([*_as_list(slot.get("evidence_ids")), *_as_list(slot.get("evidence_source_ids"))]),
            "missing_reason": _text(slot.get("missing_reason")),
            "manual_review_required": slot.get("manual_review_required") is not False,
            "display_label": _display_label(slot_name),
            "safe_status_text": _safe_status_text(status),
        }
        rows.append(row)
    return rows


def _evidence_source_ids(draft: Mapping[str, Any], slot_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    values: list[str] = []
    values.extend(_as_list(draft.get("supporting_source_ids")))
    values.extend(_as_list(draft.get("evidence_source_ids")))
    values.extend(_as_list(draft.get("source_ids")))
    for row in slot_rows:
        values.extend(_as_list(row.get("source_ids")))
        values.extend(_as_list(row.get("evidence_ids")))
    return _unique(values)


def _warnings(draft: Mapping[str, Any], slot_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    warnings: list[str] = []
    draft_status = _text(draft.get("draft_status"))
    if draft_status in {"incomplete", "needs_manual_review"}:
        warnings.append("Incomplete draft: review missing slots and confirmation needs.")
    if any(row.get("status") == SLOT_STATUS_NEEDS_SOURCE for row in slot_rows):
        warnings.append("One or more draft slots have missing source records.")
    if any(row.get("status") == SLOT_STATUS_NEEDS_CONFIRMATION for row in slot_rows):
        warnings.append("One or more draft slots need confirmation.")
    if _text(draft.get("construct_draft_status")).casefold() == "route_generation_blocked":
        warnings.append("Construct draft input is blocked; no slot readback is available.")
    return _unique(warnings)


def _review_items(draft: Mapping[str, Any], slot_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    items = _as_list(draft.get("review_items"))
    for row in slot_rows:
        if row.get("status") == SLOT_STATUS_NEEDS_SOURCE:
            items.append(f"{row['display_label']}: missing source.")
        elif row.get("status") == SLOT_STATUS_MISSING:
            items.append(f"{row['display_label']}: missing required slot.")
        elif row.get("status") == SLOT_STATUS_NEEDS_CONFIRMATION:
            items.append(f"{row['display_label']}: needs confirmation.")
    if not items:
        items.append(DEFAULT_REVIEW_ITEM)
    return _unique(items)


def _summary_lines(
    draft: Mapping[str, Any],
    *,
    missing_slot_count: int,
    present_slot_count: int,
    needs_source_count: int,
    needs_confirmation_count: int,
) -> list[str]:
    draft_status = _text(draft.get("draft_status")) or "unreported"
    route_label = _first_text(draft.get("route_label"), draft.get("source_route_id"), "unlabeled route")
    plant_context = _first_text(draft.get("plant_host_or_context"), draft.get("plant_host_context"), "unreported plant context")
    return [
        f"Construct draft readback for {route_label}.",
        f"Plant host/context: {plant_context}.",
        f"Draft status: {draft_status}; manual review required.",
        (
            "Slot summary: "
            f"{present_slot_count} present, {missing_slot_count} missing, "
            f"{needs_source_count} missing source, {needs_confirmation_count} needs confirmation."
        ),
        "Read-only summary; not final construct output.",
    ]


def build_plant_construct_draft_readback(construct_draft: Mapping[str, Any] | None) -> dict[str, Any]:
    """Convert an R330 construct draft record into a safe plain-dict readback payload."""
    draft = _mapping(construct_draft)
    if not draft:
        return _empty_payload("Invalid construct draft input.")
    if _text(draft.get("construct_draft_status")).casefold() == "route_generation_blocked":
        blocked = _empty_payload(_first_text(draft.get("reason"), "Construct draft input is blocked."))
        blocked["draft_status"] = _text(draft.get("construct_draft_status"))
        return blocked

    rows = _slot_rows(draft)
    if "construct_slots" in draft and not rows:
        return _empty_payload("Construct draft input has no readable draft slots.")

    missing_slot_count = sum(1 for row in rows if row["status"] == SLOT_STATUS_MISSING)
    present_slot_count = sum(1 for row in rows if row["status"] == SLOT_STATUS_PRESENT)
    needs_source_count = sum(1 for row in rows if row["status"] == SLOT_STATUS_NEEDS_SOURCE)
    needs_confirmation_count = sum(1 for row in rows if row["status"] == SLOT_STATUS_NEEDS_CONFIRMATION)

    manual_review = _manual_review_required(draft, rows)
    return {
        "readback_status": READBACK_STATUS_READY,
        "draft_id": _text(draft.get("draft_id")),
        "route_source_label": _first_text(draft.get("route_label"), draft.get("source_route_id"), "unlabeled route"),
        "plant_host_or_context": _first_text(
            draft.get("plant_host_or_context"),
            draft.get("plant_host_context"),
            "unreported plant context",
        ),
        "goal_type": _text(draft.get("goal_type")),
        "route_type": _text(draft.get("route_type")),
        "draft_status": _text(draft.get("draft_status")),
        "manual_review_required": manual_review,
        "safety_boundary": READBACK_BOUNDARY,
        "summary_lines": _summary_lines(
            draft,
            missing_slot_count=missing_slot_count,
            present_slot_count=present_slot_count,
            needs_source_count=needs_source_count,
            needs_confirmation_count=needs_confirmation_count,
        ),
        "slot_rows": rows,
        "missing_slot_count": missing_slot_count,
        "present_slot_count": present_slot_count,
        "needs_source_count": needs_source_count,
        "needs_confirmation_count": needs_confirmation_count,
        "evidence_source_ids": _evidence_source_ids(draft, rows),
        "warnings": _warnings(draft, rows),
        "review_items": _review_items(draft, rows),
    }
