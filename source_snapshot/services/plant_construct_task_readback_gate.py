from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA_VERSION = "v2.7-r222"
BOUNDARY_NOTE = (
    "Construct Task Readback Gate is read-only. It checks whether the current Candidate Route Review Draft "
    "has enough documentation context to enter construct task draft readback, without creating construct tasks, "
    "construct drafts, sequences, experimental steps, validation, optimization, or downstream-use judgments."
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _status_label(value: Any) -> str:
    return _text(value).replace("_", " ") or "not recorded"


def _reason(code: str, detail: str, next_item: str) -> dict[str, str]:
    return {"Reason code": code, "Readback": detail, "Next completion item": next_item}


def _missing_slot_reasons(candidate_route_review_draft: Mapping[str, Any]) -> list[dict[str, str]]:
    slots = _mapping(candidate_route_review_draft.get("required_design_slots"))
    missing_slots = [_text(value) for value in _list(slots.get("missing_slots")) if _text(value)]
    if not missing_slots and int(slots.get("missing_slot_count") or 0):
        missing_slots = ["Required design slot details"]
    return [
        _reason(
            "missing_required_design_slot",
            slot,
            "Fill required design information.",
        )
        for slot in missing_slots
    ]


def _evidence_reasons(candidate_route_review_draft: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for blocker in _list(candidate_route_review_draft.get("evidence_blockers")):
        blocker_map = _mapping(blocker)
        blocker_type = _text(blocker_map.get("Type")) or "manual_evidence_gap"
        rows.append(
            _reason(
                blocker_type,
                _text(blocker_map.get("Blocker")) or _status_label(blocker_type),
                _text(blocker_map.get("Action")) or "Review manual evidence gaps.",
            )
        )
    return rows


def _route_reasons(candidate_route_review_draft: Mapping[str, Any]) -> list[dict[str, str]]:
    route = _mapping(candidate_route_review_draft.get("route_readback"))
    if _text(route.get("route_id")):
        return []
    return [
        _reason(
            "missing_candidate_route",
            "No confirmed candidate route is available in the current readback.",
            "Confirm a candidate route in the plant review draft.",
        )
    ]


def _completion_gate_reasons(completion_gate_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    package = _mapping(completion_gate_payload.get("package_handoff_readback"))
    status = _text(package.get("status"))
    if status not in {"blocked_readback_only", "safe_empty_readback"}:
        return []
    return [
        _reason(
            "package_handoff_readback_blocked",
            _text(package.get("readback")) or "Package/handoff readback still has visible blockers.",
            _text(package.get("next_action")) or "Refresh package readback.",
        )
    ]


def _safe_actions_from_reasons(reasons: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    seen: set[str] = set()
    for reason in reasons:
        action = _text(reason.get("Next completion item"))
        if action and action.casefold() not in seen:
            seen.add(action.casefold())
            actions.append(
                {
                    "Area": _status_label(reason.get("Reason code")),
                    "Action": action,
                    "Readback-only": "yes",
                }
            )
    if not actions:
        actions.append(
            {
                "Area": "Construct task draft readback",
                "Action": "Review construct task draft readback as a separate documentation surface.",
                "Readback-only": "yes",
            }
        )
    return actions


def build_construct_task_readback_gate(
    *,
    candidate_route_review_draft: Mapping[str, Any] | None,
    completion_gate_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidate = _mapping(candidate_route_review_draft)
    completion_gate = _mapping(completion_gate_payload)
    route = _mapping(candidate.get("route_readback"))
    slot_reasons = _missing_slot_reasons(candidate)
    evidence_reasons = _evidence_reasons(candidate)
    reasons = [
        *_route_reasons(candidate),
        *slot_reasons,
        *evidence_reasons,
        *_completion_gate_reasons(completion_gate),
    ]
    can_enter_readback = bool(_text(route.get("route_id"))) and not slot_reasons and not evidence_reasons
    status = (
        "construct_task_draft_readback_available"
        if can_enter_readback
        else "construct_task_draft_readback_blocked"
    )
    if not reasons:
        reasons = [
            _reason(
                "separate_readback_surface",
                "No slot or evidence blocker is visible; construct task draft readback remains separate.",
                "Review construct task draft readback as a separate documentation surface.",
            )
        ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "section_title": "Construct Task Readback Gate",
        "boundary_note": BOUNDARY_NOTE,
        "read_only": True,
        "documentation_only": True,
        "manual_review_required": True,
        "construct_task_created": False,
        "construct_draft_created": False,
        "sequence_generated": False,
        "can_enter_construct_task_draft_readback": can_enter_readback,
        "gate_status": status,
        "route_id": _text(route.get("route_id")),
        "route_label": _text(route.get("route_label")),
        "blocked_reasons": reasons if not can_enter_readback else [],
        "next_completion_items": _safe_actions_from_reasons(reasons),
    }
    payload["status_rows"] = [
        {
            "Checkpoint": "Construct task draft readback",
            "Status": _status_label(status),
            "Readback": (
                "Available for separate readback review."
                if can_enter_readback
                else "Blocked until visible route, slot, or evidence gaps are addressed."
            ),
            "Next completion item": payload["next_completion_items"][0]["Action"],
        },
        {
            "Checkpoint": "Candidate route",
            "Status": _status_label(route.get("route_review_status")),
            "Readback": _text(route.get("route_label")) or "No route label is recorded.",
            "Next completion item": "Keep candidate route context separate from construct task draft readback.",
        },
    ]
    return payload
