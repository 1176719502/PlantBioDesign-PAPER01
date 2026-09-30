from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


PLANT_SEED_DATASET_GATE_SCHEMA_VERSION = "plant_seed_dataset_gate_registry.v2.7.r141"
PLANT_SEED_DATASET_GATE_BATCH = "v2.7-r141"

GATE_STATUS_READY_FOR_SEED_CONVERSION = "ready_for_seed_conversion"
GATE_STATUS_NEEDS_MORE_MANUAL_REVIEW = "needs_more_manual_review"
GATE_STATUS_BLOCKED_BEFORE_SEED_CONVERSION = "blocked_before_seed_conversion"

SUPPORTED_GATE_STATUSES: tuple[str, ...] = (
    GATE_STATUS_READY_FOR_SEED_CONVERSION,
    GATE_STATUS_NEEDS_MORE_MANUAL_REVIEW,
    GATE_STATUS_BLOCKED_BEFORE_SEED_CONVERSION,
)

ARTEMISIA_ANNUA_GATE_RECORD: dict[str, Any] = {
    "dataset_key": "artemisia_annua",
    "dataset_label": "Artemisia annua candidate gate",
    "plant_scope": (
        "Plant-only Artemisia annua documentation candidate from external review material; "
        "not an active seed dataset profile."
    ),
    "gate_status": GATE_STATUS_BLOCKED_BEFORE_SEED_CONVERSION,
    "conversion_allowed": False,
    "active_dataset_profile": False,
    "blocked_reasons": [
        "component identifiers missing",
        "evidence candidate 007 excluded",
        "evidence candidate 005 unresolved",
        "evidence candidate 006 background-only / cross-reference blocked",
        "missing PMCID gaps",
        "unresolved route/component/evidence cross-references",
        "route/evidence-only seed conversion not currently allowed",
    ],
    "manual_review_required": True,
    "required_next_actions": [
        "Resolve component identifiers or retain explicit placeholder/gap records.",
        "Resolve evidence candidate 005 with source-scope manual review.",
        "Keep evidence candidate 007 excluded unless a later manual gate reverses the exclusion.",
        "Reconcile regulatory-context links around evidence candidate 006.",
        "Close PMCID gaps for retained evidence candidates.",
        "Reconcile retained route, component, and evidence links before any seed conversion.",
        "Keep route/evidence-only seed conversion blocked under the current policy.",
    ],
    "source_review_summary": (
        "R140 kept the Artemisia annua pack external, plant-only, documentation-only, "
        "and manual-review-required after down-select, boundary review, component identifier "
        "review, and evidence source verification."
    ),
    "component_identifier_summary": (
        "Six reviewed component/module candidates still lack verified gene IDs, protein "
        "accessions, nucleotide accessions, and versioned database identifiers."
    ),
    "evidence_boundary_summary": (
        "Evidence candidate 007 remains excluded; evidence candidate 005 remains unresolved; "
        "evidence candidate 006 remains background/context-only and cross-reference blocked."
    ),
    "cross_reference_gap_summary": (
        "Route, component, and evidence links are not reconciled enough for seed conversion, "
        "especially around the regulatory-context cluster."
    ),
    "documentation_boundary": (
        "Read-only gate readback. This is not an active seed dataset profile, accepted evidence, "
        "component choice, route guidance, experiment confirmation, output forecast, or "
        "downstream-use judgment."
    ),
}

PLANT_SEED_DATASET_GATE_REGISTRY: dict[str, dict[str, Any]] = {
    ARTEMISIA_ANNUA_GATE_RECORD["dataset_key"]: ARTEMISIA_ANNUA_GATE_RECORD,
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _unknown_gate_record(dataset_key: str) -> dict[str, Any]:
    clean_key = _text(dataset_key, "unknown_dataset")
    return {
        "dataset_key": clean_key,
        "dataset_label": clean_key,
        "plant_scope": "Unknown plant seed dataset candidate.",
        "gate_status": GATE_STATUS_BLOCKED_BEFORE_SEED_CONVERSION,
        "conversion_allowed": False,
        "active_dataset_profile": False,
        "blocked_reasons": [
            "dataset gate record is not registered",
            "seed conversion is blocked until manual review creates an explicit gate record",
            "route/evidence-only seed conversion not currently allowed",
        ],
        "manual_review_required": True,
        "required_next_actions": [
            "Create a manual gate review record before any seed conversion.",
            "Keep the candidate out of active dispatcher dataset profiles.",
        ],
        "source_review_summary": "No registered source review summary is available for this dataset key.",
        "component_identifier_summary": "No component identifier summary is available for this dataset key.",
        "evidence_boundary_summary": "No evidence boundary summary is available for this dataset key.",
        "cross_reference_gap_summary": "No route/component/evidence cross-reference summary is available.",
        "documentation_boundary": (
            "Fail-closed read-only gate readback. Unknown dataset keys are not active seed "
            "dataset profiles and cannot be converted without manual review."
        ),
    }


def get_plant_seed_dataset_gate_record(dataset_key: str) -> dict[str, Any]:
    """Return a plain fail-closed dataset gate record."""
    key = _text(dataset_key).casefold()
    record = PLANT_SEED_DATASET_GATE_REGISTRY.get(key)
    if record is None:
        record = _unknown_gate_record(dataset_key)
    return _plain_value(
        {
            "gate_schema_version": PLANT_SEED_DATASET_GATE_SCHEMA_VERSION,
            "gate_batch": PLANT_SEED_DATASET_GATE_BATCH,
            "supported_gate_statuses": list(SUPPORTED_GATE_STATUSES),
            **record,
            "read_only": True,
            "plant_scope_only": True,
        }
    )


def list_plant_seed_dataset_gate_records() -> list[dict[str, Any]]:
    """Return all registered plant seed dataset gate records as plain payloads."""
    return [
        get_plant_seed_dataset_gate_record(key)
        for key in sorted(PLANT_SEED_DATASET_GATE_REGISTRY, key=str.casefold)
    ]


def build_plant_seed_dataset_gate_readback_rows(dataset_key: str | None = None) -> list[dict[str, Any]]:
    """Return UI/report-safe readback rows for one gate record or all registered records."""
    records = (
        [get_plant_seed_dataset_gate_record(dataset_key)]
        if dataset_key is not None
        else list_plant_seed_dataset_gate_records()
    )
    rows: list[dict[str, Any]] = []
    for record in records:
        boundary = _text(record.get("documentation_boundary"))
        for field, readback in (
            ("Gate status", record.get("gate_status")),
            ("Conversion allowed", "false" if record.get("conversion_allowed") is False else "true"),
            ("Active dataset profile", "false" if record.get("active_dataset_profile") is False else "true"),
            ("Manual review", "required" if record.get("manual_review_required") else "not required"),
            ("Blocked reasons", "; ".join(_plain_value(record.get("blocked_reasons", [])))),
            ("Required next actions", "; ".join(_plain_value(record.get("required_next_actions", [])))),
            ("Source review", record.get("source_review_summary")),
            ("Component identifiers", record.get("component_identifier_summary")),
            ("Evidence boundary", record.get("evidence_boundary_summary")),
            ("Cross-reference gaps", record.get("cross_reference_gap_summary")),
        ):
            rows.append(
                _plain_value(
                    {
                        "dataset_key": record["dataset_key"],
                        "dataset_label": record["dataset_label"],
                        "field": field,
                        "readback": _text(readback),
                        "gate_status": record["gate_status"],
                        "conversion_allowed": record["conversion_allowed"],
                        "active_dataset_profile": record["active_dataset_profile"],
                        "manual_review_required": record["manual_review_required"],
                        "documentation_boundary": boundary,
                    }
                )
            )
    return rows
