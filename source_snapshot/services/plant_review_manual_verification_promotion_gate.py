from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services import plant_review_manual_verification_status as manual_status
from services import plant_review_manual_verification_status_snapshot as status_snapshot


MANUAL_VERIFICATION_PROMOTION_GATE_SCHEMA_VERSION = (
    "plant_review_manual_verification_promotion_gate.v2.7.r158"
)
MANUAL_VERIFICATION_PROMOTION_GATE_BATCH = "v2.7-r158"
PROMOTION_GATE_STATUS_BLOCKED = "manual_verification_promotion_gate_blocked"
PROMOTION_GATE_STATUS_FAIL_CLOSED = "manual_verification_promotion_gate_fail_closed"

DOCUMENTATION_BOUNDARY = (
    "Documentation-only manual verification promotion gate readback. It explains why reviewer "
    "status records remain blocked from record promotion without writing records, filling "
    "identifiers, changing seed data, changing evidence standing, or making downstream-use "
    "judgments."
)

FAIL_CLOSED_BOUNDARY = (
    "Manual verification status snapshot input is missing, malformed, or internally conflicting, "
    "so the promotion gate fails closed and record promotion remains blocked."
)

BLOCKED_STATUS_KEYS = {
    manual_status.STATUS_BLOCKED_MISSING_IDENTIFIER,
    manual_status.STATUS_BLOCKED_SCOPE_UNCLEAR,
    manual_status.STATUS_REVIEWED_BUT_NOT_PROMOTABLE,
    manual_status.STATUS_REJECTED_BEFORE_PROMOTION,
}

IDENTIFIER_BLOCKER_FIELD_ORDER = {
    "accession": 0,
    "source_id": 1,
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


def _count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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


def _snapshot_source(
    snapshot_payload: Any,
    *,
    source_kwargs_by_key: Mapping[str, Mapping[str, Any]] | None,
    status_records: Sequence[Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], bool, list[str]]:
    if snapshot_payload is None:
        return (
            status_snapshot.build_plant_review_manual_verification_status_snapshot(
                source_kwargs_by_key=source_kwargs_by_key,
                status_records=status_records,
            ),
            False,
            [],
        )

    source = _mapping(snapshot_payload)
    task_summary = _mapping(source.get("task_summary"))
    status_summary = _mapping(source.get("verification_status_summary"))
    malformed = not source or not task_summary or not status_summary
    warnings: list[str] = []
    if malformed:
        warnings.append("Manual verification status snapshot input is missing or malformed.")
    return source, malformed, warnings


def _gate_key(queue_key: str, dataset_key: str) -> str:
    return f"r158-{queue_key}-{dataset_key}-manual-verification-promotion-gate"


def _status_blockers(status_counts: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for status_key in sorted(status_counts, key=lambda item: str(item).casefold()):
        count = _count(status_counts[status_key])
        if count <= 0:
            continue
        if status_key in BLOCKED_STATUS_KEYS or status_key == manual_status.STATUS_PENDING_MANUAL_REVIEW:
            rows.append(
                {
                    "verification_status": _text(status_key, "unknown_status"),
                    "status_record_count": count,
                    "promotion_allowed": False,
                    "blocking_reason": "Manual verification status remains a status record only.",
                }
            )
    return rows


def _identifier_blockers(snapshot_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    task_summary = _mapping(snapshot_payload.get("task_summary"))
    missing_counts = _mapping(task_summary.get("missing_field_counts"))
    blockers: list[dict[str, Any]] = []
    field_keys = sorted(
        missing_counts,
        key=lambda item: (
            IDENTIFIER_BLOCKER_FIELD_ORDER.get(str(item), len(IDENTIFIER_BLOCKER_FIELD_ORDER)),
            str(item).casefold(),
        ),
    )
    for field_key in field_keys:
        count = _count(missing_counts.get(field_key))
        if count:
            blockers.append(
                {
                    "identifier_field": field_key,
                    "blocked_count": count,
                    "promotion_allowed": False,
                    "blocking_reason": "Identifier gap remains visible for manual review.",
                }
            )

    if blockers:
        return blockers

    status_records = [_mapping(row) for row in _sequence(snapshot_payload.get("status_records"))]
    identifier_recorded_count = sum(1 for row in status_records if row.get("identifier_recorded") is True)
    if identifier_recorded_count:
        blockers.append(
            {
                "identifier_field": "reviewer_entered_reference_status",
                "blocked_count": identifier_recorded_count,
                "promotion_allowed": False,
                "blocking_reason": "Reviewer-entered reference status does not fill seed identifiers.",
            }
        )
    return blockers


def _transition_rows(transition_readbacks: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for transition in _sequence(transition_readbacks):
        row = _mapping(transition)
        if not row:
            continue
        rows.append(
            {
                "task_id": _text(row.get("task_id")),
                "from_status": _text(row.get("from_status")),
                "to_status": _text(row.get("to_status")),
                "transition_allowed": row.get("transition_allowed") is True,
                "requires_second_review": row.get("requires_second_review") is True,
                "fail_closed": row.get("fail_closed") is True,
                "promotion_allowed": False,
            }
        )
    return rows


def _second_review_required_count(
    snapshot_payload: Mapping[str, Any],
    transition_rows: Sequence[Mapping[str, Any]],
) -> int:
    status_records = [_mapping(row) for row in _sequence(snapshot_payload.get("status_records"))]
    status_count = sum(1 for row in status_records if row.get("requires_second_review") is True)
    transition_count = sum(1 for row in transition_rows if row.get("requires_second_review") is True)
    return status_count + transition_count


def _blocking_reasons(
    snapshot_payload: Mapping[str, Any],
    *,
    malformed: bool,
    status_blockers: Sequence[Mapping[str, Any]],
    identifier_blockers: Sequence[Mapping[str, Any]],
    transition_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    reasons: list[Any] = []
    task_summary = _mapping(snapshot_payload.get("task_summary"))
    status_summary = _mapping(snapshot_payload.get("verification_status_summary"))
    if malformed:
        reasons.append(FAIL_CLOSED_BOUNDARY)
    if _count(task_summary.get("ready_to_promote_count")) > 0:
        reasons.append("Task snapshot reports ready-to-promote rows, so this read-only gate fails closed.")
    if _count(status_summary.get("promotion_allowed_count")) > 0:
        reasons.append("Status snapshot reports promotion-allowed rows, so this read-only gate fails closed.")
    if _count(status_summary.get("verified_reference_recorded_count")) > 0:
        reasons.append("Reference-recorded status remains status-only and does not allow promotion.")
    for row in [*status_blockers, *identifier_blockers]:
        reasons.append(row.get("blocking_reason"))
    if any(row.get("requires_second_review") is True for row in transition_rows):
        reasons.append("At least one transition readback requires second review before any future action.")
    return _unique_texts(reasons)


def build_plant_review_manual_verification_promotion_gate(
    status_snapshot_payload: Mapping[str, Any] | None = None,
    *,
    transition_readbacks: Sequence[Mapping[str, Any]] | None = None,
    source_kwargs_by_key: Mapping[str, Mapping[str, Any]] | None = None,
    status_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a read-only promotion gate readback for manual verification snapshots."""
    snapshot_payload, malformed, warnings = _snapshot_source(
        status_snapshot_payload,
        source_kwargs_by_key=source_kwargs_by_key,
        status_records=status_records,
    )
    task_summary = _mapping(snapshot_payload.get("task_summary"))
    status_summary = _mapping(snapshot_payload.get("verification_status_summary"))
    queue_key = _text(snapshot_payload.get("queue_key"), "unknown_queue")
    dataset_key = _text(snapshot_payload.get("dataset_key"), "unknown_dataset")
    status_counts = _mapping(status_summary.get("status_counts"))
    status_blocker_rows = _status_blockers(status_counts)
    identifier_blocker_rows = _identifier_blockers(snapshot_payload)
    compact_transition_rows = _transition_rows(transition_readbacks)
    input_promotion_allowed_count = _count(status_summary.get("promotion_allowed_count"))
    input_ready_to_promote_count = _count(task_summary.get("ready_to_promote_count"))
    verified_reference_recorded_count = _count(status_summary.get("verified_reference_recorded_count"))
    second_review_count = _second_review_required_count(snapshot_payload, compact_transition_rows)
    fail_closed = (
        malformed
        or snapshot_payload.get("fail_closed") is True
        or _mapping(task_summary).get("fail_closed") is True
        or _mapping(status_summary).get("fail_closed") is True
        or input_promotion_allowed_count > 0
        or input_ready_to_promote_count > 0
        or any(row.get("fail_closed") is True for row in compact_transition_rows)
    )

    reasons = _blocking_reasons(
        snapshot_payload,
        malformed=malformed,
        status_blockers=status_blocker_rows,
        identifier_blockers=identifier_blocker_rows,
        transition_rows=compact_transition_rows,
    )

    return _plain_value(
        {
            "gate_schema_version": MANUAL_VERIFICATION_PROMOTION_GATE_SCHEMA_VERSION,
            "gate_batch": MANUAL_VERIFICATION_PROMOTION_GATE_BATCH,
            "gate_key": _gate_key(queue_key, dataset_key),
            "dataset_key": dataset_key,
            "queue_key": queue_key,
            "read_only": True,
            "plant_scope_only": True,
            "plain_dict_list_contract": True,
            "promotion_gate_status": (
                PROMOTION_GATE_STATUS_FAIL_CLOSED
                if fail_closed
                else PROMOTION_GATE_STATUS_BLOCKED
            ),
            "promotion_allowed": False,
            "promotion_allowed_count": 0,
            "input_promotion_allowed_count": input_promotion_allowed_count,
            "promotion_blocked_count": max(
                _count(snapshot_payload.get("promotion_blocked_count")),
                _count(task_summary.get("promotion_blocked_count")),
                _count(task_summary.get("records_blocked_from_promotion")),
            ),
            "ready_to_promote_count": 0,
            "input_ready_to_promote_count": input_ready_to_promote_count,
            "total_tasks": _count(task_summary.get("total_tasks")),
            "represented_records": _count(task_summary.get("represented_records")),
            "blocking_reasons": reasons,
            "status_blockers": status_blocker_rows,
            "identifier_blockers": identifier_blocker_rows,
            "transition_blockers": compact_transition_rows,
            "second_review_required_count": second_review_count,
            "verified_reference_recorded_count": verified_reference_recorded_count,
            "manual_review_required": True,
            "fail_closed": fail_closed,
            "fail_closed_reason": FAIL_CLOSED_BOUNDARY if fail_closed else "",
            "documentation_boundary": DOCUMENTATION_BOUNDARY,
            "source_policy": (
                "R158 is a read-only gate readback. It consumes status snapshot and transition "
                "readbacks without writing status records, filling identifiers, changing seed data, "
                "changing evidence standing, or promoting records."
            ),
            "warnings": warnings,
        }
    )


def build_plant_review_manual_verification_promotion_gate_readback_rows(
    gate_payload: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Return one compact promotion gate row for future readback consumers."""
    payload = _mapping(gate_payload) or build_plant_review_manual_verification_promotion_gate(**kwargs)
    return _plain_value(
        [
            {
                "gate_key": _text(payload.get("gate_key")),
                "dataset_key": _text(payload.get("dataset_key")),
                "queue_key": _text(payload.get("queue_key")),
                "promotion_gate_status": _text(payload.get("promotion_gate_status")),
                "promotion_allowed": False,
                "promotion_allowed_count": 0,
                "promotion_blocked_count": _count(payload.get("promotion_blocked_count")),
                "ready_to_promote_count": 0,
                "second_review_required_count": _count(payload.get("second_review_required_count")),
                "verified_reference_recorded_count": _count(payload.get("verified_reference_recorded_count")),
                "manual_review_required": True,
                "fail_closed": payload.get("fail_closed") is True,
                "documentation_boundary": _text(payload.get("documentation_boundary"), DOCUMENTATION_BOUNDARY),
            }
        ]
    )
