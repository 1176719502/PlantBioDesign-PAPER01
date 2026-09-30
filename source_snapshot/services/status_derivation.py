"""Display-only status helpers for saved snapshot records.

This module is intentionally non-authoritative. It does not derive readiness,
validation freshness, certification, or experiment readiness. Expression Wizard
Step 6 remains the current documentation export review checkpoint.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

SNAPSHOT_SAVED_LABEL = "Snapshot Saved"
LOADED_SNAPSHOT_LABEL = "Loaded Snapshot"
SNAPSHOT_RECORD_LABEL = "Snapshot Record"
SAVED_SNAPSHOT_NOTE = "Saved snapshot only; not validation or readiness."
HISTORICAL_VALIDATION_NOTE = "Prior validation data may be historical."
STEP_6_REVIEW_NOTE = "Use Expression Wizard Step 6 for current documentation export review."

BLOCKED_NON_AUTHORITATIVE_TERMS = frozenset(
    {
        "Ready for Export",
        "Validated",
        "Certified",
        "Experiment-ready",
        "Current Validation",
    }
)

_VALIDATION_LIKE_KEYS = frozenset(
    {
        "validation_results",
        "validation_result",
        "validation_summary",
        "validation_issues",
        "validation_warnings",
        "readiness_reasons",
        "readiness_status",
        "n_issues",
        "issue_count",
    }
)


def normalize_snapshot_status(raw_status: object) -> str:
    """Normalize saved-record status to a safe display-only snapshot label.

    Unknown values are mapped to ``Snapshot Record`` instead of echoing raw text.
    This avoids accidentally displaying authoritative wording from legacy or
    user-controlled data while still communicating that a saved record exists.
    """
    normalized = str(raw_status or "").strip().lower()
    if normalized in {"", "saved"}:
        return SNAPSHOT_SAVED_LABEL
    return SNAPSHOT_RECORD_LABEL


def derive_loaded_snapshot_label(is_loaded: bool) -> str | None:
    """Return a loaded-snapshot display label without inferring validation."""
    return LOADED_SNAPSHOT_LABEL if is_loaded else None


def has_historical_validation_data(record: dict) -> bool:
    """Detect validation-like snapshot data without judging freshness or readiness."""
    if not isinstance(record, Mapping):
        return False

    snapshot = deepcopy(dict(record))
    for key in _VALIDATION_LIKE_KEYS:
        if _contains_meaningful_value(snapshot.get(key)):
            return True

    summary = snapshot.get("summary")
    if isinstance(summary, Mapping):
        for key in _VALIDATION_LIKE_KEYS:
            if _contains_meaningful_value(summary.get(key)):
                return True

    metadata = snapshot.get("metadata")
    if isinstance(metadata, Mapping):
        for key in _VALIDATION_LIKE_KEYS:
            if _contains_meaningful_value(metadata.get(key)):
                return True

    return False


def derive_safe_status_notes(record: dict) -> list[str]:
    """Return non-authoritative explanatory notes for snapshot records."""
    notes = [SAVED_SNAPSHOT_NOTE]
    if has_historical_validation_data(record):
        notes.append(HISTORICAL_VALIDATION_NOTE)
    notes.append(STEP_6_REVIEW_NOTE)
    return notes


def _contains_meaningful_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return bool(value)
    if isinstance(value, (int, float)):
        return value > 0
    return bool(value)
