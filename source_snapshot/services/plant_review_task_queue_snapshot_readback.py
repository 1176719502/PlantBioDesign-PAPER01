from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from services import plant_review_task_queue_registry as registry


PLANT_REVIEW_TASK_QUEUE_SNAPSHOT_SCHEMA_VERSION = "plant_review_task_queue_snapshot_readback.v2.7.r153"
PLANT_REVIEW_TASK_QUEUE_SNAPSHOT_BATCH = "v2.7-r153"

MANUAL_REVIEW_BOUNDARY_TEXT = (
    "Documentation-only plant review task queue snapshot. It summarizes registered "
    "manual review queues without source lookup, identifier filling, record changes, "
    "record promotion, route improvement, or downstream-use judgment."
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


def _counter_to_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter, key=str.casefold)}


def _merge_count_maps(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for item_key, value in _mapping(row).items():
            counter[_text(item_key, "unknown")] += int(value or 0)
    return _counter_to_dict(counter)


def _task_counter(tasks: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    counter = Counter(_text(task.get(field), "unknown") for task in tasks)
    return _counter_to_dict(counter)


def _top_blocking_reasons(tasks: Sequence[Mapping[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    counter = Counter(_text(task.get("blocking_reason")) for task in tasks if _text(task.get("blocking_reason")))
    rows = sorted(counter.items(), key=lambda item: (-item[1], item[0].casefold()))
    return [
        {"blocking_reason": reason, "task_count": count}
        for reason, count in rows[:limit]
    ]


def _source_gap_counts(payload: Mapping[str, Any]) -> dict[str, int]:
    metadata = _mapping(payload.get("queue_metadata"))
    source_summary = _mapping(metadata.get("source_summary"))
    return {
        "missing_source_id_count": int(source_summary.get("missing_source_id_count") or 0),
        "missing_accession_count": int(source_summary.get("missing_accession_count") or 0),
    }


def _queue_summary_row(source: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(payload.get("summary"))
    tasks = [_mapping(task) for task in _sequence(payload.get("tasks"))]
    source_gaps = _source_gap_counts(payload)
    return {
        "queue_key": _text(source.get("queue_key")),
        "queue_label": _text(source.get("queue_label")),
        "dataset_key": _text(source.get("dataset_key")),
        "queue_status": _text(source.get("queue_status")),
        "active": source.get("active") is True,
        "manual_review_required": source.get("manual_review_required") is not False,
        "promotion_allowed": False,
        "payload_workflow_status": _text(payload.get("workflow_status")),
        "total_tasks": int(summary.get("total_tasks") or 0),
        "represented_records": int(summary.get("represented_records") or 0),
        "records_requiring_manual_review": int(summary.get("records_requiring_manual_review") or 0),
        "records_blocked_from_promotion": int(summary.get("records_blocked_from_promotion") or 0),
        "promotion_blocked_count": int(summary.get("records_blocked_from_promotion") or 0),
        "ready_to_promote_count": int(summary.get("ready_to_promote_count") or 0),
        "task_type_counts": _mapping(summary.get("task_type_counts")),
        "missing_field_counts": _mapping(summary.get("missing_field_counts")),
        "missing_source_id_count": source_gaps["missing_source_id_count"],
        "missing_accession_count": source_gaps["missing_accession_count"],
        "top_blocking_reasons": _top_blocking_reasons(tasks),
        "manual_review_boundary_text": MANUAL_REVIEW_BOUNDARY_TEXT,
        "fail_closed": summary.get("fail_closed") is True,
    }


def _snapshot_metadata(queue_keys: Sequence[str]) -> dict[str, Any]:
    return {
        "snapshot_schema_version": PLANT_REVIEW_TASK_QUEUE_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_batch": PLANT_REVIEW_TASK_QUEUE_SNAPSHOT_BATCH,
        "queue_keys": list(queue_keys),
        "read_only": True,
        "plain_dict_list_contract": True,
        "manual_review_boundary_text": MANUAL_REVIEW_BOUNDARY_TEXT,
    }


def build_plant_review_task_queue_snapshot(
    queue_keys: Sequence[str] | None = None,
    *,
    source_kwargs_by_key: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a compact snapshot for registered plant review task queues."""
    requested_keys = [
        _text(key)
        for key in (
            _sequence(queue_keys)
            if queue_keys is not None
            else [registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY]
        )
        if _text(key)
    ]
    if not requested_keys:
        requested_keys = ["unknown_queue"]
    kwargs_by_key = _mapping(source_kwargs_by_key)

    queue_rows: list[dict[str, Any]] = []
    task_type_rows: list[dict[str, Any]] = []
    missing_field_rows: list[dict[str, Any]] = []
    blocking_counter: Counter[str] = Counter()

    for queue_key in requested_keys:
        source_kwargs = _mapping(kwargs_by_key.get(queue_key))
        source = registry.get_plant_review_task_queue_source(
            queue_key,
            source_kwargs=source_kwargs,
        )
        payload = registry.get_plant_review_task_queue_payload(
            queue_key,
            source_kwargs=source_kwargs,
        )
        row = _queue_summary_row(source, payload)
        queue_rows.append(row)
        task_type_rows.append(_mapping(row.get("task_type_counts")))
        missing_field_rows.append(_mapping(row.get("missing_field_counts")))
        for item in _sequence(row.get("top_blocking_reasons")):
            reason_row = _mapping(item)
            blocking_counter[_text(reason_row.get("blocking_reason"))] += int(
                reason_row.get("task_count") or 0
            )

    top_blocking_reasons = [
        {"blocking_reason": reason, "task_count": count}
        for reason, count in sorted(blocking_counter.items(), key=lambda item: (-item[1], item[0].casefold()))[:5]
        if reason
    ]
    total_tasks = sum(int(row.get("total_tasks") or 0) for row in queue_rows)
    represented_records = sum(int(row.get("represented_records") or 0) for row in queue_rows)
    blocked_count = sum(int(row.get("records_blocked_from_promotion") or 0) for row in queue_rows)
    ready_count = sum(int(row.get("ready_to_promote_count") or 0) for row in queue_rows)

    return _plain_value(
        {
            "snapshot_metadata": _snapshot_metadata(requested_keys),
            "queue_summaries": queue_rows,
            "summary": {
                "queue_count": len(queue_rows),
                "total_tasks": total_tasks,
                "represented_records": represented_records,
                "records_blocked_from_promotion": blocked_count,
                "promotion_blocked_count": blocked_count,
                "ready_to_promote_count": ready_count,
                "task_type_counts": _merge_count_maps(task_type_rows),
                "missing_field_counts": _merge_count_maps(missing_field_rows),
                "top_blocking_reasons": top_blocking_reasons,
                "manual_review_boundary_text": MANUAL_REVIEW_BOUNDARY_TEXT,
                "fail_closed": any(row.get("fail_closed") is True for row in queue_rows),
            },
        }
    )


def build_plant_review_task_queue_readback_rows(
    snapshot_payload: Mapping[str, Any] | None = None,
    *,
    queue_keys: Sequence[str] | None = None,
    source_kwargs_by_key: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return compact plain rows for future UI/report consumers."""
    source = _mapping(snapshot_payload) or build_plant_review_task_queue_snapshot(
        queue_keys,
        source_kwargs_by_key=source_kwargs_by_key,
    )
    rows: list[dict[str, Any]] = []
    for queue_summary in _sequence(source.get("queue_summaries")):
        row = _mapping(queue_summary)
        rows.append(
            {
                "queue_key": _text(row.get("queue_key")),
                "dataset_key": _text(row.get("dataset_key")),
                "queue_status": _text(row.get("queue_status")),
                "total_tasks": int(row.get("total_tasks") or 0),
                "represented_records": int(row.get("represented_records") or 0),
                "records_blocked_from_promotion": int(row.get("records_blocked_from_promotion") or 0),
                "ready_to_promote_count": int(row.get("ready_to_promote_count") or 0),
                "missing_source_id_count": int(row.get("missing_source_id_count") or 0),
                "missing_accession_count": int(row.get("missing_accession_count") or 0),
                "promotion_allowed": row.get("promotion_allowed") is True,
                "manual_review_boundary_text": _text(
                    row.get("manual_review_boundary_text"),
                    MANUAL_REVIEW_BOUNDARY_TEXT,
                ),
                "fail_closed": row.get("fail_closed") is True,
            }
        )
    return _plain_value(rows)
