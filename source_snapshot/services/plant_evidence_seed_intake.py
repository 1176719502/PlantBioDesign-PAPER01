from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SEED_INTAKE_SCHEMA_VERSION = "plant_evidence_seed_intake.v2.7.r132"
SEED_INTAKE_BATCH = "v2.7-r132"
SEED_INTAKE_STATUS_READY = "plant_evidence_seed_intake_loaded"
SEED_INTAKE_STATUS_GAPS_PRESENT = "plant_evidence_seed_intake_gaps_present"
SEED_INTAKE_STATUS_EMPTY = "plant_evidence_seed_intake_empty"

DEFAULT_RICE_ALBUMIN_SEED_DIR = (
    Path(__file__).resolve().parents[1] / "data" / "plant_seed" / "rice_albumin"
)

SEED_FILES: tuple[tuple[str, str], ...] = (
    ("route_contexts", "route_contexts.json"),
    ("component_records", "component_records.json"),
    ("evidence_records", "evidence_records.json"),
)

PRESERVED_FIELDS: tuple[str, ...] = (
    "record_id",
    "record_type",
    "target_or_route",
    "component_name",
    "linked_component",
    "component_type",
    "source_species",
    "source_type",
    "source_id",
    "evidence_type",
    "review_status",
    "provenance_status",
    "manual_review_note",
)

BOUNDARY_NOTE = (
    "Read-only local plant seed intake for documentation review. Seed rows remain candidate "
    "or review-required records and are not accepted evidence, component choices, construct "
    "approvals, or downstream-use instructions."
)


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


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_texts(value: Any) -> list[str]:
    raw_values: list[Any]
    if isinstance(value, str):
        raw_values = [item.strip() for item in value.replace("|", ",").replace(";", ",").split(",")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        raw_values = list(value)
    else:
        raw_values = [value] if _text(value) else []

    values: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        clean = _text(item)
        key = clean.casefold()
        if clean and key not in seen:
            values.append(clean)
            seen.add(key)
    return values


def _is_missing_value(value: Any) -> bool:
    return _text(value).casefold() in {"", "missing", "not recorded", "none", "null"}


def _review_required_status(value: Any) -> bool:
    key = _text(value).casefold().replace("-", "_").replace(" ", "_")
    return (
        not key
        or "needs_manual_review" in key
        or "manual_review" in key
        or "review_required" in key
        or key in {"missing", "partial", "candidate", "malformed"}
    )


def _safe_rejected_row(
    *,
    source_file: str,
    row_index: int,
    reason: str,
    raw_record: Any,
) -> dict[str, Any]:
    return {
        "record_id": f"r132-rejected-{Path(source_file).stem}-{row_index:03d}",
        "record_type": "RejectedSeedRecord",
        "target_or_route": "rice_albumin_seed_intake",
        "source_file": source_file,
        "row_index": row_index,
        "rejection_reason": reason,
        "raw_record": _plain_value(raw_record),
        "review_status": "needs_manual_review",
        "provenance_status": "malformed",
        "needs_manual_review": True,
        "manual_review_note": (
            "Seed row could not be used as a documentation review record; manual review is "
            "required before any downstream readback."
        ),
    }


def _normal_record(raw_record: Mapping[str, Any], *, source_file: str, row_index: int) -> dict[str, Any]:
    record = {field: _plain_value(raw_record.get(field, "")) for field in PRESERVED_FIELDS}
    record["source_file"] = source_file
    record["row_index"] = row_index
    record["slot_id"] = _plain_value(raw_record.get("slot_id", ""))
    record["linked_evidence_ids"] = _list_texts(raw_record.get("linked_evidence_ids"))
    record["route_template_id"] = _text(raw_record.get("route_template_id"))
    record["goal_type_id"] = _text(raw_record.get("goal_type_id"))
    record["label"] = _text(raw_record.get("label"))
    record["target_name"] = _text(raw_record.get("target_name"))
    record["plant_host"] = _text(raw_record.get("plant_host"))
    record["tissue_or_context"] = _text(raw_record.get("tissue_or_context"))
    record["plant_species"] = _text(raw_record.get("plant_species"))
    record["tissue_or_organ"] = _text(raw_record.get("tissue_or_organ"))
    record["expression_context"] = _text(raw_record.get("expression_context"))
    record["target_product_type"] = _text(raw_record.get("target_product_type"))
    record["source_or_provenance_placeholder"] = _source_or_provenance_placeholder(record)
    record["gap_fields"] = _gap_fields(record)
    record["needs_manual_review"] = (
        _review_required_status(record.get("review_status"))
        or _review_required_status(record.get("provenance_status"))
        or bool(record["gap_fields"])
    )
    return _plain_value(record)


def _source_or_provenance_placeholder(record: Mapping[str, Any]) -> str:
    source_type = _text(record.get("source_type"))
    source_id = _text(record.get("source_id"))
    provenance_status = _text(record.get("provenance_status"))
    if _is_missing_value(source_type) or _is_missing_value(source_id):
        return "source/provenance placeholder missing"
    parts = [source_type, source_id]
    if provenance_status:
        parts.append(f"provenance_status={provenance_status}")
    return "; ".join(parts)


def _gap_fields(record: Mapping[str, Any]) -> list[str]:
    gaps: list[str] = []
    for field in ("target_or_route", "source_species", "source_type", "source_id"):
        if _is_missing_value(record.get(field)):
            gaps.append(field)
    provenance_status = _text(record.get("provenance_status")).casefold()
    if provenance_status in {"", "missing", "partial", "candidate", "malformed"}:
        gaps.append(f"provenance_status:{provenance_status or 'missing'}")
    if _review_required_status(record.get("review_status")):
        gaps.append("review_status:needs_manual_review")
    return sorted(set(gaps), key=str.casefold)


def _gap_record(record: Mapping[str, Any]) -> dict[str, Any] | None:
    gap_fields = _list_texts(record.get("gap_fields"))
    if not gap_fields:
        return None
    record_id = _text(record.get("record_id"), "unidentified_seed_record")
    return {
        "gap_id": f"r132-gap-{record_id}",
        "source_record_id": record_id,
        "record_type": _text(record.get("record_type"), "SeedRecord"),
        "target_or_route": _text(record.get("target_or_route"), "not recorded"),
        "component_name": _text(record.get("component_name")),
        "linked_component": _text(record.get("linked_component")),
        "component_type": _text(record.get("component_type")),
        "gap_type": "source_provenance_or_review_gap",
        "missing_fields": gap_fields,
        "review_status": _text(record.get("review_status"), "needs_manual_review"),
        "provenance_status": _text(record.get("provenance_status"), "missing"),
        "needs_manual_review": True,
        "source_file": _text(record.get("source_file")),
        "row_index": record.get("row_index", 0),
        "manual_review_note": _text(record.get("manual_review_note"), "manual review required"),
    }


def _load_seed_file(seed_dir: Path, source_key: str, file_name: str) -> dict[str, Any]:
    path = seed_dir / file_name
    if not path.exists():
        return {
            "source_key": source_key,
            "file_name": file_name,
            "schema_version": "",
            "batch": "",
            "records": [],
            "rejected_rows": [
                _safe_rejected_row(
                    source_file=file_name,
                    row_index=0,
                    reason="seed_file_missing",
                    raw_record={},
                )
            ],
            "warnings": [f"{file_name} is missing from the local seed directory"],
        }

    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "source_key": source_key,
            "file_name": file_name,
            "schema_version": "",
            "batch": "",
            "records": [],
            "rejected_rows": [
                _safe_rejected_row(
                    source_file=file_name,
                    row_index=0,
                    reason=f"seed_file_not_readable:{exc.__class__.__name__}",
                    raw_record={},
                )
            ],
            "warnings": [f"{file_name} could not be read as local seed JSON"],
        }

    payload = _mapping(raw_payload)
    raw_records = payload.get("records")
    if not isinstance(raw_records, Sequence) or isinstance(raw_records, (bytes, bytearray, str)):
        return {
            "source_key": source_key,
            "file_name": file_name,
            "schema_version": _text(payload.get("schema_version")),
            "batch": _text(payload.get("batch")),
            "records": [],
            "rejected_rows": [
                _safe_rejected_row(
                    source_file=file_name,
                    row_index=0,
                    reason="records_field_not_list",
                    raw_record=raw_payload,
                )
            ],
            "warnings": [f"{file_name} does not contain a records list"],
        }

    records: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for index, raw_record in enumerate(raw_records, start=1):
        if not isinstance(raw_record, Mapping):
            rejected_rows.append(
                _safe_rejected_row(
                    source_file=file_name,
                    row_index=index,
                    reason="record_not_object",
                    raw_record=raw_record,
                )
            )
            continue
        if not _text(raw_record.get("record_id")) or not _text(raw_record.get("record_type")):
            rejected_rows.append(
                _safe_rejected_row(
                    source_file=file_name,
                    row_index=index,
                    reason="missing_record_id_or_record_type",
                    raw_record=raw_record,
                )
            )
            continue
        records.append(_normal_record(raw_record, source_file=file_name, row_index=index))

    return {
        "source_key": source_key,
        "file_name": file_name,
        "schema_version": _text(payload.get("schema_version")),
        "batch": _text(payload.get("batch")),
        "records": records,
        "rejected_rows": rejected_rows,
        "warnings": [],
    }


def _records_by_type(records: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        record_type = _text(record.get("record_type"), "SeedRecord")
        grouped.setdefault(record_type, []).append(dict(record))
    return {key: grouped[key] for key in sorted(grouped, key=str.casefold)}


def _summary(
    *,
    records: Sequence[Mapping[str, Any]],
    rejected_rows: Sequence[Mapping[str, Any]],
    gap_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    provenance_counts: dict[str, int] = {}
    for record in records:
        status = _text(record.get("provenance_status"), "missing")
        provenance_counts[status] = provenance_counts.get(status, 0) + 1
    return {
        "total_records": len(records),
        "route_context_count": sum(1 for record in records if record.get("source_file") == "route_contexts.json"),
        "component_record_count": sum(1 for record in records if record.get("source_file") == "component_records.json"),
        "evidence_record_count": sum(1 for record in records if record.get("source_file") == "evidence_records.json"),
        "rejected_row_count": len(rejected_rows),
        "gap_record_count": len(gap_records),
        "manual_review_required_count": sum(1 for record in records if record.get("needs_manual_review") is True),
        "provenance_status_counts": {
            key: provenance_counts[key] for key in sorted(provenance_counts, key=str.casefold)
        },
    }


def load_plant_evidence_seed_intake(seed_dir: str | Path = DEFAULT_RICE_ALBUMIN_SEED_DIR) -> dict[str, Any]:
    """Load local plant seed JSON files into plain documentation-review payloads."""
    base_dir = Path(seed_dir)
    file_payloads = [_load_seed_file(base_dir, source_key, file_name) for source_key, file_name in SEED_FILES]
    records = [record for payload in file_payloads for record in payload["records"]]
    rejected_rows = [row for payload in file_payloads for row in payload["rejected_rows"]]
    gap_records = [
        gap
        for record in records
        for gap in [_gap_record(record)]
        if gap is not None
    ]
    warnings = [warning for payload in file_payloads for warning in payload["warnings"]]
    status = (
        SEED_INTAKE_STATUS_EMPTY
        if not records
        else SEED_INTAKE_STATUS_GAPS_PRESENT
        if rejected_rows or gap_records
        else SEED_INTAKE_STATUS_READY
    )
    payload = {
        "seed_intake_schema_version": SEED_INTAKE_SCHEMA_VERSION,
        "seed_intake_batch": SEED_INTAKE_BATCH,
        "seed_intake_status": status,
        "read_only": True,
        "plant_scope_only": True,
        "manual_review_required": True,
        "documentation_only_boundary": BOUNDARY_NOTE,
        "seed_source": {
            "seed_dir": str(base_dir),
            "files": [file_name for _, file_name in SEED_FILES],
        },
        "preserved_fields": list(PRESERVED_FIELDS),
        "summary": _summary(records=records, rejected_rows=rejected_rows, gap_records=gap_records),
        "file_sections": {
            payload["source_key"]: {
                "file_name": payload["file_name"],
                "schema_version": payload["schema_version"],
                "batch": payload["batch"],
                "records": payload["records"],
            }
            for payload in file_payloads
        },
        "records": records,
        "records_by_type": _records_by_type(records),
        "gap_records": gap_records,
        "rejected_rows": rejected_rows,
        "warnings": warnings,
    }
    payload["r118_worksheet_input"] = build_r118_evidence_worksheet_input(payload)
    payload["r128_traceability_input"] = build_r128_traceability_input(payload)
    return _plain_value(payload)


def _slot_lookup(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for record in records:
        if _text(record.get("record_type")) != "ComponentSlot":
            continue
        record_id = _text(record.get("record_id"))
        slot_id = _text(record.get("slot_id")) or record_id
        if record_id:
            lookup[record_id] = dict(record)
        if slot_id:
            lookup[slot_id] = dict(record)
    return lookup


def _component_lookup(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _text(record.get("record_id")): dict(record)
        for record in records
        if _text(record.get("record_id"))
    }


def _linked_slot(record: Mapping[str, Any], slot_lookup: Mapping[str, Mapping[str, Any]]) -> tuple[str, str]:
    direct_slot = _text(record.get("slot_id"))
    if direct_slot:
        return direct_slot, _text(record.get("component_name"), direct_slot)
    linked_component = _text(record.get("linked_component"))
    linked_slot = _mapping(slot_lookup.get(linked_component))
    slot_id = _text(linked_slot.get("slot_id")) or linked_component
    slot_label = _text(linked_slot.get("component_name")) or slot_id
    return slot_id, slot_label


def _gap_reason(record: Mapping[str, Any]) -> str:
    gaps = _list_texts(record.get("gap_fields"))
    if gaps:
        return ", ".join(gaps)
    return "manual_review_required"


def _route_context(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    route_records = [record for record in records if _text(record.get("record_type")) == "RouteContext"]
    route = route_records[0] if route_records else {}
    return {
        "route_id": _text(route.get("route_template_id") or route.get("target_or_route"), "rice_albumin_seed_route_context"),
        "route_type": _text(route.get("goal_type_id") or route.get("record_type"), "plant_seed_route_context"),
        "route_status": _text(route.get("review_status"), "needs_manual_review"),
        "selected_template": {
            "route_id": _text(route.get("route_template_id") or route.get("target_or_route")),
        },
        "plant_context": {
            "scope_status": _text(route.get("provenance_status"), "candidate"),
        },
    }


def _plant_project_intent(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    intent_records = [record for record in records if _text(record.get("record_type")) == "ProjectIntent"]
    intent = intent_records[0] if intent_records else {}
    context_records = [record for record in records if _text(record.get("record_type")) == "PlantDesignContext"]
    context = context_records[0] if context_records else {}
    return {
        "target_name": _text(intent.get("target_name") or context.get("target_product_type"), "not recorded"),
        "plant_host": _text(intent.get("plant_host") or context.get("plant_species"), "not recorded"),
        "tissue_context": _text(intent.get("tissue_or_context") or context.get("tissue_or_organ"), "not recorded"),
        "intent_summary": _text(intent.get("target_or_route"), "rice albumin seed documentation review"),
    }


def _worksheet_evidence_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    slot_lookup = _slot_lookup(records)
    components = _component_lookup(records)
    rows: list[dict[str, Any]] = []
    for record in records:
        if _text(record.get("record_type")) != "EvidenceRecord":
            continue
        linked_component_id = _text(record.get("linked_component"))
        linked_component = _mapping(components.get(linked_component_id))
        slot_id, slot_label = _linked_slot(linked_component or record, slot_lookup)
        rows.append(
            {
                "record_id": _text(record.get("record_id")),
                "evidence_id": _text(record.get("record_id")),
                "evidence_label": _text(record.get("evidence_type"), "seed evidence placeholder"),
                "linked_component_id": linked_component_id,
                "linked_component_label": _text(linked_component.get("component_name") or linked_component_id),
                "slot_id": slot_id,
                "slot_label": slot_label,
                "linked_slot_id": slot_id,
                "linked_slot_label": slot_label,
                "component_type": _text(record.get("component_type")),
                "source_or_provenance_placeholder": _text(record.get("source_or_provenance_placeholder")),
                "source_type": _text(record.get("source_type")),
                "source_id": _text(record.get("source_id")),
                "source_status": _text(record.get("provenance_status"), "missing"),
                "evidence_type": _text(record.get("evidence_type"), "seed_evidence_placeholder"),
                "evidence_status": _text(record.get("review_status"), "needs_manual_review"),
                "review_status": _text(record.get("review_status"), "needs_manual_review"),
                "gap_reason": _gap_reason(record),
                "manual_review_reasons": _list_texts(record.get("gap_fields")),
                "manual_review_note": _text(record.get("manual_review_note"), "manual review required"),
            }
        )
    return rows


def _worksheet_component_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    slot_lookup = _slot_lookup(records)
    rows: list[dict[str, Any]] = []
    for record in records:
        if _text(record.get("source_file")) != "component_records.json":
            continue
        slot_id, slot_label = _linked_slot(record, slot_lookup)
        rows.append(
            {
                "record_id": _text(record.get("record_id")),
                "component_id": _text(record.get("record_id")),
                "component_name": _text(record.get("component_name") or record.get("record_id")),
                "component_type": _text(record.get("component_type"), "component_placeholder"),
                "slot_id": slot_id,
                "slot_label": slot_label,
                "linked_slot_id": slot_id,
                "linked_slot_label": slot_label,
                "linked_component": _text(record.get("linked_component")),
                "matched_evidence_ids": _list_texts(record.get("linked_evidence_ids")),
                "evidence_ids": _list_texts(record.get("linked_evidence_ids")),
                "source_or_provenance_placeholder": _text(record.get("source_or_provenance_placeholder")),
                "source_type": _text(record.get("source_type")),
                "source_id": _text(record.get("source_id")),
                "provenance_status": _text(record.get("provenance_status"), "missing"),
                "review_status": _text(record.get("review_status"), "needs_manual_review"),
                "gap_reason": _gap_reason(record),
                "manual_review_reasons": _list_texts(record.get("gap_fields")),
                "manual_review_note": _text(record.get("manual_review_note"), "manual review required"),
            }
        )
    return rows


def _review_items(
    records: Sequence[Mapping[str, Any]],
    gap_records: Sequence[Mapping[str, Any]],
    rejected_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    slot_lookup = _slot_lookup(records)
    component_lookup = _component_lookup(records)
    rows: list[dict[str, Any]] = []
    for gap in gap_records:
        source_record_id = _text(gap.get("source_record_id"))
        source_record = _mapping(component_lookup.get(source_record_id))
        linked_component = _text(source_record.get("linked_component") or source_record.get("linked_component_id"))
        slot_id, _slot_label = _linked_slot(source_record or gap, slot_lookup)
        evidence_ids = [source_record_id] if _text(gap.get("record_type")) == "EvidenceRecord" else _list_texts(source_record.get("linked_evidence_ids"))
        component_ids = [source_record_id] if _text(gap.get("record_type")) in {"ComponentRecord", "ComponentSlot"} else [linked_component] if linked_component else []
        rows.append(
            {
                "item_id": _text(gap.get("gap_id")),
                "category": _text(gap.get("gap_type"), "source_provenance_or_review_gap"),
                "severity": "review_required",
                "slot_id": slot_id,
                "linked_slot_id": slot_id,
                "evidence_ids": evidence_ids,
                "linked_evidence_ids": evidence_ids,
                "component_ids": component_ids,
                "linked_component_ids": component_ids,
                "gap_reason": ", ".join(_list_texts(gap.get("missing_fields"))),
                "manual_review_note": _text(gap.get("manual_review_note"), "manual review required"),
            }
        )
    for rejected in rejected_rows:
        rows.append(
            {
                "item_id": _text(rejected.get("record_id")),
                "category": "rejected_seed_record",
                "severity": "review_required",
                "slot_id": "",
                "linked_slot_id": "",
                "evidence_ids": [],
                "linked_evidence_ids": [],
                "component_ids": [],
                "linked_component_ids": [],
                "gap_reason": _text(rejected.get("rejection_reason"), "seed row rejected"),
                "manual_review_note": _text(rejected.get("manual_review_note"), "manual review required"),
            }
        )
    return rows


def build_r118_evidence_worksheet_input(seed_intake_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return kwargs-compatible plain input for the R118 worksheet builder."""
    records = [_mapping(record) for record in _sequence(seed_intake_payload.get("records"))]
    gap_records = [_mapping(record) for record in _sequence(seed_intake_payload.get("gap_records"))]
    rejected_rows = [_mapping(record) for record in _sequence(seed_intake_payload.get("rejected_rows"))]
    return _plain_value(
        {
            "route_context": _route_context(records),
            "evidence_placeholders": _worksheet_evidence_records(records),
            "component_slots": _worksheet_component_records(records),
            "review_items": _review_items(records, gap_records, rejected_rows),
            "worksheet_context": {
                "source_batch": SEED_INTAKE_BATCH,
                "source_surface": "plant_evidence_seed_intake",
                "read_only": True,
            },
        }
    )


def build_r128_traceability_input(seed_intake_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return kwargs-compatible plain input for the R128 traceability readback builder."""
    records = [_mapping(record) for record in _sequence(seed_intake_payload.get("records"))]
    worksheet_input = build_r118_evidence_worksheet_input(seed_intake_payload)
    return _plain_value(
        {
            "plant_project_intent": _plant_project_intent(records),
            "route_context": worksheet_input["route_context"],
            "evidence_placeholders": worksheet_input["evidence_placeholders"],
            "component_slots": worksheet_input["component_slots"],
            "review_items": worksheet_input["review_items"],
            "handoff_review_items": worksheet_input["review_items"],
            "readback_context": {
                "source_batch": SEED_INTAKE_BATCH,
                "source_surface": "plant_evidence_seed_intake",
                "read_only": True,
            },
        }
    )
