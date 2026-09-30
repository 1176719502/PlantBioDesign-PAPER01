# -*- coding: utf-8 -*-
"""Read-only inventory helpers for legacy saved snapshots."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from services.legacy_snapshot_adapter import FORBIDDEN_READINESS_TERMS, normalize_legacy_snapshot

MISSING_SEQUENCE_WARNING = "P0: missing sequence"
CORRUPTED_DESIGN_DATA_WARNING = "P0: corrupted design data"
NORMALIZATION_ERROR_WARNING = "P0: cannot normalize safely"
HISTORICAL_VALIDATION_WITHOUT_CONTEXT_WARNING = "P0: historical validation lacks sequence or hash context"
MISSING_HOST_WARNING = "P1: missing host"
MISSING_GENE_WARNING = "P1: missing gene name"
MISSING_TIMESTAMP_WARNING = "P1: missing timestamp"
PRIMER_PROVENANCE_WARNING = "P1: primer snapshot lacks provenance"
DUPLICATE_DISPLAY_NAME_WARNING = "P1: duplicate display name"
DUPLICATE_ID_WARNING = "P1: duplicate legacy snapshot id"
MISSING_OPTIONAL_METADATA_WARNING = "P2: missing optional metadata"
ADAPTER_WARNING_PREFIX = "P2: adapter warning"
SEQUENCE_ONLY_WARNING = "P2: sequence-only fallback"

_EXAMPLE_RECORD_LIMIT = 5


def build_legacy_snapshot_inventory(records: list[dict]) -> dict:
    """Build a read-only diagnostic inventory from legacy snapshot records."""
    summary = _empty_summary()
    normalized_rows: list[dict[str, Any]] = []
    display_names: list[str] = []
    legacy_ids: list[str] = []

    for index, record in enumerate(records):
        summary["total_records"] += 1
        source_record = record if isinstance(record, Mapping) else {}
        record_warnings: list[str] = []
        high_risk = False

        try:
            normalized = normalize_legacy_snapshot(record)
        except Exception as exc:  # pragma: no cover - defensive boundary for future adapter changes
            normalized = _fallback_normalized_record(index)
            high_risk = True
            _add_warning(summary, NORMALIZATION_ERROR_WARNING)
            record_warnings.append(NORMALIZATION_ERROR_WARNING)
            record_warnings.append(f"normalization_error_type={type(exc).__name__}")

        sequence = _text(normalized.get("sequence"))
        display_name = _text(normalized.get("display_name"))
        legacy_id = _text(normalized.get("legacy_snapshot_id"))
        host = _text(normalized.get("host"))
        gene_name = _text(normalized.get("gene_name"))
        timestamp = _text(normalized.get("snapshot_created_at"))
        has_design_data = isinstance(source_record.get("design_data"), Mapping)
        has_historical_validation = bool(normalized.get("has_historical_validation"))
        has_primer_snapshot = bool(normalized.get("has_primer_snapshot"))
        is_sequence_only = bool(sequence) and not has_design_data

        if has_design_data:
            summary["expression_design_count"] += 1
        elif sequence:
            summary["sequence_only_count"] += 1

        if has_historical_validation:
            summary["historical_validation_count"] += 1
        if has_primer_snapshot:
            summary["primer_snapshot_count"] += 1

        if not sequence:
            summary["missing_sequence_count"] += 1
            high_risk = True
            _add_warning(summary, MISSING_SEQUENCE_WARNING)
            record_warnings.append(MISSING_SEQUENCE_WARNING)

        if _has_corrupted_design_data(source_record):
            high_risk = True
            _add_warning(summary, CORRUPTED_DESIGN_DATA_WARNING)
            record_warnings.append(CORRUPTED_DESIGN_DATA_WARNING)

        if has_historical_validation and not _has_sequence_or_hash_context(source_record, normalized):
            high_risk = True
            _add_warning(summary, HISTORICAL_VALIDATION_WITHOUT_CONTEXT_WARNING)
            record_warnings.append(HISTORICAL_VALIDATION_WITHOUT_CONTEXT_WARNING)

        missing_metadata = False
        if not host:
            missing_metadata = True
            _add_warning(summary, MISSING_HOST_WARNING)
            record_warnings.append(MISSING_HOST_WARNING)
        if not gene_name:
            missing_metadata = True
            _add_warning(summary, MISSING_GENE_WARNING)
            record_warnings.append(MISSING_GENE_WARNING)
        if not timestamp:
            missing_metadata = True
            _add_warning(summary, MISSING_TIMESTAMP_WARNING)
            record_warnings.append(MISSING_TIMESTAMP_WARNING)
        if missing_metadata:
            summary["missing_metadata_count"] += 1

        if has_primer_snapshot and not _has_primer_provenance(source_record):
            _add_warning(summary, PRIMER_PROVENANCE_WARNING)
            record_warnings.append(PRIMER_PROVENANCE_WARNING)

        if not _has_optional_metadata(source_record):
            _add_warning(summary, MISSING_OPTIONAL_METADATA_WARNING)
            record_warnings.append(MISSING_OPTIONAL_METADATA_WARNING)

        adapter_warnings = _safe_strings(normalized.get("load_warnings"))
        for warning in adapter_warnings:
            warning_key = f"{ADAPTER_WARNING_PREFIX}: {warning}"
            _add_warning(summary, warning_key)
            record_warnings.append(warning_key)

        if is_sequence_only:
            _add_warning(summary, SEQUENCE_ONLY_WARNING)
            record_warnings.append(SEQUENCE_ONLY_WARNING)

        if display_name:
            display_names.append(display_name)
        if legacy_id:
            legacy_ids.append(legacy_id)

        normalized_rows.append(
            {
                "index": index,
                "legacy_snapshot_id": legacy_id,
                "display_name": display_name,
                "high_risk": high_risk,
                "warnings": _unique_strings(record_warnings),
            }
        )

    duplicate_names = _duplicates(display_names)
    duplicate_ids = _duplicates(legacy_ids)
    if duplicate_names:
        _add_warning(summary, DUPLICATE_DISPLAY_NAME_WARNING, len(duplicate_names))
    if duplicate_ids:
        _add_warning(summary, DUPLICATE_ID_WARNING, len(duplicate_ids))

    high_risk_count = 0
    for row in normalized_rows:
        if row["display_name"] in duplicate_names:
            row["warnings"].append(DUPLICATE_DISPLAY_NAME_WARNING)
        if row["legacy_snapshot_id"] in duplicate_ids:
            row["warnings"].append(DUPLICATE_ID_WARNING)
        row["warnings"] = _unique_strings(row["warnings"])
        if row["high_risk"]:
            high_risk_count += 1
        if row["warnings"] and len(summary["example_records"]) < _EXAMPLE_RECORD_LIMIT:
            summary["example_records"].append(row)

    summary["high_risk_record_count"] = high_risk_count
    _assert_no_forbidden_terms(summary)
    return summary


def _empty_summary() -> dict[str, Any]:
    return {
        "total_records": 0,
        "expression_design_count": 0,
        "sequence_only_count": 0,
        "missing_sequence_count": 0,
        "historical_validation_count": 0,
        "primer_snapshot_count": 0,
        "missing_metadata_count": 0,
        "high_risk_record_count": 0,
        "warnings_by_type": {},
        "example_records": [],
    }


def _fallback_normalized_record(index: int) -> dict[str, Any]:
    return {
        "legacy_snapshot_id": "",
        "display_name": f"Legacy Snapshot {index + 1}",
        "sequence": "",
        "host": "",
        "gene_name": "",
        "snapshot_created_at": "",
        "load_warnings": [],
        "has_historical_validation": False,
        "has_primer_snapshot": False,
        "readiness_authority": False,
    }


def _add_warning(summary: dict[str, Any], warning: str, count: int = 1) -> None:
    summary["warnings_by_type"][warning] = summary["warnings_by_type"].get(warning, 0) + count


def _has_corrupted_design_data(record: Mapping[str, Any]) -> bool:
    return "design_data" in record and record.get("design_data") is not None and not isinstance(record.get("design_data"), Mapping)


def _has_sequence_or_hash_context(record: Mapping[str, Any], normalized: Mapping[str, Any]) -> bool:
    if _text(normalized.get("sequence")):
        return True
    return _first_text(
        record,
        keys=("sequence_hash", "hash", "design_hash", "snapshot_hash", "sequence_checksum"),
    ) != ""


def _has_primer_provenance(record: Mapping[str, Any]) -> bool:
    design_data = _mapping_or_empty(record.get("design_data"))
    metadata = _mapping_or_empty(design_data.get("metadata"))
    return _first_text(
        record,
        design_data,
        metadata,
        keys=(
            "primer_provenance",
            "primer_source",
            "primer_tool",
            "primer_generated_at",
            "primer_design_version",
        ),
    ) != ""


def _has_optional_metadata(record: Mapping[str, Any]) -> bool:
    design_data = _mapping_or_empty(record.get("design_data"))
    metadata = _mapping_or_empty(design_data.get("metadata"))
    return bool(metadata) or _first_text(record, design_data, keys=("source", "description", "notes")) != ""


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _first_text(*mappings: Mapping[str, Any], keys: Sequence[str]) -> str:
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            continue
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return str(value)
    return ""


def _duplicates(values: list[str]) -> set[str]:
    counts = Counter(value for value in values if value)
    return {value for value, count in counts.items() if count > 1}


def _safe_strings(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value if str(item)]
    return []


def _unique_strings(values: Sequence[str]) -> list[str]:
    unique_values = []
    for value in values:
        text = str(value)
        if text and text not in unique_values:
            unique_values.append(text)
    return unique_values


def _text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _assert_no_forbidden_terms(value: Any) -> None:
    combined = str(value)
    for forbidden_term in FORBIDDEN_READINESS_TERMS:
        if forbidden_term in combined:
            raise ValueError("Inventory summary emitted a forbidden readiness or certification term.")
