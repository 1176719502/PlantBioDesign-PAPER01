# -*- coding: utf-8 -*-
"""Read-only normalization helpers for legacy saved snapshots."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

HISTORICAL_VALIDATION_WARNING = "Prior validation data may be historical."
PRIMER_SNAPSHOT_WARNING = "Primer data is a legacy snapshot and is not readiness authority."
SEQUENCE_ONLY_FALLBACK_WARNING = "Sequence-only fallback; full design metadata is unavailable."
MISSING_METADATA_WARNING = "Legacy snapshot metadata is incomplete."

FORBIDDEN_READINESS_TERMS = (
    "Ready for Export",
    "Validated",
    "Certified",
    "Experiment-ready",
    "Current Validation",
)


def normalize_legacy_snapshot(record: dict) -> dict:
    """Return a conservative read-only view of a legacy snapshot record."""
    source_record = record if isinstance(record, Mapping) else {}
    design_data = _mapping_or_empty(source_record.get("design_data"))
    metadata = _mapping_or_empty(_first_present(source_record, design_data, key="metadata"))
    summary = _mapping_or_empty(_first_present(source_record, design_data, key="summary"))

    sequence = _string_value(_first_present(source_record, design_data, summary, key="sequence"))
    source = _string_value(_first_present(source_record, design_data, metadata, key="source"))
    validation_results = _first_present(
        source_record,
        design_data,
        summary,
        key="validation_results",
    )
    primers = _first_present(source_record, design_data, summary, metadata, key="primers")

    has_design_data = bool(design_data)
    sequence_only = bool(sequence) and not has_design_data
    normalized_source = source or "legacy snapshot"
    if sequence_only and not source:
        normalized_source = "sequence-only"

    warnings = []
    if _has_validation_results(validation_results):
        warnings.append(HISTORICAL_VALIDATION_WARNING)
    if _has_primer_snapshot(primers):
        warnings.append(PRIMER_SNAPSHOT_WARNING)
    if sequence_only:
        warnings.append(SEQUENCE_ONLY_FALLBACK_WARNING)
    if not has_design_data:
        warnings.append(MISSING_METADATA_WARNING)

    return {
        "legacy_snapshot_id": _legacy_snapshot_id(source_record, design_data, metadata),
        "display_name": _display_name(source_record, design_data, metadata, summary),
        "sequence": sequence,
        "host": _string_value(_first_present(source_record, design_data, metadata, summary, key="host")),
        "gene_name": _gene_name(source_record, design_data, metadata, summary),
        "source": normalized_source,
        "snapshot_created_at": _string_value(
            _first_present(
                source_record,
                design_data,
                metadata,
                summary,
                keys=("snapshot_created_at", "created_at", "updated_at", "date"),
            )
        ),
        "load_warnings": _unique_strings(warnings),
        "has_historical_validation": _has_validation_results(validation_results),
        "has_primer_snapshot": _has_primer_snapshot(primers),
        "readiness_authority": False,
        "revision_candidate": False,
        "historical_validation_issue_count": _validation_issue_count(validation_results),
        "primer_snapshot_count": _primer_snapshot_count(primers),
    }


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _first_present(*mappings: Mapping[str, Any], key: str | None = None, keys: Sequence[str] = ()) -> Any:
    lookup_keys = (key,) if key is not None else tuple(keys)
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            continue
        for lookup_key in lookup_keys:
            value = mapping.get(lookup_key)
            if value not in (None, ""):
                return value
    return None


def _string_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _legacy_snapshot_id(
    record: Mapping[str, Any],
    design_data: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    value = _first_present(
        record,
        design_data,
        metadata,
        keys=("legacy_snapshot_id", "load_key", "id", "design_id", "sequence_id"),
    )
    return _string_value(value)


def _display_name(
    record: Mapping[str, Any],
    design_data: Mapping[str, Any],
    metadata: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> str:
    value = _first_present(record, design_data, metadata, summary, keys=("name", "display_name", "title"))
    return _string_value(value) or "Legacy Snapshot"


def _gene_name(
    record: Mapping[str, Any],
    design_data: Mapping[str, Any],
    metadata: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> str:
    value = _first_present(
        record,
        design_data,
        metadata,
        summary,
        keys=("gene_name", "target_gene", "gene", "gene_symbol"),
    )
    if isinstance(value, Mapping):
        value = _first_present(value, keys=("name", "gene_name", "symbol"))
    return _string_value(value)


def _has_validation_results(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value) > 0
    return False


def _validation_issue_count(value: Any) -> int:
    if isinstance(value, Mapping):
        for key in ("issues", "warnings", "errors", "results", "validation_results"):
            nested = value.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
                return len(nested)
        for key in ("issue_count", "n_issues", "total_issues"):
            count = value.get(key)
            if isinstance(count, int) and count >= 0:
                return count
        return 1 if value else 0
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value)
    return 0


def _has_primer_snapshot(value: Any) -> bool:
    return _primer_snapshot_count(value) > 0


def _primer_snapshot_count(value: Any) -> int:
    if isinstance(value, Mapping):
        for key in ("primers", "primer_pairs", "results"):
            nested = value.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
                return len(nested)
        return 1 if value else 0
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value)
    return 0


def _unique_strings(values: Sequence[str]) -> list[str]:
    unique_values = []
    for value in values:
        text = str(value)
        if text and text not in unique_values:
            unique_values.append(text)
    return unique_values
