from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from services.rice_albumin_manual_provenance_verification import (
    BOUNDARY_NOTE as R143_BOUNDARY_NOTE,
    DEFAULT_RICE_ALBUMIN_SEED_DIR,
    DO_NOT_PROMOTE_STATUS,
    MANUAL_PROVENANCE_STATUS_READY,
    REVIEW_REQUIRED_STATUS,
    build_rice_albumin_manual_provenance_verification_payload,
)


MANUAL_PROVENANCE_QUEUE_SCHEMA_VERSION = (
    "rice_albumin_manual_provenance_verification_queue.v2.7.r146"
)
MANUAL_PROVENANCE_QUEUE_BATCH = "v2.7-r146"
MANUAL_PROVENANCE_QUEUE_STATUS_READY = "manual_provenance_verification_queue_ready"
MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED = "manual_provenance_verification_queue_fail_closed"

TASK_TYPES = (
    "verify_source_id",
    "verify_accession",
    "confirm_source_scope",
    "confirm_component_linkage",
    "confirm_evidence_record",
    "do_not_promote_guard",
)

DOCUMENTATION_BOUNDARY = (
    "Documentation-only manual provenance task. The queue identifies human review work "
    "without looking up sources, filling identifiers, changing seed records, accepting "
    "evidence, choosing components, or judging downstream use."
)

TASK_TEXT = {
    "verify_source_id": {
        "task_label": "Verify missing source identifier",
        "verification_question": "Which external source identifier should a human review for this record?",
        "blocking_reason": "The record has no source identifier in the local seed payload.",
        "required_manual_action": (
            "Manually inspect the appropriate external source material and record the source "
            "identifier in a separately scoped seed-data update if review supports it."
        ),
    },
    "verify_accession": {
        "task_label": "Verify missing accession",
        "verification_question": "Which accession or versioned accession should a human review for this record?",
        "blocking_reason": "The record has no accession captured in the local seed payload.",
        "required_manual_action": (
            "Manually inspect source material for an accession or versioned accession, then "
            "record it only in a separately scoped seed-data update if review supports it."
        ),
    },
    "confirm_source_scope": {
        "task_label": "Confirm source scope",
        "verification_question": "Does the candidate source category match the record scope?",
        "blocking_reason": "The record is based on local placeholders or candidate source categories only.",
        "required_manual_action": (
            "Manually compare the record scope against source material and document whether "
            "the source category is appropriate before any later status change."
        ),
    },
    "confirm_component_linkage": {
        "task_label": "Confirm component linkage",
        "verification_question": "Does the component linkage match the documented route or evidence context?",
        "blocking_reason": "The component relationship remains review-required and source-gap-visible.",
        "required_manual_action": (
            "Manually inspect the component linkage and document any source-backed correction "
            "in a separately scoped seed-data update."
        ),
    },
    "confirm_evidence_record": {
        "task_label": "Confirm evidence record",
        "verification_question": "Does the evidence placeholder have source-backed record support?",
        "blocking_reason": "The evidence record remains a local placeholder or provenance-gap row.",
        "required_manual_action": (
            "Manually inspect source material and document evidence metadata only in a "
            "separately scoped seed-data update."
        ),
    },
    "do_not_promote_guard": {
        "task_label": "Keep record blocked from promotion",
        "verification_question": "Has a human completed provenance review before any later status change?",
        "blocking_reason": "Manual provenance review is still required.",
        "required_manual_action": (
            "Keep the record in manual review and do not promote it until a later scoped "
            "human-reviewed seed update supplies the missing provenance."
        ),
    },
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


def _task_missing_fields(row: Mapping[str, Any], task_type: str) -> list[str]:
    fields = _unique_texts(_sequence(row.get("gap_fields")))
    if task_type == "verify_source_id":
        fields.append("source_id")
    if task_type == "verify_accession":
        fields.append("accession")
    if task_type == "confirm_source_scope":
        fields.extend(_sequence(row.get("candidate_source_categories")))
        fields.append("source_scope")
    if task_type == "confirm_component_linkage":
        fields.append("component_linkage")
    if task_type == "confirm_evidence_record":
        fields.append("evidence_record")
    if task_type == "do_not_promote_guard":
        fields.append(DO_NOT_PROMOTE_STATUS)
    return _unique_texts(fields)


def _record_task_types(row: Mapping[str, Any]) -> list[str]:
    safe_categories = set(_sequence(row.get("safe_review_categories")))
    record_type = _text(row.get("record_type"))
    task_types: list[str] = []

    if row.get("missing_source_id") is True or "missing_source_id" in safe_categories:
        task_types.append("verify_source_id")
    if row.get("missing_accession") is True or "missing_accession" in safe_categories:
        task_types.append("verify_accession")
    if (
        "local_placeholder_only" in safe_categories
        or "candidate_source_category_only" in safe_categories
    ):
        task_types.append("confirm_source_scope")
    if record_type == "ComponentRecord":
        task_types.append("confirm_component_linkage")
    if record_type == "EvidenceRecord":
        task_types.append("confirm_evidence_record")
    task_types.append("do_not_promote_guard")

    return [task_type for task_type in TASK_TYPES if task_type in set(task_types)]


def _task_row(row: Mapping[str, Any], task_type: str) -> dict[str, Any]:
    record_id = _text(row.get("record_id"), "unknown_rice_albumin_seed_record")
    task_copy = TASK_TEXT[task_type]
    return _plain_value(
        {
            "task_id": f"r146-{record_id}-{task_type}",
            "record_id": record_id,
            "record_type": _text(row.get("record_type"), "SeedRecord"),
            "task_type": task_type,
            "task_label": task_copy["task_label"],
            "current_review_status": _text(row.get("review_status"), REVIEW_REQUIRED_STATUS),
            "current_provenance_status": _text(row.get("provenance_status"), "missing"),
            "missing_fields": _task_missing_fields(row, task_type),
            "verification_question": task_copy["verification_question"],
            "blocking_reason": task_copy["blocking_reason"],
            "required_manual_action": task_copy["required_manual_action"],
            "promotion_blocked": True,
            "do_not_promote_until_verified": True,
            "documentation_boundary": DOCUMENTATION_BOUNDARY,
        }
    )


def _fail_closed_task(reason: str) -> dict[str, Any]:
    row = {
        "record_id": "unknown_rice_albumin_seed_records",
        "record_type": "ManualProvenancePayload",
        "review_status": REVIEW_REQUIRED_STATUS,
        "provenance_status": "malformed",
        "gap_fields": ["provenance_payload.records", reason],
    }
    task = _task_row(row, "do_not_promote_guard")
    task["task_id"] = "r146-unknown-rice-albumin-seed-records-do_not_promote_guard"
    task["blocking_reason"] = (
        "The manual provenance payload is missing or malformed, so the queue fails closed."
    )
    task["required_manual_action"] = (
        "Restore a readable R143 manual provenance payload before reviewing individual records."
    )
    return _plain_value(task)


def _summary(tasks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    record_ids = {_text(task.get("record_id")) for task in tasks if _text(task.get("record_id"))}
    source_task_records = {
        _text(task.get("record_id")) for task in tasks if task.get("task_type") == "verify_source_id"
    }
    accession_task_records = {
        _text(task.get("record_id")) for task in tasks if task.get("task_type") == "verify_accession"
    }
    manual_lookup_records = {
        _text(task.get("record_id"))
        for task in tasks
        if task.get("task_type")
        in {
            "verify_source_id",
            "verify_accession",
            "confirm_source_scope",
            "confirm_component_linkage",
            "confirm_evidence_record",
        }
    }
    blocked_records = {
        _text(task.get("record_id")) for task in tasks if task.get("promotion_blocked") is True
    }
    return {
        "total_tasks": len(tasks),
        "represented_record_count": len(record_ids),
        "records_requiring_manual_lookup": len(manual_lookup_records),
        "records_blocked_from_promotion": len(blocked_records),
        "missing_source_id_count": len(source_task_records),
        "missing_accession_count": len(accession_task_records),
        "ready_to_promote_count": 0,
        "task_type_counts": {
            task_type: sum(1 for task in tasks if task.get("task_type") == task_type)
            for task_type in TASK_TYPES
        },
        "record_ids_requiring_manual_lookup": sorted(manual_lookup_records, key=str.casefold),
        "record_ids_blocked_from_promotion": sorted(blocked_records, key=str.casefold),
        "record_ids_missing_source_id": sorted(source_task_records, key=str.casefold),
        "record_ids_missing_accession": sorted(accession_task_records, key=str.casefold),
    }


def _build_tasks_from_records(records: Sequence[Any]) -> list[dict[str, Any]]:
    tasks = [
        _task_row(row, task_type)
        for row in sorted(
            [_mapping(record) for record in records],
            key=lambda item: (_text(item.get("record_id")), _text(item.get("record_type"))),
        )
        for task_type in _record_task_types(row)
    ]
    return sorted(tasks, key=lambda item: (_text(item.get("record_id")), _text(item.get("task_type"))))


def build_rice_albumin_manual_provenance_verification_queue(
    payload: Mapping[str, Any] | None = None,
    *,
    seed_dir: str | Path = DEFAULT_RICE_ALBUMIN_SEED_DIR,
    manual_verification_dir: str | Path | None = None,
    source_review_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Return read-only manual provenance verification tasks for R131 rice albumin seed records."""
    source = _mapping(payload) or build_rice_albumin_manual_provenance_verification_payload(
        seed_dir=seed_dir,
        manual_verification_dir=manual_verification_dir,
        source_review_dir=source_review_dir,
    )
    records = source.get("records")
    warnings = _sequence(source.get("warnings"))

    if not isinstance(records, Sequence) or isinstance(records, (bytes, bytearray, str)):
        tasks = [_fail_closed_task("records_not_list")]
        workflow_status = MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED
        warnings = warnings + ["Manual provenance records are missing or malformed; queue fails closed."]
    else:
        tasks = _build_tasks_from_records(records)
        source_status = _text(source.get("workflow_status"))
        workflow_status = (
            MANUAL_PROVENANCE_QUEUE_STATUS_READY
            if source_status == MANUAL_PROVENANCE_STATUS_READY and tasks
            else MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED
        )
        if not tasks:
            tasks = [_fail_closed_task("no_task_rows")]
            workflow_status = MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED
            warnings = warnings + ["Manual provenance records produced no task rows; queue fails closed."]

    return _plain_value(
        {
            "workflow_schema_version": MANUAL_PROVENANCE_QUEUE_SCHEMA_VERSION,
            "workflow_batch": MANUAL_PROVENANCE_QUEUE_BATCH,
            "workflow_status": workflow_status,
            "source_workflow_schema_version": _text(source.get("workflow_schema_version")),
            "source_workflow_status": _text(source.get("workflow_status")),
            "read_only": True,
            "plant_scope_only": True,
            "manual_review_required": True,
            "documentation_only_boundary": R143_BOUNDARY_NOTE,
            "queue_boundary": DOCUMENTATION_BOUNDARY,
            "source_policy": (
                "The queue performs no source lookup, external API calls, identifier filling, "
                "seed record changes, evidence acceptance, component selection, or record promotion."
            ),
            "task_types": list(TASK_TYPES),
            "summary": _summary(tasks),
            "tasks": tasks,
            "warnings": warnings,
        }
    )


def build_rice_albumin_manual_provenance_queue_readback_rows(
    queue_payload: Mapping[str, Any] | None = None,
    *,
    seed_dir: str | Path = DEFAULT_RICE_ALBUMIN_SEED_DIR,
    manual_verification_dir: str | Path | None = None,
    source_review_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return compact plain row dicts for future UI or report readback."""
    source = _mapping(queue_payload) or build_rice_albumin_manual_provenance_verification_queue(
        seed_dir=seed_dir,
        manual_verification_dir=manual_verification_dir,
        source_review_dir=source_review_dir,
    )
    rows: list[dict[str, Any]] = []
    for task in _sequence(source.get("tasks")):
        row = _mapping(task)
        rows.append(
            {
                "task_id": _text(row.get("task_id")),
                "record_id": _text(row.get("record_id")),
                "record_type": _text(row.get("record_type")),
                "task_type": _text(row.get("task_type")),
                "task_label": _text(row.get("task_label")),
                "current_review_status": _text(row.get("current_review_status"), REVIEW_REQUIRED_STATUS),
                "current_provenance_status": _text(row.get("current_provenance_status"), "missing"),
                "missing_fields": _sequence(row.get("missing_fields")),
                "promotion_blocked": row.get("promotion_blocked") is True,
                "do_not_promote_until_verified": row.get("do_not_promote_until_verified") is True,
                "documentation_boundary": _text(row.get("documentation_boundary"), DOCUMENTATION_BOUNDARY),
            }
        )
    return _plain_value(rows)
