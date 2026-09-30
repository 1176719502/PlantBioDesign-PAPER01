# -*- coding: utf-8 -*-
"""Read-only migration dry-run report helpers for legacy snapshots."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from services.legacy_snapshot_adapter import FORBIDDEN_READINESS_TERMS, normalize_legacy_snapshot
from services.legacy_snapshot_inventory import (
    CORRUPTED_DESIGN_DATA_WARNING,
    DUPLICATE_DISPLAY_NAME_WARNING,
    DUPLICATE_ID_WARNING,
    HISTORICAL_VALIDATION_WITHOUT_CONTEXT_WARNING,
    MISSING_SEQUENCE_WARNING,
    NORMALIZATION_ERROR_WARNING,
    build_legacy_snapshot_inventory,
)

REPORT_TYPE = "read_only_migration_dry_run"
READ_ONLY_COMPATIBLE = "read_only_compatible"
NEEDS_REVIEW = "needs_review"
DO_NOT_MIGRATE_AUTOMATICALLY = "do_not_migrate_automatically"
MISSING_REQUIRED_DATA = "missing_required_data"

_ALLOWED_ACTIONS = frozenset(
    {
        READ_ONLY_COMPATIBLE,
        NEEDS_REVIEW,
        DO_NOT_MIGRATE_AUTOMATICALLY,
        MISSING_REQUIRED_DATA,
    }
)

_HIGH_RISK_WARNINGS = frozenset(
    {
        MISSING_SEQUENCE_WARNING,
        CORRUPTED_DESIGN_DATA_WARNING,
        NORMALIZATION_ERROR_WARNING,
        HISTORICAL_VALIDATION_WITHOUT_CONTEXT_WARNING,
    }
)

_DUPLICATE_WARNINGS = frozenset({DUPLICATE_DISPLAY_NAME_WARNING, DUPLICATE_ID_WARNING})


_HELPER_WARNING_PREFIXES = (
    "normalization_error_type=",
)


def build_migration_dry_run_report(records: list[dict]) -> dict:
    """Build a conservative read-only migration dry-run report.

    The helper accepts caller-provided records only. It does not access the
    database, write files, mutate input records, recompute readiness, or create
    migration candidates beyond diagnostic counts.
    """
    inventory = build_legacy_snapshot_inventory(records)
    record_rows = _build_record_rows(records, inventory.get("example_records", []))
    duplicate_groups = _build_duplicate_groups(record_rows)
    action_counts = _action_counts(record_rows)
    risk_counts = _risk_counts(record_rows)

    report = {
        "report_type": REPORT_TYPE,
        "total_records": inventory.get("total_records", 0),
        "migration_candidate_count": action_counts[READ_ONLY_COMPATIBLE] + action_counts[NEEDS_REVIEW],
        "read_only_compatible_count": action_counts[READ_ONLY_COMPATIBLE],
        "needs_review_count": action_counts[NEEDS_REVIEW],
        "do_not_migrate_automatically_count": action_counts[DO_NOT_MIGRATE_AUTOMATICALLY],
        "missing_required_data_count": action_counts[MISSING_REQUIRED_DATA],
        "high_risk_record_count": risk_counts["high"],
        "medium_risk_record_count": risk_counts["medium"],
        "low_risk_record_count": risk_counts["low"],
        "duplicate_groups": duplicate_groups,
        "warnings_by_type": dict(inventory.get("warnings_by_type", {})),
        "recommended_actions_summary": dict(action_counts),
        "example_records": _example_records(record_rows),
    }
    _assert_allowed_actions(report)
    _assert_no_forbidden_terms(report)
    return report


def _build_record_rows(records: list[dict], inventory_examples: list[dict]) -> list[dict[str, Any]]:
    warnings_by_index = _warnings_by_index(inventory_examples)
    rows = []
    for index, record in enumerate(records):
        warnings = warnings_by_index.get(index, [])
        normalized = _safe_normalize(record, index)
        action = _recommended_action(warnings, normalized)
        risk_level = _risk_level(warnings, action)
        rows.append(
            {
                "index": index,
                "legacy_snapshot_id": _text(normalized.get("legacy_snapshot_id")),
                "display_name": _text(normalized.get("display_name")),
                "recommended_action": action,
                "risk_level": risk_level,
                "warnings": warnings,
            }
        )
    return rows


def _warnings_by_index(example_records: list[dict]) -> dict[int, list[str]]:
    warnings_by_index = {}
    for row in example_records:
        if not isinstance(row, Mapping):
            continue
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        warnings = row.get("warnings")
        warnings_by_index[index] = _safe_strings(warnings)
    return warnings_by_index


def _safe_normalize(record: dict, index: int) -> dict[str, Any]:
    try:
        normalized = normalize_legacy_snapshot(record)
    except Exception:
        return {
            "legacy_snapshot_id": "",
            "display_name": f"Legacy Snapshot {index + 1}",
            "sequence": "",
            "has_historical_validation": False,
            "has_primer_snapshot": False,
        }
    return normalized if isinstance(normalized, Mapping) else {}


def _recommended_action(warnings: list[str], normalized: Mapping[str, Any]) -> str:
    warning_set = set(warnings)
    if MISSING_SEQUENCE_WARNING in warning_set:
        return MISSING_REQUIRED_DATA
    if warning_set & _HIGH_RISK_WARNINGS:
        return DO_NOT_MIGRATE_AUTOMATICALLY
    if warning_set & _DUPLICATE_WARNINGS:
        return NEEDS_REVIEW
    if normalized.get("has_historical_validation") or normalized.get("has_primer_snapshot"):
        return NEEDS_REVIEW
    if warnings:
        return NEEDS_REVIEW
    return READ_ONLY_COMPATIBLE


def _risk_level(warnings: list[str], action: str) -> str:
    warning_set = set(warnings)
    if action in {MISSING_REQUIRED_DATA, DO_NOT_MIGRATE_AUTOMATICALLY}:
        return "high"
    if warning_set & _HIGH_RISK_WARNINGS:
        return "high"
    meaningful_warnings = [warning for warning in warnings if not _helper_warning(warning)]
    if action == NEEDS_REVIEW or meaningful_warnings:
        return "medium"
    return "low"


def _build_duplicate_groups(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    names = Counter(row["display_name"] for row in rows if row.get("display_name"))
    ids = Counter(row["legacy_snapshot_id"] for row in rows if row.get("legacy_snapshot_id"))
    return {
        "display_name": sorted(name for name, count in names.items() if count > 1),
        "legacy_snapshot_id": sorted(snapshot_id for snapshot_id, count in ids.items() if count > 1),
    }


def _action_counts(rows: list[dict[str, Any]]) -> Counter:
    counts = Counter({action: 0 for action in _ALLOWED_ACTIONS})
    counts.update(row["recommended_action"] for row in rows)
    return counts


def _risk_counts(rows: list[dict[str, Any]]) -> Counter:
    counts = Counter({"high": 0, "medium": 0, "low": 0})
    counts.update(row["risk_level"] for row in rows)
    return counts


def _example_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["warnings"] or row["recommended_action"] != READ_ONLY_COMPATIBLE][:5]


def _safe_strings(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value if str(item)]
    return []


def _text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _helper_warning(warning: str) -> bool:
    return any(warning.startswith(prefix) for prefix in _HELPER_WARNING_PREFIXES)


def _assert_allowed_actions(report: Mapping[str, Any]) -> None:
    summary = report.get("recommended_actions_summary")
    if isinstance(summary, Mapping):
        actions = set(summary.keys())
        if not actions <= _ALLOWED_ACTIONS:
            raise ValueError("Migration dry-run report emitted an unsupported recommended action.")
    for row in report.get("example_records", []):
        if isinstance(row, Mapping) and row.get("recommended_action") not in _ALLOWED_ACTIONS:
            raise ValueError("Migration dry-run report emitted an unsupported record action.")


def _assert_no_forbidden_terms(value: Any) -> None:
    combined = str(value)
    for forbidden_term in FORBIDDEN_READINESS_TERMS:
        if forbidden_term in combined:
            raise ValueError("Migration dry-run report emitted a forbidden readiness or certification term.")
