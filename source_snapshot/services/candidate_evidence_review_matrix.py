from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from services.placeholder_review_value import (
    clean_review_value,
    has_recorded_review_value,
)


BOUNDARY_NOTE = (
    "Documentation-only evidence review. Matrix rows summarize source trace and "
    "record completeness for documentation review; they do not choose candidates or "
    "make biological use decisions."
)
EMPTY_STATE_MESSAGE = (
    "No candidate evidence records are currently available for review. Link source "
    "trace and record review status in the existing Component Library, Candidate Evidence, "
    "or Project Review Report surfaces before documentation review planning."
)
EXTERNAL_SOURCE_ACTION = (
    "Review the source trace manually and keep the record separate from runtime seed intake."
)
COMPLETE_METADATA_ACTION = (
    "Continue manual documentation review with the recorded source trace."
)
MISSING_METADATA_ACTION = (
    "Add missing source/provenance or review-status fields before documentation review."
)
RUNTIME_SEED_BLOCKED_STATUS = "runtime seed intake blocked"

_RECORD_LIST_KEYS = (
    "candidate_rows",
    "candidate_results",
    "candidate_entries",
    "records",
    "rows",
    "references",
    "profile_rows",
    "evidence_rows",
)
_MISSING_FIELD_ORDER = (
    "candidate_label",
    "source_category",
    "source_identifier",
    "source_hash",
    "review_status",
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _metadata_text(value: Any, fallback: str = "") -> str:
    return clean_review_value(value, fallback)


def _record_value(record: Any, keys: Iterable[str]) -> Any:
    if isinstance(record, Mapping):
        for key in keys:
            if key in record and has_recorded_review_value(record.get(key)):
                return record.get(key)
        return ""
    for key in keys:
        value = getattr(record, key, "")
        if has_recorded_review_value(value):
            return value
    return ""


def _as_record(record: Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    data = getattr(record, "__dict__", None)
    if isinstance(data, Mapping):
        return dict(data)
    return {}


def _extract_records(records_or_view_model: Any) -> list[Any]:
    if records_or_view_model is None:
        return []
    if isinstance(records_or_view_model, Mapping):
        for key in _RECORD_LIST_KEYS:
            rows = records_or_view_model.get(key)
            if isinstance(rows, list | tuple):
                return list(rows)
        return [records_or_view_model]
    if isinstance(records_or_view_model, (str, bytes)):
        return []
    if isinstance(records_or_view_model, Iterable):
        return list(records_or_view_model)
    return []


def _candidate_label(record: Any, fallback_index: int) -> str:
    return _text(
        _record_value(
            record,
            (
                "candidate_label",
                "display_label",
                "asset_display_name",
                "asset_label",
                "promoter_label",
                "display_name",
                "query_target",
                "name",
                "local_id",
                "part_id",
                "candidate_id",
            ),
        ),
        f"candidate-{fallback_index}",
    )


def _source_category(record: Any) -> str:
    return _text(
        _record_value(
            record,
            (
                "source_category",
                "source_database",
                "source_record_type",
                "source_type",
                "catalog",
                "asset_type",
                "part_type",
            ),
        )
    )


def _source_identifier(record: Any) -> str:
    return _text(
        _record_value(
            record,
            (
                "source_identifier",
                "stable_source_identifier",
                "source_accession",
                "source_url",
                "asset_id",
                "part_id",
                "local_id",
                "candidate_id",
            ),
        )
    )


def _source_hash(record: Any) -> str:
    return _text(
        _record_value(
            record,
            (
                "source_hash",
                "source_record_hash",
                "content_hash",
                "evidence_hash",
                "snapshot_hash",
                "sha256",
                "record_hash",
            ),
        )
    )


def _review_status(record: Any) -> str:
    return _text(
        _record_value(
            record,
            (
                "review_status",
                "source_review_status",
                "human_review_status",
                "curation_status",
                "documentation_status",
            ),
        )
    )


def _missing_fields(
    *,
    candidate_label: str,
    source_category: str,
    source_identifier: str,
    source_hash: str,
    review_status: str,
) -> list[str]:
    values = {
        "candidate_label": candidate_label,
        "source_category": source_category,
        "source_identifier": source_identifier,
        "source_hash": source_hash,
        "review_status": review_status,
    }
    return [field for field in _MISSING_FIELD_ORDER if not _metadata_text(values[field])]


def _provenance_status(source_category: str, source_identifier: str, source_hash: str) -> str:
    if all(_metadata_text(value) for value in (source_category, source_identifier, source_hash)):
        return "source trace recorded"
    if any(_metadata_text(value) for value in (source_category, source_identifier, source_hash)):
        return "source trace incomplete"
    return "source trace missing"


def _metadata_status(missing_fields: list[str]) -> str:
    return "documentation-complete" if not missing_fields else "metadata-incomplete"


def _review_focus(missing_fields: list[str]) -> str:
    has_source_gap = any(
        field in missing_fields
        for field in ("source_category", "source_identifier", "source_hash")
    )
    has_record_gap = any(field in missing_fields for field in ("candidate_label", "review_status"))
    if has_source_gap and has_record_gap:
        return "source/provenance and record review"
    if has_source_gap:
        return "source/provenance review"
    if has_record_gap:
        return "evidence-record review"
    return "manual follow-up review"


def _gap_label(missing_fields: list[str]) -> str:
    if not missing_fields:
        return "No required documentation fields missing"
    return _review_focus(missing_fields)


def _is_external_candidate(record: dict[str, Any]) -> bool:
    if record.get("not_runtime_seed") is True:
        return True
    source_scope = _text(record.get("snapshot_scope")).casefold()
    curation_status = _text(record.get("curation_status")).casefold()
    source_review_status = _text(record.get("source_review_status")).casefold()
    return (
        "candidate snapshot" in source_scope
        or curation_status in {"candidate_snapshot_only", "not_curated_yet"}
        or source_review_status in {"source_candidate_identified", "source_review_required"}
    )


def _next_manual_action(record: dict[str, Any], missing_fields: list[str]) -> str:
    if missing_fields:
        return MISSING_METADATA_ACTION
    if _is_external_candidate(record):
        return EXTERNAL_SOURCE_ACTION
    return COMPLETE_METADATA_ACTION


def _sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _text(row.get("candidate_label")).casefold(),
        _text(row.get("source_category")).casefold(),
        _text(row.get("source_identifier")).casefold(),
    )


def build_candidate_evidence_review_matrix(records_or_view_model: Any) -> dict[str, Any]:
    """Build deterministic documentation-only evidence review rows."""
    rows: list[dict[str, Any]] = []
    raw_records = _extract_records(records_or_view_model)

    for index, raw_record in enumerate(raw_records, start=1):
        record = _as_record(raw_record)
        candidate_label = _candidate_label(record, index)
        source_category = _source_category(record)
        source_identifier = _source_identifier(record)
        source_hash = _source_hash(record)
        review_status = _text(_review_status(record), "manual review needed")
        missing_fields = _missing_fields(
            candidate_label=candidate_label,
            source_category=source_category,
            source_identifier=source_identifier,
            source_hash=source_hash,
            review_status="" if review_status == "manual review needed" else review_status,
        )
        external_candidate = _is_external_candidate(record)
        runtime_seed_positive = bool(
            record.get("runtime_seed_ready") or record.get("curated_for_runtime_seed")
        )
        curation_boundary_status = (
            RUNTIME_SEED_BLOCKED_STATUS
            if external_candidate or runtime_seed_positive
            else "manual documentation review only"
        )

        rows.append(
            {
                "candidate_label": candidate_label,
                "source_category": source_category or "source not recorded",
                "source_identifier": source_identifier or "identifier not recorded",
                "provenance_status": _provenance_status(
                    source_category,
                    source_identifier,
                    source_hash,
                ),
                "metadata_status": _metadata_status(missing_fields),
                "record_review_status": _metadata_status(missing_fields),
                "review_focus": _review_focus(missing_fields),
                "gap_label": _gap_label(missing_fields),
                "review_status": review_status,
                "missing_fields": missing_fields,
                "next_manual_action": _next_manual_action(record, missing_fields),
                "boundary_note": BOUNDARY_NOTE,
                "source_hash_present": bool(source_hash),
                "external_candidate": external_candidate,
                "curation_boundary_status": curation_boundary_status,
            }
        )

    rows = sorted(rows, key=_sort_key)
    metadata_counts = Counter(row["metadata_status"] for row in rows)
    provenance_counts = Counter(row["provenance_status"] for row in rows)
    review_counts = Counter(row["review_status"] for row in rows)
    source_category_counts = Counter(row["source_category"] for row in rows)

    missing_metadata_count = sum(1 for row in rows if row["missing_fields"])
    external_candidate_count = sum(1 for row in rows if row["external_candidate"])
    runtime_seed_blocked_count = sum(
        1
        for row in rows
        if row["curation_boundary_status"] == RUNTIME_SEED_BLOCKED_STATUS
    )

    return {
        "title": "Candidate Evidence Review Matrix",
        "subtitle": "Documentation-only source/provenance and record review status check.",
        "rows": rows,
        "summary": {
            "candidate_count": len(rows),
            "documentation_complete_count": metadata_counts.get("documentation-complete", 0),
            "metadata_incomplete_count": missing_metadata_count,
            "source_trace_missing_count": provenance_counts.get("source trace missing", 0),
            "source_trace_incomplete_count": provenance_counts.get("source trace incomplete", 0),
            "external_candidate_count": external_candidate_count,
            "runtime_seed_intake_blocked_count": runtime_seed_blocked_count,
            "metadata_status_counts": dict(sorted(metadata_counts.items())),
            "provenance_status_counts": dict(sorted(provenance_counts.items())),
            "review_status_counts": dict(sorted(review_counts.items())),
            "source_category_counts": dict(sorted(source_category_counts.items())),
        },
        "empty_state_message": EMPTY_STATE_MESSAGE if not rows else "",
        "boundary_note": BOUNDARY_NOTE,
    }


def build_candidate_evidence_review_rows(records_or_view_model: Any) -> list[dict[str, Any]]:
    return build_candidate_evidence_review_matrix(records_or_view_model)["rows"]
