from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services import plant_review_task_queue


PLANT_REVIEW_TASK_QUEUE_REGISTRY_SCHEMA_VERSION = "plant_review_task_queue_registry.v2.7.r152"
PLANT_REVIEW_TASK_QUEUE_REGISTRY_BATCH = "v2.7-r152"

QUEUE_STATUS_AVAILABLE_READONLY = "available_readonly"
QUEUE_STATUS_BLOCKED_BEFORE_ACTIVATION = "blocked_before_activation"
QUEUE_STATUS_NEEDS_MANUAL_REVIEW = "needs_manual_review"
QUEUE_STATUS_UNKNOWN_FAIL_CLOSED = "unknown_fail_closed"

SUPPORTED_QUEUE_STATUSES = (
    QUEUE_STATUS_AVAILABLE_READONLY,
    QUEUE_STATUS_BLOCKED_BEFORE_ACTIVATION,
    QUEUE_STATUS_NEEDS_MANUAL_REVIEW,
    QUEUE_STATUS_UNKNOWN_FAIL_CLOSED,
)

RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY = "rice_albumin_manual_provenance_verification"

DOCUMENTATION_BOUNDARY = (
    "Read-only plant review task queue registry. It lists queue sources for "
    "documentation review without activating datasets, filling identifiers, "
    "changing records, or allowing promotion."
)

RICE_ALBUMIN_QUEUE_SOURCE: dict[str, Any] = {
    "queue_key": RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY,
    "queue_label": "Rice albumin manual provenance task queue",
    "dataset_key": "rice_albumin",
    "queue_scope": "manual_provenance_review",
    "queue_status": QUEUE_STATUS_AVAILABLE_READONLY,
    "active": True,
    "source_service": "services.plant_review_task_queue.build_rice_albumin_manual_provenance_task_queue",
    "manual_review_required": True,
    "promotion_allowed": False,
    "blocked_reasons": [
        "manual provenance review remains required",
        "record promotion remains blocked until separately scoped human review",
    ],
    "documentation_boundary": DOCUMENTATION_BOUNDARY,
}

PLANT_REVIEW_TASK_QUEUE_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY: RICE_ALBUMIN_QUEUE_SOURCE,
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


def _unknown_source(queue_key: str) -> dict[str, Any]:
    clean_key = _text(queue_key, "unknown_queue")
    return {
        "queue_key": clean_key,
        "queue_label": clean_key,
        "dataset_key": "unknown_dataset",
        "queue_scope": "unknown",
        "queue_status": QUEUE_STATUS_UNKNOWN_FAIL_CLOSED,
        "active": False,
        "source_service": "",
        "summary": {
            "total_tasks": 0,
            "represented_records": 0,
            "records_requiring_manual_review": 0,
            "records_blocked_from_promotion": 0,
            "ready_to_promote_count": 0,
            "task_type_counts": {},
            "missing_field_counts": {},
            "fail_closed": True,
        },
        "manual_review_required": True,
        "promotion_allowed": False,
        "blocked_reasons": [
            "task queue source is not registered",
            "queue lookup fails closed until a read-only source is explicitly registered",
        ],
        "documentation_boundary": DOCUMENTATION_BOUNDARY,
    }


def _build_rice_albumin_payload(source_kwargs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    kwargs = _mapping(source_kwargs)
    return plant_review_task_queue.build_rice_albumin_manual_provenance_task_queue(**kwargs)


def _queue_payload_for_source(
    source: Mapping[str, Any],
    *,
    source_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    queue_key = _text(source.get("queue_key"))
    if queue_key == RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY:
        return _build_rice_albumin_payload(source_kwargs)
    return plant_review_task_queue.build_plant_review_task_queue(
        [],
        queue_key=queue_key or "unknown_queue",
        queue_label=_text(source.get("queue_label"), "Unknown queue"),
        task_source=_text(source.get("source_service"), "unknown_source"),
        dataset_key=_text(source.get("dataset_key"), "unknown_dataset"),
        documentation_boundary=DOCUMENTATION_BOUNDARY,
    )


def _source_with_summary(
    source: Mapping[str, Any],
    *,
    source_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _queue_payload_for_source(source, source_kwargs=source_kwargs)
    entry = {
        "registry_schema_version": PLANT_REVIEW_TASK_QUEUE_REGISTRY_SCHEMA_VERSION,
        "registry_batch": PLANT_REVIEW_TASK_QUEUE_REGISTRY_BATCH,
        "supported_queue_statuses": list(SUPPORTED_QUEUE_STATUSES),
        **_mapping(source),
        "summary": _mapping(payload.get("summary")),
        "payload_workflow_status": _text(payload.get("workflow_status")),
        "read_only": True,
        "plant_scope_only": True,
    }
    entry["promotion_allowed"] = False
    entry["manual_review_required"] = True
    return _plain_value(entry)


def get_plant_review_task_queue_source(
    queue_key: str,
    *,
    source_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a read-only registered queue source, or a fail-closed unknown source."""
    key = _text(queue_key).casefold()
    source = PLANT_REVIEW_TASK_QUEUE_SOURCE_REGISTRY.get(key)
    if source is None:
        return _plain_value(
            {
                "registry_schema_version": PLANT_REVIEW_TASK_QUEUE_REGISTRY_SCHEMA_VERSION,
                "registry_batch": PLANT_REVIEW_TASK_QUEUE_REGISTRY_BATCH,
                "supported_queue_statuses": list(SUPPORTED_QUEUE_STATUSES),
                **_unknown_source(queue_key),
                "read_only": True,
                "plant_scope_only": True,
            }
        )
    return _source_with_summary(source, source_kwargs=source_kwargs)


def list_plant_review_task_queue_sources(
    *,
    source_kwargs_by_key: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return registered queue sources as plain dict/list payloads."""
    kwargs_by_key = _mapping(source_kwargs_by_key)
    return [
        get_plant_review_task_queue_source(
            key,
            source_kwargs=_mapping(kwargs_by_key.get(key)),
        )
        for key in sorted(PLANT_REVIEW_TASK_QUEUE_SOURCE_REGISTRY, key=str.casefold)
    ]


def get_plant_review_task_queue_payload(
    queue_key: str,
    *,
    source_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a registered queue payload, or a fail-closed unknown queue payload."""
    key = _text(queue_key).casefold()
    source = PLANT_REVIEW_TASK_QUEUE_SOURCE_REGISTRY.get(key)
    if source is None:
        unknown = _unknown_source(queue_key)
        return plant_review_task_queue.build_plant_review_task_queue(
            [],
            queue_key=_text(unknown.get("queue_key"), "unknown_queue"),
            queue_label=_text(unknown.get("queue_label"), "Unknown queue"),
            task_source="unknown_queue_registry_source",
            dataset_key=_text(unknown.get("dataset_key"), "unknown_dataset"),
            documentation_boundary=DOCUMENTATION_BOUNDARY,
            warnings=_sequence(unknown.get("blocked_reasons")),
        )
    return _queue_payload_for_source(source, source_kwargs=source_kwargs)
