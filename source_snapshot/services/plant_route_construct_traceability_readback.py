from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from services.plant_construct_draft_readback_adapter import build_plant_construct_draft_readback
from services.plant_evidence_review_worksheet_presenter import build_plant_evidence_review_worksheet_payload


TRACEABILITY_SCHEMA_VERSION = "plant_route_construct_traceability_readback.v2.7.r128"
TRACEABILITY_BATCH = "v2.7-r128"
TRACEABILITY_STATUS_READY = "route_construct_traceability_readback"
TRACEABILITY_STATUS_EMPTY = "route_construct_traceability_empty"

TRACEABILITY_BOUNDARY_NOTE = (
    "Read-only plant traceability readback. It explains relationships among project intent, "
    "route/context records, evidence rows, component slots, construct draft slots, and manual "
    "review items without choosing, ordering, confirming, improving, or approving biological "
    "components or downstream use."
)

TRACEABILITY_ROW_KEYS: tuple[str, ...] = (
    "trace_id",
    "route_or_context_id",
    "intent_summary",
    "linked_evidence_id",
    "linked_component",
    "linked_component_slot",
    "linked_construct_slot",
    "source_or_provenance_status",
    "review_status",
    "gap_or_followup_reason",
    "manual_review_note",
)

CONSTRUCT_SLOT_ROW_KEYS: tuple[str, ...] = (
    "slot_name",
    "display_label",
    "status",
    "safe_status_text",
    "evidence_ids",
    "source_ids",
    "missing_reason",
    "manual_review_required",
)

HANDOFF_REVIEW_ROW_KEYS: tuple[str, ...] = (
    "item_id",
    "category",
    "severity",
    "linked_evidence_ids",
    "linked_component_ids",
    "linked_slot_id",
    "reason",
    "manual_review_note",
)

SLOT_ALIASES = {
    "cds": "cds_payload_gene_or_enzyme",
    "cds_label": "cds_payload_gene_or_enzyme",
    "coding_sequence_slot": "cds_payload_gene_or_enzyme",
    "gene": "cds_payload_gene_or_enzyme",
    "gene_or_cds_source": "cds_payload_gene_or_enzyme",
    "target_payload": "cds_payload_gene_or_enzyme",
    "target_payload_cds_or_gene_enzyme": "cds_payload_gene_or_enzyme",
    "target_product": "cds_payload_gene_or_enzyme",
    "promoter_need": "promoter",
    "promoter_slot": "promoter",
    "promoter": "promoter",
    "terminator_need": "terminator",
    "terminator_slot": "terminator",
    "terminator": "terminator",
    "marker": "selectable_marker",
    "marker_need": "selectable_marker",
    "selectable_marker_slot": "selectable_marker",
    "selectable_marker": "selectable_marker",
    "vector": "vector_backbone",
    "vector_backbone_need": "vector_backbone",
    "vector_backbone_slot": "vector_backbone",
    "backbone": "vector_backbone",
    "vector_backbone": "vector_backbone",
    "plant_context": "plant_host_context",
    "plant_host_context": "plant_host_context",
    "plant_species": "plant_host_context",
    "tissue_context": "plant_host_context",
    "expression_compartment": "plant_host_context",
    "tag": "tag",
    "signal_peptide": "signal_peptide",
    "localization": "subcellular_localization",
    "subcellular_localization": "subcellular_localization",
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _key(value: Any) -> str:
    clean = _text(value).casefold().replace("-", "_").replace("/", "_").replace(" ", "_")
    return re.sub(r"_+", "_", clean).strip("_")


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values: Sequence[Any] = re.split(r"[;\n|,]+", value)
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
        item_key = clean.casefold()
        if clean and item_key not in seen:
            values.append(clean)
            seen.add(item_key)
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


def _source_payload(source_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    source = _mapping(source_payload)
    if "plant_evidence_review_worksheet" in source:
        nested = _mapping(source.get("source_payload"))
        return nested if nested else source
    return source


def _worksheet_payload(
    source_payload: Mapping[str, Any] | None,
    evidence_worksheet: Mapping[str, Any] | None,
    *,
    route_context: Mapping[str, Any] | None,
    evidence_slot_match_result: Mapping[str, Any] | None,
    component_candidate_match_result: Mapping[str, Any] | None,
    gap_manual_review_queue_result: Mapping[str, Any] | None,
    evidence_placeholders: Sequence[Any] | None,
    component_slots: Sequence[Any] | None,
    review_items: Sequence[Any] | None,
) -> dict[str, Any]:
    worksheet = _mapping(evidence_worksheet)
    if worksheet:
        return worksheet
    source = _source_payload(source_payload)
    existing = _mapping(source.get("plant_evidence_review_worksheet"))
    if existing:
        return existing
    return build_plant_evidence_review_worksheet_payload(
        source,
        route_context=route_context,
        evidence_slot_match_result=evidence_slot_match_result,
        component_candidate_match_result=component_candidate_match_result,
        gap_manual_review_queue_result=gap_manual_review_queue_result,
        evidence_placeholders=evidence_placeholders,
        component_slots=component_slots,
        review_items=review_items,
        worksheet_context={
            "reuse_batch": TRACEABILITY_BATCH,
            "reuse_surface": "route_construct_traceability_readback",
        },
    )


def _construct_readback_payload(
    source_payload: Mapping[str, Any] | None,
    construct_draft_readback: Mapping[str, Any] | None,
    construct_draft: Mapping[str, Any] | None,
) -> dict[str, Any]:
    explicit = _mapping(construct_draft_readback)
    if explicit:
        return explicit
    source = _mapping(source_payload)
    for field in (
        "plant_construct_draft_readback",
        "construct_draft_readback",
        "construct_draft_readback_payload",
    ):
        existing = _mapping(source.get(field))
        if existing:
            return existing
    draft = _mapping(construct_draft) or _mapping(source.get("construct_draft"))
    if draft:
        return build_plant_construct_draft_readback(draft)
    package_slot_readback = _construct_readback_from_package(source)
    if package_slot_readback:
        return package_slot_readback
    return {}


def _construct_readback_from_package(source_payload: Mapping[str, Any]) -> dict[str, Any]:
    package = _mapping(source_payload.get("plant_review_package"))
    slot_summary = _mapping(package.get("construct_slot_summary"))
    rows: list[dict[str, Any]] = []
    for raw_slot in _sequence(slot_summary.get("slots")):
        slot = _mapping(raw_slot)
        if not slot:
            continue
        raw_slot_id = _text(slot.get("slot_id") or slot.get("slot_name"))
        slot_name = _canonical_slot(raw_slot_id) or raw_slot_id
        if not slot_name:
            continue
        evidence_ids = _list_texts(slot.get("evidence_ids"))
        component_ids = _list_texts(slot.get("component_ids"))
        missing_required = bool(slot.get("missing_required_slot"))
        if missing_required or not evidence_ids:
            status = "needs_source"
            safe_status_text = "missing source; manual review required"
        else:
            status = "needs_confirmation"
            safe_status_text = "needs confirmation; manual review required"
        rows.append(
            {
                "slot_name": slot_name,
                "display_label": _text(slot.get("slot_label"), slot_name.replace("_", " ").title()),
                "status": status,
                "safe_status_text": safe_status_text,
                "evidence_ids": evidence_ids,
                "source_ids": evidence_ids,
                "missing_reason": (
                    "required construct slot source context is not recorded"
                    if missing_required
                    else "construct slot component link needs manual review"
                    if component_ids and not evidence_ids
                    else ""
                ),
                "manual_review_required": True,
            }
        )
    if not rows:
        return {}
    return {
        "readback_status": "construct_draft_readback_from_review_package",
        "manual_review_required": True,
        "slot_rows": rows,
    }


def _section_rows(section: Mapping[str, Any], row_field: str = "rows") -> list[dict[str, Any]]:
    return [_mapping(row) for row in _sequence(section.get(row_field)) if isinstance(row, Mapping)]


def _route_context_rows(worksheet: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _section_rows(_mapping(worksheet.get("route_context_section")))


def _route_value(route_rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> str:
    wanted = {_key(field) for field in fields}
    for row in route_rows:
        field = _key(row.get("field"))
        if field in wanted:
            value = _recorded_text(row.get("value"))
            if value:
                return value
    return ""


def _recorded_text(value: Any) -> str:
    clean = _text(value)
    if _key(clean) in {"not_recorded", "none", "null"}:
        return ""
    return clean


def _route_rows_have_content(route_rows: Sequence[Mapping[str, Any]]) -> bool:
    return any(_recorded_text(row.get("value")) for row in route_rows)


def _route_context_id(
    source_payload: Mapping[str, Any] | None,
    route_context: Mapping[str, Any] | None,
    route_rows: Sequence[Mapping[str, Any]],
) -> str:
    source = _mapping(source_payload)
    route = _mapping(route_context) or _mapping(source.get("route_context")) or _mapping(source.get("route_draft"))
    return (
        _first_text(route, ("route_id", "context_id", "project_id"))
        or _route_value(route_rows, ("route_id", "context_id", "project_id"))
        or _text(source.get("route_id"))
        or _text(source.get("project_id"))
        or "unassigned_route_context"
    )


def _intent_summary(
    source_payload: Mapping[str, Any] | None,
    plant_project_intent: Mapping[str, Any] | str | None,
    route_rows: Sequence[Mapping[str, Any]],
) -> str:
    if isinstance(plant_project_intent, str):
        return _text(plant_project_intent, "plant project intent not recorded")
    intent = _mapping(plant_project_intent)
    source = _mapping(source_payload)
    if not intent:
        intent = _mapping(source.get("plant_project_intent")) or _mapping(source.get("user_intent"))
    if intent:
        parts = [
            _first_text(intent, ("target_name", "plant_goal", "goal", "intent_summary")),
            _first_text(intent, ("plant_host", "plant_context", "host_context")),
            _first_text(intent, ("tissue_context", "expression_purpose", "review_purpose")),
        ]
        summary = "; ".join(part for part in parts if part)
        if summary:
            return summary
    return (
        _route_value(route_rows, ("plant_goal", "goal", "route_label", "route_type"))
        or _text(source.get("intent_summary"))
        or "plant project intent not recorded"
    )


def _canonical_slot(value: Any) -> str:
    raw = _key(value)
    if raw.endswith("_slot"):
        raw = raw.removesuffix("_slot")
    return SLOT_ALIASES.get(raw, raw)


def _construct_slots(construct_readback: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_row in _sequence(construct_readback.get("slot_rows")):
        row = _mapping(raw_row)
        if not row:
            continue
        slot_name = _text(row.get("slot_name"))
        rows.append(
            {
                "slot_name": slot_name,
                "display_label": _first_text(row, ("display_label", "slot_label"), slot_name.replace("_", " ").title()),
                "status": _text(row.get("status")),
                "safe_status_text": _text(row.get("safe_status_text")),
                "evidence_ids": _list_texts(row.get("evidence_ids")),
                "source_ids": _list_texts(row.get("source_ids")),
                "missing_reason": _text(row.get("missing_reason")),
                "manual_review_required": row.get("manual_review_required") is not False,
            }
        )
    return rows


def _construct_slot_lookup(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in rows:
        slot_name = _text(row.get("slot_name"))
        if slot_name:
            lookup[_canonical_slot(slot_name)] = dict(row)
    return lookup


def _linked_construct_slot(component_row: Mapping[str, Any], lookup: Mapping[str, Mapping[str, Any]]) -> str:
    candidates = [
        component_row.get("linked_slot_id"),
        component_row.get("linked_slot_label"),
        component_row.get("component_type"),
        component_row.get("linked_component_label"),
    ]
    for candidate in candidates:
        key = _canonical_slot(candidate)
        if key in lookup:
            return _text(lookup[key].get("slot_name"), key)
    return ""


def _evidence_lookup(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        evidence_id = _text(row.get("evidence_item_id"))
        if evidence_id:
            lookup.setdefault(evidence_id.casefold(), []).append(dict(row))
    return lookup


def _component_label(row: Mapping[str, Any]) -> str:
    label = _text(row.get("linked_component_label"))
    component_id = _text(row.get("linked_component_id"))
    if label and component_id and label != component_id:
        return f"{component_id} | {label}"
    return component_id or label or "component not recorded"


def _component_slot(row: Mapping[str, Any]) -> str:
    slot_id = _text(row.get("linked_slot_id"))
    slot_label = _text(row.get("linked_slot_label"))
    if slot_id and slot_label and slot_id != slot_label:
        return f"{slot_id} | {slot_label}"
    return slot_id or slot_label or "component slot not recorded"


def _source_status(row: Mapping[str, Any]) -> str:
    placeholder = _text(row.get("source_or_provenance_placeholder"))
    gap_key = _key(placeholder)
    if not placeholder:
        return "source/provenance not recorded"
    if "missing" in gap_key or "placeholder_missing" in gap_key:
        return "source/provenance gap"
    return f"source/provenance recorded: {placeholder}"


def _status_requires_review(status: Any) -> bool:
    status_key = _key(status)
    return (
        not status_key
        or "manual_review" in status_key
        or "review_required" in status_key
        or "unreviewed" in status_key
        or "missing" in status_key
        or "needs" in status_key
        or "gap" in status_key
    )


def _combined_review_status(*values: Any) -> str:
    statuses = _list_texts([value for value in values if _text(value)])
    if not statuses:
        return "manual_review_required"
    if any(_status_requires_review(status) for status in statuses):
        return "manual_review_required"
    return statuses[0]


def _join_unique(*values: Any, fallback: str = "") -> str:
    collected: list[str] = []
    for value in values:
        collected.extend(_list_texts(value))
    if collected:
        return "; ".join(collected)
    return fallback


def _normal_review_item(raw_item: Mapping[str, Any], index: int) -> dict[str, Any]:
    evidence_ids = _list_texts(raw_item.get("linked_evidence_ids") or raw_item.get("evidence_ids"))
    component_ids = _list_texts(raw_item.get("linked_component_ids") or raw_item.get("component_ids"))
    return {
        "item_id": _text(raw_item.get("item_id"), f"handoff-review-item-{index:03d}"),
        "category": _text(raw_item.get("category"), "manual_review"),
        "severity": _text(raw_item.get("severity"), "review_required"),
        "linked_evidence_ids": evidence_ids,
        "linked_component_ids": component_ids,
        "linked_slot_id": _text(raw_item.get("linked_slot_id") or raw_item.get("slot_id")),
        "reason": _text(raw_item.get("reason") or raw_item.get("gap_reason") or raw_item.get("reviewer_action_hint")),
        "manual_review_note": _text(raw_item.get("manual_review_note") or raw_item.get("note")),
    }


def _handoff_review_items(
    source_payload: Mapping[str, Any] | None,
    worksheet: Mapping[str, Any],
    handoff_review_items: Sequence[Any] | None,
) -> list[dict[str, Any]]:
    source = _mapping(source_payload)
    raw_items: list[Any] = []
    if handoff_review_items is not None:
        raw_items.extend(_sequence(handoff_review_items))
    else:
        raw_items.extend(_sequence(source.get("required_review_items")))
        raw_items.extend(_sequence(source.get("missing_information_items")))
        gap_queue = _mapping(source.get("gap_manual_review_queue_result"))
        raw_items.extend(_sequence(gap_queue.get("review_items") or gap_queue.get("queue")))
    raw_items.extend(_section_rows(_mapping(worksheet.get("manual_review_section"))))

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for index, raw_item in enumerate(raw_items, start=1):
        item = _mapping(raw_item)
        if not item:
            continue
        normalized = _normal_review_item(item, index)
        identity = (
            normalized["item_id"],
            ",".join(normalized["linked_evidence_ids"]),
            ",".join(normalized["linked_component_ids"]),
            normalized["linked_slot_id"],
        )
        if identity in seen:
            continue
        rows.append(normalized)
        seen.add(identity)
    return sorted(
        rows,
        key=lambda row: (
            row["linked_slot_id"].casefold(),
            ",".join(row["linked_evidence_ids"]).casefold(),
            ",".join(row["linked_component_ids"]).casefold(),
            row["item_id"].casefold(),
        ),
    )


def _matching_review_items(
    review_items: Sequence[Mapping[str, Any]],
    *,
    evidence_id: str,
    component_id: str,
    component_slot_id: str,
) -> list[Mapping[str, Any]]:
    matches: list[Mapping[str, Any]] = []
    evidence_key = evidence_id.casefold()
    component_key = component_id.casefold()
    slot_key = _key(component_slot_id)
    for item in review_items:
        item_evidence = {value.casefold() for value in _list_texts(item.get("linked_evidence_ids"))}
        item_components = {value.casefold() for value in _list_texts(item.get("linked_component_ids"))}
        item_slot = _key(item.get("linked_slot_id"))
        if (
            (evidence_key and evidence_key in item_evidence)
            or (component_key and component_key in item_components)
            or (slot_key and slot_key == item_slot)
        ):
            matches.append(item)
    return matches


def _row_base(
    *,
    route_or_context_id: str,
    intent_summary: str,
    linked_evidence_id: str,
    linked_component: str,
    linked_component_slot: str,
    linked_construct_slot: str,
    source_or_provenance_status: str,
    review_status: str,
    gap_or_followup_reason: str,
    manual_review_note: str,
) -> dict[str, Any]:
    return {
        "trace_id": "",
        "route_or_context_id": route_or_context_id,
        "intent_summary": intent_summary,
        "linked_evidence_id": linked_evidence_id,
        "linked_component": linked_component,
        "linked_component_slot": linked_component_slot,
        "linked_construct_slot": linked_construct_slot,
        "source_or_provenance_status": source_or_provenance_status,
        "review_status": review_status,
        "gap_or_followup_reason": gap_or_followup_reason,
        "manual_review_note": manual_review_note,
    }


def _trace_rows(
    *,
    route_or_context_id: str,
    intent_summary: str,
    evidence_rows: Sequence[Mapping[str, Any]],
    component_rows: Sequence[Mapping[str, Any]],
    construct_rows: Sequence[Mapping[str, Any]],
    review_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    evidence_by_id = _evidence_lookup(evidence_rows)
    construct_lookup = _construct_slot_lookup(construct_rows)
    rows: list[dict[str, Any]] = []

    for component_row in component_rows:
        component_id = _text(component_row.get("linked_component_id"))
        component_slot_id = _text(component_row.get("linked_slot_id"))
        linked_evidence_ids = _list_texts(component_row.get("linked_evidence_ids")) or [""]
        construct_slot = _linked_construct_slot(component_row, construct_lookup)
        for evidence_id in linked_evidence_ids:
            evidence_row = (evidence_by_id.get(evidence_id.casefold()) or [{}])[0]
            matches = _matching_review_items(
                review_items,
                evidence_id=evidence_id,
                component_id=component_id,
                component_slot_id=component_slot_id,
            )
            rows.append(
                _row_base(
                    route_or_context_id=route_or_context_id,
                    intent_summary=intent_summary,
                    linked_evidence_id=evidence_id,
                    linked_component=_component_label(component_row),
                    linked_component_slot=_component_slot(component_row),
                    linked_construct_slot=construct_slot,
                    source_or_provenance_status=_source_status(component_row),
                    review_status=_combined_review_status(
                        component_row.get("review_status"),
                        evidence_row.get("review_status"),
                        [item.get("severity") for item in matches],
                    ),
                    gap_or_followup_reason=_join_unique(
                        component_row.get("gap_reason"),
                        evidence_row.get("gap_reason"),
                        [item.get("reason") for item in matches],
                        fallback="no recorded gap or follow-up reason",
                    ),
                    manual_review_note=_join_unique(
                        component_row.get("manual_review_note"),
                        evidence_row.get("manual_review_note"),
                        [item.get("manual_review_note") for item in matches],
                        fallback="manual review required",
                    ),
                )
            )

    if not rows:
        for evidence_row in evidence_rows:
            evidence_id = _text(evidence_row.get("evidence_item_id"))
            component_id = _text(evidence_row.get("linked_component_id"))
            component_slot_id = _text(evidence_row.get("linked_slot_id"))
            matches = _matching_review_items(
                review_items,
                evidence_id=evidence_id,
                component_id=component_id,
                component_slot_id=component_slot_id,
            )
            rows.append(
                _row_base(
                    route_or_context_id=route_or_context_id,
                    intent_summary=intent_summary,
                    linked_evidence_id=evidence_id,
                    linked_component=_text(evidence_row.get("linked_component_label") or component_id, "component not recorded"),
                    linked_component_slot=_component_slot(evidence_row),
                    linked_construct_slot="",
                    source_or_provenance_status=_source_status(evidence_row),
                    review_status=_combined_review_status(evidence_row.get("review_status"), [item.get("severity") for item in matches]),
                    gap_or_followup_reason=_join_unique(
                        evidence_row.get("gap_reason"),
                        [item.get("reason") for item in matches],
                        fallback="evidence traceability needs manual review",
                    ),
                    manual_review_note=_join_unique(
                        evidence_row.get("manual_review_note"),
                        [item.get("manual_review_note") for item in matches],
                        fallback="manual review required",
                    ),
                )
            )

    traced_construct_slots = {_text(row.get("linked_construct_slot")).casefold() for row in rows if _text(row.get("linked_construct_slot"))}
    for construct_row in construct_rows:
        slot_name = _text(construct_row.get("slot_name"))
        if not slot_name or slot_name.casefold() in traced_construct_slots:
            continue
        if not _status_requires_review(construct_row.get("status")) and _list_texts(construct_row.get("evidence_ids")):
            continue
        rows.append(
            _row_base(
                route_or_context_id=route_or_context_id,
                intent_summary=intent_summary,
                linked_evidence_id=", ".join(_list_texts(construct_row.get("evidence_ids"))),
                linked_component="component not recorded",
                linked_component_slot="component slot not recorded",
                linked_construct_slot=slot_name,
                source_or_provenance_status="source/provenance not recorded",
                review_status=_combined_review_status(construct_row.get("status")),
                gap_or_followup_reason=_text(construct_row.get("missing_reason"), "construct draft slot needs traceability review"),
                manual_review_note="manual review required",
            )
        )

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row["route_or_context_id"].casefold(),
            row["linked_construct_slot"].casefold(),
            row["linked_component_slot"].casefold(),
            row["linked_evidence_id"].casefold(),
            row["linked_component"].casefold(),
            row["gap_or_followup_reason"].casefold(),
        ),
    )
    for index, row in enumerate(sorted_rows, start=1):
        row["trace_id"] = (
            f"r128-trace-{index:03d}-"
            f"{_key(row.get('route_or_context_id')) or 'route'}-"
            f"{_key(row.get('linked_construct_slot')) or _key(row.get('linked_component_slot')) or 'slot'}-"
            f"{_key(row.get('linked_evidence_id')) or _key(row.get('linked_component')) or 'item'}"
        )
    return sorted_rows


def _summary(rows: Sequence[Mapping[str, Any]], construct_rows: Sequence[Mapping[str, Any]], has_content: bool) -> dict[str, Any]:
    return {
        "trace_row_count": len(rows),
        "evidence_link_count": sum(1 for row in rows if _text(row.get("linked_evidence_id"))),
        "component_slot_link_count": sum(1 for row in rows if _text(row.get("linked_component_slot"))),
        "construct_slot_link_count": sum(1 for row in rows if _text(row.get("linked_construct_slot"))),
        "construct_slot_count": len(construct_rows),
        "gap_or_followup_count": sum(
            1
            for row in rows
            if _status_requires_review(row.get("review_status"))
            or "gap" in _key(row.get("source_or_provenance_status"))
            or "not_recorded" in _key(row.get("source_or_provenance_status"))
        ),
        "manual_review_required": True,
        "empty_input": not has_content,
    }


def build_plant_route_construct_traceability_readback(
    source_payload: Mapping[str, Any] | None = None,
    *,
    plant_project_intent: Mapping[str, Any] | str | None = None,
    route_context: Mapping[str, Any] | None = None,
    evidence_worksheet: Mapping[str, Any] | None = None,
    evidence_slot_match_result: Mapping[str, Any] | None = None,
    component_candidate_match_result: Mapping[str, Any] | None = None,
    gap_manual_review_queue_result: Mapping[str, Any] | None = None,
    evidence_placeholders: Sequence[Any] | None = None,
    component_slots: Sequence[Any] | None = None,
    review_items: Sequence[Any] | None = None,
    construct_draft_readback: Mapping[str, Any] | None = None,
    construct_draft: Mapping[str, Any] | None = None,
    handoff_review_items: Sequence[Any] | None = None,
    readback_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic read-only plant route-to-construct traceability readback."""
    worksheet = _worksheet_payload(
        source_payload,
        evidence_worksheet,
        route_context=route_context,
        evidence_slot_match_result=evidence_slot_match_result,
        component_candidate_match_result=component_candidate_match_result,
        gap_manual_review_queue_result=gap_manual_review_queue_result,
        evidence_placeholders=evidence_placeholders,
        component_slots=component_slots,
        review_items=review_items,
    )
    construct_readback = _construct_readback_payload(source_payload, construct_draft_readback, construct_draft)
    route_rows = _route_context_rows(worksheet)
    route_or_context_id = _route_context_id(source_payload, route_context, route_rows)
    intent = _intent_summary(source_payload, plant_project_intent, route_rows)
    evidence_rows = _section_rows(_mapping(worksheet.get("evidence_review_section")))
    component_rows = _section_rows(_mapping(worksheet.get("component_slot_linkage_section")))
    construct_rows = _construct_slots(construct_readback)
    handoff_rows = _handoff_review_items(source_payload, worksheet, handoff_review_items)
    trace_rows = _trace_rows(
        route_or_context_id=route_or_context_id,
        intent_summary=intent,
        evidence_rows=evidence_rows,
        component_rows=component_rows,
        construct_rows=construct_rows,
        review_items=handoff_rows,
    )
    has_content = bool(
        _route_rows_have_content(route_rows)
        or evidence_rows
        or component_rows
        or construct_rows
        or handoff_rows
    )

    return _plain_value(
        {
            "traceability_schema_version": TRACEABILITY_SCHEMA_VERSION,
            "traceability_batch": TRACEABILITY_BATCH,
            "traceability_status": TRACEABILITY_STATUS_READY if has_content else TRACEABILITY_STATUS_EMPTY,
            "read_only": True,
            "plant_scope_only": True,
            "manual_review_required": True,
            "reuse_source": "plant_evidence_review_worksheet_presenter",
            "stable_keys": {
                "traceability_row_keys": list(TRACEABILITY_ROW_KEYS),
                "construct_slot_row_keys": list(CONSTRUCT_SLOT_ROW_KEYS),
                "handoff_review_row_keys": list(HANDOFF_REVIEW_ROW_KEYS),
            },
            "summary": _summary(trace_rows, construct_rows, has_content),
            "intent_section": {
                "columns": ["field", "value"],
                "rows": [
                    {"field": "intent_summary", "value": intent},
                    {"field": "route_or_context_id", "value": route_or_context_id},
                ],
            },
            "route_context_section": {
                "columns": ["field", "value"],
                "rows": route_rows,
            },
            "construct_slot_section": {
                "columns": list(CONSTRUCT_SLOT_ROW_KEYS),
                "rows": construct_rows,
            },
            "handoff_review_section": {
                "columns": list(HANDOFF_REVIEW_ROW_KEYS),
                "rows": handoff_rows,
            },
            "traceability_section": {
                "columns": list(TRACEABILITY_ROW_KEYS),
                "rows": trace_rows,
            },
            "boundary_section": {
                "boundary_note": TRACEABILITY_BOUNDARY_NOTE,
                "allowed_output_categories": [
                    "documentation_readback",
                    "traceability_relationships",
                    "gap_review_status",
                    "manual_review_status",
                ],
            },
            "readback_context": _plain_value(readback_context or {}),
            "warnings": [] if has_content else ["traceability input warning: no readable plant route, evidence, component, or construct payload was provided"],
        }
    )
