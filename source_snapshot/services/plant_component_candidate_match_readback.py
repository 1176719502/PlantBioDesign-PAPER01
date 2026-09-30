from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


BOUNDARY_NOTICE = (
    "Documentation-only Plant Component Library candidate match readback for manual review. "
    "It groups existing component-style records by route construct slot without selecting a "
    "final component, ranking candidates, generating sequences, scoring outcomes, producing "
    "experiment procedures, or judging downstream use."
)
BLOCKED_OUTPUTS_NOTICE = (
    "Blocked output families remain outside this readback layer: final component selection, "
    "component ranking, biological part advice, sequence generation, outcome scoring, "
    "experiment procedure generation, and downstream-use judgments."
)
EMPTY_STATE_MESSAGE = (
    "Provide a plant route draft with required slots to review candidate Component Library "
    "records for documentation-only manual review."
)

READBACK_SECTION_KEYS: tuple[str, ...] = (
    "route_summary",
    "candidate_match_summary",
    "slot_candidate_rows",
    "unmatched_slot_rows",
    "evidence_coverage_rows",
    "manual_review_items",
    "boundary_notice",
    "blocked_outputs_notice",
    "empty_state",
)

COMPONENT_FIELD_KEYS: tuple[str, ...] = (
    "component_id",
    "component_name",
    "component_type",
    "slot_type",
    "plant_context",
    "host_context",
    "evidence_status",
    "source_id",
    "source_label",
    "citation",
    "notes",
    "review_status",
)

_NON_PLANT_TERMS: tuple[str, ...] = (
    "bacterial",
    "bacteria",
    "e. coli",
    "ecoli",
    "escherichia",
    "yeast",
    "saccharomyces",
    "pichia",
    "mammalian",
    "human cell",
    "cho cell",
    "hek293",
    "mouse",
)

_PLANT_TERMS: tuple[str, ...] = (
    "plant",
    "rice",
    "oryza",
    "oryza sativa",
    "nicotiana",
    "benthamiana",
    "arabidopsis",
    "maize",
    "corn",
    "wheat",
    "soybean",
    "tobacco",
    "chloroplast",
    "plastid",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_")


def _title(value: Any) -> str:
    return _text(value).replace("_", " ").title()


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray, str)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _slot_type_from_slot(slot: Mapping[str, Any]) -> str:
    return _text(slot.get("slot_type") or slot.get("slot_name") or slot.get("field"))


def _slot_status(slot: Mapping[str, Any]) -> str:
    return _text(slot.get("status")) or "missing"


def _component_type(record: Mapping[str, Any]) -> str:
    return _text(
        record.get("slot_type")
        or record.get("component_type")
        or record.get("asset_type")
        or record.get("part_type")
        or record.get("component_category")
    )


def _component_id(record: Mapping[str, Any]) -> str:
    return _text(
        record.get("component_id")
        or record.get("asset_id")
        or record.get("part_id")
        or record.get("profile_id")
        or record.get("source_record_id")
    )


def _component_name(record: Mapping[str, Any]) -> str:
    return _text(
        record.get("component_name")
        or record.get("component_label")
        or record.get("asset_label")
        or record.get("asset_display_name")
        or record.get("display_name")
        or record.get("part_label")
    )


def _plant_context_from_record(record: Mapping[str, Any]) -> str:
    return _text(
        record.get("plant_context")
        or record.get("host_context")
        or record.get("domain_or_source_context")
        or record.get("organism_or_source_context")
        or record.get("species_label")
        or record.get("species")
    )


def _route_plant_context(route_draft: Mapping[str, Any]) -> str:
    context = route_draft.get("plant_context")
    if isinstance(context, Mapping):
        return _text(
            context.get("provided_context")
            or context.get("provided_host")
            or context.get("selected_context")
        )
    return _text(context)


def _contains_any(blob: str, terms: Sequence[str]) -> bool:
    return any(term in blob for term in terms)


def _record_scope_status(record: Mapping[str, Any]) -> str:
    context_blob = " ".join(
        part
        for part in (
            _plant_context_from_record(record),
            _text(record.get("host_context")),
            _text(record.get("component_type")),
            _text(record.get("slot_type")),
        )
        if part
    ).casefold()
    if _contains_any(context_blob, _NON_PLANT_TERMS) and not _contains_any(context_blob, _PLANT_TERMS):
        return "out_of_scope_manual_review"
    return "plant_scope_candidate"


def _slot_matches_component(slot_type: str, component_type: str) -> bool:
    slot_key = _key(slot_type)
    component_key = _key(component_type)
    if not slot_key or not component_key:
        return False
    return slot_key == component_key or slot_key.removesuffix("_slot") == component_key.removesuffix("_slot")


def _candidate_context_status(route_context: str, component_context: str) -> str:
    if route_context and component_context and _key(route_context) == _key(component_context):
        return "candidate_context_match"
    if route_context and component_context and (
        _key(route_context) in _key(component_context) or _key(component_context) in _key(route_context)
    ):
        return "candidate_context_overlap"
    if component_context:
        return "candidate_context_recorded"
    return "candidate_context_not_recorded"


def _base_readback(empty_reason: str) -> dict[str, Any]:
    return {
        "route_summary": {},
        "candidate_match_summary": {
            "total_slots": 0,
            "slots_with_candidates": 0,
            "total_candidate_rows": 0,
            "unmatched_slots": 0,
            "evidence_context_rows": 0,
            "manual_review_required": True,
            "manual_review_status": "manual_review_required",
        },
        "slot_candidate_rows": [],
        "unmatched_slot_rows": [],
        "evidence_coverage_rows": [],
        "manual_review_items": [
            {
                "review_type": "input_needed",
                "field": "route_draft",
                "note": empty_reason,
                "status": "manual_review",
            }
        ],
        "boundary_notice": {
            "title": "Documentation-only boundary",
            "notice": BOUNDARY_NOTICE,
        },
        "blocked_outputs_notice": {
            "title": "Blocked output families",
            "notice": BLOCKED_OUTPUTS_NOTICE,
        },
        "empty_state": {
            "is_empty": True,
            "title": "No candidate match readback available",
            "message": EMPTY_STATE_MESSAGE,
        },
    }


def _route_summary(route_draft: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "route_id": _text(route_draft.get("route_id")),
        "route_name": _text(route_draft.get("route_name")),
        "route_type": _text(route_draft.get("route_type")),
        "plant_context": _plain_value(route_draft.get("plant_context")),
        "draft_status": _text(route_draft.get("draft_status")),
        "boundary_note": _text(route_draft.get("boundary_note")),
    }


def _candidate_row(
    *,
    row_index: int,
    slot_index: int,
    slot: Mapping[str, Any],
    record: Mapping[str, Any],
    route_context: str,
) -> dict[str, Any]:
    slot_type = _slot_type_from_slot(slot)
    component_context = _plant_context_from_record(record)
    return {
        "row_id": f"candidate-{row_index:02d}",
        "slot_row_id": f"slot-{slot_index:02d}",
        "slot_type": slot_type,
        "slot_label": _title(slot_type),
        "slot_status": _slot_status(slot),
        "component_id": _component_id(record),
        "component_name": _component_name(record),
        "component_type": _component_type(record),
        "plant_context": _text(record.get("plant_context")),
        "host_context": _text(record.get("host_context")),
        "candidate_context_status": _candidate_context_status(route_context, component_context),
        "candidate_scope_status": _record_scope_status(record),
        "evidence_status": _text(record.get("evidence_status")),
        "source_id": _text(record.get("source_id")),
        "source_label": _text(record.get("source_label")),
        "citation": _plain_value(record.get("citation")),
        "notes": _text(record.get("notes")),
        "review_status": _text(record.get("review_status")),
        "manual_review_required": True,
    }


def _unmatched_slot_row(slot_index: int, slot: Mapping[str, Any]) -> dict[str, Any]:
    slot_type = _slot_type_from_slot(slot)
    return {
        "row_id": f"unmatched-{slot_index:02d}",
        "slot_row_id": f"slot-{slot_index:02d}",
        "slot_type": slot_type,
        "slot_label": _title(slot_type),
        "slot_status": _slot_status(slot),
        "candidate_status": "missing_candidate",
        "manual_review_required": True,
        "note": "No existing plant-scope component-style record matched this construct slot for documentation review.",
    }


def _evidence_row(row_index: int, candidate: Mapping[str, Any]) -> dict[str, Any]:
    has_evidence = any(
        _text(candidate.get(field))
        for field in ("evidence_status", "source_id", "source_label", "citation", "review_status")
    )
    return {
        "row_id": f"evidence-{row_index:02d}",
        "slot_type": _text(candidate.get("slot_type")),
        "component_id": _text(candidate.get("component_id")),
        "component_name": _text(candidate.get("component_name")),
        "evidence_status": _text(candidate.get("evidence_status")),
        "source_id": _text(candidate.get("source_id")),
        "source_label": _text(candidate.get("source_label")),
        "citation": _plain_value(candidate.get("citation")),
        "review_status": _text(candidate.get("review_status")),
        "evidence_context_status": "candidate_evidence_context_recorded" if has_evidence else "candidate_evidence_context_not_recorded",
        "manual_review_required": True,
    }


def _manual_review_items(
    *,
    candidate_rows: Sequence[Mapping[str, Any]],
    unmatched_rows: Sequence[Mapping[str, Any]],
    out_of_scope_count: int,
    component_records_provided: bool,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not component_records_provided:
        items.append(
            {
                "review_type": "component_records_needed",
                "field": "component_records",
                "note": "Add existing component-style records to inspect candidate slot matches for documentation review.",
                "status": "manual_review",
            }
        )
    for row in unmatched_rows:
        items.append(
            {
                "review_type": "missing_candidate",
                "field": row["slot_type"],
                "note": "Construct slot has no candidate component record in this readback.",
                "status": "manual_review",
            }
        )
    if out_of_scope_count:
        items.append(
            {
                "review_type": "out_of_scope_component_records",
                "field": "component_records",
                "note": f"{out_of_scope_count} non-plant or out-of-scope component record(s) were excluded from candidate grouping.",
                "status": "manual_review",
            }
        )
    for row in candidate_rows:
        if _text(row.get("evidence_status")) or _text(row.get("source_id")) or _text(row.get("source_label")):
            continue
        items.append(
            {
                "review_type": "candidate_evidence_context_needed",
                "field": row["slot_type"],
                "note": f"Candidate component {row['component_id'] or row['component_name'] or 'record'} lacks recorded evidence/source context.",
                "status": "manual_review",
            }
        )
    return items or [
        {
            "review_type": "candidate_context_review",
            "field": "slot_candidate_rows",
            "note": "Review candidate rows and source/provenance context before any downstream documentation reuse.",
            "status": "manual_review",
        }
    ]


def _candidate_summary(
    *,
    total_slots: int,
    candidate_rows: Sequence[Mapping[str, Any]],
    unmatched_rows: Sequence[Mapping[str, Any]],
    evidence_rows: Sequence[Mapping[str, Any]],
    out_of_scope_count: int,
) -> dict[str, Any]:
    candidates_by_slot = Counter(_text(row.get("slot_type")) for row in candidate_rows)
    evidence_recorded = sum(
        1 for row in evidence_rows if row.get("evidence_context_status") == "candidate_evidence_context_recorded"
    )
    return {
        "total_slots": total_slots,
        "slots_with_candidates": len(candidates_by_slot),
        "total_candidate_rows": len(candidate_rows),
        "unmatched_slots": len(unmatched_rows),
        "out_of_scope_component_records": out_of_scope_count,
        "candidate_count_by_slot": dict(sorted(candidates_by_slot.items(), key=lambda item: item[0].casefold())),
        "evidence_context_rows": len(evidence_rows),
        "candidates_with_evidence_context": evidence_recorded,
        "candidates_missing_evidence_context": len(evidence_rows) - evidence_recorded,
        "manual_review_required": True,
        "manual_review_status": "manual_review_required",
    }


def build_plant_component_candidate_match_readback(
    route_draft: dict[str, Any],
    component_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build deterministic candidate/manual-review component readback for a plant route draft."""
    if not isinstance(route_draft, Mapping) or not route_draft:
        return _base_readback("A route draft mapping is required for candidate component readback.")

    required_slots = _mapping_list(route_draft.get("required_slots"))
    if not required_slots:
        readback = _base_readback("The route draft does not include required construct slots.")
        readback["route_summary"] = _route_summary(route_draft)
        return {key: readback[key] for key in READBACK_SECTION_KEYS}

    route_context = _route_plant_context(route_draft)
    records = [record for record in component_records or [] if isinstance(record, Mapping)]
    candidate_records = [record for record in records if _record_scope_status(record) != "out_of_scope_manual_review"]
    out_of_scope_count = len(records) - len(candidate_records)
    sorted_records = sorted(
        candidate_records,
        key=lambda record: (
            _key(_component_type(record)),
            _key(_plant_context_from_record(record)),
            _key(_component_id(record)),
            _key(_component_name(record)),
        ),
    )

    candidate_rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []
    candidate_index = 1
    for slot_index, slot in enumerate(required_slots, start=1):
        slot_type = _slot_type_from_slot(slot)
        slot_matches = [
            record
            for record in sorted_records
            if _slot_matches_component(slot_type, _component_type(record))
        ]
        if not slot_matches:
            unmatched_rows.append(_unmatched_slot_row(slot_index, slot))
            continue
        slot_matches.sort(
            key=lambda record: (
                0
                if _candidate_context_status(route_context, _plant_context_from_record(record))
                == "candidate_context_match"
                else 1,
                _key(_component_id(record)),
                _key(_component_name(record)),
            )
        )
        for record in slot_matches:
            candidate_rows.append(
                _candidate_row(
                    row_index=candidate_index,
                    slot_index=slot_index,
                    slot=slot,
                    record=record,
                    route_context=route_context,
                )
            )
            candidate_index += 1

    evidence_rows = [_evidence_row(index, row) for index, row in enumerate(candidate_rows, start=1)]
    manual_review_items = _manual_review_items(
        candidate_rows=candidate_rows,
        unmatched_rows=unmatched_rows,
        out_of_scope_count=out_of_scope_count,
        component_records_provided=component_records is not None,
    )

    readback = {
        "route_summary": _route_summary(route_draft),
        "candidate_match_summary": _candidate_summary(
            total_slots=len(required_slots),
            candidate_rows=candidate_rows,
            unmatched_rows=unmatched_rows,
            evidence_rows=evidence_rows,
            out_of_scope_count=out_of_scope_count,
        ),
        "slot_candidate_rows": candidate_rows,
        "unmatched_slot_rows": unmatched_rows,
        "evidence_coverage_rows": evidence_rows,
        "manual_review_items": manual_review_items,
        "boundary_notice": {
            "title": "Documentation-only boundary",
            "notice": _text(route_draft.get("boundary_note")) or BOUNDARY_NOTICE,
        },
        "blocked_outputs_notice": {
            "title": "Blocked output families",
            "notice": BLOCKED_OUTPUTS_NOTICE,
            "blocked_output_families": _plain_value(route_draft.get("blocked_outputs") or []),
        },
        "empty_state": {
            "is_empty": False,
            "title": "",
            "message": "",
        },
    }
    return {key: readback[key] for key in READBACK_SECTION_KEYS}
