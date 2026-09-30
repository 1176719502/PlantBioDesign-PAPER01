from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.plant_evidence_review_worksheet_presenter import (
    build_followup_queue_filter_view,
    build_plant_evidence_review_worksheet_payload,
)
from services.plant_evidence_seed_intake import (
    DEFAULT_RICE_ALBUMIN_SEED_DIR,
    SEED_INTAKE_BATCH,
    build_r118_evidence_worksheet_input,
    build_r128_traceability_input,
    load_plant_evidence_seed_intake,
)
from services.plant_review_handoff_data_adapter import build_plant_review_handoff_payload
from services.plant_route_construct_traceability_readback import (
    build_plant_route_construct_traceability_readback,
)


PLANT_SEED_REVIEW_DISPATCHER_SCHEMA_VERSION = "plant_seed_review_workflow.v2.7.r138"
PLANT_SEED_REVIEW_DISPATCHER_BATCH = "v2.7-r138"
PLANT_SEED_REVIEW_STATUS_UNSUPPORTED_DATASET = "plant_seed_review_workflow_unsupported_dataset"
PLANT_SEED_REVIEW_STATUS_EMPTY = "plant_seed_review_workflow_empty"


@dataclass(frozen=True)
class PlantSeedReviewDataset:
    dataset_key: str
    seed_dir: Path
    workflow_schema_version: str
    workflow_batch: str
    workflow_status_ready: str
    workflow_status_empty: str
    workflow_boundary_note: str
    visible_mount_schema_version: str
    visible_mount_batch: str
    visible_mount_boundary_note: str
    handoff_package_id: str
    handoff_source_surface: str
    route_fallback_id: str
    empty_state: str


RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_SCHEMA_VERSION = "rice_albumin_seed_review_workflow.v2.7.r133"
RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_BATCH = "v2.7-r133"
RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_STATUS_READY = "rice_albumin_seed_review_workflow_ready"
RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_STATUS_EMPTY = "rice_albumin_seed_review_workflow_empty"
RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_SCHEMA_VERSION = "rice_albumin_seed_review_visible_mount.v2.7.r134"
RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_BATCH = "v2.7-r134"

RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_BOUNDARY_NOTE = (
    "Read-only rice albumin seed-to-review workflow wiring. It loads local seed records "
    "and reuses existing documentation-review presenters without accepting evidence, "
    "choosing components, approving constructs, producing route improvement guidance, "
    "claiming experimental confirmation, or judging downstream use."
)

RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_BOUNDARY_NOTE = (
    "Local seed-data review mount for documentation-only manual review. It shows the R133 rice "
    "albumin seed-to-review payload, provenance gaps, rejected seed rows, worksheet follow-up, "
    "and traceability readback without accepting evidence, choosing components, confirming "
    "constructs, producing route improvement guidance, or judging downstream use."
)

RICE_ALBUMIN_DATASET = PlantSeedReviewDataset(
    dataset_key="rice_albumin",
    seed_dir=DEFAULT_RICE_ALBUMIN_SEED_DIR,
    workflow_schema_version=RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_SCHEMA_VERSION,
    workflow_batch=RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_BATCH,
    workflow_status_ready=RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_STATUS_READY,
    workflow_status_empty=RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_STATUS_EMPTY,
    workflow_boundary_note=RICE_ALBUMIN_SEED_REVIEW_WORKFLOW_BOUNDARY_NOTE,
    visible_mount_schema_version=RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_SCHEMA_VERSION,
    visible_mount_batch=RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_BATCH,
    visible_mount_boundary_note=RICE_ALBUMIN_SEED_REVIEW_VISIBLE_MOUNT_BOUNDARY_NOTE,
    handoff_package_id="r133-rice-albumin-seed-review-readback",
    handoff_source_surface="rice_albumin_seed_review_workflow",
    route_fallback_id="rice_albumin_seed_route_context",
    empty_state=(
        "No readable rice albumin seed review rows are available. The surface remains "
        "read-only and needs manual review."
    ),
)

PLANT_SEED_REVIEW_DATASETS: dict[str, PlantSeedReviewDataset] = {
    RICE_ALBUMIN_DATASET.dataset_key: RICE_ALBUMIN_DATASET,
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


def _dataset_profile(dataset_key: str) -> PlantSeedReviewDataset | None:
    return PLANT_SEED_REVIEW_DATASETS.get(_text(dataset_key).casefold())


def _workflow_status(
    dataset: PlantSeedReviewDataset,
    seed_payload: Mapping[str, Any],
    worksheet: Mapping[str, Any],
    traceability: Mapping[str, Any],
) -> str:
    seed_records = _sequence(seed_payload.get("records"))
    worksheet_rows = _sequence(_mapping(worksheet.get("evidence_review_section")).get("rows"))
    trace_rows = _sequence(_mapping(traceability.get("traceability_section")).get("rows"))
    if seed_records or worksheet_rows or trace_rows:
        return dataset.workflow_status_ready
    return dataset.workflow_status_empty


def _empty_unsupported_dataset_payload(dataset_key: str) -> dict[str, Any]:
    dataset_label = _text(dataset_key, "not recorded")
    return _plain_value(
        {
            "workflow_schema_version": PLANT_SEED_REVIEW_DISPATCHER_SCHEMA_VERSION,
            "workflow_batch": PLANT_SEED_REVIEW_DISPATCHER_BATCH,
            "workflow_status": PLANT_SEED_REVIEW_STATUS_UNSUPPORTED_DATASET,
            "read_only": True,
            "plant_scope_only": True,
            "manual_review_required": True,
            "documentation_only_boundary": (
                "Read-only plant seed review dispatcher. Unsupported dataset keys are not loaded; "
                "manual review remains required."
            ),
            "reuse_sources": [
                "services.plant_evidence_seed_intake",
                "services.plant_evidence_review_worksheet_presenter",
                "services.plant_route_construct_traceability_readback",
                "services.plant_review_handoff_data_adapter",
            ],
            "seed_intake": {
                "seed_intake_status": PLANT_SEED_REVIEW_STATUS_UNSUPPORTED_DATASET,
                "read_only": True,
                "plant_scope_only": True,
                "manual_review_required": True,
                "summary": {
                    "total_records": 0,
                    "gap_record_count": 0,
                    "rejected_row_count": 0,
                },
                "records": [],
                "gap_records": [],
                "rejected_rows": [],
                "warnings": [f"Unsupported plant seed review dataset key: {dataset_label}"],
            },
            "evidence_worksheet": build_plant_evidence_review_worksheet_payload(),
            "followup_queue_view": build_followup_queue_filter_view({"rows": []}),
            "route_construct_traceability": build_plant_route_construct_traceability_readback(),
            "handoff_readback": {
                "handoff_status": "manual_review_required",
                "manual_review_required": True,
                "required_review_items": [],
                "missing_information_items": [],
                "evidence_traceability_items": [],
                "component_traceability_items": [],
                "evidence_worksheet_handoff_readback": {},
                "route_construct_traceability_readback": {},
                "source_traceability": {},
                "warnings": [f"Unsupported plant seed review dataset key: {dataset_label}"],
            },
            "summary": {
                "seed_record_count": 0,
                "seed_gap_record_count": 0,
                "worksheet_evidence_row_count": 0,
                "worksheet_component_slot_row_count": 0,
                "worksheet_followup_queue_count": 0,
                "traceability_row_count": 0,
                "handoff_required_review_item_count": 0,
            },
            "warnings": [f"Unsupported plant seed review dataset key: {dataset_label}"],
        }
    )


def _handoff_source_payload(
    *,
    dataset: PlantSeedReviewDataset,
    seed_payload: Mapping[str, Any],
    worksheet_input: Mapping[str, Any],
    worksheet: Mapping[str, Any],
) -> dict[str, Any]:
    route_context = _mapping(worksheet_input.get("route_context"))
    review_items = _sequence(worksheet_input.get("review_items"))
    evidence_ids = [
        _text(row.get("evidence_item_id") or row.get("record_id"))
        for row in _sequence(_mapping(worksheet.get("evidence_review_section")).get("rows"))
        if isinstance(row, Mapping) and _text(row.get("evidence_item_id") or row.get("record_id"))
    ]
    component_ids = [
        _text(row.get("linked_component_id") or row.get("component_id"))
        for row in _sequence(_mapping(worksheet.get("component_slot_linkage_section")).get("rows"))
        if isinstance(row, Mapping) and _text(row.get("linked_component_id") or row.get("component_id"))
    ]
    route_id = _text(route_context.get("route_id"), dataset.route_fallback_id)
    return _plain_value(
        {
            "route_context": route_context,
            "evidence_placeholders": _sequence(worksheet_input.get("evidence_placeholders")),
            "component_slots": _sequence(worksheet_input.get("component_slots")),
            "review_items": review_items,
            "plant_evidence_review_worksheet": worksheet,
            "readback_presenter": {
                "package_header": {
                    "package_id": dataset.handoff_package_id,
                    "package_status": "manual_review_required",
                    "package_type": "documentation_review_readback",
                    "route_id": route_id,
                    "manual_review_required": True,
                },
                "review_queue_section": {"rows": review_items},
                "traceability_section": {
                    "route_ids": [route_id],
                    "evidence_ids": evidence_ids,
                    "component_ids": component_ids,
                },
            },
            "seed_intake_status": _text(seed_payload.get("seed_intake_status")),
            "manual_review_required": True,
        }
    )


def _handoff_readback_view(handoff_payload: Mapping[str, Any]) -> dict[str, Any]:
    return _plain_value(
        {
            "handoff_schema_version": _text(handoff_payload.get("handoff_schema_version")),
            "handoff_status": _text(handoff_payload.get("handoff_status"), "manual_review_required"),
            "manual_review_required": handoff_payload.get("manual_review_required") is not False,
            "required_review_items": _sequence(handoff_payload.get("required_review_items")),
            "missing_information_items": _sequence(handoff_payload.get("missing_information_items")),
            "evidence_traceability_items": _sequence(handoff_payload.get("evidence_traceability_items")),
            "component_traceability_items": _sequence(handoff_payload.get("component_traceability_items")),
            "evidence_worksheet_handoff_readback": _mapping(
                handoff_payload.get("evidence_worksheet_handoff_readback")
            ),
            "route_construct_traceability_readback": _mapping(
                handoff_payload.get("route_construct_traceability_readback")
            ),
            "source_traceability": _mapping(handoff_payload.get("source_traceability")),
            "warnings": _sequence(handoff_payload.get("warnings")),
        }
    )


def _seed_summary_rows(seed_payload: Mapping[str, Any], workflow_summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    seed_summary = _mapping(seed_payload.get("summary"))
    return [
        {"Field": "Mount type", "Readback": "local seed-data review"},
        {"Field": "Documentation boundary", "Readback": "documentation-only"},
        {"Field": "Manual review", "Readback": "needs manual review"},
        {"Field": "Seed intake status", "Readback": _text(seed_payload.get("seed_intake_status"))},
        {"Field": "Seed records", "Readback": str(seed_summary.get("total_records", 0))},
        {"Field": "Provenance gaps", "Readback": str(seed_summary.get("gap_record_count", 0))},
        {"Field": "Rejected seed rows", "Readback": str(seed_summary.get("rejected_row_count", 0))},
        {"Field": "Worksheet evidence rows", "Readback": str(workflow_summary.get("worksheet_evidence_row_count", 0))},
        {"Field": "Worksheet follow-up rows", "Readback": str(workflow_summary.get("worksheet_followup_queue_count", 0))},
        {"Field": "Traceability rows", "Readback": str(workflow_summary.get("traceability_row_count", 0))},
    ]


def _seed_record_rows(seed_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in _sequence(seed_payload.get("records")):
        if not isinstance(record, Mapping):
            continue
        rows.append(
            {
                "record_id": _text(record.get("record_id")),
                "record_type": _text(record.get("record_type")),
                "route_or_context_id": _text(
                    record.get("route_template_id") or record.get("target_or_route"),
                    "not recorded",
                ),
                "component_or_context_id": _text(
                    record.get("linked_component") or record.get("slot_id") or record.get("record_id"),
                    "not recorded",
                ),
                "evidence_ids": _sequence(record.get("linked_evidence_ids")),
                "review_status": _text(record.get("review_status"), "needs_manual_review"),
                "provenance_status": _text(record.get("provenance_status"), "missing"),
                "gap_fields": _sequence(record.get("gap_fields")),
                "manual_review_note": _text(record.get("manual_review_note"), "manual review required"),
            }
        )
    return rows


def _rejected_seed_rows(seed_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rejected in _sequence(seed_payload.get("rejected_rows")):
        if not isinstance(rejected, Mapping):
            continue
        rows.append(
            {
                "record_id": _text(rejected.get("record_id")),
                "record_type": _text(rejected.get("record_type"), "RejectedSeedRecord"),
                "source_file": _text(rejected.get("source_file")),
                "row_index": rejected.get("row_index", 0),
                "rejection_reason": _text(rejected.get("rejection_reason"), "seed row rejected"),
                "review_status": _text(rejected.get("review_status"), "needs_manual_review"),
                "provenance_status": _text(rejected.get("provenance_status"), "malformed"),
                "manual_review_note": _text(rejected.get("manual_review_note"), "manual review required"),
            }
        )
    return rows


def build_plant_seed_review_visible_mount(
    workflow_payload: Mapping[str, Any] | None = None,
    *,
    dataset_key: str = "rice_albumin",
    seed_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return a UI-ready read-only plant seed review mount payload."""
    dataset = _dataset_profile(dataset_key)
    source = _mapping(workflow_payload) or build_plant_seed_review_workflow(
        dataset_key=dataset_key,
        seed_path=seed_path,
    )
    seed_payload = _mapping(source.get("seed_intake"))
    summary = _mapping(source.get("summary"))
    visible_schema = dataset.visible_mount_schema_version if dataset else PLANT_SEED_REVIEW_DISPATCHER_SCHEMA_VERSION
    visible_batch = dataset.visible_mount_batch if dataset else PLANT_SEED_REVIEW_DISPATCHER_BATCH
    boundary_note = dataset.visible_mount_boundary_note if dataset else _text(source.get("documentation_only_boundary"))
    empty_state = dataset.empty_state if dataset else "No readable plant seed review rows are available."
    return _plain_value(
        {
            "visible_mount_schema_version": visible_schema,
            "visible_mount_batch": visible_batch,
            "visible_mount_status": _text(source.get("workflow_status"), PLANT_SEED_REVIEW_STATUS_EMPTY),
            "read_only": True,
            "plant_scope_only": True,
            "manual_review_required": True,
            "mount_label": "local seed-data review",
            "documentation_only_boundary": boundary_note,
            "summary_rows": _seed_summary_rows(seed_payload, summary),
            "seed_record_rows": _seed_record_rows(seed_payload),
            "rejected_seed_rows": _rejected_seed_rows(seed_payload),
            "evidence_worksheet": _mapping(source.get("evidence_worksheet")),
            "followup_queue_view": _mapping(source.get("followup_queue_view")),
            "route_construct_traceability": _mapping(source.get("route_construct_traceability")),
            "handoff_readback": _mapping(source.get("handoff_readback")),
            "warnings": _sequence(source.get("warnings")) + _sequence(seed_payload.get("warnings")),
            "empty_state": empty_state,
        }
    )


def build_plant_seed_review_workflow(
    *,
    dataset_key: str = "rice_albumin",
    seed_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load a supported local plant seed dataset into the existing review readback chain."""
    dataset = _dataset_profile(dataset_key)
    if dataset is None:
        return _empty_unsupported_dataset_payload(dataset_key)

    seed_dir = Path(seed_path) if seed_path is not None else dataset.seed_dir
    seed_payload = load_plant_evidence_seed_intake(seed_dir)
    worksheet_input = _mapping(seed_payload.get("r118_worksheet_input")) or build_r118_evidence_worksheet_input(seed_payload)
    worksheet = build_plant_evidence_review_worksheet_payload(**worksheet_input)
    followup_view = build_followup_queue_filter_view(worksheet.get("followup_queue_section"))
    traceability_input = _mapping(seed_payload.get("r128_traceability_input")) or build_r128_traceability_input(seed_payload)
    traceability = build_plant_route_construct_traceability_readback(
        **traceability_input,
        evidence_worksheet=worksheet,
    )
    handoff_payload = build_plant_review_handoff_payload(
        _handoff_source_payload(
            dataset=dataset,
            seed_payload=seed_payload,
            worksheet_input=worksheet_input,
            worksheet=worksheet,
        ),
        {
            "source_batch": dataset.workflow_batch,
            "source_surface": dataset.handoff_source_surface,
            "seed_intake_batch": SEED_INTAKE_BATCH,
        },
    )

    return _plain_value(
        {
            "workflow_schema_version": dataset.workflow_schema_version,
            "workflow_batch": dataset.workflow_batch,
            "workflow_status": _workflow_status(dataset, seed_payload, worksheet, traceability),
            "read_only": True,
            "plant_scope_only": True,
            "manual_review_required": True,
            "documentation_only_boundary": dataset.workflow_boundary_note,
            "reuse_sources": [
                "services.plant_evidence_seed_intake",
                "services.plant_evidence_review_worksheet_presenter",
                "services.plant_route_construct_traceability_readback",
                "services.plant_review_handoff_data_adapter",
            ],
            "seed_intake": seed_payload,
            "evidence_worksheet": worksheet,
            "followup_queue_view": followup_view,
            "route_construct_traceability": traceability,
            "handoff_readback": _handoff_readback_view(handoff_payload),
            "summary": {
                "seed_record_count": int(_mapping(seed_payload.get("summary")).get("total_records") or 0),
                "seed_gap_record_count": int(_mapping(seed_payload.get("summary")).get("gap_record_count") or 0),
                "worksheet_evidence_row_count": int(_mapping(worksheet.get("summary")).get("evidence_row_count") or 0),
                "worksheet_component_slot_row_count": int(
                    _mapping(worksheet.get("summary")).get("component_slot_row_count") or 0
                ),
                "worksheet_followup_queue_count": int(
                    _mapping(worksheet.get("summary")).get("followup_queue_count") or 0
                ),
                "traceability_row_count": int(_mapping(traceability.get("summary")).get("trace_row_count") or 0),
                "handoff_required_review_item_count": len(_sequence(handoff_payload.get("required_review_items"))),
            },
        }
    )
