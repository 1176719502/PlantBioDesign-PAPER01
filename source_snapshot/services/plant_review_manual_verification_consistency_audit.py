from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services import plant_review_manual_verification_promotion_gate as promotion_gate
from services import plant_review_manual_verification_status as manual_status
from services import plant_review_manual_verification_status_snapshot as status_snapshot
from services import plant_review_task_queue_registry as registry
from services import plant_review_task_queue_snapshot_readback as task_snapshot


MANUAL_VERIFICATION_CONSISTENCY_AUDIT_SCHEMA_VERSION = (
    "plant_review_manual_verification_consistency_audit.v2.7.r159"
)
MANUAL_VERIFICATION_CONSISTENCY_AUDIT_BATCH = "v2.7-r159"
AUDIT_STATUS_READY = "manual_verification_consistency_audit_ready"
AUDIT_STATUS_FAIL_CLOSED = "manual_verification_consistency_audit_fail_closed"

DOCUMENTATION_BOUNDARY = (
    "Documentation-only manual verification consistency audit. It checks queue, status, "
    "snapshot, transition, and gate readbacks without writing records, filling identifiers, "
    "changing seed data, changing evidence standing, or promoting records."
)

FAIL_CLOSED_BOUNDARY = (
    "Manual verification consistency inputs are missing, malformed, or internally "
    "conflicting, so this audit fails closed and record promotion remains blocked."
)

STATUS_DEFAULT_WARNING = (
    "Missing manual status rows are treated as pending manual review for audit readback."
)


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


def _task_rows(queue_payload: Mapping[str, Any], snapshot_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    direct_tasks = [_mapping(row) for row in _sequence(queue_payload.get("tasks"))]
    if direct_tasks:
        return direct_tasks
    return [_mapping(row) for row in _sequence(snapshot_payload.get("tasks"))]


def _queue_rows(queue_payload: Mapping[str, Any], snapshot_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [_mapping(row) for row in _sequence(snapshot_payload.get("queue_summaries"))]
    if rows:
        return rows
    metadata = _mapping(queue_payload.get("queue_metadata"))
    summary = _mapping(queue_payload.get("summary"))
    if not metadata and not summary:
        return []
    return [
        {
            "queue_key": _text(metadata.get("queue_key")),
            "dataset_key": _text(metadata.get("dataset_key")),
            "total_tasks": _count(summary.get("total_tasks")),
            "ready_to_promote_count": _count(summary.get("ready_to_promote_count")),
            "promotion_allowed": metadata.get("promotion_allowed") is True,
            "fail_closed": summary.get("fail_closed") is True,
        }
    ]


def _status_records(
    status_payload: Mapping[str, Any],
    snapshot_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = [_mapping(row) for row in _sequence(status_payload.get("status_records"))]
    if rows:
        return rows
    return [_mapping(row) for row in _sequence(snapshot_payload.get("status_records"))]


def _status_summary(
    status_payload: Mapping[str, Any],
    snapshot_payload: Mapping[str, Any],
) -> dict[str, Any]:
    return _mapping(status_payload.get("summary")) or _mapping(
        snapshot_payload.get("verification_status_summary")
    )


def _task_index(tasks: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for task in tasks:
        task_id = _text(task.get("task_id"))
        if task_id and task_id not in index:
            index[task_id] = _mapping(task)
    return index


def _status_index(records: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        task_id = _text(record.get("task_id"))
        if task_id:
            index.setdefault(task_id, []).append(_mapping(record))
    return index


def _queue_key(queue_payload: Mapping[str, Any], snapshot_payload: Mapping[str, Any]) -> str:
    metadata = _mapping(queue_payload.get("queue_metadata"))
    snapshot_metadata = _mapping(snapshot_payload.get("snapshot_metadata"))
    queue_keys = [_text(value) for value in _sequence(snapshot_metadata.get("queue_keys")) if _text(value)]
    return _text(
        metadata.get("queue_key"),
        _text(queue_keys[0] if queue_keys else "", "unknown_queue"),
    )


def _dataset_key(queue_payload: Mapping[str, Any], snapshot_payload: Mapping[str, Any]) -> str:
    metadata = _mapping(queue_payload.get("queue_metadata"))
    queue_rows = [_mapping(row) for row in _sequence(snapshot_payload.get("queue_summaries"))]
    return _text(
        metadata.get("dataset_key"),
        _text(queue_rows[0].get("dataset_key") if queue_rows else "", "unknown_dataset"),
    )


def _dataset_mismatch_findings(
    expected_dataset_key: str,
    tasks: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    queue_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in tasks:
        dataset_key = _text(row.get("dataset_key"), expected_dataset_key)
        if dataset_key and dataset_key != expected_dataset_key:
            findings.append(
                {
                    "finding_type": "task_dataset_mismatch",
                    "task_id": _text(row.get("task_id")),
                    "expected_dataset_key": expected_dataset_key,
                    "observed_dataset_key": dataset_key,
                    "fail_closed": True,
                }
            )
    for row in records:
        dataset_key = _text(row.get("dataset_key"), expected_dataset_key)
        if dataset_key and dataset_key != expected_dataset_key:
            findings.append(
                {
                    "finding_type": "status_dataset_mismatch",
                    "task_id": _text(row.get("task_id")),
                    "status_record_id": _text(row.get("status_record_id")),
                    "expected_dataset_key": expected_dataset_key,
                    "observed_dataset_key": dataset_key,
                    "fail_closed": True,
                }
            )
    for row in queue_rows:
        dataset_key = _text(row.get("dataset_key"), expected_dataset_key)
        if dataset_key and dataset_key != expected_dataset_key:
            findings.append(
                {
                    "finding_type": "queue_summary_dataset_mismatch",
                    "queue_key": _text(row.get("queue_key")),
                    "expected_dataset_key": expected_dataset_key,
                    "observed_dataset_key": dataset_key,
                    "fail_closed": True,
                }
            )
    return findings


def _missing_status_findings(
    tasks: Sequence[Mapping[str, Any]],
    records_by_task: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for task in tasks:
        task_id = _text(task.get("task_id"))
        if task_id and task_id not in records_by_task:
            findings.append(
                {
                    "finding_type": "task_without_status",
                    "task_id": task_id,
                    "record_id": _text(task.get("record_id")),
                    "assumed_verification_status": manual_status.STATUS_PENDING_MANUAL_REVIEW,
                    "manual_review_required": True,
                    "fail_closed": False,
                }
            )
    return findings


def _unknown_status_findings(
    records: Sequence[Mapping[str, Any]],
    tasks_by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for record in records:
        task_id = _text(record.get("task_id"))
        if task_id and task_id not in tasks_by_id:
            findings.append(
                {
                    "finding_type": "unknown_task_status_record",
                    "task_id": task_id,
                    "status_record_id": _text(record.get("status_record_id")),
                    "verification_status": _text(record.get("verification_status")),
                    "fail_closed": True,
                }
            )
    return findings


def _promotion_conflict_findings(
    status_summary: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    gate_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    gate_blocks_promotion = gate_payload.get("promotion_allowed") is not True
    findings: list[dict[str, Any]] = []
    if not gate_blocks_promotion:
        return findings

    summary_count = _count(status_summary.get("promotion_allowed_count"))
    if summary_count:
        findings.append(
            {
                "finding_type": "status_summary_promotion_conflict",
                "promotion_allowed_count": summary_count,
                "gate_promotion_allowed": False,
                "fail_closed": True,
            }
        )
    for record in records:
        if record.get("promotion_allowed") is True:
            findings.append(
                {
                    "finding_type": "status_record_promotion_conflict",
                    "task_id": _text(record.get("task_id")),
                    "status_record_id": _text(record.get("status_record_id")),
                    "verification_status": _text(record.get("verification_status")),
                    "gate_promotion_allowed": False,
                    "fail_closed": True,
                }
            )
    return findings


def _verified_reference_without_promotion_findings(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for record in records:
        if (
            _text(record.get("verification_status"))
            == manual_status.STATUS_VERIFIED_REFERENCE_RECORDED
            and record.get("promotion_allowed") is not True
        ):
            findings.append(
                {
                    "finding_type": "verified_reference_recorded_status_only",
                    "task_id": _text(record.get("task_id")),
                    "status_record_id": _text(record.get("status_record_id")),
                    "promotion_allowed": False,
                    "fail_closed": False,
                }
            )
    return findings


def _input_fail_closed(
    queue_payload: Mapping[str, Any],
    snapshot_payload: Mapping[str, Any],
    status_payload: Mapping[str, Any],
    status_snapshot_payload: Mapping[str, Any],
    gate_payload: Mapping[str, Any],
) -> bool:
    return any(
        [
            _mapping(queue_payload.get("summary")).get("fail_closed") is True,
            _mapping(snapshot_payload.get("summary")).get("fail_closed") is True,
            _mapping(status_payload.get("summary")).get("fail_closed") is True,
            status_snapshot_payload.get("fail_closed") is True,
            gate_payload.get("fail_closed") is True,
        ]
    )


def build_plant_review_manual_verification_consistency_audit(
    task_queue_payload: Mapping[str, Any] | None = None,
    *,
    task_snapshot_payload: Mapping[str, Any] | None = None,
    status_payload: Mapping[str, Any] | None = None,
    status_snapshot_payload: Mapping[str, Any] | None = None,
    promotion_gate_payload: Mapping[str, Any] | None = None,
    source_kwargs_by_key: Mapping[str, Mapping[str, Any]] | None = None,
    status_records: Sequence[Mapping[str, Any]] | None = None,
    queue_key: str | None = None,
    dataset_key: str | None = None,
) -> dict[str, Any]:
    """Return a read-only consistency audit across manual verification readbacks."""
    queue_payload = _mapping(task_queue_payload)
    if not queue_payload and queue_key:
        queue_payload = registry.get_plant_review_task_queue_payload(
            queue_key,
            source_kwargs=_mapping(_mapping(source_kwargs_by_key).get(queue_key)),
        )
    snapshot_payload = _mapping(task_snapshot_payload) or task_snapshot.build_plant_review_task_queue_snapshot(
        [queue_key] if queue_key else None,
        source_kwargs_by_key=source_kwargs_by_key,
    )
    if not queue_payload:
        default_queue_key = _text(queue_key, registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY)
        queue_payload = registry.get_plant_review_task_queue_payload(
            default_queue_key,
            source_kwargs=_mapping(_mapping(source_kwargs_by_key).get(default_queue_key)),
        )

    status_source = _mapping(status_payload)
    if not status_source:
        status_source = manual_status.build_plant_review_manual_verification_status(
            queue_payload,
            status_records=status_records,
        )
    status_snapshot_input = queue_payload if _sequence(queue_payload.get("tasks")) else snapshot_payload
    status_snapshot_source = _mapping(status_snapshot_payload) or (
        status_snapshot.build_plant_review_manual_verification_status_snapshot(
            status_snapshot_input,
            status_payload=status_source,
        )
    )
    gate_source = _mapping(promotion_gate_payload) or promotion_gate.build_plant_review_manual_verification_promotion_gate(
        status_snapshot_source
    )

    tasks = _task_rows(queue_payload, snapshot_payload)
    records = _status_records(status_source, status_snapshot_source)
    rows = _queue_rows(queue_payload, snapshot_payload)
    tasks_by_id = _task_index(tasks)
    records_by_task = _status_index(records)
    clean_queue_key = _text(queue_key, _queue_key(queue_payload, snapshot_payload))
    clean_dataset_key = _text(dataset_key, _dataset_key(queue_payload, snapshot_payload))
    status_summary = _status_summary(status_source, status_snapshot_source)

    missing_status_findings = _missing_status_findings(tasks, records_by_task)
    unknown_status_findings = _unknown_status_findings(records, tasks_by_id)
    dataset_mismatch_findings = _dataset_mismatch_findings(
        clean_dataset_key,
        tasks,
        records,
        rows,
    )
    promotion_conflict_findings = _promotion_conflict_findings(
        status_summary,
        records,
        gate_source,
    )
    status_only_findings = _verified_reference_without_promotion_findings(records)
    blocking_findings = [
        *unknown_status_findings,
        *dataset_mismatch_findings,
        *promotion_conflict_findings,
    ]
    warning_findings = [
        *missing_status_findings,
        *status_only_findings,
    ]
    if not records:
        warning_findings.append(
            {
                "finding_type": "missing_status_payload",
                "assumed_verification_status": manual_status.STATUS_PENDING_MANUAL_REVIEW,
                "manual_review_required": True,
                "fail_closed": False,
            }
        )
    if missing_status_findings:
        warning_findings.append(
            {
                "finding_type": "missing_status_default_policy",
                "finding_note": STATUS_DEFAULT_WARNING,
                "fail_closed": False,
            }
        )

    fail_closed = bool(blocking_findings) or _input_fail_closed(
        queue_payload,
        snapshot_payload,
        status_source,
        status_snapshot_source,
        gate_source,
    )

    return _plain_value(
        {
            "audit_schema_version": MANUAL_VERIFICATION_CONSISTENCY_AUDIT_SCHEMA_VERSION,
            "audit_batch": MANUAL_VERIFICATION_CONSISTENCY_AUDIT_BATCH,
            "audit_status": AUDIT_STATUS_FAIL_CLOSED if fail_closed else AUDIT_STATUS_READY,
            "fail_closed": fail_closed,
            "queue_key": clean_queue_key,
            "dataset_key": clean_dataset_key,
            "total_tasks": len(tasks) or _count(_mapping(snapshot_payload.get("summary")).get("total_tasks")),
            "status_record_count": len(records) or _count(status_summary.get("total_status_records")),
            "tasks_without_status_count": len(missing_status_findings),
            "unknown_task_status_count": len(unknown_status_findings),
            "dataset_mismatch_count": len(dataset_mismatch_findings),
            "promotion_conflict_count": len(promotion_conflict_findings),
            "verified_reference_without_promotion_count": len(status_only_findings),
            "promotion_allowed": False,
            "promotion_allowed_count": 0,
            "ready_to_promote_count": 0,
            "gate_promotion_allowed": gate_source.get("promotion_allowed") is True,
            "gate_promotion_allowed_count": _count(gate_source.get("promotion_allowed_count")),
            "blocking_findings": blocking_findings,
            "warning_findings": warning_findings,
            "manual_review_required": True,
            "read_only": True,
            "plant_scope_only": True,
            "plain_dict_list_contract": True,
            "documentation_boundary": DOCUMENTATION_BOUNDARY,
            "source_policy": (
                "R159 is a read-only audit. It does not write status records, fill source "
                "or accession fields, change seed data, change evidence standing, or "
                "promote records."
            ),
            "fail_closed_reason": FAIL_CLOSED_BOUNDARY if fail_closed else "",
        }
    )


def build_plant_review_manual_verification_consistency_audit_rows(
    audit_payload: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Return one compact consistency-audit row for future readback consumers."""
    payload = _mapping(audit_payload) or build_plant_review_manual_verification_consistency_audit(
        **kwargs
    )
    return _plain_value(
        [
            {
                "queue_key": _text(payload.get("queue_key")),
                "dataset_key": _text(payload.get("dataset_key")),
                "audit_status": _text(payload.get("audit_status")),
                "total_tasks": _count(payload.get("total_tasks")),
                "status_record_count": _count(payload.get("status_record_count")),
                "tasks_without_status_count": _count(payload.get("tasks_without_status_count")),
                "unknown_task_status_count": _count(payload.get("unknown_task_status_count")),
                "dataset_mismatch_count": _count(payload.get("dataset_mismatch_count")),
                "promotion_conflict_count": _count(payload.get("promotion_conflict_count")),
                "verified_reference_without_promotion_count": _count(
                    payload.get("verified_reference_without_promotion_count")
                ),
                "promotion_allowed": False,
                "ready_to_promote_count": 0,
                "manual_review_required": True,
                "fail_closed": payload.get("fail_closed") is True,
                "documentation_boundary": _text(payload.get("documentation_boundary"), DOCUMENTATION_BOUNDARY),
            }
        ]
    )
