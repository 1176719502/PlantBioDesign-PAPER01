from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services import plant_review_manual_verification_status as manual_status


MANUAL_VERIFICATION_TRANSITION_GUARD_SCHEMA_VERSION = (
    "plant_review_manual_verification_transition_guard.v2.7.r157"
)
MANUAL_VERIFICATION_TRANSITION_GUARD_BATCH = "v2.7-r157"
TRANSITION_STATUS_ALLOWED = "manual_verification_transition_allowed_status_only"
TRANSITION_STATUS_BLOCKED = "manual_verification_transition_blocked"
TRANSITION_STATUS_FAIL_CLOSED = "manual_verification_transition_fail_closed"

DOCUMENTATION_BOUNDARY = (
    "Documentation-only manual verification transition readback. It checks reviewer-entered "
    "status movement without writing status records, changing seed records, filling identifiers, "
    "changing evidence standing, allowing record promotion, or making downstream-use judgments."
)

FAIL_CLOSED_BOUNDARY = (
    "Manual verification transition input is missing, malformed, or outside the supported status "
    "vocabulary, so the transition readback fails closed and record promotion remains blocked."
)

BLOCKED_OR_REJECTED_STATUSES = {
    manual_status.STATUS_BLOCKED_MISSING_IDENTIFIER,
    manual_status.STATUS_BLOCKED_SCOPE_UNCLEAR,
    manual_status.STATUS_REJECTED_BEFORE_PROMOTION,
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _unique_texts(values: Sequence[Any]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            rows.append(clean)
            seen.add(key)
    return rows


def _status_value(raw_status: Any) -> tuple[str, dict[str, Any], bool]:
    if isinstance(raw_status, Mapping):
        record = _mapping(raw_status)
        value = _text(
            record.get("verification_status"),
            _text(record.get("status"), _text(record.get("transition_status"))),
        ).casefold()
        return value, record, bool(value)
    value = _text(raw_status).casefold()
    return value, {}, bool(value)


def _status_label(status_key: str) -> str:
    return status_key if status_key in manual_status.SUPPORTED_VERIFICATION_STATUSES else "unknown_status"


def _record_reasons(record: Mapping[str, Any]) -> list[str]:
    return _unique_texts(
        [
            *_sequence(record.get("blocking_reasons")),
            record.get("blocking_reason"),
            record.get("promotion_blocked_reason"),
            record.get("fail_closed_reason"),
        ]
    )


def _task_identity(
    current_record: Mapping[str, Any],
    requested_record: Mapping[str, Any],
    task: Mapping[str, Any] | None,
) -> tuple[str, bool]:
    task_record = _mapping(task)
    task_values = [
        task_record.get("task_id"),
        current_record.get("task_id"),
        requested_record.get("task_id"),
    ]
    task_id = _text(next((value for value in task_values if _text(value)), ""))
    mapping_input = bool(current_record or requested_record or task_record)
    return task_id, bool(task_id) or not mapping_input


def _blocked_transition_reasons(from_status: str, to_status: str) -> list[str]:
    reasons: list[str] = []
    if from_status not in manual_status.SUPPORTED_VERIFICATION_STATUSES:
        reasons.append("Current manual verification status is not in the supported vocabulary.")
    if to_status not in manual_status.SUPPORTED_VERIFICATION_STATUSES:
        reasons.append("Requested manual verification status is not in the supported vocabulary.")
    if (
        from_status == manual_status.STATUS_REJECTED_BEFORE_PROMOTION
        and to_status == manual_status.STATUS_VERIFIED_REFERENCE_RECORDED
    ):
        reasons.append(
            "Rejected status cannot move directly to reference-recorded status in this guard; "
            "a separately scoped second review remains required."
        )
    return reasons


def build_plant_review_manual_verification_transition_guard(
    current_status: Mapping[str, Any] | str | None,
    requested_next_status: Mapping[str, Any] | str | None,
    *,
    task: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a read-only transition readback for manual verification status movement."""
    from_status, from_record, has_from_status = _status_value(current_status)
    to_status, to_record, has_to_status = _status_value(requested_next_status)
    task_id, has_task_identity = _task_identity(from_record, to_record, task)

    blocking_reasons = _unique_texts(
        [
            *_record_reasons(from_record),
            *_record_reasons(to_record),
            *_blocked_transition_reasons(from_status, to_status),
        ]
    )
    if not has_from_status:
        blocking_reasons.append("Current manual verification status input is missing or malformed.")
    if not has_to_status:
        blocking_reasons.append("Requested manual verification status input is missing or malformed.")
    if not has_task_identity:
        blocking_reasons.append("Task identity is missing from the supplied manual verification input.")

    unsupported = (
        not has_from_status
        or not has_to_status
        or not has_task_identity
        or from_status not in manual_status.SUPPORTED_VERIFICATION_STATUSES
        or to_status not in manual_status.SUPPORTED_VERIFICATION_STATUSES
    )
    rejected_to_reference = (
        from_status == manual_status.STATUS_REJECTED_BEFORE_PROMOTION
        and to_status == manual_status.STATUS_VERIFIED_REFERENCE_RECORDED
    )
    fail_closed = unsupported or rejected_to_reference
    transition_allowed = not fail_closed
    requires_second_review = (
        rejected_to_reference
        or from_record.get("requires_second_review") is True
        or to_record.get("requires_second_review") is True
    )

    if fail_closed:
        transition_status = TRANSITION_STATUS_FAIL_CLOSED
    elif to_status in BLOCKED_OR_REJECTED_STATUSES:
        transition_status = TRANSITION_STATUS_BLOCKED
    else:
        transition_status = TRANSITION_STATUS_ALLOWED

    return _plain_value(
        {
            "transition_schema_version": MANUAL_VERIFICATION_TRANSITION_GUARD_SCHEMA_VERSION,
            "transition_batch": MANUAL_VERIFICATION_TRANSITION_GUARD_BATCH,
            "read_only": True,
            "plant_scope_only": True,
            "plain_dict_list_contract": True,
            "transition_allowed": transition_allowed,
            "transition_status": transition_status,
            "task_id": _text(task_id, "manual-verification-transition-task"),
            "from_status": _status_label(from_status),
            "to_status": _status_label(to_status),
            "blocking_reasons": _unique_texts(blocking_reasons),
            "manual_review_required": True,
            "promotion_allowed": False,
            "requires_second_review": requires_second_review,
            "fail_closed": fail_closed,
            "documentation_boundary": DOCUMENTATION_BOUNDARY,
            "source_policy": (
                "R157 is a read-only transition guard. It does not write status records, "
                "fill source or accession fields, change seed data, change evidence standing, "
                "or promote records."
            ),
            "fail_closed_reason": FAIL_CLOSED_BOUNDARY if fail_closed else "",
        }
    )


def build_plant_review_manual_verification_transition_readback_rows(
    transition_payloads: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return compact transition rows for future readback consumers."""
    rows: list[dict[str, Any]] = []
    for payload in _sequence(transition_payloads):
        row = _mapping(payload)
        rows.append(
            {
                "task_id": _text(row.get("task_id")),
                "from_status": _text(row.get("from_status")),
                "to_status": _text(row.get("to_status")),
                "transition_allowed": row.get("transition_allowed") is True,
                "transition_status": _text(row.get("transition_status")),
                "manual_review_required": True,
                "promotion_allowed": False,
                "requires_second_review": row.get("requires_second_review") is True,
                "fail_closed": row.get("fail_closed") is True,
                "documentation_boundary": _text(row.get("documentation_boundary"), DOCUMENTATION_BOUNDARY),
            }
        )
    return _plain_value(rows)
