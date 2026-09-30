from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from services.rice_albumin_manual_provenance_verification import (
    DEFAULT_RICE_ALBUMIN_SEED_DIR,
    REVIEW_REQUIRED_STATUS,
)
from services.rice_albumin_manual_provenance_verification_queue import (
    DOCUMENTATION_BOUNDARY as RICE_ALBUMIN_QUEUE_BOUNDARY,
    build_rice_albumin_manual_provenance_verification_queue,
)


PLANT_REVIEW_TASK_QUEUE_SCHEMA_VERSION = "plant_review_task_queue.v2.7.r151"
PLANT_REVIEW_TASK_QUEUE_BATCH = "v2.7-r151"
PLANT_REVIEW_TASK_QUEUE_STATUS_READY = "plant_review_task_queue_ready"
PLANT_REVIEW_TASK_QUEUE_STATUS_FAIL_CLOSED = "plant_review_task_queue_fail_closed"

DOCUMENTATION_BOUNDARY = (
    "Documentation-only plant review task queue. It records manual review tasks "
    "without source lookup, identifier filling, record promotion, biological "
    "component choice, route improvement, or downstream-use judgment."
)

FAIL_CLOSED_BOUNDARY = (
    "The task queue input is empty or malformed, so the queue remains closed for "
    "manual review and promotion is blocked."
)

TASK_ROW_FIELDS = (
    "task_id",
    "task_source",
    "dataset_key",
    "record_id",
    "record_type",
    "task_type",
    "task_label",
    "current_review_status",
    "current_provenance_status",
    "missing_fields",
    "verification_question",
    "blocking_reason",
    "required_manual_action",
    "promotion_blocked",
    "do_not_promote_until_verified",
    "documentation_boundary",
)

MANUAL_REVIEW_STATUSES = {
    "needs_manual_review",
    "manual_review_required",
    "review_required",
    "requires_manual_review",
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


def _task_row(
    row: Mapping[str, Any],
    *,
    task_source: str,
    dataset_key: str,
    default_boundary: str,
) -> dict[str, Any]:
    record_id = _text(row.get("record_id"), "unknown_plant_review_record")
    task_type = _text(row.get("task_type"), "manual_review_guard")
    task_id = _text(row.get("task_id"), f"{task_source}-{record_id}-{task_type}")
    missing_fields = _unique_texts(_sequence(row.get("missing_fields")))
    promotion_blocked = row.get("promotion_blocked") is not False
    do_not_promote = row.get("do_not_promote_until_verified") is not False

    return {
        "task_id": task_id,
        "task_source": _text(row.get("task_source"), task_source),
        "dataset_key": _text(row.get("dataset_key"), dataset_key),
        "record_id": record_id,
        "record_type": _text(row.get("record_type"), "PlantReviewRecord"),
        "task_type": task_type,
        "task_label": _text(row.get("task_label"), "Manual review task"),
        "current_review_status": _text(row.get("current_review_status"), REVIEW_REQUIRED_STATUS),
        "current_provenance_status": _text(row.get("current_provenance_status"), "missing"),
        "missing_fields": missing_fields,
        "verification_question": _text(
            row.get("verification_question"),
            "What must a human review before this record can change status?",
        ),
        "blocking_reason": _text(
            row.get("blocking_reason"),
            "Manual review remains required for this record.",
        ),
        "required_manual_action": _text(
            row.get("required_manual_action"),
            "Complete manual review in a separately scoped update before any status change.",
        ),
        "promotion_blocked": promotion_blocked,
        "do_not_promote_until_verified": do_not_promote,
        "documentation_boundary": _text(row.get("documentation_boundary"), default_boundary),
    }


def _fail_closed_task(
    *,
    queue_key: str,
    task_source: str,
    dataset_key: str,
    reason: str,
    default_boundary: str,
) -> dict[str, Any]:
    return {
        "task_id": f"{queue_key}-fail-closed-manual-review-guard",
        "task_source": task_source,
        "dataset_key": dataset_key,
        "record_id": "unknown_plant_review_records",
        "record_type": "PlantReviewTaskQueueInput",
        "task_type": "manual_review_guard",
        "task_label": "Keep queue closed for manual review",
        "current_review_status": REVIEW_REQUIRED_STATUS,
        "current_provenance_status": "malformed",
        "missing_fields": ["task_rows", reason],
        "verification_question": "Can the task input be read before individual records are reviewed?",
        "blocking_reason": FAIL_CLOSED_BOUNDARY,
        "required_manual_action": "Restore readable task rows before reviewing individual records.",
        "promotion_blocked": True,
        "do_not_promote_until_verified": True,
        "documentation_boundary": default_boundary,
    }


def _record_groups(tasks: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        record_id = _text(task.get("record_id"))
        if record_id:
            groups.setdefault(record_id, []).append(dict(task))
    return groups


def _record_needs_manual_review(tasks: Sequence[Mapping[str, Any]]) -> bool:
    for task in tasks:
        status = _text(task.get("current_review_status")).casefold()
        if status in MANUAL_REVIEW_STATUSES:
            return True
        if _text(task.get("required_manual_action")):
            return True
    return False


def _record_is_blocked(tasks: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        task.get("promotion_blocked") is True or task.get("do_not_promote_until_verified") is True
        for task in tasks
    )


def _summary(tasks: Sequence[Mapping[str, Any]], *, fail_closed: bool) -> dict[str, Any]:
    groups = _record_groups(tasks)
    blocked_records = sorted(
        [record_id for record_id, rows in groups.items() if _record_is_blocked(rows)],
        key=str.casefold,
    )
    manual_records = sorted(
        [record_id for record_id, rows in groups.items() if _record_needs_manual_review(rows)],
        key=str.casefold,
    )
    ready_records = sorted(
        [
            record_id
            for record_id, rows in groups.items()
            if not fail_closed and not _record_is_blocked(rows) and not _record_needs_manual_review(rows)
        ],
        key=str.casefold,
    )
    task_type_counts = Counter(_text(task.get("task_type"), "unknown") for task in tasks)
    missing_field_counts = Counter(
        field for task in tasks for field in _unique_texts(_sequence(task.get("missing_fields")))
    )

    return {
        "total_tasks": len(tasks),
        "represented_records": len(groups),
        "records_requiring_manual_review": len(manual_records),
        "records_blocked_from_promotion": len(blocked_records),
        "ready_to_promote_count": len(ready_records),
        "task_type_counts": {
            key: task_type_counts[key] for key in sorted(task_type_counts, key=str.casefold)
        },
        "missing_field_counts": {
            key: missing_field_counts[key] for key in sorted(missing_field_counts, key=str.casefold)
        },
        "fail_closed": fail_closed,
        "record_ids_requiring_manual_review": manual_records,
        "record_ids_blocked_from_promotion": blocked_records,
        "record_ids_ready_to_promote": ready_records,
    }


def build_plant_review_task_queue(
    task_rows: Sequence[Mapping[str, Any]] | None,
    *,
    queue_key: str,
    queue_label: str,
    task_source: str,
    dataset_key: str,
    queue_metadata: Mapping[str, Any] | None = None,
    documentation_boundary: str = DOCUMENTATION_BOUNDARY,
    warnings: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Return a read-only plant review task queue using plain dict/list payloads."""
    source_rows = _sequence(task_rows)
    metadata = _mapping(queue_metadata)
    queue_warnings = [_text(warning) for warning in _sequence(warnings) if _text(warning)]
    fail_closed = not source_rows or any(not isinstance(row, Mapping) for row in source_rows)

    if fail_closed:
        tasks = [
            _fail_closed_task(
                queue_key=_text(queue_key, "plant_review_task_queue"),
                task_source=_text(task_source, "unknown_task_source"),
                dataset_key=_text(dataset_key, "unknown_dataset"),
                reason="empty_or_malformed_task_rows",
                default_boundary=documentation_boundary,
            )
        ]
        queue_warnings.append("Plant review task rows are empty or malformed; queue fails closed.")
    else:
        tasks = [
            _task_row(
                _mapping(row),
                task_source=_text(task_source, "plant_review_task_source"),
                dataset_key=_text(dataset_key, "plant_review_dataset"),
                default_boundary=documentation_boundary,
            )
            for row in source_rows
        ]

    tasks = sorted(
        tasks,
        key=lambda item: (
            _text(item.get("dataset_key")),
            _text(item.get("record_id")),
            _text(item.get("task_type")),
            _text(item.get("task_id")),
        ),
    )

    return _plain_value(
        {
            "workflow_schema_version": PLANT_REVIEW_TASK_QUEUE_SCHEMA_VERSION,
            "workflow_batch": PLANT_REVIEW_TASK_QUEUE_BATCH,
            "workflow_status": (
                PLANT_REVIEW_TASK_QUEUE_STATUS_FAIL_CLOSED
                if fail_closed
                else PLANT_REVIEW_TASK_QUEUE_STATUS_READY
            ),
            "queue_metadata": {
                "queue_key": _text(queue_key, "plant_review_task_queue"),
                "queue_label": _text(queue_label, "Plant review task queue"),
                "task_source": _text(task_source, "plant_review_task_source"),
                "dataset_key": _text(dataset_key, "plant_review_dataset"),
                "read_only": True,
                "plain_dict_list_contract": True,
                "manual_review_required": True,
                "promotion_allowed": False,
                "documentation_boundary": documentation_boundary,
                **metadata,
            },
            "summary": _summary(tasks, fail_closed=fail_closed),
            "task_row_fields": list(TASK_ROW_FIELDS),
            "tasks": tasks,
            "warnings": queue_warnings,
        }
    )


def build_rice_albumin_manual_provenance_task_queue(
    queue_payload: Mapping[str, Any] | None = None,
    *,
    seed_dir: str | Path = DEFAULT_RICE_ALBUMIN_SEED_DIR,
    manual_verification_dir: str | Path | None = None,
    source_review_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Represent the existing R146 rice albumin queue with the R151 generic contract."""
    source = _mapping(queue_payload) or build_rice_albumin_manual_provenance_verification_queue(
        seed_dir=seed_dir,
        manual_verification_dir=manual_verification_dir,
        source_review_dir=source_review_dir,
    )
    return build_plant_review_task_queue(
        _sequence(source.get("tasks")),
        queue_key="rice_albumin_manual_provenance_verification",
        queue_label="Rice albumin manual provenance task queue",
        task_source="r146_rice_albumin_manual_provenance_queue",
        dataset_key="rice_albumin",
        queue_metadata={
            "source_workflow_schema_version": _text(source.get("workflow_schema_version")),
            "source_workflow_status": _text(source.get("workflow_status")),
            "source_workflow_batch": _text(source.get("workflow_batch")),
            "source_summary": _mapping(source.get("summary")),
        },
        documentation_boundary=RICE_ALBUMIN_QUEUE_BOUNDARY,
        warnings=_sequence(source.get("warnings")),
    )
