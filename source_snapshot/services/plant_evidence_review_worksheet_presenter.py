from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import re
from typing import Any

from services.plant_review_module_card_schema import BLOCKED_OUTPUT_CATEGORIES


WORKSHEET_SCHEMA_VERSION = "plant_evidence_review_worksheet.v2.7.r118"
WORKSHEET_BATCH = "v2.7-r118"
WORKSHEET_TYPE = "plant_evidence_review_worksheet"

WORKSHEET_BOUNDARY_STATEMENT = (
    "Documentation-only plant evidence review worksheet for manual review. It organizes "
    "evidence, component-slot linkage, provenance gaps, and review status without "
    "biological recommendation, sequence generation, route improvement guidance, "
    "experimental confirmation, or downstream-use judgment."
)

EMPTY_WORKSHEET_STATUS = "empty_manual_review_required"
SUPPORTED_WORKSHEET_STATUS = "plant_evidence_review_worksheet"
OVERALL_STATE_REQUIRES_MANUAL_REVIEW = "requires manual review"
OVERALL_STATE_EVIDENCE_INCOMPLETE = "evidence incomplete"
OVERALL_STATE_READY_FOR_DISCUSSION = "ready for discussion"

EVIDENCE_REVIEW_COLUMNS: tuple[str, ...] = (
    "row_id",
    "evidence_item_id",
    "evidence_label",
    "linked_component_id",
    "linked_component_label",
    "linked_slot_id",
    "linked_slot_label",
    "source_or_provenance_placeholder",
    "evidence_type",
    "evidence_status",
    "review_status",
    "gap_reason",
    "manual_review_note",
    "documentation_only_boundary",
)

COMPONENT_SLOT_COLUMNS: tuple[str, ...] = (
    "row_id",
    "linked_slot_id",
    "linked_slot_label",
    "linked_component_id",
    "linked_component_label",
    "component_type",
    "linked_evidence_ids",
    "source_or_provenance_placeholder",
    "review_status",
    "gap_reason",
    "manual_review_note",
)

MANUAL_REVIEW_COLUMNS: tuple[str, ...] = (
    "row_id",
    "item_id",
    "category",
    "severity",
    "linked_slot_id",
    "linked_component_ids",
    "linked_evidence_ids",
    "gap_reason",
    "manual_review_note",
)

FOLLOWUP_QUEUE_COLUMNS: tuple[str, ...] = (
    "followup_id",
    "followup_type",
    "linked_evidence_id",
    "linked_component",
    "linked_slot",
    "reason",
    "suggested_review_action",
    "review_status",
)

ALL_FOLLOWUP_TYPES_FILTER = "all_followup_types"


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _key(value: Any) -> str:
    clean = _text(value).casefold().replace("-", "_").replace("/", "_").replace(" ", "_")
    return re.sub(r"_+", "_", clean).strip("_")


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values: Iterable[Any] = re.split(r"[;\n|,]+", value)
    elif isinstance(value, Mapping):
        raw_values = sorted(value.keys(), key=lambda item: str(item))
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
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


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _first_text(record: Mapping[str, Any], fields: Sequence[str], fallback: str = "") -> str:
    for field in fields:
        value = _text(record.get(field))
        if value:
            return value
    return fallback


def _review_status(value: Any, fallback: str = "manual_review_required") -> str:
    status = _text(value)
    return status if status else fallback


def _source_placeholder_from_evidence(record: Mapping[str, Any]) -> str:
    source = record.get("source")
    if isinstance(source, Mapping):
        parts = [
            _text(source.get("source_label")),
            _text(source.get("source_identifier")),
            _text(source.get("source_type")),
            _text(source.get("source_url")),
        ]
        joined = ", ".join(part for part in parts if part)
        if joined:
            return joined
    return _first_text(
        record,
        (
            "source_or_provenance_placeholder",
            "source_reference",
            "source_label",
            "source_identifier",
            "source_status",
            "provenance_status",
            "provenance_note",
            "citation",
        ),
        "source/provenance placeholder missing",
    )


def _source_placeholder_from_component(record: Mapping[str, Any]) -> str:
    traceability = record.get("traceability")
    if isinstance(traceability, Mapping):
        parts = [
            _text(traceability.get("source_label")),
            _text(traceability.get("source_reference")),
            _text(traceability.get("source_database")),
            _text(traceability.get("source_accession")),
            _text(traceability.get("source_record_id")),
        ]
        joined = ", ".join(part for part in parts if part)
        if joined:
            return joined
    if _key(record.get("provenance_status")) in {
        "source_provenance_missing",
        "source_recorded_provenance_missing",
    }:
        return "source/provenance placeholder missing"
    return _first_text(
        record,
        (
            "source_or_provenance_placeholder",
            "source_reference",
            "source_label",
            "provenance_status",
            "provenance_note",
        ),
        "source/provenance placeholder missing",
    )


def _gap_reason_from_reasons(reasons: Any, fallback: str = "") -> str:
    reason_values = _list_texts(reasons)
    if reason_values:
        return ", ".join(reason_values)
    return fallback


def _gap_reason_from_evidence(record: Mapping[str, Any], slot: Mapping[str, Any]) -> str:
    reasons = _list_texts(record.get("manual_review_reasons"))
    reasons.extend(_list_texts(slot.get("manual_review_reasons")))
    missing_metadata = _mapping(record.get("source_completeness")).get("missing_metadata")
    reasons.extend(f"missing_{item}" for item in _list_texts(missing_metadata))
    return _gap_reason_from_reasons(reasons, _text(slot.get("missing_evidence_reason"), "no_gap_reason_recorded"))


def _gap_reason_from_component(record: Mapping[str, Any], slot: Mapping[str, Any]) -> str:
    reasons = _list_texts(record.get("manual_review_reasons"))
    reasons.extend(_list_texts(slot.get("manual_review_reasons")))
    missing_fields = _mapping(record.get("source_completeness")).get("missing_fields")
    reasons.extend(f"missing_{item}" for item in _list_texts(missing_fields))
    return _gap_reason_from_reasons(reasons, _text(slot.get("missing_component_reason"), "no_gap_reason_recorded"))


def _slot_rows(result: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_field in ("slots", "slot_matches"):
        for raw_slot in _sequence(result.get(source_field)):
            slot = _mapping(raw_slot)
            slot_id = _key(slot.get("slot_id") or slot.get("slot_name"))
            if not slot_id or slot_id in seen:
                continue
            slot["slot_id"] = slot_id
            rows.append(slot)
            seen.add(slot_id)
    return rows


def _evidence_id(record: Mapping[str, Any], index: int) -> str:
    return _text(
        record.get("record_id")
        or record.get("evidence_id")
        or record.get("source_id")
        or record.get("id"),
        f"evidence-item-{index:03d}",
    )


def _component_id(record: Mapping[str, Any], index: int) -> str:
    return _text(
        record.get("component_id")
        or record.get("asset_id")
        or record.get("part_id")
        or record.get("id"),
        f"component-item-{index:03d}",
    )


def _component_label(record: Mapping[str, Any]) -> str:
    return _first_text(record, ("component_name", "component_label", "asset_label", "display_name", "name"), "not recorded")


def _evidence_candidate_rows(evidence_result: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot in _slot_rows(evidence_result):
        slot_id = _text(slot.get("slot_id"))
        candidates = [
            _mapping(candidate)
            for candidate in _sequence(slot.get("candidate_evidence") or slot.get("candidate_records") or slot.get("candidates"))
            if isinstance(candidate, Mapping)
        ]
        if not candidates and _text(slot.get("slot_status")):
            candidates = [
                {
                    "record_id": _text(slot.get("evidence_id") or slot.get("matched_evidence_id")),
                    "title": "",
                    "evidence_status": _text(slot.get("slot_status")),
                    "manual_review_reasons": slot.get("manual_review_reasons"),
                }
            ]
        for index, candidate in enumerate(candidates, start=1):
            evidence_id = _evidence_id(candidate, index)
            rows.append(
                {
                    "evidence_item_id": evidence_id,
                    "evidence_label": _first_text(candidate, ("title", "evidence_label", "label"), "not recorded"),
                    "linked_component_id": "",
                    "linked_component_label": "",
                    "linked_slot_id": slot_id,
                    "linked_slot_label": _text(slot.get("slot_label"), slot_id or "not recorded"),
                    "source_or_provenance_placeholder": _source_placeholder_from_evidence(candidate),
                    "evidence_type": _first_text(candidate, ("evidence_type", "source_type"), "evidence_placeholder"),
                    "evidence_status": _first_text(candidate, ("evidence_status", "review_status"), _text(slot.get("slot_status"), "manual_review_required")),
                    "review_status": _review_status(candidate.get("review_status") or slot.get("slot_status")),
                    "gap_reason": _gap_reason_from_evidence(candidate, slot),
                    "manual_review_note": _first_text(candidate, ("manual_review_note", "note"), "manual review required"),
                    "documentation_only_boundary": WORKSHEET_BOUNDARY_STATEMENT,
                }
            )
    return rows


def _direct_evidence_rows(records: Sequence[Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, raw_record in enumerate(_sequence(records), start=1):
        record = _mapping(raw_record)
        if not record:
            continue
        evidence_id = _evidence_id(record, index)
        slot_id = _key(record.get("slot_id") or record.get("linked_slot_id"))
        component_id = _text(record.get("component_id") or record.get("linked_component_id"))
        rows.append(
            {
                "evidence_item_id": evidence_id,
                "evidence_label": _first_text(record, ("title", "evidence_label", "label"), "not recorded"),
                "linked_component_id": component_id,
                "linked_component_label": _first_text(record, ("component_name", "linked_component_label"), ""),
                "linked_slot_id": slot_id,
                "linked_slot_label": _text(record.get("slot_label") or record.get("linked_slot_label"), slot_id or "not recorded"),
                "source_or_provenance_placeholder": _source_placeholder_from_evidence(record),
                "evidence_type": _first_text(record, ("evidence_type", "source_type"), "evidence_placeholder"),
                "evidence_status": _first_text(record, ("evidence_status", "source_status", "review_status"), "manual_review_required"),
                "review_status": _review_status(record.get("review_status")),
                "gap_reason": _gap_reason_from_reasons(
                    record.get("gap_reason") or record.get("manual_review_reasons"),
                    "no_gap_reason_recorded",
                ),
                "manual_review_note": _first_text(record, ("manual_review_note", "manual_notes", "note"), "manual review required"),
                "documentation_only_boundary": WORKSHEET_BOUNDARY_STATEMENT,
            }
        )
    return rows


def _component_slot_rows(component_result: Mapping[str, Any] | None, component_slots: Sequence[Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot in _slot_rows(component_result):
        slot_id = _text(slot.get("slot_id"))
        candidates = [
            _mapping(candidate)
            for candidate in _sequence(slot.get("candidate_components") or slot.get("candidate_records") or slot.get("candidates"))
            if isinstance(candidate, Mapping)
        ]
        if not candidates and _text(slot.get("slot_status")):
            candidates = [{}]
        for index, candidate in enumerate(candidates, start=1):
            component_id = _component_id(candidate, index) if candidate else ""
            rows.append(
                {
                    "linked_slot_id": slot_id,
                    "linked_slot_label": _text(slot.get("slot_label"), slot_id or "not recorded"),
                    "linked_component_id": component_id,
                    "linked_component_label": _component_label(candidate) if candidate else "not recorded",
                    "component_type": _first_text(candidate, ("component_type", "asset_type"), _text(slot.get("component_type"), "component_placeholder")),
                    "linked_evidence_ids": _list_texts(candidate.get("matched_evidence_ids") or slot.get("matched_evidence_ids")),
                    "source_or_provenance_placeholder": _source_placeholder_from_component(candidate) if candidate else "source/provenance placeholder missing",
                    "review_status": _review_status(slot.get("slot_status")),
                    "gap_reason": _gap_reason_from_component(candidate, slot) if candidate else _text(slot.get("missing_component_reason"), "missing_component_candidate"),
                    "manual_review_note": _first_text(candidate, ("manual_review_note", "manual_notes", "note"), "manual review required"),
                }
            )

    for index, raw_record in enumerate(_sequence(component_slots), start=1):
        record = _mapping(raw_record)
        if not record:
            continue
        slot_id = _key(record.get("slot_id") or record.get("linked_slot_id"))
        rows.append(
            {
                "linked_slot_id": slot_id,
                "linked_slot_label": _text(record.get("slot_label") or record.get("linked_slot_label"), slot_id or "not recorded"),
                "linked_component_id": _component_id(record, index),
                "linked_component_label": _component_label(record),
                "component_type": _first_text(record, ("component_type", "slot_type", "asset_type"), "component_placeholder"),
                "linked_evidence_ids": _list_texts(record.get("matched_evidence_ids") or record.get("evidence_ids")),
                "source_or_provenance_placeholder": _source_placeholder_from_component(record),
                "review_status": _review_status(record.get("review_status") or record.get("slot_status")),
                "gap_reason": _gap_reason_from_reasons(
                    record.get("gap_reason") or record.get("manual_review_reasons"),
                    "no_gap_reason_recorded",
                ),
                "manual_review_note": _first_text(record, ("manual_review_note", "manual_notes", "note"), "manual review required"),
            }
        )
    return rows


def _component_lookup(component_rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for row in component_rows:
        for evidence_id in _list_texts(row.get("linked_evidence_ids")):
            key = _text(evidence_id).casefold()
            if key and key not in lookup:
                lookup[key] = {
                    "linked_component_id": _text(row.get("linked_component_id")),
                    "linked_component_label": _text(row.get("linked_component_label")),
                }
    return lookup


def _link_evidence_rows_to_components(
    evidence_rows: Sequence[Mapping[str, Any]],
    component_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    lookup = _component_lookup(component_rows)
    linked_rows: list[dict[str, Any]] = []
    for row in evidence_rows:
        normalized = dict(row)
        if not _text(normalized.get("linked_component_id")):
            component = lookup.get(_text(normalized.get("evidence_item_id")).casefold(), {})
            normalized["linked_component_id"] = component.get("linked_component_id", "")
            normalized["linked_component_label"] = component.get("linked_component_label", "")
        linked_rows.append(normalized)
    return linked_rows


def _review_items(gap_queue: Mapping[str, Any] | None, review_items: Sequence[Any] | None) -> list[dict[str, Any]]:
    raw_items: list[Any] = []
    if isinstance(gap_queue, Mapping):
        raw_items.extend(_sequence(gap_queue.get("review_items") or gap_queue.get("queue")))
    raw_items.extend(_sequence(review_items))

    rows: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items, start=1):
        item = _mapping(raw_item)
        if not item:
            continue
        rows.append(
            {
                "item_id": _text(item.get("item_id"), f"manual-review-item-{index:03d}"),
                "category": _text(item.get("category"), "manual_review"),
                "severity": _text(item.get("severity"), "review_required"),
                "linked_slot_id": _key(item.get("slot_id") or item.get("linked_slot_id")),
                "linked_component_ids": _list_texts(item.get("component_ids") or item.get("linked_component_ids")),
                "linked_evidence_ids": _list_texts(item.get("evidence_ids") or item.get("linked_evidence_ids")),
                "gap_reason": _gap_reason_from_reasons(
                    item.get("gap_reason") or item.get("upstream_review_reasons"),
                    _text(item.get("category"), "manual_review"),
                ),
                "manual_review_note": _first_text(item, ("manual_review_note", "note", "reason"), "manual review required"),
            }
        )
    return rows


def _sort_evidence_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            _text(row.get("linked_slot_id")).casefold(),
            _text(row.get("evidence_item_id")).casefold(),
            _text(row.get("linked_component_id")).casefold(),
            _text(row.get("evidence_label")).casefold(),
        ),
    )
    for index, row in enumerate(sorted_rows, start=1):
        row["row_id"] = (
            f"r118-evidence-{index:03d}-"
            f"{_key(row.get('linked_slot_id')) or 'slot'}-"
            f"{_key(row.get('evidence_item_id')) or 'evidence'}-"
            f"{_key(row.get('linked_component_id')) or 'component'}"
        )
    return sorted_rows


def _sort_component_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            _text(row.get("linked_slot_id")).casefold(),
            _text(row.get("linked_component_id")).casefold(),
            _text(row.get("linked_component_label")).casefold(),
        ),
    )
    for index, row in enumerate(sorted_rows, start=1):
        row["row_id"] = (
            f"r118-component-slot-{index:03d}-"
            f"{_key(row.get('linked_slot_id')) or 'slot'}-"
            f"{_key(row.get('linked_component_id')) or 'component'}"
        )
    return sorted_rows


def _sort_review_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            _text(row.get("severity")).casefold(),
            _text(row.get("category")).casefold(),
            _text(row.get("linked_slot_id")).casefold(),
            _text(row.get("item_id")).casefold(),
        ),
    )
    for index, row in enumerate(sorted_rows, start=1):
        row["row_id"] = (
            f"r118-manual-review-{index:03d}-"
            f"{_key(row.get('category')) or 'review'}-"
            f"{_key(row.get('linked_slot_id')) or 'context'}"
        )
    return sorted_rows


def _route_context_rows(route_context: Mapping[str, Any] | None) -> list[dict[str, str]]:
    route = _mapping(route_context)
    template = _mapping(route.get("selected_template"))
    plant_context = _mapping(route.get("plant_context"))
    return [
        {"field": "route_id", "value": _text(route.get("route_id"), "not recorded")},
        {"field": "route_type", "value": _text(route.get("route_type"), "not recorded")},
        {"field": "route_status", "value": _text(route.get("route_status") or route.get("draft_status"), "not recorded")},
        {"field": "route_template_id", "value": _text(template.get("route_id") or template.get("template_id"), "not recorded")},
        {"field": "plant_scope_status", "value": _text(plant_context.get("scope_status"), "not recorded")},
    ]


def _source_or_provenance_missing(row: Mapping[str, Any]) -> bool:
    source_key = _key(row.get("source_or_provenance_placeholder"))
    gap_key = _key(row.get("gap_reason"))
    return (
        "missing" in source_key
        or "provenance" in gap_key
        or "missing_source" in gap_key
        or "source_provenance_missing" in gap_key
    )


def _weak_or_unreviewed_evidence(row: Mapping[str, Any]) -> bool:
    status_key = _key(row.get("evidence_status"))
    review_key = _key(row.get("review_status"))
    gap_key = _key(row.get("gap_reason"))
    return (
        status_key in {"weak", "unreviewed", "needs_review", "manual_review_required"}
        or review_key in {"unreviewed", "needs_review", "manual_review_required"}
        or "weak" in gap_key
        or "unreviewed" in gap_key
    )


def _manual_review_required(row: Mapping[str, Any]) -> bool:
    row_text = _key(
        " ".join(
            _text(row.get(field))
            for field in ("review_status", "severity", "category", "gap_reason", "manual_review_note")
        )
    )
    return "manual_review" in row_text or "review_required" in row_text


def _linked_component_label(row: Mapping[str, Any]) -> str:
    return _text(row.get("linked_component_id") or row.get("linked_component_label"))


def _linked_slot_label(row: Mapping[str, Any]) -> str:
    return _text(row.get("linked_slot_id") or row.get("linked_slot_label"))


def _followup_base(
    *,
    followup_type: str,
    linked_evidence_id: str = "",
    linked_component: str = "",
    linked_slot: str = "",
    reason: str,
    suggested_review_action: str,
    review_status: str,
) -> dict[str, str]:
    return {
        "followup_id": "",
        "followup_type": followup_type,
        "linked_evidence_id": linked_evidence_id,
        "linked_component": linked_component,
        "linked_slot": linked_slot,
        "reason": reason,
        "suggested_review_action": suggested_review_action,
        "review_status": review_status,
    }


def _component_slot_linkage_gap(row: Mapping[str, Any]) -> bool:
    gap_key = _key(row.get("gap_reason"))
    return (
        not _text(row.get("linked_component_id"))
        or not _list_texts(row.get("linked_evidence_ids"))
        or "missing_component" in gap_key
        or "evidence_link" in gap_key
        or "linkage" in gap_key
    )


def _build_followup_queue(
    *,
    evidence_rows: Sequence[Mapping[str, Any]],
    component_rows: Sequence[Mapping[str, Any]],
    manual_review_rows: Sequence[Mapping[str, Any]],
    blocked_outputs: Sequence[str],
    has_content: bool,
) -> list[dict[str, str]]:
    if not has_content:
        return []

    rows: list[dict[str, str]] = []
    for evidence_row in evidence_rows:
        evidence_id = _text(evidence_row.get("evidence_item_id"))
        linked_component = _linked_component_label(evidence_row)
        linked_slot = _linked_slot_label(evidence_row)
        reason = _text(evidence_row.get("gap_reason"), "evidence review follow-up required")
        review_status = _review_status(evidence_row.get("review_status"))
        if _source_or_provenance_missing(evidence_row):
            rows.append(
                _followup_base(
                    followup_type="missing_provenance",
                    linked_evidence_id=evidence_id,
                    linked_component=linked_component,
                    linked_slot=linked_slot,
                    reason=reason,
                    suggested_review_action="add or confirm source/provenance documentation",
                    review_status=review_status,
                )
            )
        if _weak_or_unreviewed_evidence(evidence_row):
            rows.append(
                _followup_base(
                    followup_type="weak_or_unreviewed_evidence",
                    linked_evidence_id=evidence_id,
                    linked_component=linked_component,
                    linked_slot=linked_slot,
                    reason=reason,
                    suggested_review_action="confirm evidence level and review status",
                    review_status=review_status,
                )
            )
        if _manual_review_required(evidence_row):
            rows.append(
                _followup_base(
                    followup_type="manual_review_required",
                    linked_evidence_id=evidence_id,
                    linked_component=linked_component,
                    linked_slot=linked_slot,
                    reason=reason,
                    suggested_review_action="manual evidence review required",
                    review_status=review_status,
                )
            )

    for component_row in component_rows:
        linked_evidence_ids = _list_texts(component_row.get("linked_evidence_ids"))
        linked_evidence_id = ", ".join(linked_evidence_ids)
        linked_component = _linked_component_label(component_row)
        linked_slot = _linked_slot_label(component_row)
        reason = _text(component_row.get("gap_reason"), "component-slot linkage follow-up required")
        review_status = _review_status(component_row.get("review_status"))
        if _source_or_provenance_missing(component_row):
            rows.append(
                _followup_base(
                    followup_type="missing_provenance",
                    linked_evidence_id=linked_evidence_id,
                    linked_component=linked_component,
                    linked_slot=linked_slot,
                    reason=reason,
                    suggested_review_action="add or confirm component source/provenance documentation",
                    review_status=review_status,
                )
            )
        if _component_slot_linkage_gap(component_row):
            rows.append(
                _followup_base(
                    followup_type="component_slot_linkage_gap",
                    linked_evidence_id=linked_evidence_id,
                    linked_component=linked_component,
                    linked_slot=linked_slot,
                    reason=reason,
                    suggested_review_action="clarify linked component slot and evidence traceability",
                    review_status=review_status,
                )
            )
        if _manual_review_required(component_row):
            rows.append(
                _followup_base(
                    followup_type="manual_review_required",
                    linked_evidence_id=linked_evidence_id,
                    linked_component=linked_component,
                    linked_slot=linked_slot,
                    reason=reason,
                    suggested_review_action="manual component-slot review required",
                    review_status=review_status,
                )
            )

    for review_row in manual_review_rows:
        rows.append(
            _followup_base(
                followup_type="manual_review_required",
                linked_evidence_id=", ".join(_list_texts(review_row.get("linked_evidence_ids"))),
                linked_component=", ".join(_list_texts(review_row.get("linked_component_ids"))),
                linked_slot=_linked_slot_label(review_row),
                reason=_text(review_row.get("gap_reason"), _text(review_row.get("category"), "manual review required")),
                suggested_review_action="review the recorded manual-review item",
                review_status=_text(review_row.get("severity"), "review_required"),
            )
        )

    for blocked_output in sorted(_list_texts(blocked_outputs), key=str.casefold):
        rows.append(
            _followup_base(
                followup_type="boundary_only_category",
                reason="blocked output boundary category recorded for manual review",
                suggested_review_action="keep as documentation-only boundary; manual review only",
                review_status="boundary_only",
            )
        )

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row["followup_type"].casefold(),
            row["linked_slot"].casefold(),
            row["linked_component"].casefold(),
            row["linked_evidence_id"].casefold(),
            row["reason"].casefold(),
        ),
    )
    for index, row in enumerate(sorted_rows, start=1):
        row["followup_id"] = (
            f"r122-followup-{index:03d}-"
            f"{_key(row.get('followup_type')) or 'review'}-"
            f"{_key(row.get('linked_slot')) or 'boundary'}-"
            f"{_key(row.get('linked_evidence_id')) or _key(row.get('linked_component')) or 'item'}"
        )
    return sorted_rows


def followup_queue_type_options(followup_queue_section: Mapping[str, Any] | None) -> list[str]:
    """Return deterministic follow-up type filter options from an R122 queue section."""
    section = _mapping(followup_queue_section)
    types = {
        _text(row.get("followup_type"))
        for row in _sequence(section.get("rows"))
        if isinstance(row, Mapping) and _text(row.get("followup_type"))
    }
    return sorted(types, key=str.casefold)


def filter_followup_queue_rows(
    followup_queue_section: Mapping[str, Any] | None,
    *,
    followup_type: str = ALL_FOLLOWUP_TYPES_FILTER,
) -> list[dict[str, Any]]:
    """Return copied R122 queue rows filtered by followup_type without mutating the source payload."""
    section = _mapping(followup_queue_section)
    selected_type = _text(followup_type)
    rows: list[dict[str, Any]] = []
    for row in _sequence(section.get("rows")):
        if not isinstance(row, Mapping):
            continue
        row_copy = dict(row)
        if selected_type and selected_type != ALL_FOLLOWUP_TYPES_FILTER and row_copy.get("followup_type") != selected_type:
            continue
        rows.append(row_copy)
    return rows


def group_followup_queue_rows_by_type(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group copied follow-up queue rows by followup_type using deterministic type ordering."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        followup_type = _text(row.get("followup_type"), "untyped_followup")
        grouped.setdefault(followup_type, []).append(dict(row))
    return {key: grouped[key] for key in sorted(grouped, key=str.casefold)}


def build_followup_queue_filter_view(
    followup_queue_section: Mapping[str, Any] | None,
    *,
    followup_type: str = ALL_FOLLOWUP_TYPES_FILTER,
    group_by_type: bool = True,
) -> dict[str, Any]:
    """Build a read-only filter/group view over the existing R122 follow-up queue payload."""
    options = followup_queue_type_options(followup_queue_section)
    selected_type = _text(followup_type) or ALL_FOLLOWUP_TYPES_FILTER
    if selected_type != ALL_FOLLOWUP_TYPES_FILTER and selected_type not in options:
        selected_type = ALL_FOLLOWUP_TYPES_FILTER
    filtered_rows = filter_followup_queue_rows(followup_queue_section, followup_type=selected_type)
    grouped_rows = group_followup_queue_rows_by_type(filtered_rows) if group_by_type else {}
    return _plain_value(
        {
            "read_only": True,
            "filter_key": "followup_type",
            "selected_followup_type": selected_type,
            "followup_type_options": options,
            "filtered_count": len(filtered_rows),
            "total_count": len(filter_followup_queue_rows(followup_queue_section)),
            "group_by_type": bool(group_by_type),
            "group_counts": {key: len(value) for key, value in grouped_rows.items()},
            "rows": filtered_rows,
            "grouped_rows": grouped_rows,
            "empty_state": (
                "No worksheet follow-up queue items match the selected documentation-review issue type."
                if options
                else "No worksheet follow-up queue items are available yet."
            ),
            "boundary_note": (
                "Filters and groups are for read-only documentation-review inspection only; they do not select, "
                "validate, prioritize, or order components by importance."
            ),
        }
    )


def _build_summary_rollup(
    *,
    evidence_rows: Sequence[Mapping[str, Any]],
    component_rows: Sequence[Mapping[str, Any]],
    manual_review_rows: Sequence[Mapping[str, Any]],
    blocked_outputs: Sequence[str],
    has_content: bool,
) -> dict[str, Any]:
    linked_slot_ids = {
        _text(row.get("linked_slot_id")).casefold()
        for row in component_rows
        if _text(row.get("linked_slot_id")) and _text(row.get("linked_component_id"))
    }
    missing_source_or_provenance_count = sum(
        1 for row in [*evidence_rows, *component_rows] if _source_or_provenance_missing(row)
    )
    weak_or_unreviewed_evidence_count = sum(1 for row in evidence_rows if _weak_or_unreviewed_evidence(row))
    manual_review_required_count = len(manual_review_rows) + sum(
        1 for row in [*evidence_rows, *component_rows] if _manual_review_required(row)
    )
    blocked_boundary_category_count = len(_list_texts(blocked_outputs))

    if not has_content or not evidence_rows:
        overall_review_state = OVERALL_STATE_EVIDENCE_INCOMPLETE
    elif (
        manual_review_required_count
        or missing_source_or_provenance_count
        or weak_or_unreviewed_evidence_count
    ):
        overall_review_state = OVERALL_STATE_REQUIRES_MANUAL_REVIEW
    else:
        overall_review_state = OVERALL_STATE_READY_FOR_DISCUSSION

    return {
        "total_evidence_rows": len(evidence_rows),
        "linked_component_slot_count": len(linked_slot_ids),
        "missing_source_or_provenance_count": missing_source_or_provenance_count,
        "weak_or_unreviewed_evidence_count": weak_or_unreviewed_evidence_count,
        "manual_review_required_count": manual_review_required_count,
        "blocked_boundary_category_count": blocked_boundary_category_count,
        "overall_review_state": overall_review_state,
        "evidence_row_count": len(evidence_rows),
        "component_slot_row_count": len(component_rows),
        "manual_review_item_count": len(manual_review_rows),
        "provenance_gap_count": missing_source_or_provenance_count,
        "empty_input": not has_content,
    }


def _extract_source_payloads(source_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    source = _mapping(source_payload)
    chain_package = _mapping(source.get("plant_review_package"))
    chain = _mapping(source.get("chain_result"))
    if not chain and "chain_schema_version" in source:
        chain = source

    package = chain_package or _mapping(source.get("review_package"))
    route_context = (
        _mapping(source.get("route_context"))
        or _mapping(source.get("route_draft"))
        or _mapping(package.get("route_summary"))
    )
    evidence_result = (
        _mapping(source.get("evidence_slot_match_result"))
        or _mapping(chain.get("evidence_slot_match_result"))
        or _mapping(package.get("evidence_summary"))
    )
    component_result = (
        _mapping(source.get("component_candidate_match_result"))
        or _mapping(chain.get("component_candidate_match_result"))
        or _mapping(package.get("component_candidate_summary"))
    )
    gap_queue = (
        _mapping(source.get("gap_manual_review_queue_result"))
        or _mapping(chain.get("gap_manual_review_queue_result"))
        or {"review_items": _sequence(package.get("review_queue"))}
    )
    return {
        "route_context": route_context,
        "evidence_slot_match_result": evidence_result,
        "component_candidate_match_result": component_result,
        "gap_manual_review_queue_result": gap_queue,
        "evidence_placeholders": source.get("evidence_placeholders"),
        "component_slots": source.get("component_slots") or source.get("component_placeholders"),
        "review_items": source.get("review_items"),
        "blocked_output_categories": source.get("blocked_output_categories") or package.get("blocked_output_boundaries"),
    }


def build_plant_evidence_review_worksheet_payload(
    source_payload: Mapping[str, Any] | None = None,
    *,
    route_context: Mapping[str, Any] | None = None,
    evidence_slot_match_result: Mapping[str, Any] | None = None,
    component_candidate_match_result: Mapping[str, Any] | None = None,
    gap_manual_review_queue_result: Mapping[str, Any] | None = None,
    evidence_placeholders: Sequence[Any] | None = None,
    component_slots: Sequence[Any] | None = None,
    review_items: Sequence[Any] | None = None,
    worksheet_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic read-only worksheet payload from existing Plant Review data."""
    extracted = _extract_source_payloads(source_payload)
    route = _mapping(route_context) or extracted["route_context"]
    evidence_result = _mapping(evidence_slot_match_result) or extracted["evidence_slot_match_result"]
    component_result = _mapping(component_candidate_match_result) or extracted["component_candidate_match_result"]
    gap_queue = _mapping(gap_manual_review_queue_result) or extracted["gap_manual_review_queue_result"]
    evidence_items = evidence_placeholders if evidence_placeholders is not None else extracted["evidence_placeholders"]
    component_items = component_slots if component_slots is not None else extracted["component_slots"]
    manual_items = review_items if review_items is not None else extracted["review_items"]

    raw_component_rows = _component_slot_rows(component_result, component_items)
    component_rows = _sort_component_rows(raw_component_rows)
    raw_evidence_rows = [
        *_evidence_candidate_rows(evidence_result),
        *_direct_evidence_rows(evidence_items),
    ]
    evidence_rows = _sort_evidence_rows(_link_evidence_rows_to_components(raw_evidence_rows, component_rows))
    manual_review_rows = _sort_review_rows(_review_items(gap_queue, manual_items))
    blocked_outputs = _list_texts(extracted.get("blocked_output_categories"))
    blocked_outputs.extend(_list_texts(gap_queue.get("blocked_output_categories")))
    if not blocked_outputs:
        blocked_outputs = list(BLOCKED_OUTPUT_CATEGORIES)
    has_content = bool(route or evidence_rows or component_rows or manual_review_rows)
    summary = _build_summary_rollup(
        evidence_rows=evidence_rows,
        component_rows=component_rows,
        manual_review_rows=manual_review_rows,
        blocked_outputs=blocked_outputs,
        has_content=has_content,
    )
    followup_rows = _build_followup_queue(
        evidence_rows=evidence_rows,
        component_rows=component_rows,
        manual_review_rows=manual_review_rows,
        blocked_outputs=blocked_outputs,
        has_content=has_content,
    )
    summary["followup_queue_count"] = len(followup_rows)
    summary["followup_queue_type_counts"] = {
        followup_type: sum(1 for row in followup_rows if row["followup_type"] == followup_type)
        for followup_type in sorted({row["followup_type"] for row in followup_rows}, key=str.casefold)
    }

    payload = {
        "worksheet_schema_version": WORKSHEET_SCHEMA_VERSION,
        "worksheet_batch": WORKSHEET_BATCH,
        "worksheet_type": WORKSHEET_TYPE,
        "worksheet_status": SUPPORTED_WORKSHEET_STATUS if has_content else EMPTY_WORKSHEET_STATUS,
        "read_only": True,
        "plant_scope_only": True,
        "manual_review_required": True,
        "documentation_only_boundary": WORKSHEET_BOUNDARY_STATEMENT,
        "stable_keys": {
            "evidence_review_row_keys": list(EVIDENCE_REVIEW_COLUMNS),
            "component_slot_row_keys": list(COMPONENT_SLOT_COLUMNS),
            "manual_review_row_keys": list(MANUAL_REVIEW_COLUMNS),
            "followup_queue_row_keys": list(FOLLOWUP_QUEUE_COLUMNS),
        },
        "summary": summary,
        "route_context_section": {
            "columns": ["field", "value"],
            "rows": _route_context_rows(route),
        },
        "evidence_review_section": {
            "columns": list(EVIDENCE_REVIEW_COLUMNS),
            "rows": evidence_rows,
        },
        "component_slot_linkage_section": {
            "columns": list(COMPONENT_SLOT_COLUMNS),
            "rows": component_rows,
        },
        "manual_review_section": {
            "columns": list(MANUAL_REVIEW_COLUMNS),
            "rows": manual_review_rows,
        },
        "followup_queue_section": {
            "columns": list(FOLLOWUP_QUEUE_COLUMNS),
            "rows": followup_rows,
        },
        "boundary_section": {
            "boundary_statements": [WORKSHEET_BOUNDARY_STATEMENT],
            "blocked_output_categories": sorted(_list_texts(blocked_outputs), key=str.casefold),
            "allowed_output_categories": [
                "documentation_readback",
                "evidence_gap_review",
                "component_slot_traceability",
                "manual_review_status",
            ],
        },
        "worksheet_context": _plain_value(worksheet_context or {}),
        "warnings": [] if has_content else ["worksheet input warning: no readable plant review evidence payload was provided"],
    }
    return _plain_value(payload)
