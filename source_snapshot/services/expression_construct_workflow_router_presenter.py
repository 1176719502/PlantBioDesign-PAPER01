from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


PRESENTER_STATUS_AVAILABLE = "expression_construct_workflow_router_presenter_available"
PRESENTER_STATUS_EMPTY = "expression_construct_workflow_router_presenter_empty"
PAGE_TITLE = "Expression Construct Workflow Route"
SUBTITLE = "UI-safe readback for documentation-only expression construct route review."
EMPTY_STATE_MESSAGE = "No readable expression construct workflow router result was supplied."
NOT_PROVIDED = "Not provided"

ACTIVE_MAINLINE_CATEGORY = "active_mainline"
FUTURE_ROUTE_CATEGORY = "future_route_candidate"
FALLBACK_CATEGORY = "fallback"

BASE_BOUNDARY_NOTES = [
    "documentation-only route readback",
    "manual review required before downstream interpretation",
    "no component choice, sequence, procedure, or lab-use judgment",
    "records router fields for traceability only",
]

ROUTE_STATUS_LABELS = {
    ACTIVE_MAINLINE_CATEGORY: "Active expression construct review mainline",
    FUTURE_ROUTE_CATEGORY: "Future route candidate for manual triage",
    FALLBACK_CATEGORY: "Fallback clarification route",
}

UNSAFE_NOTE_REPLACEMENTS = {
    "not a " + "build" + "-ready design": "no downstream-use judgment",
    "no biological " + "feasibility, validation, or optimization claim": (
        "no lab-use, evidence-confirmation, or improvement claim"
    ),
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_text_list(value: Any) -> list[str]:
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


def _safe_note(note: str) -> str:
    safe = _text(note)
    for unsafe, replacement in UNSAFE_NOTE_REPLACEMENTS.items():
        safe = safe.replace(unsafe, replacement)
    return safe


def _boundary_notes(router_result: Mapping[str, Any]) -> list[str]:
    supplied = [_safe_note(note) for note in _as_text_list(router_result.get("documentation_only_boundary_notes"))]
    return _unique([*BASE_BOUNDARY_NOTES, *supplied])


def _route_category(router_result: Mapping[str, Any]) -> str:
    category = _text(router_result.get("route_category"))
    if category in {ACTIVE_MAINLINE_CATEGORY, FUTURE_ROUTE_CATEGORY, FALLBACK_CATEGORY}:
        return category
    return FALLBACK_CATEGORY


def _route_status(category: str, router_result: Mapping[str, Any]) -> dict[str, Any]:
    manual_review_required = _bool(router_result.get("manual_review_required"), True)
    return {
        "route_category": category,
        "status_label": ROUTE_STATUS_LABELS.get(category, ROUTE_STATUS_LABELS[FALLBACK_CATEGORY]),
        "active_mainline": category == ACTIVE_MAINLINE_CATEGORY,
        "future_candidate": category == FUTURE_ROUTE_CATEGORY,
        "fallback": category == FALLBACK_CATEGORY,
        "confidence_category": _text(router_result.get("confidence_category"), "low"),
        "manual_review_required": manual_review_required,
        "tone": "attention" if category == FALLBACK_CATEGORY else "neutral",
    }


def _slot_rows(required_slots: Sequence[str], missing_slots: Sequence[str]) -> list[dict[str, str]]:
    missing = {slot.casefold() for slot in missing_slots}
    rows: list[dict[str, str]] = []
    for slot in required_slots:
        rows.append(
            {
                "slot_key": slot,
                "review_status": "missing or unknown" if slot.casefold() in missing else "present in router result",
            }
        )
    return rows


def _summary_card(
    *,
    router_result: Mapping[str, Any],
    category: str,
    required_slots: Sequence[str],
    missing_slots: Sequence[str],
    boundary_notes: Sequence[str],
) -> dict[str, Any]:
    return {
        "matched_workflow_route": _text(router_result.get("matched_workflow_route"), NOT_PROVIDED),
        "route_category": category,
        "route_status_label": ROUTE_STATUS_LABELS.get(category, ROUTE_STATUS_LABELS[FALLBACK_CATEGORY]),
        "confidence_category": _text(router_result.get("confidence_category"), "low"),
        "manual_review_required": _bool(router_result.get("manual_review_required"), True),
        "required_slot_count": len(required_slots),
        "missing_or_unknown_slot_count": len(missing_slots),
        "boundary_summary": boundary_notes[0] if boundary_notes else BASE_BOUNDARY_NOTES[0],
    }


def _matched_intent_text(router_result: Mapping[str, Any]) -> str:
    for key in ("matched_intent_text", "user_intent_text", "intent_text", "source_intent_text"):
        value = _text(router_result.get(key))
        if value:
            return value
    return "Intent text was not included in the router result."


def _is_readable_router_result(router_result: Mapping[str, Any]) -> bool:
    return bool(
        _text(router_result.get("matched_workflow_route"))
        and _text(router_result.get("route_category"))
        and isinstance(router_result.get("required_information_slots"), Sequence)
        and not isinstance(router_result.get("required_information_slots"), (str, bytes, bytearray))
    )


def _empty_presenter(reason: str = EMPTY_STATE_MESSAGE) -> dict[str, Any]:
    warning = _text(reason, EMPTY_STATE_MESSAGE)
    boundary_notes = list(BASE_BOUNDARY_NOTES)
    return {
        "status": PRESENTER_STATUS_EMPTY,
        "page_title": PAGE_TITLE,
        "subtitle": SUBTITLE,
        "route_summary_card": {
            "matched_workflow_route": "",
            "route_category": FALLBACK_CATEGORY,
            "route_status_label": ROUTE_STATUS_LABELS[FALLBACK_CATEGORY],
            "confidence_category": "low",
            "manual_review_required": True,
            "required_slot_count": 0,
            "missing_or_unknown_slot_count": 0,
            "boundary_summary": boundary_notes[0],
        },
        "route_status": {
            "route_category": FALLBACK_CATEGORY,
            "status_label": ROUTE_STATUS_LABELS[FALLBACK_CATEGORY],
            "active_mainline": False,
            "future_candidate": False,
            "fallback": True,
            "confidence_category": "low",
            "manual_review_required": True,
            "tone": "attention",
        },
        "matched_intent_text": "Intent text was not included in the router result.",
        "suggested_review_stages": [],
        "suggested_review_stage_rows": [],
        "required_information_slots": [],
        "required_information_slot_rows": [],
        "missing_or_unknown_slots": [],
        "safe_next_review_action": "Collect a readable router result before showing route readback.",
        "documentation_only_boundary_notes": boundary_notes,
        "warnings": [warning],
        "empty_state": {"is_empty": True, "message": warning, "manual_review_required": True},
    }


def build_expression_construct_workflow_router_presenter(
    router_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Convert an R341 router result into deterministic UI-safe readback sections."""
    result = _mapping(router_result)
    if not result or not _is_readable_router_result(result):
        return _empty_presenter("Invalid or empty expression construct workflow router result.")

    category = _route_category(result)
    required_slots = _as_text_list(result.get("required_information_slots"))
    missing_slots = _as_text_list(result.get("missing_information_slots"))
    stages = _as_text_list(result.get("suggested_review_stages"))
    boundary_notes = _boundary_notes(result)
    warnings = _as_text_list(result.get("warnings"))

    if category == FALLBACK_CATEGORY and not warnings:
        warnings = ["Router result used the fallback clarification route."]

    return {
        "status": PRESENTER_STATUS_AVAILABLE,
        "page_title": PAGE_TITLE,
        "subtitle": SUBTITLE,
        "route_summary_card": _summary_card(
            router_result=result,
            category=category,
            required_slots=required_slots,
            missing_slots=missing_slots,
            boundary_notes=boundary_notes,
        ),
        "route_status": _route_status(category, result),
        "matched_intent_text": _matched_intent_text(result),
        "suggested_review_stages": stages,
        "suggested_review_stage_rows": [
            {"stage": stage, "review_status": "manual review required"} for stage in stages
        ],
        "required_information_slots": required_slots,
        "required_information_slot_rows": _slot_rows(required_slots, missing_slots),
        "missing_or_unknown_slots": missing_slots,
        "safe_next_review_action": _text(
            result.get("safe_next_review_action"),
            "Review the route result and record missing information before downstream interpretation.",
        ),
        "documentation_only_boundary_notes": boundary_notes,
        "warnings": warnings,
        "empty_state": {"is_empty": False, "message": "", "manual_review_required": True},
    }
