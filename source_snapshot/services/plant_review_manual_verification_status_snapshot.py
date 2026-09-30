from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from services import plant_review_manual_verification_status as manual_status
from services import plant_review_task_queue_snapshot_readback as task_snapshot


MANUAL_VERIFICATION_STATUS_SNAPSHOT_SCHEMA_VERSION = (
    "plant_review_manual_verification_status_snapshot.v2.7.r156"
)
MANUAL_VERIFICATION_STATUS_SNAPSHOT_BATCH = "v2.7-r156"
MANUAL_VERIFICATION_STATUS_SNAPSHOT_READY = (
    "plant_review_manual_verification_status_snapshot_ready"
)
MANUAL_VERIFICATION_STATUS_SNAPSHOT_FAIL_CLOSED = (
    "plant_review_manual_verification_status_snapshot_fail_closed"
)

DOCUMENTATION_BOUNDARY = (
    "Documentation-only plant review manual verification status snapshot. It joins "
    "queue readback and reviewer-entered status readback without source lookup, "
    "identifier filling, evidence-standing changes, record promotion, component "
    "choice, route improvement, or downstream-use judgment."
)

FAIL_CLOSED_BOUNDARY = (
    "Manual verification status snapshot input is missing or malformed, so readback "
    "fails closed and promotion remains blocked."
)

BLOCKED_STATUS_KEYS = (
    manual_status.STATUS_BLOCKED_MISSING_IDENTIFIER,
    manual_status.STATUS_BLOCKED_SCOPE_UNCLEAR,
    manual_status.STATUS_REVIEWED_BUT_NOT_PROMOTABLE,
    manual_status.STATUS_REJECTED_BEFORE_PROMOTION,
)

_MISSING = object()


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


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter, key=str.casefold)}


def _count_map(value: Any) -> dict[str, int]:
    return {
        _text(key, "unknown"): _count(count)
        for key, count in _mapping(value).items()
    }


def _snapshot_source(
    task_snapshot_payload: Any,
    *,
    queue_keys: Sequence[str] | None,
    source_kwargs_by_key: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], bool, list[str]]:
    if task_snapshot_payload is _MISSING:
        return (
            task_snapshot.build_plant_review_task_queue_snapshot(
                queue_keys,
                source_kwargs_by_key=source_kwargs_by_key,
            ),
            False,
            [],
        )

    source = _mapping(task_snapshot_payload)
    queue_rows = _sequence(source.get("queue_summaries"))
    summary = _mapping(source.get("summary"))
    task_rows = _sequence(source.get("tasks"))
    malformed = not source or (not queue_rows and not task_rows and not summary)
    warnings = []
    if malformed:
        warnings.append("Task snapshot input is missing or malformed; R156 readback fails closed.")
    return source, malformed, warnings


def _status_source(
    status_payload: Any,
    snapshot_payload: Mapping[str, Any],
    *,
    status_records: Sequence[Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], bool, list[str]]:
    if status_payload is _MISSING:
        return (
            manual_status.build_plant_review_manual_verification_status(
                snapshot_payload,
                status_records=status_records,
            ),
            False,
            [],
        )

    source = _mapping(status_payload)
    records = source.get("status_records")
    summary = _mapping(source.get("summary"))
    malformed = not source or not isinstance(records, Sequence) or isinstance(
        records, (bytes, bytearray, str)
    ) or not summary
    warnings = []
    if malformed:
        warnings.append("Manual verification status input is missing or malformed; R156 readback fails closed.")
    return source, malformed, warnings


def _single_value(values: Sequence[str], fallback: str) -> str:
    clean_values = sorted({_text(value) for value in values if _text(value)}, key=str.casefold)
    if len(clean_values) == 1:
        return clean_values[0]
    if len(clean_values) > 1:
        return "multiple"
    return fallback


def _snapshot_identity(queue_key: str, dataset_key: str) -> str:
    return f"r156-{queue_key}-{dataset_key}-manual-verification-status-snapshot"


def _queue_rows(snapshot_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_mapping(row) for row in _sequence(snapshot_payload.get("queue_summaries"))]


def _task_rows(snapshot_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_mapping(row) for row in _sequence(snapshot_payload.get("tasks"))]


def _task_index(snapshot_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for task in _task_rows(snapshot_payload):
        task_id = _text(task.get("task_id"))
        if task_id:
            index[task_id] = task
    for row in _queue_rows(snapshot_payload):
        queue_key = _text(row.get("queue_key"), "plant_review_queue")
        task_id = f"{queue_key}-summary-manual-status"
        index.setdefault(
            task_id,
            {
                "task_id": task_id,
                "queue_key": queue_key,
                "dataset_key": _text(row.get("dataset_key"), "plant_review_dataset"),
                "task_type": "queue_summary_manual_status",
            },
        )
    return index


def _task_summary(snapshot_payload: Mapping[str, Any], *, malformed: bool) -> dict[str, Any]:
    summary = _mapping(snapshot_payload.get("summary"))
    queue_rows = _queue_rows(snapshot_payload)
    task_rows = _task_rows(snapshot_payload)
    queue_count = len(queue_rows) if queue_rows else (1 if task_rows else 0)
    queue_fail_closed = any(_mapping(row).get("fail_closed") is True for row in queue_rows)

    if task_rows and not summary:
        task_type_counter = Counter(_text(row.get("task_type"), "unknown") for row in task_rows)
        blocked_records = {
            _text(row.get("record_id"))
            for row in task_rows
            if row.get("promotion_blocked") is True or row.get("do_not_promote_until_verified") is True
        }
        represented_records = {
            _text(row.get("record_id"))
            for row in task_rows
            if _text(row.get("record_id"))
        }
        return {
            "queue_count": queue_count,
            "total_tasks": len(task_rows),
            "represented_records": len(represented_records),
            "records_blocked_from_promotion": len(blocked_records),
            "promotion_blocked_count": len(blocked_records),
            "ready_to_promote_count": 0,
            "task_type_counts": _counter_dict(task_type_counter),
            "fail_closed": malformed or queue_fail_closed,
        }

    blocked_count = _count(summary.get("promotion_blocked_count"))
    if blocked_count == 0:
        blocked_count = _count(summary.get("records_blocked_from_promotion"))
    return {
        "queue_count": queue_count or _count(summary.get("queue_count")),
        "total_tasks": _count(summary.get("total_tasks")),
        "represented_records": _count(summary.get("represented_records")),
        "records_blocked_from_promotion": _count(summary.get("records_blocked_from_promotion")),
        "promotion_blocked_count": blocked_count,
        "ready_to_promote_count": _count(summary.get("ready_to_promote_count")),
        "task_type_counts": _count_map(summary.get("task_type_counts")),
        "fail_closed": malformed or summary.get("fail_closed") is True or queue_fail_closed,
    }


def _status_records(status_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_mapping(row) for row in _sequence(status_payload.get("status_records"))]


def _status_summary(status_payload: Mapping[str, Any], *, malformed: bool) -> dict[str, Any]:
    source_summary = _mapping(status_payload.get("summary"))
    records = _status_records(status_payload)
    status_counts = Counter(_text(row.get("verification_status"), "unknown") for row in records)
    promotion_allowed_count = sum(1 for row in records if row.get("promotion_allowed") is True)
    return {
        "total_status_records": _count(
            source_summary.get("total_status_records")
            if source_summary
            else len(records)
        ),
        "pending_count": _count(source_summary.get("pending_count")),
        "manual_review_in_progress_count": _count(source_summary.get("manual_review_in_progress_count")),
        "blocked_count": _count(source_summary.get("blocked_count")),
        "reviewed_but_not_promotable_count": _count(
            source_summary.get("reviewed_but_not_promotable_count")
        ),
        "rejected_count": _count(source_summary.get("rejected_count")),
        "verified_reference_recorded_count": _count(
            source_summary.get("verified_reference_recorded_count")
        ),
        "promotion_allowed_count": max(
            _count(source_summary.get("promotion_allowed_count")),
            promotion_allowed_count,
        ),
        "do_not_promote_count": _count(source_summary.get("do_not_promote_count")),
        "status_counts": _count_map(source_summary.get("status_counts")) or _counter_dict(status_counts),
        "fail_closed": malformed or source_summary.get("fail_closed") is True or promotion_allowed_count > 0,
    }


def _blocked_status_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(
        _text(record.get("verification_status"), "unknown")
        for record in records
        if _text(record.get("verification_status")) in BLOCKED_STATUS_KEYS
    )
    return _counter_dict(counter)


def _status_by_task_type(
    records: Sequence[Mapping[str, Any]],
    task_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter[str]] = {}
    for record in records:
        task_id = _text(record.get("task_id"))
        task = _mapping(task_index.get(task_id))
        task_type = _text(task.get("task_type"), _text(record.get("task_type"), "unknown_task_type"))
        status_key = _text(record.get("verification_status"), "unknown")
        grouped.setdefault(task_type, Counter())[status_key] += 1
    return {
        task_type: _counter_dict(counter)
        for task_type, counter in sorted(grouped.items(), key=lambda item: item[0].casefold())
    }


def _unknown_status_record_count(
    records: Sequence[Mapping[str, Any]],
    task_index: Mapping[str, Mapping[str, Any]],
) -> int:
    if not task_index:
        return len(records)
    return sum(1 for record in records if _text(record.get("task_id")) not in task_index)


def _compact_status_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "status_record_id": _text(record.get("status_record_id")),
                "task_id": _text(record.get("task_id")),
                "queue_key": _text(record.get("queue_key")),
                "dataset_key": _text(record.get("dataset_key")),
                "record_id": _text(record.get("record_id")),
                "verification_status": _text(record.get("verification_status")),
                "identifier_recorded": record.get("identifier_recorded") is True,
                "promotion_allowed": record.get("promotion_allowed") is True,
                "do_not_promote_until_verified": record.get("do_not_promote_until_verified") is not False,
                "documentation_boundary": _text(record.get("documentation_boundary"), DOCUMENTATION_BOUNDARY),
            }
        )
    return rows


def build_plant_review_manual_verification_status_snapshot(
    task_snapshot_payload: Mapping[str, Any] | None | object = _MISSING,
    *,
    status_payload: Mapping[str, Any] | None | object = _MISSING,
    queue_keys: Sequence[str] | None = None,
    source_kwargs_by_key: Mapping[str, Mapping[str, Any]] | None = None,
    status_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a read-only R153 plus R155 status snapshot for plant review queues."""
    snapshot_payload, snapshot_malformed, snapshot_warnings = _snapshot_source(
        task_snapshot_payload,
        queue_keys=queue_keys,
        source_kwargs_by_key=source_kwargs_by_key,
    )
    status_source, status_malformed, status_warnings = _status_source(
        status_payload,
        snapshot_payload,
        status_records=status_records,
    )
    queue_rows = _queue_rows(snapshot_payload)
    task_rows = _task_rows(snapshot_payload)
    queue_key = _single_value(
        [
            *[_text(row.get("queue_key")) for row in queue_rows],
            *[_text(row.get("queue_key")) for row in task_rows],
        ],
        "unknown_queue",
    )
    dataset_key = _single_value(
        [
            *[_text(row.get("dataset_key")) for row in queue_rows],
            *[_text(row.get("dataset_key")) for row in task_rows],
        ],
        "unknown_dataset",
    )
    task_index = _task_index(snapshot_payload)
    records = _status_records(status_source)
    task_summary = _task_summary(snapshot_payload, malformed=snapshot_malformed)
    status_summary = _status_summary(status_source, malformed=status_malformed)
    unknown_count = _unknown_status_record_count(records, task_index)
    promotion_allowed_count = _count(status_summary.get("promotion_allowed_count"))
    fail_closed = (
        snapshot_malformed
        or status_malformed
        or task_summary.get("fail_closed") is True
        or status_summary.get("fail_closed") is True
        or unknown_count > 0
        or promotion_allowed_count > 0
    )
    warnings = [
        *snapshot_warnings,
        *status_warnings,
        *[
            _text(warning)
            for warning in _sequence(status_source.get("warnings"))
            if _text(warning)
        ],
    ]
    if unknown_count:
        warnings.append(
            "One or more manual verification status records reference tasks that are not "
            "present in the supplied task snapshot."
        )

    return _plain_value(
        {
            "snapshot_schema_version": MANUAL_VERIFICATION_STATUS_SNAPSHOT_SCHEMA_VERSION,
            "snapshot_batch": MANUAL_VERIFICATION_STATUS_SNAPSHOT_BATCH,
            "workflow_status": (
                MANUAL_VERIFICATION_STATUS_SNAPSHOT_FAIL_CLOSED
                if fail_closed
                else MANUAL_VERIFICATION_STATUS_SNAPSHOT_READY
            ),
            "snapshot_id": _snapshot_identity(queue_key, dataset_key),
            "queue_key": queue_key,
            "dataset_key": dataset_key,
            "read_only": True,
            "plant_scope_only": True,
            "plain_dict_list_contract": True,
            "task_summary": task_summary,
            "verification_status_summary": status_summary,
            "status_by_task_type": _status_by_task_type(records, task_index),
            "blocked_status_counts": _blocked_status_counts(records),
            "verified_reference_recorded_count": _count(
                status_summary.get("verified_reference_recorded_count")
            ),
            "promotion_allowed_count": promotion_allowed_count,
            "promotion_blocked_count": _count(task_summary.get("promotion_blocked_count")),
            "unknown_status_record_count": unknown_count,
            "manual_review_required": True,
            "fail_closed": fail_closed,
            "fail_closed_reason": FAIL_CLOSED_BOUNDARY if fail_closed else "",
            "documentation_boundary": DOCUMENTATION_BOUNDARY,
            "source_policy": (
                "R156 is a read-only adapter. It does not write seed data, add persistent "
                "storage, fill source or accession fields, change evidence standing, or "
                "promote records."
            ),
            "status_records": _compact_status_rows(records),
            "warnings": warnings,
        }
    )


def build_plant_review_manual_verification_status_snapshot_readback_rows(
    snapshot_payload: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Return one compact plain row for future UI/report consumers."""
    payload = _mapping(snapshot_payload) or build_plant_review_manual_verification_status_snapshot(
        **kwargs
    )
    task_summary = _mapping(payload.get("task_summary"))
    status_summary = _mapping(payload.get("verification_status_summary"))
    return _plain_value(
        [
            {
                "snapshot_id": _text(payload.get("snapshot_id")),
                "queue_key": _text(payload.get("queue_key")),
                "dataset_key": _text(payload.get("dataset_key")),
                "total_tasks": _count(task_summary.get("total_tasks")),
                "represented_records": _count(task_summary.get("represented_records")),
                "records_blocked_from_promotion": _count(
                    task_summary.get("records_blocked_from_promotion")
                ),
                "ready_to_promote_count": _count(task_summary.get("ready_to_promote_count")),
                "verified_reference_recorded_count": _count(
                    status_summary.get("verified_reference_recorded_count")
                ),
                "promotion_allowed_count": _count(payload.get("promotion_allowed_count")),
                "promotion_blocked_count": _count(payload.get("promotion_blocked_count")),
                "unknown_status_record_count": _count(payload.get("unknown_status_record_count")),
                "manual_review_required": payload.get("manual_review_required") is True,
                "fail_closed": payload.get("fail_closed") is True,
                "documentation_boundary": _text(payload.get("documentation_boundary"), DOCUMENTATION_BOUNDARY),
            }
        ]
    )
