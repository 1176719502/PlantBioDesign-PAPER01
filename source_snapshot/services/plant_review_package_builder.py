from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import re
from typing import Any

from services.plant_gap_manual_review_queue_builder import (
    CATEGORY_AMBIGUITY,
    CATEGORY_BLOCKED_OUTPUT,
    CATEGORY_COMPONENT_GAP,
    CATEGORY_EVIDENCE_GAP,
    CATEGORY_PROVENANCE_GAP,
    CATEGORY_REQUIRED_SLOT_GAP,
    CATEGORY_ROUTE_CONTEXT_GAP,
    CATEGORY_UNSUPPORTED_SCOPE,
    SEVERITY_BLOCKER,
    SEVERITY_INFORMATIONAL,
    SEVERITY_REVIEW_REQUIRED,
)
from services.plant_review_module_card_registry import get_plant_review_module_card_by_id
from services.plant_review_module_card_schema import (
    BLOCKED_OUTPUT_CATEGORIES,
    CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
)


PACKAGE_BUILDER_VERSION = "v2.7-r74"
PACKAGE_SCHEMA_VERSION = "plant_review_package.v2.7.r74"
PACKAGE_TYPE = "plant_review_package"

PACKAGE_BOUNDARY_NOTE = (
    "Documentation-only Plant review package for manual review. It preserves route, "
    "slot, evidence, component, gap, and traceability context without selecting final "
    "components, generating sequences or protocols, predicting outcomes, optimizing "
    "routes, validating designs, or judging wet-lab use."
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

_UNSUPPORTED_ROUTE_STATUSES: tuple[str, ...] = (
    "unsupported_non_plant_scope",
    "mixed_scope_manual_review",
    "unknown_or_ambiguous",
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


def _first_text(record: Mapping[str, Any], fields: Sequence[str]) -> str:
    for field in fields:
        value = _text(record.get(field))
        if value:
            return value
    return ""


def _route_context_blob(route_draft: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for field in ("route_id", "route_label", "route_name", "route_type", "route_status", "draft_status", "boundary_note"):
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


def _route_match_status(route_draft: Mapping[str, Any]) -> str:
    route_match = route_draft.get("route_match")
    if isinstance(route_match, Mapping):
        return _text(route_match.get("route_match_status"))
    return ""


def _route_scope_status(route_draft: Mapping[str, Any]) -> str:
    context = route_draft.get("plant_context")
    if isinstance(context, Mapping):
        return _text(context.get("scope_status"))
    return ""


def _is_unsupported_route(route_draft: Mapping[str, Any]) -> bool:
    route_id = _key(route_draft.get("route_id"))
    route_type = _text(route_draft.get("route_type"))
    route_match_status = _route_match_status(route_draft)
    scope_status = _route_scope_status(route_draft)
    blob = _route_context_blob(route_draft)

    if route_id.startswith("unsupported"):
        return True
    if route_type and route_type != CURRENT_ACTIVE_PLANT_ROUTE_TYPE:
        return True
    if route_match_status in _UNSUPPORTED_ROUTE_STATUSES:
        return True
    if scope_status and scope_status not in {"plant_scope_review", "missing_plant_route_context"}:
        return True
    return any(marker in blob for marker in _NON_PLANT_ROUTE_MARKERS)


def _required_flag(slot: Mapping[str, Any]) -> bool:
    for field in ("required", "is_required", "required_slot"):
        if isinstance(slot.get(field), bool):
            return bool(slot.get(field))
    optional = slot.get("optional")
    if isinstance(optional, bool):
        return not optional
    return True


def _slot_id(slot: Mapping[str, Any]) -> str:
    return _key(slot.get("slot_id") or slot.get("slot_name") or slot.get("id") or slot.get("name"))


def _slot_label(slot: Mapping[str, Any], slot_id: str) -> str:
    return _text(slot.get("slot_label") or slot.get("label") or slot.get("display_name") or slot_id)


def _evidence_ids_from_slot(slot: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(slot, Mapping):
        return []
    ids: list[str] = []
    ids.extend(_list_texts(slot.get("matched_evidence_ids")))
    ids.extend(_list_texts(slot.get("evidence_ids")))
    for candidate_key in ("candidate_evidence", "candidate_records", "candidates"):
        for candidate in slot.get(candidate_key) or []:
            if isinstance(candidate, Mapping):
                ids.append(_text(candidate.get("record_id") or candidate.get("evidence_id") or candidate.get("source_id")))
    return _unique_texts(ids)


def _component_ids_from_slot(slot: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(slot, Mapping):
        return []
    ids: list[str] = []
    ids.extend(_list_texts(slot.get("component_ids")))
    for candidate in slot.get("candidate_components") or slot.get("candidate_records") or slot.get("candidates") or []:
        if isinstance(candidate, Mapping):
            ids.append(_text(candidate.get("component_id") or candidate.get("asset_id") or candidate.get("part_id")))
    return _unique_texts(ids)


def _slots_by_id(result: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    if not isinstance(result, Mapping):
        return by_id
    for source_field in ("slots", "slot_matches"):
        for slot in result.get(source_field) or []:
            if not isinstance(slot, Mapping):
                continue
            slot_id = _slot_id(slot)
            if slot_id and slot_id not in by_id:
                by_id[slot_id] = slot
    return by_id


def _collect_required_slots(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source_field in ("required_construct_slots", "required_slots", "construct_slots"):
        for raw_slot in route_draft.get(source_field) or []:
            if not isinstance(raw_slot, Mapping):
                continue
            slot_id = _slot_id(raw_slot)
            if not slot_id or slot_id in seen:
                continue
            slots.append(
                {
                    "slot_id": slot_id,
                    "slot_label": _slot_label(raw_slot, slot_id),
                    "slot_status": _text(raw_slot.get("slot_status") or raw_slot.get("status")),
                    "required": _required_flag(raw_slot),
                    "optional": not _required_flag(raw_slot),
                    "missing_required_slot": bool(raw_slot.get("missing_required_slot")),
                    "slot_sources": [source_field],
                }
            )
            seen.add(slot_id)

    template = route_draft.get("selected_template")
    if isinstance(template, Mapping):
        for raw_slot_id in _list_texts(template.get("required_slots")):
            slot_id = _key(raw_slot_id)
            if slot_id and slot_id not in seen:
                slots.append(
                    {
                        "slot_id": slot_id,
                        "slot_label": _text(raw_slot_id),
                        "slot_status": "",
                        "required": True,
                        "optional": False,
                        "missing_required_slot": False,
                        "slot_sources": ["selected_template.required_slots"],
                    }
                )
                seen.add(slot_id)

    return sorted(slots, key=lambda item: (_text(item["slot_id"]).casefold(), _text(item["slot_label"]).casefold()))


def _module_id(module: Mapping[str, Any]) -> str:
    return _text(module.get("module_id") or module.get("id") or module.get("name"))


def _module_label(module: Mapping[str, Any], module_id: str) -> str:
    return _text(module.get("module_label") or module.get("display_name") or module.get("module_name") or module_id)


def _module_slot_ids(module: Mapping[str, Any]) -> list[str]:
    return _unique_texts(_key(slot_id) for slot_id in _list_texts(module.get("required_slots")))


def _module_blocked_outputs(module: Mapping[str, Any]) -> list[str]:
    outputs = _list_texts(module.get("blocked_outputs"))
    module_id = _module_id(module)
    if module_id:
        registry_card = get_plant_review_module_card_by_id(module_id)
        if isinstance(registry_card, Mapping):
            outputs.extend(_list_texts(registry_card.get("blocked_outputs")))
    return _unique_texts(outputs)


def _collect_modules(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_field in ("module_card_summaries", "required_modules", "module_cards"):
        for module in route_draft.get(source_field) or []:
            if not isinstance(module, Mapping):
                continue
            module_id = _module_id(module)
            if not module_id or module_id in seen:
                continue
            modules.append(
                {
                    "module_id": module_id,
                    "module_label": _module_label(module, module_id),
                    "route_id": _text(route_draft.get("route_id")),
                    "required_slot_ids": _module_slot_ids(module),
                    "blocked_output_categories": _module_blocked_outputs(module),
                }
            )
            seen.add(module_id)

    template = route_draft.get("selected_template")
    if isinstance(template, Mapping):
        for module_id in _list_texts(template.get("required_module_ids") or template.get("required_module_cards")):
            if module_id in seen:
                continue
            registry_card = get_plant_review_module_card_by_id(module_id) or {}
            modules.append(
                {
                    "module_id": module_id,
                    "module_label": _text(registry_card.get("display_name")) or module_id,
                    "route_id": _text(route_draft.get("route_id")),
                    "required_slot_ids": _unique_texts(_key(slot_id) for slot_id in _list_texts(registry_card.get("required_slots"))),
                    "blocked_output_categories": _list_texts(registry_card.get("blocked_outputs")),
                }
            )
            seen.add(module_id)

    return sorted(modules, key=lambda item: _text(item["module_id"]).casefold())


def _module_by_slot(modules: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    by_slot: dict[str, str] = {}
    for module in modules:
        module_id = _text(module.get("module_id"))
        for slot_id in _list_texts(module.get("required_slot_ids")):
            by_slot.setdefault(_key(slot_id), module_id)
    return by_slot


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


def _source_completeness_status(slot_or_candidate: Mapping[str, Any]) -> str:
    completeness = slot_or_candidate.get("source_completeness")
    if isinstance(completeness, Mapping):
        if completeness.get("has_source") is False:
            return "source_missing"
        if completeness.get("has_provenance") is False:
            return "provenance_missing"
        if completeness.get("has_source") is True or completeness.get("has_provenance") is True:
            return "source_or_provenance_recorded"
    return ""


def _normalize_review_queue(gap_manual_review_queue_result: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(gap_manual_review_queue_result, Mapping):
        return []
    raw_items = gap_manual_review_queue_result.get("review_items") or gap_manual_review_queue_result.get("queue") or []
    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, Mapping):
            continue
        category = _text(item.get("category")) or "manual_review"
        severity = _text(item.get("severity")) or SEVERITY_REVIEW_REQUIRED
        priority_value = item.get("priority")
        try:
            priority = int(priority_value)
        except (TypeError, ValueError):
            priority = 999
        manual_review_reasons = _unique_texts(
            [
                *_list_texts(item.get("manual_review_reasons")),
                *_list_texts(item.get("upstream_review_reasons")),
            ]
        )
        missing_context_reasons = [
            reason
            for reason in manual_review_reasons
            if "missing" in _key(reason) or "context_gap" in _key(reason)
        ]
        normalized = {
            "item_id": _text(item.get("item_id")) or f"r74-review-item-{index:03d}",
            "category": category,
            "severity": severity,
            "priority": priority,
            "route_id": _text(item.get("route_id")),
            "module_id": _text(item.get("module_id")),
            "slot_id": _key(item.get("slot_id")),
            "slot_label": _text(item.get("slot_label")),
            "evidence_ids": _unique_texts(_list_texts(item.get("evidence_ids"))),
            "component_ids": _unique_texts(_list_texts(item.get("component_ids"))),
            "manual_review_reasons": manual_review_reasons,
            "missing_context_reasons": _unique_texts(missing_context_reasons),
            "note": _text(item.get("note")),
        }
        items.append(normalized)

    items.sort(
        key=lambda item: (
            int(item["priority"]),
            _text(item["category"]).casefold(),
            _text(item["route_id"]).casefold(),
            _text(item["module_id"]).casefold(),
            _text(item["slot_id"]).casefold(),
            ",".join(item["evidence_ids"]).casefold(),
            ",".join(item["component_ids"]).casefold(),
            _text(item["note"]).casefold(),
        )
    )
    return items


def _review_queue_counts(review_queue: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "review_queue_total": len(review_queue),
        "blocker_count": sum(1 for item in review_queue if item.get("severity") == SEVERITY_BLOCKER),
        "review_required_count": sum(1 for item in review_queue if item.get("severity") == SEVERITY_REVIEW_REQUIRED),
        "informational_count": sum(1 for item in review_queue if item.get("severity") == SEVERITY_INFORMATIONAL),
    }


def _blocked_output_boundaries(route: Mapping[str, Any], modules: Sequence[Mapping[str, Any]], gap_result: Mapping[str, Any] | None) -> list[str]:
    outputs: list[str] = []
    outputs.extend(_list_texts(route.get("blocked_outputs")))
    template = route.get("selected_template")
    if isinstance(template, Mapping):
        outputs.extend(_list_texts(template.get("blocked_outputs")))
    for module in modules:
        outputs.extend(_list_texts(module.get("blocked_output_categories")))
    if isinstance(gap_result, Mapping):
        outputs.extend(_list_texts(gap_result.get("blocked_output_categories")))
    if not outputs:
        outputs.extend(BLOCKED_OUTPUT_CATEGORIES)
    return sorted(_unique_texts(outputs), key=str.casefold)


def _route_summary(route: Mapping[str, Any]) -> dict[str, Any]:
    template = route.get("selected_template")
    route_match = route.get("route_match")
    plant_context = route.get("plant_context")
    return {
        "route_id": _text(route.get("route_id")),
        "route_label": _text(route.get("route_label") or route.get("route_name") or route.get("display_name")),
        "route_status": _text(route.get("route_status") or route.get("draft_status")),
        "route_type": _text(route.get("route_type")),
        "route_template_id": _text(template.get("route_id") or template.get("template_id")) if isinstance(template, Mapping) else "",
        "matched_trigger_terms": _list_texts(route_match.get("matched_trigger_terms")) if isinstance(route_match, Mapping) else [],
        "matched_context_terms": _list_texts(route_match.get("matched_context_terms")) if isinstance(route_match, Mapping) else [],
        "plant_scope_status": _text(plant_context.get("scope_status")) if isinstance(plant_context, Mapping) else "",
        "documentation_only_boundary": PACKAGE_BOUNDARY_NOTE,
    }


def _design_intent_summary(route: Mapping[str, Any], package_metadata: Mapping[str, Any] | None, user_context: Mapping[str, Any] | None) -> dict[str, Any]:
    target_summary = route.get("target_summary")
    intent_summary = route.get("intent_summary")
    plant_context = route.get("plant_context")
    metadata = package_metadata if isinstance(package_metadata, Mapping) else {}
    context = user_context if isinstance(user_context, Mapping) else {}
    target_terms: list[str] = []
    product_terms: list[str] = []
    host_terms: list[str] = []
    context_terms: list[str] = []

    if isinstance(target_summary, Mapping):
        target_terms.extend(_list_texts(target_summary.get("target_name")))
        target_terms.extend(_list_texts(target_summary.get("target_or_product_terms")))
        product_terms.extend(_list_texts(target_summary.get("product")))
        product_terms.extend(_list_texts(target_summary.get("known_cds_source")))
    if isinstance(intent_summary, Mapping):
        target_terms.extend(_list_texts(intent_summary.get("target_name")))
        product_terms.extend(_list_texts(intent_summary.get("target_or_product_terms")))
        context_terms.extend(_list_texts(intent_summary.get("expression_purpose")))
    if isinstance(plant_context, Mapping):
        host_terms.extend(_list_texts(plant_context.get("provided_host")))
        host_terms.extend(_list_texts(plant_context.get("host_plant_terms")))
        context_terms.extend(_list_texts(plant_context.get("provided_context")))
        context_terms.extend(_list_texts(plant_context.get("selected_context")))
        context_terms.extend(_list_texts(plant_context.get("expression_context_terms")))
    for source in (metadata, context):
        target_terms.extend(_list_texts(source.get("target") or source.get("target_name")))
        product_terms.extend(_list_texts(source.get("product")))
        host_terms.extend(_list_texts(source.get("host") or source.get("plant_host")))
        context_terms.extend(_list_texts(source.get("context") or source.get("plant_context")))

    return {
        "target_terms": _unique_texts(target_terms),
        "product_terms": _unique_texts(product_terms),
        "host_terms": _unique_texts(host_terms),
        "context_terms": _unique_texts(context_terms),
        "unresolved_intent_fields": _unique_texts(
            [
                *_list_texts(route.get("missing_fields")),
                *_list_texts(route.get("unresolved_fields")),
                *_list_texts(route.get("missing_context")),
            ]
        ),
        "manual_review_notes": _unique_texts(
            [
                *_list_texts(route.get("manual_review_notes")),
                *_list_texts(route.get("manual_review_reasons")),
            ]
        ),
    }


def _construct_slot_summary(
    route: Mapping[str, Any],
    evidence_result: Mapping[str, Any] | None,
    component_result: Mapping[str, Any] | None,
    modules: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    slots = _collect_required_slots(route)
    evidence_by_slot = _slots_by_id(evidence_result)
    component_by_slot = _slots_by_id(component_result)
    module_by_slot = _module_by_slot(modules)
    missing_fields = {_key(item) for item in _list_texts(route.get("missing_fields"))}
    normalized_slots: list[dict[str, Any]] = []
    for slot in slots:
        slot_id = _text(slot.get("slot_id"))
        evidence_slot = evidence_by_slot.get(slot_id)
        component_slot = component_by_slot.get(slot_id)
        status_values = [
            _text(slot.get("slot_status")),
            _text(evidence_slot.get("slot_status")) if isinstance(evidence_slot, Mapping) else "",
            _text(component_slot.get("slot_status")) if isinstance(component_slot, Mapping) else "",
        ]
        missing_required = bool(slot.get("missing_required_slot")) or (
            bool(slot.get("required")) and (slot_id in missing_fields or _key(slot.get("slot_status")) == "missing")
        )
        normalized_slots.append(
            {
                "slot_id": slot_id,
                "slot_label": _text(slot.get("slot_label")),
                "slot_status": _unique_texts(status_values),
                "required": bool(slot.get("required")),
                "optional": bool(slot.get("optional")),
                "missing_required_slot": missing_required,
                "module_id": module_by_slot.get(slot_id, ""),
                "evidence_ids": _evidence_ids_from_slot(evidence_slot),
                "component_ids": _component_ids_from_slot(component_slot),
            }
        )
    return {
        "total_slots": len(normalized_slots),
        "missing_required_slot_count": sum(1 for slot in normalized_slots if slot["missing_required_slot"]),
        "slots": normalized_slots,
    }


def _evidence_summary(evidence_result: Mapping[str, Any] | None) -> dict[str, Any]:
    slots = _slots_by_id(evidence_result)
    slot_rows: list[dict[str, Any]] = []
    evidence_ids: list[str] = []
    for slot_id, slot in sorted(slots.items(), key=lambda item: item[0].casefold()):
        ids = _evidence_ids_from_slot(slot)
        evidence_ids.extend(ids)
        slot_rows.append(
            {
                "slot_id": slot_id,
                "slot_label": _text(slot.get("slot_label")),
                "slot_status": _text(slot.get("slot_status")),
                "evidence_ids": ids,
                "evidence_count": len(ids),
                "evidence_gap": _key(slot.get("slot_status")) == "missing_evidence" or not ids,
                "source_completeness_status": _source_completeness_status(slot),
            }
        )
    unique_ids = sorted(_unique_texts(evidence_ids), key=str.casefold)
    return {
        "evidence_ids": unique_ids,
        "evidence_count": len(unique_ids),
        "evidence_gap_count": sum(1 for row in slot_rows if row["evidence_gap"]),
        "source_provenance_completeness_summary": {
            "slot_count": len(slot_rows),
            "slots_with_source_or_provenance_recorded": sum(
                1 for row in slot_rows if row["source_completeness_status"] == "source_or_provenance_recorded"
            ),
            "slots_with_source_or_provenance_gap": sum(
                1 for row in slot_rows if row["source_completeness_status"] in {"source_missing", "provenance_missing"}
            ),
        },
        "evidence_validation_claim_present": False,
        "slots": slot_rows,
    }


def _component_candidate_summary(component_result: Mapping[str, Any] | None) -> dict[str, Any]:
    slots = _slots_by_id(component_result)
    slot_rows: list[dict[str, Any]] = []
    component_ids: list[str] = []
    provenance_gap_count = 0
    duplicate_count = 0
    for slot_id, slot in sorted(slots.items(), key=lambda item: item[0].casefold()):
        ids = _component_ids_from_slot(slot)
        component_ids.extend(ids)
        candidates: list[dict[str, Any]] = []
        for candidate in slot.get("candidate_components") or []:
            if not isinstance(candidate, Mapping):
                continue
            candidate_id = _text(candidate.get("component_id") or candidate.get("asset_id") or candidate.get("part_id"))
            missing_provenance = _candidate_missing_provenance(candidate)
            duplicate_or_alias = _candidate_duplicate_or_alias(candidate)
            provenance_gap_count += 1 if missing_provenance else 0
            duplicate_count += 1 if duplicate_or_alias else 0
            candidates.append(
                {
                    "component_id": candidate_id,
                    "component_type": _text(candidate.get("component_type")),
                    "candidate_status": "manual_review_candidate",
                    "provenance_status": _text(candidate.get("provenance_status")),
                    "missing_provenance": missing_provenance,
                    "duplicate_or_alias_flag": duplicate_or_alias,
                    "matched_evidence_ids": _list_texts(candidate.get("matched_evidence_ids")),
                }
            )
        slot_rows.append(
            {
                "slot_id": slot_id,
                "slot_label": _text(slot.get("slot_label")),
                "slot_status": _text(slot.get("slot_status")),
                "component_ids": ids,
                "component_count": len(ids),
                "component_gap": _key(slot.get("slot_status")) == "missing_component_candidate" or not ids,
                "candidate_components": sorted(candidates, key=lambda item: _text(item["component_id"]).casefold()),
            }
        )
    unique_ids = sorted(_unique_texts(component_ids), key=str.casefold)
    return {
        "component_ids": unique_ids,
        "component_count": len(unique_ids),
        "component_gap_count": sum(1 for row in slot_rows if row["component_gap"]),
        "provenance_gap_count": provenance_gap_count,
        "duplicate_or_alias_count": duplicate_count,
        "final_or_recommended_component_present": False,
        "slots": slot_rows,
    }


def _gap_manual_review_summary(review_queue: Sequence[Mapping[str, Any]], blocked_outputs: Sequence[str]) -> dict[str, Any]:
    counts = _review_queue_counts(review_queue)
    return {
        **counts,
        "missing_required_slot_count": sum(1 for item in review_queue if item.get("category") == CATEGORY_REQUIRED_SLOT_GAP),
        "evidence_gap_count": sum(1 for item in review_queue if item.get("category") == CATEGORY_EVIDENCE_GAP),
        "component_gap_count": sum(1 for item in review_queue if item.get("category") == CATEGORY_COMPONENT_GAP),
        "provenance_gap_count": sum(1 for item in review_queue if item.get("category") == CATEGORY_PROVENANCE_GAP),
        "ambiguity_or_duplicate_count": sum(1 for item in review_queue if item.get("category") == CATEGORY_AMBIGUITY),
        "blocked_output_boundary_count": len(blocked_outputs),
        "unsupported_scope_count": sum(1 for item in review_queue if item.get("category") == CATEGORY_UNSUPPORTED_SCOPE),
        "route_context_gap_count": sum(1 for item in review_queue if item.get("category") == CATEGORY_ROUTE_CONTEXT_GAP),
    }


def _upstream_result_versions(
    evidence_result: Mapping[str, Any] | None,
    component_result: Mapping[str, Any] | None,
    gap_result: Mapping[str, Any] | None,
) -> dict[str, str]:
    versions: dict[str, str] = {}
    for label, result in (
        ("evidence_slot_match_result", evidence_result),
        ("component_candidate_match_result", component_result),
        ("gap_manual_review_queue_result", gap_result),
    ):
        if not isinstance(result, Mapping):
            continue
        version = _first_text(result, ("schema_version", "matcher_version", "queue_version", "result_version"))
        if version:
            versions[label] = version
    return versions


def _warnings(
    route: Mapping[str, Any],
    evidence_result: Mapping[str, Any] | None,
    component_result: Mapping[str, Any] | None,
    gap_result: Mapping[str, Any] | None,
) -> list[str]:
    warnings: list[str] = []
    if not route:
        warnings.append("route_context_gap: route draft is missing or malformed")
    elif not _text(route.get("route_id")):
        warnings.append("route_context_gap: route_id is missing")
    for label, result in (
        ("R69 evidence slot match result", evidence_result),
        ("R70 component candidate match result", component_result),
        ("R72 gap manual review queue result", gap_result),
    ):
        if not isinstance(result, Mapping) or not result:
            warnings.append(f"missing upstream result warning: {label} is missing or malformed")
    if route and _is_unsupported_route(route):
        warnings.append("unsupported_scope: route draft is outside the Plant Expression Vector review scope")
    return _unique_texts(warnings)


def _package_status(
    route: Mapping[str, Any],
    evidence_result: Mapping[str, Any] | None,
    component_result: Mapping[str, Any] | None,
    gap_result: Mapping[str, Any] | None,
    review_queue: Sequence[Mapping[str, Any]],
) -> str:
    if not route and not isinstance(evidence_result, Mapping) and not isinstance(component_result, Mapping) and not isinstance(gap_result, Mapping):
        return "empty_or_invalid_input"
    if not route and not review_queue:
        return "empty_or_invalid_input"
    if route and _is_unsupported_route(route):
        return "blocked"
    if any(item.get("category") == CATEGORY_UNSUPPORTED_SCOPE or item.get("severity") == SEVERITY_BLOCKER for item in review_queue):
        return "blocked"
    if any(item.get("severity") == SEVERITY_REVIEW_REQUIRED for item in review_queue):
        return "manual_review_required"
    if not _text(route.get("route_id")):
        return "manual_review_required"
    return "review_ready"


def _package_id(route: Mapping[str, Any], metadata: Mapping[str, Any] | None) -> str:
    if isinstance(metadata, Mapping) and _text(metadata.get("package_id")):
        return _key(metadata.get("package_id"))
    route_id = _key(route.get("route_id")) or "unknown_route"
    template = route.get("selected_template")
    template_id = _key(template.get("route_id") or template.get("template_id")) if isinstance(template, Mapping) else ""
    parts = ["plant_review_package", route_id]
    if template_id:
        parts.append(template_id)
    parts.append(PACKAGE_BUILDER_VERSION.replace(".", "_").replace("-", "_"))
    return "-".join(part for part in parts if part)


def build_plant_review_package(
    route_draft: Mapping[str, Any] | None,
    evidence_slot_match_result: Mapping[str, Any] | None,
    component_candidate_match_result: Mapping[str, Any] | None,
    gap_manual_review_queue_result: Mapping[str, Any] | None,
    package_metadata: Mapping[str, Any] | None = None,
    user_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic documentation-only Plant review package payload."""
    route = dict(route_draft) if isinstance(route_draft, Mapping) else {}
    evidence_result = dict(evidence_slot_match_result) if isinstance(evidence_slot_match_result, Mapping) else None
    component_result = dict(component_candidate_match_result) if isinstance(component_candidate_match_result, Mapping) else None
    gap_result = dict(gap_manual_review_queue_result) if isinstance(gap_manual_review_queue_result, Mapping) else None
    metadata = dict(package_metadata) if isinstance(package_metadata, Mapping) else {}
    context = dict(user_context) if isinstance(user_context, Mapping) else {}

    modules = _collect_modules(route)
    review_queue = _normalize_review_queue(gap_result)
    blocked_outputs = _blocked_output_boundaries(route, modules, gap_result)
    construct_summary = _construct_slot_summary(route, evidence_result, component_result, modules)
    evidence_summary = _evidence_summary(evidence_result)
    component_summary = _component_candidate_summary(component_result)
    gap_summary = _gap_manual_review_summary(review_queue, blocked_outputs)

    gap_summary["missing_required_slot_count"] = max(
        gap_summary["missing_required_slot_count"],
        int(construct_summary["missing_required_slot_count"]),
    )
    gap_summary["evidence_gap_count"] = max(
        gap_summary["evidence_gap_count"],
        int(evidence_summary["evidence_gap_count"]),
    )
    gap_summary["component_gap_count"] = max(
        gap_summary["component_gap_count"],
        int(component_summary["component_gap_count"]),
    )
    gap_summary["provenance_gap_count"] = max(
        gap_summary["provenance_gap_count"],
        int(component_summary["provenance_gap_count"]),
    )
    gap_summary["ambiguity_or_duplicate_count"] = max(
        gap_summary["ambiguity_or_duplicate_count"],
        int(component_summary["duplicate_or_alias_count"]),
    )
    if route and _is_unsupported_route(route):
        gap_summary["unsupported_scope_count"] = max(1, int(gap_summary["unsupported_scope_count"]))

    status = _package_status(route, evidence_result, component_result, gap_result, review_queue)
    warnings = _warnings(route, evidence_result, component_result, gap_result)

    return _plain_value(
        {
            "package_id": _package_id(route, metadata),
            "package_schema_version": PACKAGE_SCHEMA_VERSION,
            "package_type": PACKAGE_TYPE,
            "route_summary": _route_summary(route),
            "design_intent_summary": _design_intent_summary(route, metadata, context),
            "module_card_summary": {
                "module_count": len(modules),
                "modules": modules,
            },
            "construct_slot_summary": construct_summary,
            "evidence_summary": evidence_summary,
            "component_candidate_summary": component_summary,
            "gap_manual_review_summary": gap_summary,
            "review_queue": review_queue,
            "blocked_output_boundaries": blocked_outputs,
            "traceability": {
                "source_payloads_present": {
                    "route_draft": bool(route),
                    "evidence_slot_match_result": isinstance(evidence_result, Mapping) and bool(evidence_result),
                    "component_candidate_match_result": isinstance(component_result, Mapping) and bool(component_result),
                    "gap_manual_review_queue_result": isinstance(gap_result, Mapping) and bool(gap_result),
                },
                "route_ids": _unique_texts([route.get("route_id")]),
                "slot_ids": [slot["slot_id"] for slot in construct_summary["slots"]],
                "evidence_ids": evidence_summary["evidence_ids"],
                "component_ids": component_summary["component_ids"],
                "module_ids": [module["module_id"] for module in modules],
                "upstream_result_versions": _upstream_result_versions(evidence_result, component_result, gap_result),
                "package_builder_version": PACKAGE_BUILDER_VERSION,
            },
            "manual_review_required": True,
            "package_status": status,
            "package_warnings": warnings,
        }
    )
