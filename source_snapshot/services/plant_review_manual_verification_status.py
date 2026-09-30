from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


MANUAL_VERIFICATION_STATUS_SCHEMA_VERSION = "plant_review_manual_verification_status.v2.7.r155"
MANUAL_VERIFICATION_STATUS_BATCH = "v2.7-r155"
MANUAL_VERIFICATION_STATUS_READY = "plant_review_manual_verification_status_ready"
MANUAL_VERIFICATION_STATUS_FAIL_CLOSED = "plant_review_manual_verification_status_fail_closed"

STATUS_PENDING_MANUAL_REVIEW = "pending_manual_review"
STATUS_MANUAL_REVIEW_IN_PROGRESS = "manual_review_in_progress"
STATUS_BLOCKED_MISSING_IDENTIFIER = "blocked_missing_identifier"
STATUS_BLOCKED_SCOPE_UNCLEAR = "blocked_scope_unclear"
STATUS_REVIEWED_BUT_NOT_PROMOTABLE = "reviewed_but_not_promotable"
STATUS_REJECTED_BEFORE_PROMOTION = "rejected_before_promotion"
STATUS_VERIFIED_REFERENCE_RECORDED = "verified_reference_recorded"

SUPPORTED_VERIFICATION_STATUSES = (
    STATUS_PENDING_MANUAL_REVIEW,
    STATUS_MANUAL_REVIEW_IN_PROGRESS,
    STATUS_BLOCKED_MISSING_IDENTIFIER,
    STATUS_BLOCKED_SCOPE_UNCLEAR,
    STATUS_REVIEWED_BUT_NOT_PROMOTABLE,
    STATUS_REJECTED_BEFORE_PROMOTION,
    STATUS_VERIFIED_REFERENCE_RECORDED,
)

STATUS_RECORD_FIELDS = (
    "status_record_id",
    "task_id",
    "queue_key",
    "dataset_key",
    "record_id",
    "record_type",
    "verification_status",
    "reviewer_note",
    "reviewed_reference_kind",
    "reviewed_reference_value",
    "identifier_recorded",
    "promotion_allowed",
    "promotion_blocked_reason",
    "requires_second_review",
    "do_not_promote_until_verified",
    "documentation_boundary",
)

DOCUMENTATION_BOUNDARY = (
    "Documentation-only plant review manual status record. It records reviewer-entered "
    "status data without changing seed records, filling identifiers, changing evidence "
    "standing, allowing promotion, or making downstream-use judgments."
)

FAIL_CLOSED_BOUNDARY = (
    "Manual status input is empty or malformed, so status readback fails closed and "
    "promotion remains blocked."
)

IDENTIFIER_FIELD_HINTS = {
    "source_id",
    "source_identifier",
    "accession",
    "accession_id",
    "database_id",
    "pmid",
    "doi",
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


def _status_record_index(status_records: Sequence[Any] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for raw_record in _sequence(status_records):
        record = _mapping(raw_record)
        task_id = _text(record.get("task_id"))
        if task_id and task_id not in index:
            index[task_id] = record
    return index


def _queue_metadata(source: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _mapping(source.get("queue_metadata"))
    if metadata:
        return metadata
    snapshot_metadata = _mapping(source.get("snapshot_metadata"))
    queue_keys = _sequence(snapshot_metadata.get("queue_keys"))
    return {
        "queue_key": _text(queue_keys[0] if queue_keys else "", "plant_review_manual_verification_status"),
        "dataset_key": "plant_review",
    }


def _task_rows_from_source(source_payload_or_rows: Any) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    if isinstance(source_payload_or_rows, Mapping):
        source = _mapping(source_payload_or_rows)
        metadata = _queue_metadata(source)
        tasks = [_mapping(task) for task in _sequence(source.get("tasks")) if isinstance(task, Mapping)]
        if tasks:
            return tasks, metadata, False

        queue_summaries = [
            _mapping(row) for row in _sequence(source.get("queue_summaries")) if isinstance(row, Mapping)
        ]
        if queue_summaries:
            rows = [
                {
                    "task_id": f"{_text(row.get('queue_key'), 'plant_review_queue')}-summary-manual-status",
                    "queue_key": _text(row.get("queue_key"), _text(metadata.get("queue_key"))),
                    "dataset_key": _text(row.get("dataset_key"), _text(metadata.get("dataset_key"))),
                    "record_id": _text(row.get("queue_key"), "plant_review_queue_summary"),
                    "record_type": "PlantReviewTaskQueueSummary",
                    "task_type": "queue_summary_manual_status",
                    "task_label": "Queue summary manual status",
                    "blocking_reason": _text(
                        row.get("manual_review_boundary_text"),
                        "Queue summary remains documentation-only and promotion remains blocked.",
                    ),
                    "promotion_blocked": True,
                    "do_not_promote_until_verified": True,
                    "documentation_boundary": _text(
                        row.get("manual_review_boundary_text"),
                        DOCUMENTATION_BOUNDARY,
                    ),
                }
                for row in queue_summaries
            ]
            return rows, metadata, False

        return [], metadata, True

    rows = [_mapping(row) for row in _sequence(source_payload_or_rows) if isinstance(row, Mapping)]
    return rows, {}, not bool(rows)


def _status_from_record(status_record: Mapping[str, Any], task: Mapping[str, Any]) -> str:
    requested = _text(status_record.get("verification_status")).casefold()
    if requested in SUPPORTED_VERIFICATION_STATUSES:
        return requested

    missing_fields = {_text(field).casefold() for field in _sequence(task.get("missing_fields"))}
    if missing_fields & IDENTIFIER_FIELD_HINTS and task.get("promotion_blocked") is True:
        return STATUS_PENDING_MANUAL_REVIEW
    return STATUS_PENDING_MANUAL_REVIEW


def _promotion_blocked_reason(
    verification_status: str,
    status_record: Mapping[str, Any],
    task: Mapping[str, Any],
) -> str:
    explicit_reason = _text(status_record.get("promotion_blocked_reason"))
    if explicit_reason:
        return explicit_reason
    if verification_status == STATUS_VERIFIED_REFERENCE_RECORDED:
        return (
            "Reviewer-entered reference status is recorded only in this status payload; "
            "record promotion remains blocked until a separately scoped seed update."
        )
    if verification_status == STATUS_REJECTED_BEFORE_PROMOTION:
        return "Reviewer status rejects this task before any record promotion."
    return _text(task.get("blocking_reason"), "Manual review status does not allow record promotion.")


def _status_record_id(queue_key: str, task_id: str, status_record: Mapping[str, Any]) -> str:
    explicit_id = _text(status_record.get("status_record_id"))
    if explicit_id:
        return explicit_id
    return f"r155-{queue_key}-{task_id}-manual-verification-status"


def _status_row(
    task: Mapping[str, Any],
    *,
    status_record: Mapping[str, Any],
    queue_key: str,
    dataset_key: str,
) -> dict[str, Any]:
    task_id = _text(task.get("task_id"), "unknown-plant-review-task")
    verification_status = _status_from_record(status_record, task)
    reviewed_kind = _text(status_record.get("reviewed_reference_kind"))
    reviewed_value = _text(status_record.get("reviewed_reference_value"))
    identifier_recorded = (
        verification_status == STATUS_VERIFIED_REFERENCE_RECORDED
        and bool(reviewed_kind)
        and bool(reviewed_value)
    )
    return {
        "status_record_id": _status_record_id(queue_key, task_id, status_record),
        "task_id": task_id,
        "queue_key": _text(task.get("queue_key"), queue_key),
        "dataset_key": _text(task.get("dataset_key"), dataset_key),
        "record_id": _text(task.get("record_id"), "unknown_plant_review_record"),
        "record_type": _text(task.get("record_type"), "PlantReviewRecord"),
        "verification_status": verification_status,
        "reviewer_note": _text(status_record.get("reviewer_note")),
        "reviewed_reference_kind": reviewed_kind,
        "reviewed_reference_value": reviewed_value,
        "identifier_recorded": identifier_recorded,
        "promotion_allowed": False,
        "promotion_blocked_reason": _promotion_blocked_reason(verification_status, status_record, task),
        "requires_second_review": status_record.get("requires_second_review") is True,
        "do_not_promote_until_verified": True,
        "documentation_boundary": _text(
            status_record.get("documentation_boundary"),
            _text(task.get("documentation_boundary"), DOCUMENTATION_BOUNDARY),
        ),
    }


def _fail_closed_status_record(reason: str) -> dict[str, Any]:
    return {
        "status_record_id": "r155-fail-closed-manual-verification-status",
        "task_id": "unknown-plant-review-task",
        "queue_key": "unknown_queue",
        "dataset_key": "unknown_dataset",
        "record_id": "unknown_plant_review_records",
        "record_type": "PlantReviewManualStatusInput",
        "verification_status": STATUS_BLOCKED_SCOPE_UNCLEAR,
        "reviewer_note": "",
        "reviewed_reference_kind": "",
        "reviewed_reference_value": "",
        "identifier_recorded": False,
        "promotion_allowed": False,
        "promotion_blocked_reason": f"{FAIL_CLOSED_BOUNDARY} Reason: {reason}.",
        "requires_second_review": True,
        "do_not_promote_until_verified": True,
        "documentation_boundary": DOCUMENTATION_BOUNDARY,
    }


def _summary(records: Sequence[Mapping[str, Any]], *, fail_closed: bool) -> dict[str, Any]:
    status_counts = Counter(_text(record.get("verification_status"), "unknown") for record in records)
    blocked_count = (
        status_counts[STATUS_BLOCKED_MISSING_IDENTIFIER]
        + status_counts[STATUS_BLOCKED_SCOPE_UNCLEAR]
    )
    promotion_allowed_count = sum(1 for record in records if record.get("promotion_allowed") is True)
    do_not_promote_count = sum(
        1 for record in records if record.get("do_not_promote_until_verified") is True
    )
    return {
        "total_status_records": len(records),
        "pending_count": status_counts[STATUS_PENDING_MANUAL_REVIEW],
        "manual_review_in_progress_count": status_counts[STATUS_MANUAL_REVIEW_IN_PROGRESS],
        "blocked_count": blocked_count,
        "reviewed_but_not_promotable_count": status_counts[STATUS_REVIEWED_BUT_NOT_PROMOTABLE],
        "rejected_count": status_counts[STATUS_REJECTED_BEFORE_PROMOTION],
        "verified_reference_recorded_count": status_counts[STATUS_VERIFIED_REFERENCE_RECORDED],
        "promotion_allowed_count": promotion_allowed_count,
        "do_not_promote_count": do_not_promote_count,
        "status_counts": {
            key: status_counts[key]
            for key in sorted(status_counts, key=str.casefold)
        },
        "fail_closed": fail_closed or promotion_allowed_count > 0,
        "fail_closed_state": (
            "closed_for_manual_review"
            if fail_closed or promotion_allowed_count > 0
            else "open_for_manual_status_readback_only"
        ),
    }


def build_plant_review_manual_verification_status(
    source_payload_or_rows: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    *,
    status_records: Sequence[Mapping[str, Any]] | None = None,
    queue_key: str | None = None,
    dataset_key: str | None = None,
) -> dict[str, Any]:
    """Return read-only manual verification status readback for plant review tasks."""
    tasks, metadata, malformed = _task_rows_from_source(source_payload_or_rows)
    explicit_status_by_task = _status_record_index(status_records)
    default_queue_key = _text(queue_key, _text(metadata.get("queue_key"), "plant_review_manual_status"))
    default_dataset_key = _text(dataset_key, _text(metadata.get("dataset_key"), "plant_review_dataset"))

    if malformed:
        records = [_fail_closed_status_record("empty_or_malformed_task_input")]
        warnings = ["Manual verification status input is empty or malformed; readback fails closed."]
        fail_closed = True
    else:
        records = [
            _status_row(
                task,
                status_record=_mapping(explicit_status_by_task.get(_text(task.get("task_id")))),
                queue_key=default_queue_key,
                dataset_key=default_dataset_key,
            )
            for task in tasks
        ]
        records = sorted(
            records,
            key=lambda item: (
                _text(item.get("queue_key")),
                _text(item.get("dataset_key")),
                _text(item.get("record_id")),
                _text(item.get("task_id")),
            ),
        )
        warnings = []
        fail_closed = False

    return _plain_value(
        {
            "workflow_schema_version": MANUAL_VERIFICATION_STATUS_SCHEMA_VERSION,
            "workflow_batch": MANUAL_VERIFICATION_STATUS_BATCH,
            "workflow_status": (
                MANUAL_VERIFICATION_STATUS_FAIL_CLOSED
                if fail_closed
                else MANUAL_VERIFICATION_STATUS_READY
            ),
            "read_only": True,
            "plant_scope_only": True,
            "plain_dict_list_contract": True,
            "supported_verification_statuses": list(SUPPORTED_VERIFICATION_STATUSES),
            "status_record_fields": list(STATUS_RECORD_FIELDS),
            "documentation_boundary": DOCUMENTATION_BOUNDARY,
            "source_policy": (
                "Status records are reviewer-entered readback data only. This service does not "
                "write seed data, fill identifiers, look up sources, change evidence standing, "
                "or promote records."
            ),
            "summary": _summary(records, fail_closed=fail_closed),
            "status_records": records,
            "warnings": warnings,
        }
    )


def build_plant_review_manual_verification_status_readback_rows(
    status_payload: Mapping[str, Any] | None = None,
    *,
    source_payload_or_rows: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    status_records: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return compact manual verification status rows for future readback consumers."""
    payload = _mapping(status_payload) or build_plant_review_manual_verification_status(
        source_payload_or_rows,
        status_records=status_records,
    )
    rows: list[dict[str, Any]] = []
    for raw_record in _sequence(payload.get("status_records")):
        record = _mapping(raw_record)
        rows.append(
            {
                "status_record_id": _text(record.get("status_record_id")),
                "task_id": _text(record.get("task_id")),
                "queue_key": _text(record.get("queue_key")),
                "dataset_key": _text(record.get("dataset_key")),
                "record_id": _text(record.get("record_id")),
                "verification_status": _text(record.get("verification_status")),
                "identifier_recorded": record.get("identifier_recorded") is True,
                "promotion_allowed": False,
                "do_not_promote_until_verified": True,
                "documentation_boundary": _text(record.get("documentation_boundary"), DOCUMENTATION_BOUNDARY),
            }
        )
    return _plain_value(rows)
