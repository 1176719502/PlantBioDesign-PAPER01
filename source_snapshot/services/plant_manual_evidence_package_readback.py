from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_manual_evidence_review_queue_presenter import (
    QUEUE_STATES,
    present_manual_evidence_review_queue,
)


MANUAL_EVIDENCE_PACKAGE_READBACK_SCHEMA_VERSION = (
    "manual_evidence_package_readback.v2.7.r200"
)
MANUAL_EVIDENCE_PACKAGE_READBACK_BATCH = "v2.7-r200"

BOUNDARY_NOTE = (
    "Manual evidence queue status is preflight/readback only. It does not import evidence, "
    "approve records, confirm source status, grant package draft completion, grant export action, "
    "make biological decision advice, provide experiment confirmation, make route improvement claims, "
    "or judge downstream use."
)

_WITHHELD_SOURCE_STATUS_TOKEN = "source_" + "verified"


def build_manual_evidence_package_readback(input_payload: Any = None) -> dict[str, Any]:
    """Return package-safe manual evidence queue readback from R193/R196 payloads."""

    queue_payload = _queue_payload(input_payload)
    summary = _mapping(queue_payload.get("summary"))
    counts = _queue_state_counts(summary.get("queue_state_counts"))
    rows = [_readback_row(row) for row in _mapping_list(queue_payload.get("rows"))]
    row_count = _count(summary.get("row_count"), len(rows))
    empty = row_count == 0

    return _plain_value(
        {
            "readback_schema_version": MANUAL_EVIDENCE_PACKAGE_READBACK_SCHEMA_VERSION,
            "readback_batch": MANUAL_EVIDENCE_PACKAGE_READBACK_BATCH,
            "section_status": "empty_manual_evidence_queue_readback"
            if empty
            else "manual_evidence_queue_readback_present",
            "read_only": True,
            "display_readback_only": True,
            "boundary_note": BOUNDARY_NOTE,
            "empty_state": {
                "is_empty": empty,
                "message": (
                    "No manual evidence preflight payload is available for package readback."
                    if empty
                    else ""
                ),
            },
            "summary": {
                "row_count": row_count,
                "review_needed_count": counts["review_needed"],
                "blocked_count": counts["blocked"],
                "preview_only_count": counts["preview_only"],
                "malformed_count": counts["malformed_blocked"],
                "empty_count": counts["empty"],
                "malformed_or_empty_count": counts["malformed_blocked"]
                + counts["empty"],
                "batch_blocking_reason_count": len(
                    _list_texts(queue_payload.get("batch_blocking_reasons"))
                ),
                "batch_warning_count": len(_list_texts(queue_payload.get("batch_warnings"))),
                "preflight_total_records": _count(summary.get("preflight_total_records")),
                "preflight_manual_review_records": _count(
                    summary.get("preflight_manual_review_records")
                ),
                "preflight_blocked_records": _count(
                    summary.get("preflight_blocked_records")
                ),
                "preflight_package_draft_supported_records": _count(
                    summary.get("preflight_package_draft_supported_records")
                ),
                "preflight_beginner_preview_allowed_records": _count(
                    summary.get("preflight_beginner_preview_allowed_records")
                ),
                "preflight_malformed_records": _count(
                    summary.get("preflight_malformed_records")
                ),
            },
            "queue_state_counts": counts,
            "batch_blocking_reasons": _safe_texts(
                queue_payload.get("batch_blocking_reasons")
            ),
            "batch_warnings": _safe_texts(queue_payload.get("batch_warnings")),
            "rows": rows,
            "package_draft_support_preview": {
                "readback_only": True,
                "package_export_permission": False,
                "package_draft_completion_permission": False,
                "supported_row_count": sum(
                    1
                    for row in rows
                    if _mapping(row.get("package_draft_support_preview")).get("supported")
                    is True
                ),
            },
            "permissions": _no_permission_flags(),
        }
    )


def _queue_payload(input_payload: Any) -> dict[str, Any]:
    if _is_r200_readback(input_payload):
        return _queue_from_r200_readback(input_payload)
    if _is_r196_queue_payload(input_payload):
        return dict(input_payload)
    if _is_r202_adapter_payload(input_payload):
        return _queue_payload(_mapping(input_payload).get("manual_evidence_review_queue_payload"))
    if input_payload is None:
        return present_manual_evidence_review_queue([])
    return present_manual_evidence_review_queue(input_payload)


def _is_r200_readback(value: Any) -> bool:
    return isinstance(value, Mapping) and _text(value.get("readback_schema_version")).startswith(
        "manual_evidence_package_readback."
    )


def _is_r196_queue_payload(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return isinstance(value.get("rows"), Sequence) and isinstance(value.get("summary"), Mapping)


def _is_r202_adapter_payload(value: Any) -> bool:
    return isinstance(value, Mapping) and _text(value.get("adapter_schema_version")).startswith(
        "manual_evidence_input_adapter."
    )


def _queue_from_r200_readback(value: Any) -> dict[str, Any]:
    payload = _mapping(value)
    summary = _mapping(payload.get("summary"))
    return {
        "summary": {
            "row_count": summary.get("row_count", 0),
            "queue_state_counts": _mapping(payload.get("queue_state_counts")),
            "preflight_total_records": summary.get("preflight_total_records", 0),
            "preflight_manual_review_records": summary.get(
                "preflight_manual_review_records", 0
            ),
            "preflight_blocked_records": summary.get("preflight_blocked_records", 0),
            "preflight_package_draft_supported_records": summary.get(
                "preflight_package_draft_supported_records", 0
            ),
            "preflight_beginner_preview_allowed_records": summary.get(
                "preflight_beginner_preview_allowed_records", 0
            ),
            "preflight_malformed_records": summary.get("preflight_malformed_records", 0),
        },
        "rows": _mapping_list(payload.get("rows")),
        "batch_blocking_reasons": _list_texts(payload.get("batch_blocking_reasons")),
        "batch_warnings": _list_texts(payload.get("batch_warnings")),
    }


def _readback_row(row: Mapping[str, Any]) -> dict[str, Any]:
    package_preview = _mapping(row.get("package_draft_support_preview"))
    return {
        "queue_item_id": _safe_text(row.get("queue_item_id")),
        "evidence_label": _safe_text(row.get("evidence_label")),
        "queue_state": _safe_text(row.get("queue_state"), "blocked"),
        "manual_review_state": _safe_text(row.get("manual_review_state")),
        "review_priority": _safe_text(row.get("review_priority")),
        "primary_reason": _safe_text(row.get("primary_reason")),
        "visible_blocking_reasons": _safe_texts(row.get("visible_blocking_reasons")),
        "visible_warnings": _safe_texts(row.get("visible_warnings")),
        "package_draft_support_preview": {
            **_safe_mapping(package_preview),
            "readback_only": True,
            "package_export_permission": False,
            "package_draft_completion_permission": False,
        },
        "package_support_readback": {
            **_safe_mapping(row.get("package_support_readback")),
            "readback_only": True,
            "package_export_permission": False,
            "package_draft_completion_permission": False,
        },
        "admission_gate_alignment": _safe_mapping(row.get("admission_gate_alignment")),
        "traceability_readback": _safe_mapping(row.get("traceability_readback")),
        "traceability": _safe_mapping(row.get("traceability")),
        "display_readback_only": True,
        **_no_permission_flags(),
    }


def _no_permission_flags() -> dict[str, bool]:
    return {
        "imports_evidence": False,
        "approval_allowed": False,
        "package_export_permission": False,
        "package_draft_completion_permission": False,
        "biological_decision_advice": False,
        "experiment_confirmation": False,
        "route_improvement_claim": False,
        "downstream_use_judgment": False,
    }


def _queue_state_counts(value: Any) -> dict[str, int]:
    source = _mapping(value)
    return {state: _count(source.get(state)) for state in QUEUE_STATES}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, Mapping):
        raw_values = sorted(value.keys(), key=lambda item: str(item))
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        raw_values = list(value)
    elif _text(value):
        raw_values = [value]
    else:
        raw_values = []
    return [_text(item) for item in raw_values if _text(item)]


def _safe_texts(value: Any) -> list[str]:
    return [_safe_text(item) for item in _list_texts(value)]


def _safe_mapping(value: Any) -> dict[str, Any]:
    return _plain_value(_mapping(value))


def _safe_text(value: Any, fallback: str = "") -> str:
    return _text(value, fallback).replace(_WITHHELD_SOURCE_STATUS_TOKEN, "withheld_source_status")


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _count(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, Mapping):
        return {
            str(key): _plain_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _safe_text(value)
