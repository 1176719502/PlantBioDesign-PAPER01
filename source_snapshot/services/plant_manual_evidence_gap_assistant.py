"""R204 read-only gap assistant for manual evidence review payloads.

The assistant consumes R202 adapter, R193 preflight, R196 queue, or R200
package-readback style payloads and returns plain readback sections. It explains
missing documentation fields and blocked states without changing records,
checking sources, granting package support, or giving biological advice.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_manual_evidence_input_adapter import (
    build_manual_evidence_input_adapter_payload,
)
from services.plant_manual_evidence_package_readback import (
    build_manual_evidence_package_readback,
)
from services.plant_manual_evidence_review_queue_presenter import (
    QUEUE_STATES,
    present_manual_evidence_review_queue,
)


GAP_ASSISTANT_SCHEMA_VERSION = "manual_evidence_gap_assistant.v2.7.r204"
GAP_ASSISTANT_BATCH = "v2.7-r204"

BOUNDARY_NOTE = (
    "Manual Evidence Gap Assistant is documentation-only data-completion guidance. "
    "It keeps manual review, source/provenance, traceability, and package-support "
    "blockers visible without changing records or judging downstream use."
)

MISSING_FIELD_LABELS = {
    "evidence_label": "evidence_label",
    "source_note": "source_note",
    "evidence_type": "evidence_type",
    "review_note": "review_note",
    "traceability_label": "traceability_label",
    "source_status": "source status",
    "package_support_status": "package support status",
}


def build_manual_evidence_gap_assistant(input_payload: Any = None) -> dict[str, Any]:
    """Return a deterministic plain-dict gap assistant payload."""

    context = _normalized_context(input_payload)
    queue_payload = context["queue_payload"]
    rows = [_assistant_row(row, context) for row in _mapping_list(queue_payload.get("rows"))]
    counts = {state: sum(1 for row in rows if row["queue_state"] == state) for state in QUEUE_STATES}
    top_blockers = _unique(
        reason for row in rows for reason in row["blocking_reasons_preserved"]
    )
    top_warnings = _unique(warning for row in rows for warning in row["warnings_preserved"])
    empty = len(rows) == 0

    return _plain_value(
        {
            "gap_assistant_schema_version": GAP_ASSISTANT_SCHEMA_VERSION,
            "gap_assistant_batch": GAP_ASSISTANT_BATCH,
            "payload_kind": "manual_evidence_gap_assistant_readback",
            "read_only": True,
            "display_readback_only": True,
            "documentation_only": True,
            "boundary_note": BOUNDARY_NOTE,
            "empty_state": {
                "is_empty": empty,
                "message": (
                    "No manual evidence draft is available; enter local draft fields to see data-completion gaps."
                    if empty
                    else ""
                ),
                "safe_next_actions": (
                    [
                        "Add a local evidence label if a manual evidence draft should be reviewed.",
                        "Add a source note only as documentation context.",
                        "Keep beginner preview context separate from package support.",
                    ]
                    if empty
                    else []
                ),
            },
            "summary": {
                "row_count": len(rows),
                "missing_field_count": sum(len(row["missing_fields"]) for row in rows),
                "blocker_count": len(top_blockers),
                "warning_count": len(top_warnings),
                "queue_state_counts": counts,
                "package_support_supported_row_count": sum(
                    1
                    for row in rows
                    if _mapping(row.get("package_draft_support_preview")).get("supported")
                    is True
                ),
                "readback_only_row_count": len(rows),
            },
            "top_blockers": top_blockers,
            "top_warnings": top_warnings,
            "rows": rows,
            "permissions": _no_permission_flags(),
            "source_payload_kind": context["source_payload_kind"],
        }
    )


def _normalized_context(input_payload: Any) -> dict[str, Any]:
    adapter_payload = _adapter_payload(input_payload)
    preflight_records = _preflight_records(input_payload, adapter_payload)
    queue_payload = _queue_payload(input_payload, adapter_payload)
    package_readback = build_manual_evidence_package_readback(queue_payload)
    normalized_records = _mapping_list(adapter_payload.get("normalized_manual_evidence_records"))

    return {
        "source_payload_kind": _source_payload_kind(input_payload),
        "adapter_payload": adapter_payload,
        "preflight_by_record_id": _by_record_id(preflight_records),
        "normalized_by_record_id": _normalized_by_record_id(normalized_records),
        "queue_payload": queue_payload,
        "package_readback": package_readback,
    }


def _assistant_row(row: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    traceability = _mapping(row.get("traceability") or row.get("traceability_readback"))
    record_id = _text(traceability.get("record_id"))
    normalized = _mapping(_mapping(context.get("normalized_by_record_id")).get(record_id))
    preflight = _mapping(_mapping(context.get("preflight_by_record_id")).get(record_id))
    source_status = _mapping(row.get("source_status") or row.get("source_readback"))
    package_preview = _mapping(row.get("package_draft_support_preview"))
    if not package_preview:
        package_preview = _mapping(row.get("package_support_readback"))
    queue_state = _text(row.get("queue_state"), "blocked")
    missing_fields = _missing_fields(
        row=row,
        normalized=normalized,
        preflight=preflight,
        source_status=source_status,
        package_preview=package_preview,
    )
    state_explanation = _state_explanation(queue_state, row, package_preview)
    safe_actions = _safe_next_actions(
        queue_state=queue_state,
        missing_fields=missing_fields,
        row=row,
        package_preview=package_preview,
    )

    return {
        "queue_item_id": _text(row.get("queue_item_id")),
        "evidence_label": _text(row.get("evidence_label"), "Manual evidence preflight input"),
        "queue_state": queue_state,
        "gap_summary": _gap_summary(missing_fields, queue_state, row),
        "missing_fields": missing_fields,
        "state_explanation": state_explanation,
        "package_support_explanation": _package_support_explanation(package_preview),
        "safe_next_data_completion_actions": safe_actions,
        "blocking_reasons_preserved": _list_texts(
            row.get("visible_blocking_reasons") or row.get("blocking_reasons")
        ),
        "warnings_preserved": _list_texts(row.get("visible_warnings") or row.get("warnings")),
        "manual_review_state": _text(row.get("manual_review_state")),
        "package_draft_support_preview": _plain_value(package_preview),
        "admission_gate_alignment": _plain_value(row.get("admission_gate_alignment")),
        "r189_admission_gate_alignment": _plain_value(row.get("admission_gate_alignment")),
        "source_status": _plain_value(source_status),
        "traceability_readback": _plain_value(
            row.get("traceability_readback") or traceability
        ),
        "traceability": _plain_value(traceability),
        "display_readback_only": True,
        **_no_permission_flags(),
    }


def _missing_fields(
    *,
    row: Mapping[str, Any],
    normalized: Mapping[str, Any],
    preflight: Mapping[str, Any],
    source_status: Mapping[str, Any],
    package_preview: Mapping[str, Any],
) -> list[str]:
    missing: list[str] = []
    source_identity = _mapping(normalized.get("source_identity"))
    metadata = _mapping(normalized.get("evidence_entry_metadata"))
    scope = _mapping(normalized.get("evidence_scope"))
    review = _mapping(normalized.get("provenance_and_review"))
    adapter_traceability = _mapping(normalized.get("adapter_traceability"))

    if not _text(row.get("evidence_label")) or not _text(source_identity.get("source_title")):
        missing.append(MISSING_FIELD_LABELS["evidence_label"])

    source_fields_present = _list_texts(
        source_status.get("source_fields_present")
        or _mapping(row.get("source_readback")).get("source_fields_present")
    )
    if _text(source_status.get("status")) == "missing_source" or not source_fields_present:
        missing.append(MISSING_FIELD_LABELS["source_note"])

    evidence_type_status = _mapping(preflight.get("evidence_type_status"))
    if (
        _text(evidence_type_status.get("status")) == "missing_evidence_type"
        or adapter_traceability.get("evidence_type_recorded") is False
        or not _text(scope.get("claim_type") or scope.get("evidence_type"))
    ):
        missing.append(MISSING_FIELD_LABELS["evidence_type"])

    if (
        adapter_traceability.get("review_note_recorded") is False
        or not _text(metadata.get("notes_for_curator") or review.get("reviewer_note"))
    ):
        missing.append(MISSING_FIELD_LABELS["review_note"])

    if (
        adapter_traceability.get("traceability_label_recorded") is False
        or not _text(adapter_traceability.get("traceability_label"))
    ):
        missing.append(MISSING_FIELD_LABELS["traceability_label"])

    if not _text(source_status.get("status")):
        missing.append(MISSING_FIELD_LABELS["source_status"])

    if not _text(package_preview.get("status")):
        missing.append(MISSING_FIELD_LABELS["package_support_status"])

    for field in _list_texts(preflight.get("missing_required_fields")):
        if field not in missing:
            missing.append(field)
    return _unique(missing)


def _gap_summary(missing_fields: Sequence[str], queue_state: str, row: Mapping[str, Any]) -> str:
    if queue_state == "empty":
        return "No readable manual evidence draft is available."
    if queue_state == "malformed_blocked":
        return "Manual evidence input is malformed and needs data cleanup before review."
    if missing_fields:
        return "Missing data fields: " + ", ".join(missing_fields)
    blockers = _list_texts(row.get("visible_blocking_reasons") or row.get("blocking_reasons"))
    if blockers:
        return "No extra field gap was inferred, but blockers remain visible."
    return "Core manual evidence fields are present for documentation review."


def _state_explanation(
    queue_state: str,
    row: Mapping[str, Any],
    package_preview: Mapping[str, Any],
) -> str:
    if queue_state == "review_needed":
        return (
            "The record has enough local draft context for manual review readback, "
            "but it is not treated as reviewed source material."
        )
    if queue_state == "blocked":
        return "The record remains blocked because required data or review blockers are still present."
    if queue_state == "preview_only":
        return (
            "The record is allowed only as beginner preview context; package support remains separate."
        )
    if queue_state == "malformed_blocked":
        return "The record shape cannot be read safely and remains blocked."
    if queue_state == "empty":
        return "No readable manual evidence record is available yet."
    if package_preview.get("supported") is True:
        return "The row reports package support in upstream readback; this assistant still only summarizes gaps."
    return _text(row.get("primary_reason"), "Manual evidence readback requires review.")


def _package_support_explanation(package_preview: Mapping[str, Any]) -> str:
    supported = package_preview.get("supported") is True
    status = _text(package_preview.get("status"), "blocked")
    blockers = _list_texts(package_preview.get("blocking_reasons"))
    if supported:
        return "Upstream readback reports package support; this assistant does not grant package permissions."
    if blockers:
        return "Package support remains blocked/readback-only: " + "; ".join(blockers)
    return f"Package support remains {status}/readback-only."


def _safe_next_actions(
    *,
    queue_state: str,
    missing_fields: Sequence[str],
    row: Mapping[str, Any],
    package_preview: Mapping[str, Any],
) -> list[str]:
    actions: list[str] = []
    if MISSING_FIELD_LABELS["source_note"] in missing_fields:
        actions.append("Add a source note as local documentation context.")
    if MISSING_FIELD_LABELS["evidence_type"] in missing_fields:
        actions.append("Add a safe manual evidence type.")
    if MISSING_FIELD_LABELS["traceability_label"] in missing_fields:
        actions.append("Add a traceability label for local readback.")
    if MISSING_FIELD_LABELS["review_note"] in missing_fields:
        actions.append("Add a review note for manual follow-up.")
    if MISSING_FIELD_LABELS["evidence_label"] in missing_fields:
        actions.append("Add an evidence label for reviewer readability.")

    blocker_text = " ".join(
        [
            *_list_texts(row.get("visible_blocking_reasons") or row.get("blocking_reasons")),
            *_list_texts(package_preview.get("blocking_reasons")),
        ]
    ).casefold()
    if "beginner preview" in blocker_text or queue_state == "preview_only":
        actions.append("Keep beginner preview separate from package support.")
    if "placeholder" in blocker_text or "demo" in blocker_text or "example" in blocker_text:
        actions.append("Keep demo/example material as manual-review-only context.")
    if "conflict" in blocker_text or "deprecated" in blocker_text:
        actions.append("Resolve the conflict/deprecated marker before package readback use.")
    if not actions:
        actions.append("Keep as manual-review-only until a reviewer completes documentation checks.")
    return _unique(actions)


def _adapter_payload(input_payload: Any) -> dict[str, Any]:
    if _is_r202_adapter_payload(input_payload):
        return dict(input_payload)
    adapted = build_manual_evidence_input_adapter_payload(input_payload)
    return adapted if isinstance(adapted, dict) else {}


def _preflight_records(input_payload: Any, adapter_payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if _is_r202_adapter_payload(input_payload):
        preflight = _mapping(input_payload.get("manual_evidence_preflight_payload"))
        return _mapping_list(preflight.get("records"))
    if isinstance(input_payload, Mapping) and "records" in input_payload:
        return _mapping_list(input_payload.get("records"))
    preflight = _mapping(adapter_payload.get("manual_evidence_preflight_payload"))
    return _mapping_list(preflight.get("records"))


def _queue_payload(input_payload: Any, adapter_payload: Mapping[str, Any]) -> dict[str, Any]:
    if _is_r196_queue_payload(input_payload):
        return dict(input_payload)
    if _is_r200_readback(input_payload):
        return _queue_from_r200_readback(input_payload)
    if _is_r202_adapter_payload(input_payload):
        return _mapping(input_payload.get("manual_evidence_review_queue_payload"))
    queue = _mapping(adapter_payload.get("manual_evidence_review_queue_payload"))
    if _mapping(queue.get("summary")).get("row_count"):
        return queue
    return present_manual_evidence_review_queue(input_payload)


def _source_payload_kind(input_payload: Any) -> str:
    if _is_r202_adapter_payload(input_payload):
        return "r202_adapter_payload"
    if _is_r196_queue_payload(input_payload):
        return "r196_queue_payload"
    if _is_r200_readback(input_payload):
        return "r200_package_readback"
    if isinstance(input_payload, Mapping) and "records" in input_payload:
        return "r193_preflight_payload"
    if isinstance(input_payload, Sequence) and not isinstance(input_payload, (bytes, bytearray, str)):
        return "list_payload"
    return "empty_or_project_payload"


def _is_r202_adapter_payload(value: Any) -> bool:
    return isinstance(value, Mapping) and _text(value.get("adapter_schema_version")).startswith(
        "manual_evidence_input_adapter."
    )


def _is_r196_queue_payload(value: Any) -> bool:
    return isinstance(value, Mapping) and isinstance(value.get("rows"), Sequence) and isinstance(value.get("summary"), Mapping)


def _is_r200_readback(value: Any) -> bool:
    return isinstance(value, Mapping) and _text(value.get("readback_schema_version")).startswith(
        "manual_evidence_package_readback."
    )


def _queue_from_r200_readback(value: Any) -> dict[str, Any]:
    readback = _mapping(value)
    summary = _mapping(readback.get("summary"))
    return {
        "summary": {
            "row_count": summary.get("row_count", 0),
            "queue_state_counts": _mapping(readback.get("queue_state_counts")),
        },
        "rows": _mapping_list(readback.get("rows")),
        "batch_blocking_reasons": _list_texts(readback.get("batch_blocking_reasons")),
        "batch_warnings": _list_texts(readback.get("batch_warnings")),
    }


def _by_record_id(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for record in records:
        traceability = _mapping(record.get("traceability"))
        record_id = _text(traceability.get("record_id"))
        if record_id:
            result[record_id] = record
    return result


def _normalized_by_record_id(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for record in records:
        metadata = _mapping(record.get("evidence_entry_metadata"))
        record_id = _text(metadata.get("evidence_entry_id") or metadata.get("record_id"))
        if record_id:
            result[record_id] = record
    return result


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
    return _unique(_text(item) for item in raw_values if _text(item))


def _unique(values: Any) -> list[Any]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


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


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback
