"""Read-only presenter for R193 manual evidence preflight queue readback.

R196 turns plain preflight dict/list payloads into display-safe queue rows for a
future Plant Review UI/report mount. It does not import evidence, verify
sources, approve records, write files, or grant package export behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


QUEUE_SCHEMA_VERSION = "manual_evidence_review_queue_readback.v2.7.r196"
QUEUE_BATCH = "v2.7-r196"

QUEUE_STATES = (
    "review_needed",
    "blocked",
    "preview_only",
    "malformed_blocked",
    "empty",
)


def present_manual_evidence_review_queue(input_payload: Any) -> dict[str, Any]:
    """Return a plain-dict queue readback for one preflight record or a batch."""

    if isinstance(input_payload, Mapping) and "records" in input_payload:
        return present_manual_evidence_review_queue_batch(input_payload)
    if isinstance(input_payload, Sequence) and not isinstance(
        input_payload, (bytes, bytearray, str)
    ):
        return present_manual_evidence_review_queue_batch(list(input_payload))
    return present_manual_evidence_review_queue_record(input_payload)


def present_manual_evidence_review_queue_batch(input_payload: Any) -> dict[str, Any]:
    """Return queue readback rows for an R193-style batch dict or record list."""

    if isinstance(input_payload, Mapping):
        records = _sequence(input_payload.get("records"))
        preflight_summary = _mapping(input_payload.get("summary"))
        preflight_status = _text(input_payload.get("preflight_status"), "blocked")
        batch_blocking_reasons = _list_texts(input_payload.get("blocking_reasons"))
        batch_warnings = _list_texts(input_payload.get("warnings"))
    elif isinstance(input_payload, Sequence) and not isinstance(
        input_payload, (bytes, bytearray, str)
    ):
        records = list(input_payload)
        preflight_summary = {}
        preflight_status = "manual_review_required" if records else "blocked"
        batch_blocking_reasons = []
        batch_warnings = []
    else:
        records = []
        preflight_summary = {"malformed_records": 1, "total_records": 0}
        preflight_status = "blocked"
        batch_blocking_reasons = ["records must be a list or R193 batch dict"]
        batch_warnings = []

    rows = [
        present_manual_evidence_review_queue_record(record, row_index=index)
        for index, record in enumerate(records, start=1)
    ]
    queue_state_counts = {
        state: sum(1 for row in rows if row["queue_state"] == state)
        for state in QUEUE_STATES
    }
    summary = {
        "row_count": len(rows),
        "queue_state_counts": queue_state_counts,
        "preflight_total_records": preflight_summary.get("total_records", len(rows)),
        "preflight_ready_records": preflight_summary.get("ready_records", 0),
        "preflight_manual_review_records": preflight_summary.get(
            "manual_review_records", 0
        ),
        "preflight_blocked_records": preflight_summary.get("blocked_records", 0),
        "preflight_package_draft_supported_records": preflight_summary.get(
            "package_draft_supported_records", 0
        ),
        "preflight_beginner_preview_allowed_records": preflight_summary.get(
            "beginner_preview_allowed_records", 0
        ),
        "preflight_malformed_records": preflight_summary.get(
            "malformed_records", queue_state_counts["malformed_blocked"]
        ),
    }

    return _plain_value(
        {
            "payload_kind": "manual_evidence_review_queue_readback_batch",
            "queue_schema_version": QUEUE_SCHEMA_VERSION,
            "queue_batch": QUEUE_BATCH,
            "read_only": True,
            "display_readback_only": True,
            "preflight_status": preflight_status,
            "rows": rows,
            "summary": summary,
            "preflight_summary": preflight_summary,
            "batch_blocking_reasons": batch_blocking_reasons,
            "batch_warnings": batch_warnings,
            "automatic_import_allowed": False,
            "automatic_approval_allowed": False,
            "automatic_package_export_allowed": False,
        }
    )


def present_manual_evidence_review_queue_record(
    preflight_result: Any, *, row_index: int | None = None
) -> dict[str, Any]:
    """Return one display-safe queue row from an R193-style preflight dict."""

    if not isinstance(preflight_result, Mapping):
        return _fail_closed_row(
            queue_state="malformed_blocked",
            row_index=row_index,
            blocking_reasons=["preflight result must be a dict"],
            primary_reason="preflight result must be a dict",
        )
    if not preflight_result:
        return _fail_closed_row(
            queue_state="empty",
            row_index=row_index,
            blocking_reasons=["no readable preflight record"],
            primary_reason="no readable preflight record",
        )

    package_preview = _mapping(preflight_result.get("package_draft_support_preview"))
    source_status = _mapping(preflight_result.get("source_status"))
    placeholder_status = _mapping(preflight_result.get("placeholder_status"))
    admission_gate_alignment = _mapping(preflight_result.get("admission_gate_alignment"))
    traceability = _mapping(preflight_result.get("traceability"))
    blocking_reasons = _list_texts(preflight_result.get("blocking_reasons"))
    warnings = _list_texts(preflight_result.get("warnings"))
    missing_fields = _list_texts(preflight_result.get("missing_required_fields"))

    queue_state = _queue_state(
        preflight_result=preflight_result,
        package_preview=package_preview,
        placeholder_status=placeholder_status,
        admission_gate_alignment=admission_gate_alignment,
        blocking_reasons=blocking_reasons,
        missing_fields=missing_fields,
        traceability=traceability,
    )
    visible_blockers = _visible_blocking_reasons(
        queue_state=queue_state,
        blocking_reasons=blocking_reasons,
        package_preview=package_preview,
        missing_fields=missing_fields,
    )
    primary_reason = _primary_reason(
        queue_state=queue_state,
        visible_blockers=visible_blockers,
        warnings=warnings,
        manual_review_state=_text(preflight_result.get("manual_review_state")),
        admission_gate_alignment=admission_gate_alignment,
    )

    return _plain_value(
        {
            "payload_kind": "manual_evidence_review_queue_readback_row",
            "queue_schema_version": QUEUE_SCHEMA_VERSION,
            "queue_batch": QUEUE_BATCH,
            "queue_item_id": _queue_item_id(traceability, row_index),
            "evidence_label": _evidence_label(traceability, row_index),
            "queue_state": queue_state,
            "review_priority": _review_priority(queue_state, visible_blockers),
            "primary_reason": primary_reason,
            "preflight_status": _text(preflight_result.get("preflight_status"), "blocked"),
            "manual_review_state": _text(
                preflight_result.get("manual_review_state"),
                "cannot_review_until_required_fields_are_present",
            ),
            "source_status": source_status,
            "placeholder_status": placeholder_status,
            "placeholder_demo_example_status": {
                "status": _text(
                    placeholder_status.get("status"), "no_placeholder_detected"
                ),
                "has_placeholder_values": bool(
                    placeholder_status.get("has_placeholder_values", False)
                ),
                "placeholder_fields": _list_texts(
                    placeholder_status.get("placeholder_fields")
                ),
            },
            "package_draft_support_preview": package_preview,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "admission_gate_alignment": admission_gate_alignment,
            "traceability": traceability,
            "visible_blocking_reasons": visible_blockers,
            "visible_warnings": warnings,
            "package_support_readback": _package_support_readback(package_preview),
            "source_readback": _source_readback(source_status),
            "traceability_readback": _traceability_readback(traceability),
            "display_readback_only": True,
            "imports_evidence": False,
            "approval_allowed": False,
            "package_export_permission": False,
            "package_draft_completion_permission": False,
            "biological_recommendation": False,
            "experiment_validation_claim": False,
            "optimization_claim": False,
            "wet_lab_readiness_judgment": False,
            "r189_admission_gate_is_preserved": bool(
                admission_gate_alignment.get("r189_gate_used", False)
            ),
            "r193_preflight_can_override_r189": bool(
                admission_gate_alignment.get("r189_gate_can_be_overridden", False)
            ),
        }
    )


def _queue_state(
    *,
    preflight_result: Mapping[str, Any],
    package_preview: Mapping[str, Any],
    placeholder_status: Mapping[str, Any],
    admission_gate_alignment: Mapping[str, Any],
    blocking_reasons: list[str],
    missing_fields: list[str],
    traceability: Mapping[str, Any],
) -> str:
    input_shape = _text(traceability.get("input_shape"))
    if input_shape == "malformed" or missing_fields == ["record"]:
        return "malformed_blocked"
    if _looks_like_empty_preflight(traceability, missing_fields):
        return "empty"
    if (
        admission_gate_alignment.get("beginner_preview_allowed") is True
        and package_preview.get("supported") is not True
    ):
        return "preview_only"
    if _text(preflight_result.get("preflight_status")) == "blocked":
        return "blocked"
    if blocking_reasons:
        return "blocked"
    if _text(admission_gate_alignment.get("package_draft_support_status")) == "demo_only":
        return "blocked"
    return "review_needed"


def _looks_like_empty_preflight(
    traceability: Mapping[str, Any], missing_fields: list[str]
) -> bool:
    if not missing_fields:
        return False
    identity_values = [
        traceability.get("record_id"),
        traceability.get("display_name"),
        traceability.get("route_scope"),
    ]
    return not any(_text(value) for value in identity_values)


def _visible_blocking_reasons(
    *,
    queue_state: str,
    blocking_reasons: list[str],
    package_preview: Mapping[str, Any],
    missing_fields: list[str],
) -> list[str]:
    reasons = list(blocking_reasons)
    reasons.extend(_list_texts(package_preview.get("blocking_reasons")))
    reasons.extend(f"missing required field: {field}" for field in missing_fields)
    if queue_state == "preview_only":
        reasons.append("beginner preview only; package draft support remains blocked")
    if queue_state == "empty":
        reasons.append("no readable preflight record")
    if queue_state == "malformed_blocked" and not reasons:
        reasons.append("preflight result must be a dict")
    return _unique(reasons)


def _primary_reason(
    *,
    queue_state: str,
    visible_blockers: list[str],
    warnings: list[str],
    manual_review_state: str,
    admission_gate_alignment: Mapping[str, Any],
) -> str:
    if visible_blockers:
        return visible_blockers[0]
    if queue_state == "preview_only":
        return _text(
            admission_gate_alignment.get("beginner_preview_status"),
            "beginner preview only",
        )
    if warnings:
        return warnings[0]
    return manual_review_state or "manual review readback"


def _review_priority(queue_state: str, visible_blockers: list[str]) -> str:
    blocker_text = " ".join(visible_blockers).casefold()
    if queue_state in {"malformed_blocked", "empty"}:
        return "input_required"
    if queue_state == "preview_only":
        return "preview_context"
    if "conflict" in blocker_text or "deprecated" in blocker_text:
        return "blocked_high_attention"
    if queue_state == "blocked":
        return "blocked_attention"
    return "manual_review_standard"


def _package_support_readback(package_preview: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": _text(package_preview.get("status"), "blocked"),
        "supported": bool(package_preview.get("supported", False)),
        "blocking_reasons": _list_texts(package_preview.get("blocking_reasons")),
        "readback_only": True,
        "package_export_permission": False,
        "package_draft_completion_permission": False,
    }


def _source_readback(source_status: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": _text(source_status.get("status"), "missing_source"),
        "source_fields_present": _list_texts(source_status.get("source_fields_present")),
        "source_type": _text(source_status.get("source_type")),
        "input_provenance_status": _text(
            source_status.get("input_provenance_status"), "missing_source"
        ),
        "readback_only": True,
    }


def _traceability_readback(traceability: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "record_id": _text(traceability.get("record_id")),
        "record_type": _text(traceability.get("record_type")),
        "display_name": _text(traceability.get("display_name")),
        "route_scope": _text(traceability.get("route_scope")),
        "source_fields_present": _list_texts(traceability.get("source_fields_present")),
        "input_shape": _text(traceability.get("input_shape"), "unknown"),
        "readback_only": True,
    }


def _fail_closed_row(
    *,
    queue_state: str,
    row_index: int | None,
    blocking_reasons: list[str],
    primary_reason: str,
) -> dict[str, Any]:
    return _plain_value(
        {
            "payload_kind": "manual_evidence_review_queue_readback_row",
            "queue_schema_version": QUEUE_SCHEMA_VERSION,
            "queue_batch": QUEUE_BATCH,
            "queue_item_id": _fallback_queue_item_id(row_index),
            "evidence_label": "Manual evidence preflight input",
            "queue_state": queue_state,
            "review_priority": _review_priority(queue_state, blocking_reasons),
            "primary_reason": primary_reason,
            "preflight_status": "blocked",
            "manual_review_state": "cannot_review_until_required_fields_are_present",
            "source_status": {},
            "placeholder_status": {},
            "placeholder_demo_example_status": {
                "status": "no_placeholder_detected",
                "has_placeholder_values": False,
                "placeholder_fields": [],
            },
            "package_draft_support_preview": {
                "status": "blocked",
                "supported": False,
                "blocking_reasons": list(blocking_reasons),
            },
            "blocking_reasons": list(blocking_reasons),
            "warnings": [],
            "admission_gate_alignment": {
                "r189_gate_used": False,
                "r189_gate_can_be_overridden": False,
                "package_draft_support_allowed": False,
                "beginner_preview_allowed": False,
            },
            "traceability": {
                "record_id": "",
                "record_type": "",
                "display_name": "",
                "route_scope": "",
                "source_fields_present": [],
                "input_shape": "malformed"
                if queue_state == "malformed_blocked"
                else "empty",
            },
            "visible_blocking_reasons": list(blocking_reasons),
            "visible_warnings": [],
            "package_support_readback": {
                "status": "blocked",
                "supported": False,
                "blocking_reasons": list(blocking_reasons),
                "readback_only": True,
                "package_export_permission": False,
                "package_draft_completion_permission": False,
            },
            "source_readback": {
                "status": "missing_source",
                "source_fields_present": [],
                "source_type": "",
                "input_provenance_status": "missing_source",
                "readback_only": True,
            },
            "traceability_readback": {
                "record_id": "",
                "record_type": "",
                "display_name": "",
                "route_scope": "",
                "source_fields_present": [],
                "input_shape": "malformed"
                if queue_state == "malformed_blocked"
                else "empty",
                "readback_only": True,
            },
            "display_readback_only": True,
            "imports_evidence": False,
            "approval_allowed": False,
            "package_export_permission": False,
            "package_draft_completion_permission": False,
            "biological_recommendation": False,
            "experiment_validation_claim": False,
            "optimization_claim": False,
            "wet_lab_readiness_judgment": False,
            "r189_admission_gate_is_preserved": False,
            "r193_preflight_can_override_r189": False,
        }
    )


def _queue_item_id(traceability: Mapping[str, Any], row_index: int | None) -> str:
    record_id = _key(traceability.get("record_id"))
    if record_id:
        return f"r196-manual-evidence-queue-{record_id}"
    return _fallback_queue_item_id(row_index)


def _fallback_queue_item_id(row_index: int | None) -> str:
    if row_index is not None:
        return f"r196-manual-evidence-queue-row-{row_index:03d}"
    return "r196-manual-evidence-queue-row-001"


def _evidence_label(traceability: Mapping[str, Any], row_index: int | None) -> str:
    return _text(
        traceability.get("display_name") or traceability.get("record_id"),
        f"Manual evidence preflight row {row_index or 1}",
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, Mapping):
        raw_values = sorted(value.keys(), key=lambda item: str(item))
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_values = list(value)
    elif _text(value):
        raw_values = [value]
    else:
        raw_values = []
    return _unique(_text(item) for item in raw_values if _text(item))


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _plain_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _unique(values: Any) -> list[Any]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _key(value: Any) -> str:
    text = _text(value).casefold().replace(" ", "-").replace("_", "-")
    keep = []
    previous_dash = False
    for char in text:
        if char.isalnum():
            keep.append(char)
            previous_dash = False
        elif not previous_dash:
            keep.append("-")
            previous_dash = True
    return "".join(keep).strip("-")


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback
