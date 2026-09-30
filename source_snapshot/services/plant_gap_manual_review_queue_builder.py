from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import re
from typing import Any

from services.plant_review_module_card_schema import (
    BLOCKED_OUTPUT_CATEGORIES,
    CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
)


QUEUE_BOUNDARY_NOTE = (
    "Documentation-only plant gap and manual review queue. It preserves route, "
    "evidence, component, source, and provenance traceability for manual review "
    "without creating sequences, protocols, final components, final designs, "
    "biological ranking, outcome forecasts, or downstream-use judgments."
)

QUEUE_STATUS_SUPPORTED = "plant_gap_manual_review_queue"
QUEUE_STATUS_FAIL_SAFE = "fail_safe_manual_review_queue"
QUEUE_STATUS_UNSUPPORTED = "unsupported_plant_gap_manual_review_queue"

SEVERITY_BLOCKER = "blocker"
SEVERITY_REVIEW_REQUIRED = "review_required"
SEVERITY_INFORMATIONAL = "informational"

CATEGORY_ROUTE_CONTEXT_GAP = "route_context_gap"
CATEGORY_REQUIRED_SLOT_GAP = "required_slot_gap"
CATEGORY_EVIDENCE_GAP = "evidence_gap"
CATEGORY_COMPONENT_GAP = "component_gap"
CATEGORY_PROVENANCE_GAP = "provenance_gap"
CATEGORY_AMBIGUITY = "ambiguity_or_duplicate_review"
CATEGORY_BLOCKED_OUTPUT = "blocked_output_boundary"
CATEGORY_UNSUPPORTED_SCOPE = "unsupported_scope"

_CATEGORY_PRIORITY: dict[str, int] = {
    CATEGORY_UNSUPPORTED_SCOPE: 10,
    CATEGORY_ROUTE_CONTEXT_GAP: 20,
    CATEGORY_REQUIRED_SLOT_GAP: 30,
    CATEGORY_EVIDENCE_GAP: 40,
    CATEGORY_COMPONENT_GAP: 50,
    CATEGORY_PROVENANCE_GAP: 60,
    CATEGORY_AMBIGUITY: 70,
    CATEGORY_BLOCKED_OUTPUT: 80,
}

_UNSUPPORTED_ROUTE_STATUSES: tuple[str, ...] = (
    "unsupported_non_plant_scope",
    "mixed_scope_manual_review",
    "unknown_or_ambiguous",
)

_NON_PLANT_ROUTE_MARKERS: tuple[str, ...] = (
    "unsupported_non_plant",
    "bacterial",
    "bacteria",
    "e_coli",
    "ecoli",
    "escherichia",
    "yeast",
    "mammalian",
    "cho",
    "hek293",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    clean = _text(value).casefold().replace("-", "_").replace("/", "_").replace(" ", "_")
    return re.sub(r"_+", "_", clean).strip("_")


def _searchable(value: Any) -> str:
    return " ".join(_text(value).casefold().replace("-", " ").replace("_", " ").split())


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values: Iterable[Any] = re.split(r"[;\n|,]+", value)
    elif isinstance(value, Mapping):
        raw_values = sorted(value.keys(), key=lambda item: str(item))
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_values = list(value)
    else:
        raw_values = [value] if _text(value) else []
    return [_text(item) for item in raw_values if _text(item)]


def _unique_texts(values: Iterable[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            unique.append(clean)
            seen.add(key)
    return unique


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _route_context_blob(route_draft: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for field in ("route_id", "route_name", "route_type", "draft_status", "boundary_note"):
        parts.append(_text(route_draft.get(field)))
    for field in ("plant_context", "target_summary", "intent_summary", "route_match"):
        value = route_draft.get(field)
        if isinstance(value, Mapping):
            parts.extend(_text(item) for item in value.values())
    template = route_draft.get("selected_template")
    if isinstance(template, Mapping):
        for field in ("route_id", "route_type", "display_name", "plant_context"):
            parts.append(_text(template.get(field)))
        for field in ("trigger_terms", "supported_host_contexts"):
            parts.extend(_list_texts(template.get(field)))
    return _searchable(" ".join(part for part in parts if part))


def _route_scope_status(route_draft: Mapping[str, Any]) -> str:
    context = route_draft.get("plant_context")
    if isinstance(context, Mapping):
        return _text(context.get("scope_status"))
    return ""


def _route_match_status(route_draft: Mapping[str, Any]) -> str:
    route_match = route_draft.get("route_match")
    if isinstance(route_match, Mapping):
        return _text(route_match.get("route_match_status"))
    return ""


def _is_unsupported_route(route_draft: Mapping[str, Any]) -> bool:
    route_id = _key(route_draft.get("route_id"))
    route_type = _text(route_draft.get("route_type"))
    template = route_draft.get("selected_template")
    scope_status = _route_scope_status(route_draft)
    route_match_status = _route_match_status(route_draft)
    blob = _route_context_blob(route_draft)

    if route_id.startswith("unsupported"):
        return True
    if route_type and route_type != CURRENT_ACTIVE_PLANT_ROUTE_TYPE:
        return True
    if route_match_status in _UNSUPPORTED_ROUTE_STATUSES and route_id.startswith("unsupported"):
        return True
    if scope_status and scope_status not in {"plant_scope_review", "missing_plant_route_context"}:
        return True
    return any(marker in blob for marker in _NON_PLANT_ROUTE_MARKERS)


def _has_route_context(route_draft: Mapping[str, Any]) -> bool:
    route_id = _text(route_draft.get("route_id"))
    template = route_draft.get("selected_template")
    if not route_id or route_id.startswith("unknown"):
        return False
    if not isinstance(template, Mapping) or not template:
        return False
    if _route_match_status(route_draft) == "unknown_or_ambiguous":
        return False
    return True


def _module_by_slot(route_draft: Mapping[str, Any]) -> dict[str, str]:
    by_slot: dict[str, str] = {}
    for module in route_draft.get("module_card_summaries") or route_draft.get("required_modules") or []:
        if not isinstance(module, Mapping):
            continue
        module_id = _text(module.get("module_id"))
        for slot_id in _list_texts(module.get("required_slots")):
            by_slot.setdefault(_key(slot_id), module_id)
    return by_slot


def _required_slots(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source_field in ("required_construct_slots", "required_slots"):
        for slot in route_draft.get(source_field) or []:
            if not isinstance(slot, Mapping):
                continue
            slot_id = _text(slot.get("slot_id") or slot.get("slot_name") or slot.get("id") or slot.get("name"))
            slot_key = _key(slot_id)
            if not slot_key or slot_key in seen:
                continue
            slots.append(
                {
                    "slot_id": slot_key,
                    "slot_label": _text(slot.get("slot_label") or slot.get("label") or slot_id),
                    "slot_status": _text(slot.get("status") or slot.get("slot_status")),
                    "slot_value": _text(slot.get("value") or slot.get("slot_value")),
                    "slot_sources": [source_field],
                }
            )
            seen.add(slot_key)

    template = route_draft.get("selected_template")
    if isinstance(template, Mapping):
        for slot_id in _list_texts(template.get("required_slots")):
            slot_key = _key(slot_id)
            if slot_key and slot_key not in seen:
                slots.append(
                    {
                        "slot_id": slot_key,
                        "slot_label": _text(slot_id),
                        "slot_status": "",
                        "slot_value": "",
                        "slot_sources": ["selected_template.required_slots"],
                    }
                )
                seen.add(slot_key)
    return slots


def _slot_by_id(result: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(result, Mapping):
        return by_id
    for source_field in ("slots", "slot_matches"):
        for slot in result.get(source_field) or []:
            if not isinstance(slot, Mapping):
                continue
            slot_id = _key(slot.get("slot_id") or slot.get("slot_name"))
            if slot_id and slot_id not in by_id:
                by_id[slot_id] = dict(slot)
    return by_id


def _evidence_ids_from_slot(slot: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(slot, Mapping):
        return []
    ids: list[str] = []
    ids.extend(_list_texts(slot.get("matched_evidence_ids")))
    for candidate_key in ("candidate_evidence", "candidate_records", "candidates"):
        for candidate in slot.get(candidate_key) or []:
            if isinstance(candidate, Mapping):
                ids.append(_text(candidate.get("record_id") or candidate.get("evidence_id") or candidate.get("source_id")))
    return _unique_texts(ids)


def _component_ids_from_slot(slot: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(slot, Mapping):
        return []
    ids: list[str] = []
    for candidate in slot.get("candidate_components") or slot.get("candidate_records") or slot.get("candidates") or []:
        if isinstance(candidate, Mapping):
            ids.append(_text(candidate.get("component_id") or candidate.get("asset_id") or candidate.get("part_id")))
    return _unique_texts(ids)


def _candidate_source_refs(candidate: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    traceability = candidate.get("traceability")
    if isinstance(traceability, Mapping):
        for key in ("source_label", "source_reference", "source_database", "source_accession", "source_record_id"):
            refs.append(_text(traceability.get(key)))
    for key in ("source_label", "source_reference", "source_database", "source_accession", "source_record_id"):
        refs.append(_text(candidate.get(key)))
    return _unique_texts(refs)


def _candidate_missing_provenance(candidate: Mapping[str, Any]) -> bool:
    completeness = candidate.get("source_completeness")
    if isinstance(completeness, Mapping):
        if completeness.get("has_source") is False or completeness.get("has_provenance") is False:
            return True
        missing = {_key(item) for item in _list_texts(completeness.get("missing_fields"))}
        if missing.intersection({"source", "provenance", "evidence_link"}):
            return True
    reasons = {_key(item) for item in _list_texts(candidate.get("manual_review_reasons"))}
    status = _key(candidate.get("provenance_status"))
    return "missing_provenance_or_source" in reasons or status in {
        "source_provenance_missing",
        "source_recorded_provenance_missing",
    }


def _candidate_duplicate_or_alias(candidate: Mapping[str, Any]) -> bool:
    if bool(candidate.get("duplicate_or_alias_flag")):
        return True
    reasons = {_key(item) for item in _list_texts(candidate.get("manual_review_reasons"))}
    return bool(reasons.intersection({"duplicate_or_alias_review", "ambiguous_evidence_context"}))


def _upstream_reasons(*results: Mapping[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    for result in results:
        if not isinstance(result, Mapping):
            continue
        reasons.extend(_list_texts(result.get("manual_review_reasons")))
        reasons.extend(_list_texts(result.get("missing_context")))
        for item in result.get("manual_review_items") or []:
            if isinstance(item, Mapping):
                reasons.append(_text(item.get("review_type")))
                reasons.append(_text(item.get("note")))
    return _unique_texts(reasons)


def _blocked_outputs(route_draft: Mapping[str, Any] | None) -> list[str]:
    if isinstance(route_draft, Mapping):
        outputs = _list_texts(route_draft.get("blocked_outputs"))
        template = route_draft.get("selected_template")
        if isinstance(template, Mapping):
            outputs.extend(_list_texts(template.get("blocked_outputs")))
        if outputs:
            return _unique_texts(outputs)
    return list(BLOCKED_OUTPUT_CATEGORIES)


def _item(
    *,
    category: str,
    severity: str,
    route_id: str,
    note: str,
    module_id: str = "",
    slot_id: str = "",
    slot_label: str = "",
    evidence_ids: Sequence[str] | None = None,
    component_ids: Sequence[str] | None = None,
    source_references: Sequence[str] | None = None,
    provenance_references: Sequence[str] | None = None,
    upstream_review_reasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "item_id": "",
        "category": category,
        "severity": severity,
        "priority": _CATEGORY_PRIORITY[category],
        "route_id": route_id,
        "module_id": module_id,
        "slot_id": slot_id,
        "slot_label": slot_label,
        "evidence_ids": _unique_texts(evidence_ids or []),
        "component_ids": _unique_texts(component_ids or []),
        "source_references": _unique_texts(source_references or []),
        "provenance_references": _unique_texts(provenance_references or []),
        "upstream_review_reasons": _unique_texts(upstream_review_reasons or []),
        "note": note,
    }


def _sort_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sorted_items = sorted(
        (dict(item) for item in items),
        key=lambda item: (
            int(item.get("priority") or 0),
            _text(item.get("route_id")).casefold(),
            _text(item.get("module_id")).casefold(),
            _text(item.get("slot_id")).casefold(),
            ",".join(_list_texts(item.get("evidence_ids"))).casefold(),
            ",".join(_list_texts(item.get("component_ids"))).casefold(),
            _text(item.get("note")).casefold(),
        ),
    )
    for index, item in enumerate(sorted_items, start=1):
        category = _key(item.get("category")) or "review_item"
        slot = _key(item.get("slot_id")) or "route"
        component = _key(",".join(_list_texts(item.get("component_ids")))) or "context"
        item["item_id"] = f"r72-{index:03d}-{category}-{slot}-{component}"
    return sorted_items


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    blocker_count = sum(1 for item in items if item.get("severity") == SEVERITY_BLOCKER)
    review_count = sum(1 for item in items if item.get("severity") == SEVERITY_REVIEW_REQUIRED)
    info_count = sum(1 for item in items if item.get("severity") == SEVERITY_INFORMATIONAL)
    return {
        "total_items": len(items),
        "blocker_count": blocker_count,
        "review_required_count": review_count,
        "informational_count": info_count,
        "missing_required_slot_count": sum(1 for item in items if item.get("category") == CATEGORY_REQUIRED_SLOT_GAP),
        "evidence_gap_count": sum(1 for item in items if item.get("category") == CATEGORY_EVIDENCE_GAP),
        "component_gap_count": sum(1 for item in items if item.get("category") == CATEGORY_COMPONENT_GAP),
        "provenance_gap_count": sum(1 for item in items if item.get("category") == CATEGORY_PROVENANCE_GAP),
        "manual_review_required": True,
    }


def build_plant_gap_manual_review_queue(
    route_draft: Mapping[str, Any] | None,
    evidence_slot_match_result: Mapping[str, Any] | None,
    component_candidate_match_result: Mapping[str, Any] | None,
    user_context: Mapping[str, Any] | str | None = None,
) -> dict[str, Any]:
    """Build a deterministic plant gap and manual-review queue from R68-R70 outputs."""
    route = dict(route_draft) if isinstance(route_draft, Mapping) else {}
    evidence_result = dict(evidence_slot_match_result) if isinstance(evidence_slot_match_result, Mapping) else {}
    component_result = dict(component_candidate_match_result) if isinstance(component_candidate_match_result, Mapping) else {}
    route_id = _text(route.get("route_id"))
    route_type = _text(route.get("route_type"))
    upstream_reasons = _upstream_reasons(route, evidence_result, component_result)
    items: list[dict[str, Any]] = []

    slots = _required_slots(route)
    module_by_slot = _module_by_slot(route)
    evidence_by_slot = _slot_by_id(evidence_result)
    component_by_slot = _slot_by_id(component_result)

    if not route:
        items.append(
            _item(
                category=CATEGORY_ROUTE_CONTEXT_GAP,
                severity=SEVERITY_BLOCKER,
                route_id="",
                note="Route context is missing; provide an R68 plant route draft before queue review.",
                upstream_review_reasons=upstream_reasons,
            )
        )
    elif _is_unsupported_route(route):
        items.append(
            _item(
                category=CATEGORY_UNSUPPORTED_SCOPE,
                severity=SEVERITY_BLOCKER,
                route_id=route_id,
                note="Route draft is outside the supported Plant Expression Vector review scope.",
                upstream_review_reasons=upstream_reasons,
            )
        )
    elif not _has_route_context(route):
        items.append(
            _item(
                category=CATEGORY_ROUTE_CONTEXT_GAP,
                severity=SEVERITY_BLOCKER,
                route_id=route_id,
                note="Route or template context is missing or ambiguous for plant queue review.",
                upstream_review_reasons=upstream_reasons,
            )
        )

    if route and not slots:
        items.append(
            _item(
                category=CATEGORY_ROUTE_CONTEXT_GAP,
                severity=SEVERITY_BLOCKER,
                route_id=route_id,
                note="Required route slots are missing from the route draft context.",
                upstream_review_reasons=upstream_reasons,
            )
        )

    for slot in slots:
        slot_id = _text(slot.get("slot_id"))
        slot_label = _text(slot.get("slot_label"))
        module_id = module_by_slot.get(slot_id, "")
        slot_status = _key(slot.get("slot_status"))
        if slot_status == "missing" or not _text(slot.get("slot_value")) and slot_id in {_key(item) for item in _list_texts(route.get("missing_fields"))}:
            items.append(
                _item(
                    category=CATEGORY_REQUIRED_SLOT_GAP,
                    severity=SEVERITY_REVIEW_REQUIRED,
                    route_id=route_id,
                    module_id=module_id,
                    slot_id=slot_id,
                    slot_label=slot_label,
                    note="Required slot is not filled in the route draft and needs source-backed documentation review.",
                    upstream_review_reasons=upstream_reasons,
                )
            )

        evidence_slot = evidence_by_slot.get(slot_id)
        evidence_ids = _evidence_ids_from_slot(evidence_slot)
        evidence_status = _key(evidence_slot.get("slot_status")) if isinstance(evidence_slot, Mapping) else ""
        if not evidence_slot or evidence_status == "missing_evidence" or not evidence_ids:
            items.append(
                _item(
                    category=CATEGORY_EVIDENCE_GAP,
                    severity=SEVERITY_REVIEW_REQUIRED,
                    route_id=route_id,
                    module_id=module_id,
                    slot_id=slot_id,
                    slot_label=slot_label,
                    note="Slot has no matched source evidence in the R69 result.",
                    upstream_review_reasons=_unique_texts(
                        [*upstream_reasons, *_list_texts(evidence_slot.get("manual_review_reasons"))]
                    )
                    if isinstance(evidence_slot, Mapping)
                    else upstream_reasons,
                )
            )

        component_slot = component_by_slot.get(slot_id)
        component_ids = _component_ids_from_slot(component_slot)
        component_status = _key(component_slot.get("slot_status")) if isinstance(component_slot, Mapping) else ""
        if evidence_ids and (
            not component_slot
            or component_status == "missing_component_candidate"
            or not component_ids
        ):
            items.append(
                _item(
                    category=CATEGORY_COMPONENT_GAP,
                    severity=SEVERITY_REVIEW_REQUIRED,
                    route_id=route_id,
                    module_id=module_id,
                    slot_id=slot_id,
                    slot_label=slot_label,
                    evidence_ids=evidence_ids,
                    note="Slot has matched evidence but no component candidate in the R70 result.",
                    upstream_review_reasons=_unique_texts(
                        [*upstream_reasons, *_list_texts(component_slot.get("manual_review_reasons"))]
                    )
                    if isinstance(component_slot, Mapping)
                    else upstream_reasons,
                )
            )

        if isinstance(component_slot, Mapping):
            for candidate in component_slot.get("candidate_components") or []:
                if not isinstance(candidate, Mapping):
                    continue
                candidate_id = _text(candidate.get("component_id"))
                candidate_evidence_ids = _list_texts(candidate.get("matched_evidence_ids")) or evidence_ids
                source_refs = _candidate_source_refs(candidate)
                if _candidate_missing_provenance(candidate):
                    items.append(
                        _item(
                            category=CATEGORY_PROVENANCE_GAP,
                            severity=SEVERITY_REVIEW_REQUIRED,
                            route_id=route_id,
                            module_id=module_id,
                            slot_id=slot_id,
                            slot_label=slot_label,
                            evidence_ids=candidate_evidence_ids,
                            component_ids=[candidate_id],
                            source_references=source_refs,
                            provenance_references=[_text(candidate.get("provenance_status"))],
                            note="Component candidate is retained for review but source or provenance metadata is incomplete.",
                            upstream_review_reasons=_unique_texts(
                                [*upstream_reasons, *_list_texts(candidate.get("manual_review_reasons"))]
                            ),
                        )
                    )
                if _candidate_duplicate_or_alias(candidate):
                    items.append(
                        _item(
                            category=CATEGORY_AMBIGUITY,
                            severity=SEVERITY_REVIEW_REQUIRED,
                            route_id=route_id,
                            module_id=module_id,
                            slot_id=slot_id,
                            slot_label=slot_label,
                            evidence_ids=candidate_evidence_ids,
                            component_ids=[candidate_id],
                            source_references=source_refs,
                            provenance_references=[_text(candidate.get("provenance_status"))],
                            note="Component candidate has duplicate, alias, or ambiguous-source signals and must not be auto-merged.",
                            upstream_review_reasons=_unique_texts(
                                [*upstream_reasons, *_list_texts(candidate.get("manual_review_reasons"))]
                            ),
                        )
                    )

    blocked_outputs = _blocked_outputs(route)
    if blocked_outputs:
        items.append(
            _item(
                category=CATEGORY_BLOCKED_OUTPUT,
                severity=SEVERITY_INFORMATIONAL,
                route_id=route_id,
                note="Blocked output categories remain boundary reminders for this documentation-only queue.",
                source_references=blocked_outputs,
                upstream_review_reasons=upstream_reasons,
            )
        )

    sorted_items = _sort_items(items)
    status = QUEUE_STATUS_SUPPORTED
    if not route:
        status = QUEUE_STATUS_FAIL_SAFE
    elif any(item["category"] == CATEGORY_UNSUPPORTED_SCOPE for item in sorted_items):
        status = QUEUE_STATUS_UNSUPPORTED

    context_metadata = _plain_value(user_context or {})
    return {
        "queue_status": status,
        "plant_scope_supported": status == QUEUE_STATUS_SUPPORTED,
        "manual_review_required": True,
        "final_design_present": False,
        "active_component_selection": False,
        "active_plant_design_route": False,
        "route_context": {
            "route_id": route_id,
            "route_type": route_type,
            "route_status": _text(route.get("draft_status")),
            "scope_status": _route_scope_status(route),
        },
        "context_metadata": context_metadata,
        "review_categories": [
            CATEGORY_ROUTE_CONTEXT_GAP,
            CATEGORY_REQUIRED_SLOT_GAP,
            CATEGORY_EVIDENCE_GAP,
            CATEGORY_COMPONENT_GAP,
            CATEGORY_PROVENANCE_GAP,
            CATEGORY_AMBIGUITY,
            CATEGORY_BLOCKED_OUTPUT,
            CATEGORY_UNSUPPORTED_SCOPE,
        ],
        "review_items": sorted_items,
        "queue": sorted_items,
        "upstream_manual_review_reasons": upstream_reasons,
        "blocked_output_categories": blocked_outputs,
        "summary": _summary(sorted_items),
        "boundary_note": QUEUE_BOUNDARY_NOTE,
    }
