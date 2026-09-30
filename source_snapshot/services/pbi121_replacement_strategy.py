"""Persisted, non-editable pBI121 exact-replacement strategy records."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import ensure_biodesign_runtime_dir
from core.pbi121_replacement_contract import (
    Pbi121ReplacementContractError,
    replacement_contract,
    validate_pbi121_source,
)
from services.real_genbank_asset_import import PBI121_ACCESSION, build_pbi121_asset_bundle


STRATEGY_SCHEMA_VERSION = "pbi121-replacement-strategy-v2"
LEGACY_STRATEGY_SCHEMA_VERSION = "pbi121-replacement-strategy-v1"
STRATEGY_FILE_NAME = "pbi121_replacement_strategy.json"
FIXED_STRATEGY_ID = "pbi121-af485783.1-exact-replacement-v1"


class Pbi121ReplacementStrategyError(ValueError):
    """Raised when a persisted strategy differs from the fixed contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _strategy_path(runtime_root: Path | None = None) -> Path:
    root = runtime_root or ensure_biodesign_runtime_dir()
    return root / STRATEGY_FILE_NAME


def source_audit() -> dict[str, Any]:
    return build_pbi121_asset_bundle()["audit"]


def _feature_by_id(audit: dict[str, Any], feature_id: str) -> dict[str, Any] | None:
    return next((row for row in audit["features"] if row["feature_id"] == feature_id), None)


def _feature_spans(feature: dict[str, Any], length: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for part in feature.get("location_parts") or []:
        start = int(part.get("start_zero_based") or 0)
        end = int(part.get("end_zero_based_exclusive") or 0)
        if 0 <= start < end <= length:
            spans.append((start, end))
    return spans


def interval_spans(start: int, end: int, length: int) -> list[tuple[int, int]]:
    """Convert a 1-based inclusive circular interval to 0-based half-open spans."""
    if length <= 0 or start < 1 or end < 1 or start > length or end > length:
        raise Pbi121ReplacementStrategyError("Replacement coordinates are outside the source record.")
    if start == end + 1:
        raise Pbi121ReplacementStrategyError("Replacement interval length must be greater than zero.")
    zero_start, zero_end = start - 1, end
    return [(zero_start, zero_end)] if start <= end else [(zero_start, length), (0, zero_end)]


def _contains(container: list[tuple[int, int]], candidate: list[tuple[int, int]]) -> bool:
    return all(any(left <= start and end <= right for left, right in container) for start, end in candidate)


def _overlaps(first: list[tuple[int, int]], second: list[tuple[int, int]]) -> bool:
    return any(a_start < b_end and b_start < a_end for a_start, a_end in first for b_start, b_end in second)


def classify_features(
    audit: dict[str, Any], *, replacement_start: int, replacement_end: int, protected_feature_ids: set[str]
) -> list[dict[str, Any]]:
    replacement = interval_spans(replacement_start, replacement_end, int(audit["length"]))
    rows: list[dict[str, Any]] = []
    for feature in audit["features"]:
        spans = _feature_spans(feature, int(audit["length"]))
        feature_id = str(feature["feature_id"])
        if feature_id in protected_feature_ids:
            relationship = "protected"
        elif str(feature.get("type") or "") == "source":
            relationship = "retained"
        elif not spans:
            relationship = "needs_manual_review"
        elif _contains(replacement, spans):
            relationship = "removed"
        elif _overlaps(replacement, spans):
            relationship = "partially_overlapped"
        else:
            relationship = "retained"
        rows.append(
            {
                "feature_id": feature_id,
                "name": str(feature.get("name") or feature.get("type") or "unnamed feature"),
                "type": str(feature.get("type") or "misc_feature"),
                "location": str(feature.get("location_expression") or ""),
                "strand": feature.get("strand"),
                "relationship": relationship,
            }
        )
    return rows


def _border_ids(audit: dict[str, Any]) -> tuple[str, str]:
    left = next(str(row["feature_id"]) for row in audit["features"] if row["asset_type"] == "left_border")
    right = next(str(row["feature_id"]) for row in audit["features"] if row["asset_type"] == "right_border")
    return left, right


def _fixed_strategy(audit: dict[str, Any]) -> dict[str, Any]:
    contract = validate_pbi121_source(audit["sequence"], accession_version=audit["accession"])
    left, right = _border_ids(audit)
    rows = classify_features(
        audit,
        replacement_start=int(contract["replacement_start"]),
        replacement_end=int(contract["replacement_end"]),
        protected_feature_ids={left, right},
    )
    now = _utc_now()
    return {
        "schema_version": STRATEGY_SCHEMA_VERSION,
        "strategy_id": FIXED_STRATEGY_ID,
        "source_accession": audit["accession"],
        "source_record_sha256": audit["source_record_sha256"],
        "source_sequence_sha256": audit["sequence_sha256"],
        "source_asset_id": contract["asset_id"],
        "asset_kind": contract["asset_kind"],
        "strategy_status": "ready_for_construct_use",
        "strategy_origin": "system_fixed_contract",
        "editable": False,
        "confirmed_left_border": left,
        "confirmed_right_border": right,
        "t_dna_direction": "RB_to_LB",
        "target_t_dna_interval": {
            "start_one_based": 2479,
            "end_one_based": 8620,
            "crosses_origin": False,
            "coordinate_convention": "1-based-inclusive",
            "normalized_spans_zero_based_half_open": [(2478, 8620)],
        },
        "replacement_start": contract["replacement_start"],
        "replacement_end": contract["replacement_end"],
        "coordinate_system": contract["coordinate_system"],
        "normalized_replacement_span": [
            contract["normalized_replacement_start"],
            contract["normalized_replacement_end"],
        ],
        "replacement_length": contract["replacement_length"],
        "replacement_sha256": contract["replacement_sha256"],
        "replacement_mode": "replacement",
        "insertion_orientation": "forward",
        "insertion_orientation_relative_to_t_dna": "forward",
        "normalized_canonical_orientation": "forward",
        "retained_feature_ids": [row["feature_id"] for row in rows if row["relationship"] == "retained"],
        "removed_feature_ids": [row["feature_id"] for row in rows if row["relationship"] == "removed"],
        "partially_overlapped_feature_ids": [
            row["feature_id"] for row in rows if row["relationship"] == "partially_overlapped"
        ],
        "protected_feature_ids": [left, right],
        "reviewed_key_features": {"gus": True, "nptii": True},
        "feature_review_rows": rows,
        "replacement_contract": contract,
        "validation_blockers": [],
        "validation_warnings": [contract["warning_text"]],
        "manual_review_notes": "",
        "created_at": now,
        "updated_at": now,
    }


def evaluate_strategy(record: dict[str, Any], audit: dict[str, Any] | None = None) -> dict[str, Any]:
    audit = audit or source_audit()
    expected = _fixed_strategy(audit)
    result = copy.deepcopy(record)
    blockers: list[str] = []
    try:
        validate_pbi121_source(audit["sequence"], accession_version=audit["accession"])
    except Pbi121ReplacementContractError as exc:
        blockers.append(str(exc))

    exact_fields = (
        "source_accession",
        "source_record_sha256",
        "source_sequence_sha256",
        "source_asset_id",
        "asset_kind",
        "confirmed_left_border",
        "confirmed_right_border",
        "t_dna_direction",
        "replacement_start",
        "replacement_end",
        "coordinate_system",
        "normalized_replacement_span",
        "replacement_length",
        "replacement_sha256",
        "replacement_mode",
        "insertion_orientation",
        "insertion_orientation_relative_to_t_dna",
        "normalized_canonical_orientation",
        "reviewed_key_features",
    )
    is_legacy = result.get("schema_version") == LEGACY_STRATEGY_SCHEMA_VERSION
    for field in exact_fields:
        if is_legacy and field not in result:
            continue
        if result.get(field) != expected.get(field):
            blockers.append(f"The saved pBI121 strategy field '{field}' differs from the fixed replacement contract.")
    if result.get("replacement_contract") not in (None, expected["replacement_contract"]):
        blockers.append("The saved pBI121 replacement-contract snapshot differs from the fixed contract.")

    result.update(
        {
            key: copy.deepcopy(value)
            for key, value in expected.items()
            if key
            in {
                "schema_version",
                "strategy_id",
                "strategy_origin",
                "editable",
                "target_t_dna_interval",
                "retained_feature_ids",
                "removed_feature_ids",
                "partially_overlapped_feature_ids",
                "protected_feature_ids",
                "feature_review_rows",
                "replacement_contract",
                "validation_warnings",
            }
        }
    )
    if is_legacy:
        for field in exact_fields:
            result.setdefault(field, copy.deepcopy(expected[field]))
    result["validation_blockers"] = blockers
    result["strategy_status"] = "blocked" if blockers else "ready_for_construct_use"
    result.setdefault("created_at", expected["created_at"])
    result["updated_at"] = _utc_now()
    return result


def new_strategy() -> dict[str, Any]:
    return _fixed_strategy(source_audit())


def update_strategy(record: dict[str, Any], **changes: Any) -> dict[str, Any]:
    updated = copy.deepcopy(record)
    allowed = set(_fixed_strategy(source_audit())) | {"reviewed_key_features"}
    for key, value in changes.items():
        if key not in allowed:
            raise Pbi121ReplacementStrategyError(f"Unsupported replacement-strategy field: {key}")
        updated[key] = copy.deepcopy(value)
    return evaluate_strategy(updated)


def save_strategy(record: dict[str, Any], runtime_root: Path | None = None) -> dict[str, Any]:
    evaluated = evaluate_strategy(record)
    if evaluated["validation_blockers"]:
        raise Pbi121ReplacementStrategyError("; ".join(evaluated["validation_blockers"]))
    path = _strategy_path(runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(evaluated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    return evaluated


def load_strategy(runtime_root: Path | None = None) -> dict[str, Any]:
    path = _strategy_path(runtime_root)
    if not path.exists():
        return save_strategy(new_strategy(), runtime_root=runtime_root)
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Pbi121ReplacementStrategyError("The saved pBI121 replacement strategy cannot be read.") from exc
    if not isinstance(stored, dict) or stored.get("schema_version") not in {
        STRATEGY_SCHEMA_VERSION,
        LEGACY_STRATEGY_SCHEMA_VERSION,
    }:
        raise Pbi121ReplacementStrategyError("The saved pBI121 replacement strategy has an unsupported schema.")
    evaluated = evaluate_strategy(stored)
    if stored.get("schema_version") == LEGACY_STRATEGY_SCHEMA_VERSION and not evaluated["validation_blockers"]:
        return save_strategy(evaluated, runtime_root=runtime_root)
    return evaluated


def strategy_summary(runtime_root: Path | None = None) -> dict[str, Any]:
    try:
        record = load_strategy(runtime_root)
    except Pbi121ReplacementStrategyError as exc:
        return {
            "source_loaded": False,
            "strategy_exists": _strategy_path(runtime_root).exists(),
            "strategy_status": "blocked",
            "missing_conditions": [str(exc)],
            "ready_for_construct_use": False,
            "complete_plasmid_generated": False,
            "strategy_origin": "unreadable_record",
        }
    return {
        "source_loaded": record["source_accession"] == PBI121_ACCESSION,
        "strategy_exists": _strategy_path(runtime_root).exists(),
        "strategy_status": record["strategy_status"],
        "missing_conditions": list(record["validation_blockers"]),
        "ready_for_construct_use": record["strategy_status"] == "ready_for_construct_use",
        "complete_plasmid_generated": False,
        "strategy_origin": record["strategy_origin"],
        "replacement_contract": copy.deepcopy(record["replacement_contract"]),
    }
