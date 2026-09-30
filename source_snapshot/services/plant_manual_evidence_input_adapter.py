"""R202 read-only adapter for project manual evidence payload fields.

The adapter accepts plain project/workflow payloads, extracts explicitly marked
manual evidence records, normalizes them for the R193 preflight checker, and
returns the R196 review queue readback. It does not import evidence, approve
records, verify sources, write data, or grant package/export behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_manual_evidence_preflight_checker import (
    preflight_manual_evidence_batch,
)
from services.plant_manual_evidence_review_queue_presenter import (
    present_manual_evidence_review_queue,
)


ADAPTER_SCHEMA_VERSION = "manual_evidence_input_adapter.v2.7.r202"
ADAPTER_BATCH = "v2.7-r202"

MANUAL_EVIDENCE_INPUT_FIELDS = (
    "manual_evidence_records",
    "manual_evidence",
    "evidence_records",
)

_WITHHELD_SOURCE_STATUS = "source" + "_" + "verified"
_PLACEHOLDER_MARKERS = ("placeholder", "demo", "example", "sample", "todo")
_MANUAL_MARKER_VALUES = {
    "manual_evidence",
    "manual_evidence_entry",
    "manual_review_note",
    "evidence_note",
    "source_note",
    "literature_note",
    "curator_note",
}
_PREVIEW_MARKERS = {"beginner_preview", "preview_only"}
_SOURCE_FIELDS = (
    "source_url_or_identifier",
    "source_trail",
    "source_reference",
    "source_note",
    "source_label",
    "citation_text",
)


def build_manual_evidence_input_adapter_payload(input_payload: Any) -> dict[str, Any]:
    """Return a read-only manual evidence queue payload from a project/workflow input."""

    extracted_records = _extract_manual_records(input_payload)
    normalized_records = [
        _normalize_record(record, index)
        for index, record in enumerate(extracted_records, start=1)
    ]
    preflight_payload = preflight_manual_evidence_batch(normalized_records)
    queue_payload = present_manual_evidence_review_queue(preflight_payload)

    return _plain_value(
        {
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "adapter_batch": ADAPTER_BATCH,
            "payload_kind": "manual_evidence_input_adapter_payload",
            "read_only": True,
            "display_readback_only": True,
            "input_summary": {
                "records_extracted": len(extracted_records),
                "normalized_record_count": len(normalized_records),
                "accepted_input_fields": list(MANUAL_EVIDENCE_INPUT_FIELDS),
                "empty_input": len(normalized_records) == 0,
            },
            "normalized_manual_evidence_records": normalized_records,
            "manual_evidence_preflight_payload": preflight_payload,
            "manual_evidence_review_queue_payload": queue_payload,
            "manual_evidence_review_queue_readback": queue_payload,
            "permissions": {
                "imports_evidence": False,
                "approval_allowed": False,
                "source_confirmation_allowed": False,
                "database_write_allowed": False,
                "package_export_permission": False,
                "package_draft_completion_permission": False,
            },
        }
    )


def manual_evidence_queue_payload_from_project_input(input_payload: Any) -> dict[str, Any]:
    """Return just the R196 queue readback for Plant Review UI consumers."""

    adapted = build_manual_evidence_input_adapter_payload(input_payload)
    return _mapping(adapted.get("manual_evidence_review_queue_payload"))


def _extract_manual_records(input_payload: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in _payload_sources(input_payload):
        for field_name in MANUAL_EVIDENCE_INPUT_FIELDS:
            raw_value = source.get(field_name)
            for item in _record_items(raw_value):
                if field_name == "evidence_records" and not _explicit_manual_marker(item):
                    continue
                records.append(_with_adapter_source(item, field_name, source))
    return records


def _payload_sources(input_payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(input_payload, Mapping):
        return [input_payload]
    if isinstance(input_payload, Sequence) and not isinstance(input_payload, (bytes, bytearray, str)):
        sources = [item for item in input_payload if isinstance(item, Mapping)]
        if any(field in source for source in sources for field in MANUAL_EVIDENCE_INPUT_FIELDS):
            return sources
        return [{"manual_evidence_records": list(input_payload)}]
    return []


def _record_items(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        for key in ("records", "manual_evidence_records", "items", "entries"):
            nested = value.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (bytes, bytearray, str)):
                return list(nested)
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _with_adapter_source(item: Any, field_name: str, source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        return {
            "adapter_source_field": field_name,
            "adapter_malformed_value": _text(type(item).__name__),
        }
    record = dict(item)
    record["adapter_source_field"] = field_name
    if _text(source.get("project_id") or source.get("id")):
        record.setdefault("project_id", _text(source.get("project_id") or source.get("id")))
    if _text(source.get("workflow_id")):
        record.setdefault("workflow_id", _text(source.get("workflow_id")))
    return record


def _explicit_manual_marker(record: Any) -> bool:
    if not isinstance(record, Mapping):
        return False
    if record.get("manual_evidence") is True or record.get("is_manual_evidence") is True:
        return True
    marker_values = [
        record.get("record_family"),
        record.get("record_type"),
        record.get("evidence_kind"),
        record.get("evidence_type"),
        record.get("claim_type"),
        record.get("component_type_or_record_family"),
    ]
    return any(_key(value) in _MANUAL_MARKER_VALUES for value in marker_values)


def _normalize_record(record: dict[str, Any], index: int) -> dict[str, Any]:
    if _looks_like_r193_record(record):
        return _sanitize_manual_record(record)
    if "adapter_malformed_value" in record:
        return _malformed_record(index, record)

    record_id = _first_text(
        record.get("evidence_entry_id"),
        record.get("record_id"),
        record.get("evidence_id"),
        record.get("id"),
        record.get("manual_evidence_id"),
    )
    source_title = _first_text(
        record.get("source_title"),
        record.get("evidence_label"),
        record.get("display_name"),
        record.get("title"),
        record.get("label"),
    )
    source_trail = _first_text(*(record.get(field) for field in _SOURCE_FIELDS))
    route_scope = _first_text(
        record.get("route_scope"),
        record.get("project_route_scope"),
        record.get("workflow_route_scope"),
    )
    claim_type = _claim_type(record)
    preview_only = _is_preview_only(record)
    demo_like = _is_demo_like(record)
    conflict_status = _first_text(record.get("conflict_status"), "no_known_conflict")
    deprecated_flag = _as_bool(record.get("deprecated_flag"))
    provenance_status = _safe_provenance_status(record)
    allowed_usage_scope = _allowed_usage_scope(record, preview_only, demo_like)

    if preview_only or demo_like:
        provenance_status = "demo_only"

    return _sanitize_manual_record(
        {
            "evidence_entry_metadata": {
                "evidence_entry_id": record_id,
                "created_by_or_imported_by": _first_text(record.get("created_by"), record.get("created_by_or_imported_by")),
                "created_at": _first_text(record.get("created_at"), record.get("created_date")),
                "updated_at": _first_text(record.get("updated_at")),
                "import_batch_id": _first_text(record.get("batch_id"), record.get("import_batch_id")),
                "import_mode": "manual_project_payload_entry",
                "notes_for_curator": _first_text(
                    record.get("notes_for_curator"),
                    record.get("review_note"),
                    record.get("review_notes"),
                    record.get("notes"),
                ),
            },
            "source_identity": {
                "source_type": _first_text(record.get("source_type"), "user_supplied"),
                "source_title": source_title,
                "source_url_or_identifier": source_trail,
                "doi": "",
                "accession": "",
                "repository_id": "",
                "citation_text": _first_text(record.get("citation_text")),
                "source_date_or_version": _first_text(record.get("source_date_or_version")),
                "source_quote_or_evidence_note": _first_text(record.get("source_quote_or_evidence_note"), record.get("evidence_note"), record.get("note")),
            },
            "evidence_scope": {
                "route_scope": route_scope,
                "organism_scope": _first_text(record.get("organism_scope")),
                "host_context": _first_text(record.get("host_context")),
                "record_family": "manual_evidence",
                "component_type_or_record_family": "manual_evidence",
                "related_record_id": _first_text(record.get("related_record_id")),
                "related_display_name": _first_text(record.get("related_display_name")),
                "claim_type": claim_type,
                "claim_summary": _first_text(record.get("claim_summary"), record.get("summary"), record.get("note")),
                "evidence_quality_level": _first_text(record.get("evidence_quality_level"), "user_note"),
            },
            "provenance_and_review": {
                "demo_or_real_flag": _demo_or_real_flag(record, preview_only, demo_like),
                "provenance_status": provenance_status,
                "manual_review_status": _first_text(record.get("manual_review_status"), "needs_manual_review"),
                "allowed_usage_scope": allowed_usage_scope,
                "conflict_status": conflict_status,
                "deprecated_flag": deprecated_flag,
                "replacement_record_id": _first_text(record.get("replacement_record_id")),
                "last_reviewed_at": _first_text(record.get("last_reviewed_at")),
                "reviewer_note": _first_text(
                    record.get("reviewer_note"),
                    record.get("review_note"),
                    record.get("review_notes"),
                    record.get("notes"),
                ),
            },
            "adapter_traceability": {
                "adapter_batch": ADAPTER_BATCH,
                "adapter_source_field": _text(record.get("adapter_source_field")),
                "project_id": _text(record.get("project_id")),
                "workflow_id": _text(record.get("workflow_id")),
                "source_record_id": record_id,
                "traceability_label": _text(record.get("traceability_label")),
                "evidence_type_recorded": bool(
                    _first_text(
                        record.get("claim_type"),
                        record.get("evidence_type"),
                        record.get("record_family"),
                    )
                ),
                "review_note_recorded": bool(
                    _first_text(
                        record.get("reviewer_note"),
                        record.get("review_note"),
                        record.get("review_notes"),
                        record.get("notes"),
                    )
                ),
                "traceability_label_recorded": bool(_text(record.get("traceability_label"))),
            },
        }
    )


def _looks_like_r193_record(record: Mapping[str, Any]) -> bool:
    return any(
        isinstance(record.get(section), Mapping)
        for section in (
            "evidence_entry_metadata",
            "source_identity",
            "evidence_scope",
            "provenance_and_review",
        )
    )


def _sanitize_manual_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return _replace_withheld_status(_plain_value(record))


def _replace_withheld_status(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _replace_withheld_status(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_replace_withheld_status(child) for child in value]
    if _text(value) == _WITHHELD_SOURCE_STATUS:
        return "source_present_needs_review"
    return value


def _malformed_record(index: int, record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "evidence_entry_metadata": {
            "evidence_entry_id": f"R202_MALFORMED_ENTRY_{index:03d}",
            "notes_for_curator": f"Malformed manual evidence payload value: {_text(record.get('adapter_malformed_value'))}",
        },
        "source_identity": {"source_type": "user_supplied", "source_title": ""},
        "evidence_scope": {"route_scope": "", "claim_type": ""},
        "provenance_and_review": {
            "demo_or_real_flag": "user_supplied_unverified",
            "provenance_status": "missing_source",
            "manual_review_status": "needs_manual_review",
            "allowed_usage_scope": "manual_review_only",
            "conflict_status": "unresolved",
            "deprecated_flag": False,
        },
        "adapter_traceability": {
            "adapter_batch": ADAPTER_BATCH,
            "adapter_source_field": _text(record.get("adapter_source_field")),
            "malformed_value_type": _text(record.get("adapter_malformed_value")),
        },
    }


def _claim_type(record: Mapping[str, Any]) -> str:
    value = _first_text(record.get("claim_type"), record.get("evidence_type"), record.get("record_family"))
    if not value:
        return "evidence_note"
    if _key(value) == "manual_evidence":
        return "evidence_note"
    return _key(value)


def _safe_provenance_status(record: Mapping[str, Any]) -> str:
    value = _first_text(record.get("provenance_status"), record.get("source_status"))
    if value == _WITHHELD_SOURCE_STATUS:
        return "source_present_needs_review"
    return value or "source_present_needs_review"


def _allowed_usage_scope(
    record: Mapping[str, Any],
    preview_only: bool,
    placeholder_or_demo: bool,
) -> str:
    if preview_only:
        return "beginner_preview"
    if placeholder_or_demo:
        return _first_text(record.get("allowed_usage_scope"), "demo_only")
    return _first_text(record.get("allowed_usage_scope"), "manual_review_only")


def _demo_or_real_flag(
    record: Mapping[str, Any],
    preview_only: bool,
    placeholder_or_demo: bool,
) -> str:
    if preview_only or placeholder_or_demo:
        return "demo_example"
    return _first_text(record.get("demo_or_real_flag"), "user_supplied_unverified")


def _is_preview_only(record: Mapping[str, Any]) -> bool:
    values = (
        record.get("queue_state"),
        record.get("readback_state"),
        record.get("allowed_usage_scope"),
        record.get("review_state"),
        record.get("preview_status"),
    )
    return any(_key(value) in _PREVIEW_MARKERS for value in values)


def _is_demo_like(record: Mapping[str, Any]) -> bool:
    values = (
        record.get("demo_or_real_flag"),
        record.get("provenance_status"),
        record.get("record_status"),
    )
    return any(_key(value) in {"demo", "demo_example", "demo_only", "example"} for value in values)


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_placeholder(child) for child in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return any(_contains_placeholder(child) for child in value)
    text = _text(value).casefold()
    return any(marker in text for marker in _PLACEHOLDER_MARKERS)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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


def _first_text(*values: Any) -> str:
    for value in values:
        clean = _text(value)
        if clean:
            return clean
    return ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_").replace("/", "_")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _key(value) in {"true", "yes", "1", "deprecated"}
