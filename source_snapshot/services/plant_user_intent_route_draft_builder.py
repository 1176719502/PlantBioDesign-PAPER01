from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from services.plant_expression_route_template_registry import (
    DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
    get_all_plant_expression_route_templates,
)
from services.plant_review_module_card_registry import get_plant_review_module_card_by_id
from services.plant_review_module_card_schema import BLOCKED_OUTPUT_CATEGORIES


INTENT_FIELDS: tuple[str, ...] = (
    "intent_text",
    "user_intent_text",
    "target_name",
    "target",
    "product",
    "target_type",
    "plant_host",
    "host",
    "host_plant",
    "plant_context",
    "context",
    "tissue_context",
    "expression_context",
    "route_candidate",
    "expression_purpose",
    "known_cds_source",
    "known_component_ids",
    "known_vector_or_backbone",
    "localization_context",
    "evidence_sources",
    "notes",
)

DRAFT_STATUS_NEEDS_INPUT = "needs_input"
DRAFT_STATUS_MANUAL_REVIEW_REQUIRED = "manual_review_required"
DRAFT_STATUS_DOCUMENTATION_REVIEW_PENDING = "documentation_review_pending"
DRAFT_STATUS_BLOCKED_UNSUPPORTED = "blocked_unsupported"

BOUNDARY_NOTE = (
    "Documentation-only plant expression route draft for manual review. It records user-provided "
    "intent, selected route template readback, required module cards, missing fields, evidence "
    "pointers, and blocked output families without generating sequences, final constructs, "
    "biological recommendations, scoring, outcome claims, or lab-use judgments."
)

_PLANT_TERMS: tuple[str, ...] = (
    "plant",
    "rice",
    "oryza",
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

_EXPRESSION_VECTOR_CONTEXT_TERMS: tuple[str, ...] = (
    "expression",
    "vector",
    "construct",
    "cassette",
    "reporter",
    "transient",
    "stable",
    "secreted",
    "secretion",
    "localization",
    "localisation",
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

_HOST_TERM_LABELS: tuple[tuple[str, str], ...] = (
    ("oryza sativa", "Oryza sativa"),
    ("oryza", "rice"),
    ("rice", "rice"),
    ("n. benthamiana", "Nicotiana benthamiana"),
    ("nicotiana benthamiana", "Nicotiana benthamiana"),
    ("n benthamiana", "Nicotiana benthamiana"),
    ("benthamiana", "Nicotiana benthamiana"),
    ("nicotiana", "Nicotiana"),
    ("arabidopsis", "Arabidopsis"),
    ("maize", "maize"),
    ("corn", "maize"),
    ("wheat", "wheat"),
    ("soybean", "soybean"),
    ("tobacco", "tobacco"),
)

_TISSUE_CONTEXT_TERMS: tuple[str, ...] = (
    "seed",
    "seeds",
    "leaf",
    "leaves",
    "root",
    "roots",
    "callus",
    "tissue",
    "grain",
)

_EXPRESSION_CONTEXT_LABELS: tuple[tuple[str, str], ...] = (
    ("transient expression", "transient expression"),
    ("leaf transient", "transient expression"),
    ("stable plant expression", "stable plant expression"),
    ("stable transformation", "stable plant expression"),
    ("stable plant line", "stable plant expression"),
    ("secreted protein", "secreted protein expression"),
    ("secretion", "secreted protein expression"),
    ("signal peptide", "secreted or localized protein expression"),
    ("localization tag", "localization-tagged expression"),
    ("localisation tag", "localization-tagged expression"),
    ("subcellular localization", "localization-tagged expression"),
    ("reporter expression", "reporter expression"),
    ("reporter", "reporter expression"),
    ("gfp", "reporter expression"),
    ("luciferase", "reporter expression"),
    ("plant expression vector", "plant expression vector review"),
    ("plant vector", "plant expression vector review"),
)

_COMPONENT_SLOT_ALIASES: dict[str, str] = {
    "promoter": "promoter_slot",
    "plant_promoter": "promoter_slot",
    "leader": "leader_slot",
    "leader_sequence": "leader_slot",
    "cds": "coding_sequence_slot",
    "coding_sequence": "coding_sequence_slot",
    "coding_sequence_slot": "coding_sequence_slot",
    "gene": "coding_sequence_slot",
    "terminator": "terminator_slot",
    "plant_terminator": "terminator_slot",
    "signal_peptide": "signal_peptide_slot",
    "signal": "signal_peptide_slot",
    "marker": "marker_slot",
    "selectable_marker": "marker_slot",
    "reporter": "reporter_slot",
}


def _searchable(value: Any) -> str:
    return " ".join(_text(value).casefold().replace("-", " ").replace("_", " ").split())


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_")


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_has_value(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return any(_has_value(item) for item in value)
    return True


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        clean = _text(value)
        return [clean] if clean else []
    if isinstance(value, Mapping):
        return [_text(key) for key in sorted(value, key=lambda item: str(item)) if _text(key)]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_text(item) for item in value if _text(item)]
    clean = _text(value)
    return [clean] if clean else []


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _dedupe_text(items: Sequence[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _text(item)
        key = clean.casefold()
        if clean and key not in seen:
            values.append(clean)
            seen.add(key)
    return values


def _string_intent_to_fields(intent_text: str) -> dict[str, Any]:
    text = _text(intent_text)
    searchable = _searchable(text)
    target_name = _extract_target_from_text(text)
    host = _infer_host_plant(searchable)
    tissue = _infer_tissue_context(searchable)
    expression_context = _infer_expression_context(searchable)
    plant_context_parts = _dedupe_text([host, tissue, expression_context])
    return {
        "intent_text": text,
        "user_intent_text": text,
        "target_name": target_name,
        "plant_host": host,
        "plant_context": " ".join(plant_context_parts),
        "tissue_context": tissue,
        "expression_context": expression_context,
        "expression_purpose": "documentation review" if _has_any_term(searchable, _EXPRESSION_VECTOR_CONTEXT_TERMS) else "",
    }


def _normalize_intent_input(intent: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(intent, str):
        raw_data = _string_intent_to_fields(intent)
    elif isinstance(intent, Mapping):
        raw_data = dict(intent)
        raw_text = _text(raw_data.get("intent_text") or raw_data.get("user_intent_text"))
        if raw_text:
            inferred = _string_intent_to_fields(raw_text)
            for key, value in inferred.items():
                raw_data.setdefault(key, value)
    else:
        raise TypeError("intent must be a mapping or string")

    normalized = {field: raw_data.get(field) for field in INTENT_FIELDS}
    normalized["target_name"] = (
        normalized.get("target_name")
        or normalized.get("target")
        or normalized.get("product")
        or ""
    )
    normalized["plant_host"] = (
        normalized.get("plant_host")
        or normalized.get("host_plant")
        or normalized.get("host")
        or ""
    )
    normalized["plant_context"] = (
        normalized.get("plant_context")
        or normalized.get("tissue_context")
        or normalized.get("expression_context")
        or normalized.get("context")
        or ""
    )
    normalized["route_candidate"] = normalized.get("route_candidate") or ""
    return normalized


def _intent_blob(intent: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for field in INTENT_FIELDS:
        value = intent.get(field)
        if isinstance(value, Mapping):
            parts.extend(_text(key) for key in value)
            parts.extend(_text(item) for item in value.values())
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            parts.extend(_text(item) for item in value)
        else:
            parts.append(_text(value))
    return _searchable(" ".join(part for part in parts if part))


def _scope_blob(intent: Mapping[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            _text(intent.get("plant_host")),
            _text(intent.get("plant_context")),
        )
        if part
    )
    return _searchable(scope)


def _has_any_term(blob: str, terms: Sequence[str]) -> bool:
    searchable_blob = _searchable(blob)
    return any(_searchable(term) in searchable_blob for term in terms)


def _is_non_plant_scope(intent: Mapping[str, Any]) -> bool:
    blob = _intent_blob(intent).replace("non plant", "nonplant")
    if not blob:
        return False
    return _has_any_term(blob, _NON_PLANT_TERMS) and not _has_any_term(blob, _PLANT_TERMS)


def _has_mixed_scope(intent: Mapping[str, Any]) -> bool:
    blob = _intent_blob(intent).replace("non plant", "nonplant")
    return _has_any_term(blob, _NON_PLANT_TERMS) and _has_any_term(blob, _PLANT_TERMS)


def _extract_target_from_text(intent_text: str) -> str:
    text = _text(intent_text)
    patterns = (
        r"\bexpress\s+(.+?)\s+in\s+",
        r"\bexpression\s+of\s+(.+?)\s+in\s+",
        r"\breview\s+(.+?)\s+in\s+",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            target = re.sub(
                r"\b(plant|transient|stable|expression|vector|review)\b",
                "",
                match.group(1),
                flags=re.IGNORECASE,
            )
            return " ".join(target.split()).strip(" ,.;:")
    return ""


def _infer_host_plant(searchable_blob: str) -> str:
    for term, label in _HOST_TERM_LABELS:
        if _searchable(term) in searchable_blob:
            return label
    return ""


def _infer_tissue_context(searchable_blob: str) -> str:
    matches = [term for term in _TISSUE_CONTEXT_TERMS if _searchable(term) in searchable_blob]
    if "leaves" in matches and "leaf" in matches:
        matches.remove("leaf")
    if "seeds" in matches and "seed" in matches:
        matches.remove("seed")
    return " ".join(matches[:2])


def _infer_expression_context(searchable_blob: str) -> str:
    for term, label in _EXPRESSION_CONTEXT_LABELS:
        if _searchable(term) in searchable_blob:
            return label
    return ""


def _matched_terms(blob: str, terms: Sequence[str]) -> list[str]:
    searchable_blob = _searchable(blob)
    return [term for term in terms if _searchable(term) and _searchable(term) in searchable_blob]


def _route_match_candidates(intent: Mapping[str, Any]) -> list[dict[str, Any]]:
    blob = _intent_blob(intent)
    route_candidate = _text(intent.get("route_candidate"))
    if route_candidate:
        blob = _searchable(f"{blob} {route_candidate}")

    candidates: list[dict[str, Any]] = []
    for index, template in enumerate(get_all_plant_expression_route_templates()):
        trigger_matches = _matched_terms(blob, template.get("trigger_terms", []))
        context_matches = _matched_terms(blob, template.get("supported_host_contexts", []))
        identity_matches = _matched_terms(
            blob,
            (
                template.get("route_id", ""),
                template.get("display_name", ""),
                template.get("route_name", ""),
                template.get("plant_context", ""),
            ),
        )
        score = (len(trigger_matches) * 4) + (len(context_matches) * 3) + len(identity_matches)
        if not score:
            continue
        candidates.append(
            {
                "template": template,
                "route_id": template.get("route_id", ""),
                "score": score,
                "registry_order": index,
                "matched_trigger_terms": trigger_matches,
                "matched_host_context_terms": context_matches,
                "matched_route_terms": identity_matches,
            }
        )
    return sorted(candidates, key=lambda item: (-int(item["score"]), int(item["registry_order"])))


def _select_route_template(intent: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = _route_match_candidates(intent)
    if not candidates:
        return {}, {
            "route_match_status": "unknown_or_ambiguous",
            "candidate_route_id": "",
            "candidate_route_name": "",
            "score": "0",
            "matched_trigger_terms": [],
            "matched_host_context_terms": [],
            "matched_route_terms": [],
            "candidate_routes": [],
        }

    top = candidates[0]
    template = top["template"]
    return template, {
        "route_match_status": "matched",
        "candidate_route_id": template.get("route_id", ""),
        "candidate_route_name": template.get("display_name", ""),
        "score": str(top["score"]),
        "matched_trigger_terms": list(top["matched_trigger_terms"]),
        "matched_host_context_terms": list(top["matched_host_context_terms"]),
        "matched_route_terms": list(top["matched_route_terms"]),
        "candidate_routes": [
            {
                "route_id": candidate["route_id"],
                "score": str(candidate["score"]),
                "matched_trigger_terms": list(candidate["matched_trigger_terms"]),
                "matched_host_context_terms": list(candidate["matched_host_context_terms"]),
            }
            for candidate in candidates
        ],
    }


def _draft_id(route_id: str) -> str:
    clean = "".join(char.lower() if char.isalnum() else "-" for char in route_id)
    clean = "-".join(part for part in clean.split("-") if part)
    return f"plant-route-draft-{clean or DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID}"


def _component_slot_values(known_component_ids: Any) -> dict[str, str]:
    slot_values: dict[str, str] = {}
    if isinstance(known_component_ids, Mapping):
        items = known_component_ids.items()
    elif isinstance(known_component_ids, Sequence) and not isinstance(
        known_component_ids, (str, bytes, bytearray)
    ):
        items = ((_text(item), item) for item in known_component_ids)
    else:
        items = ()

    for raw_key, raw_value in items:
        if not _has_value(raw_value):
            continue
        key = _key(raw_key)
        slot_name = _COMPONENT_SLOT_ALIASES.get(key)
        if slot_name and slot_name not in slot_values:
            slot_values[slot_name] = _text(raw_value) or _text(raw_key)
            continue
        value_text = f"{raw_key} {_text(raw_value)}".casefold()
        for alias, candidate_slot in _COMPONENT_SLOT_ALIASES.items():
            if alias.replace("_", " ") in value_text or alias in value_text:
                slot_values.setdefault(candidate_slot, _text(raw_value) or _text(raw_key))
    return slot_values


def _slot_values(intent: Mapping[str, Any]) -> dict[str, str]:
    component_slots = _component_slot_values(intent.get("known_component_ids"))
    evidence_sources = _as_text_list(intent.get("evidence_sources"))
    known_cds_source = _text(intent.get("known_cds_source"))
    plant_host = _text(intent.get("plant_host"))
    plant_context = _text(intent.get("plant_context"))

    values: dict[str, str] = {
        "target_name": _text(intent.get("target_name")),
        "plant_context": plant_context or plant_host,
        "documentation_goal": _text(intent.get("expression_purpose")),
        "plant_species": plant_host or plant_context,
        "host_context_note": plant_context or plant_host,
        "cds_label": known_cds_source,
        "sequence_source_note": known_cds_source,
        "backbone_label": _text(intent.get("known_vector_or_backbone")),
        "localization_note": _text(intent.get("localization_context")),
        "source_reference": evidence_sources[0] if evidence_sources else known_cds_source,
        "manual_review_note": _text(intent.get("notes")),
        "promoter_source_reference": evidence_sources[0] if evidence_sources else "",
        "terminator_source_reference": evidence_sources[0] if evidence_sources else "",
        "reporter_slot": component_slots.get("reporter_slot", _text(intent.get("target_name"))),
    }
    values.update(component_slots)
    return values


def _provided_fields(intent: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"field": field, "value": _plain_value(intent.get(field))}
        for field in INTENT_FIELDS
        if _has_value(intent.get(field))
    ]


def _evidence_summary(intent: Mapping[str, Any]) -> list[dict[str, str]]:
    evidence_sources = intent.get("evidence_sources")
    if isinstance(evidence_sources, Mapping):
        return [
            {"source_id": _text(key), "value": _text(evidence_sources[key])}
            for key in sorted(evidence_sources, key=lambda item: str(item))
            if _text(key) or _text(evidence_sources[key])
        ]
    sources = _as_text_list(evidence_sources)
    return [{"source_id": source, "value": source} for source in sources]


def _required_slots(template: Mapping[str, Any], slot_values: Mapping[str, str]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for slot_name in template.get("required_slots", []):
        value = _text(slot_values.get(slot_name))
        slots.append(
            {
                "slot_name": slot_name,
                "status": "provided" if value else "missing",
                "value": value,
                "manual_review_required": True,
            }
        )
    return slots


def _required_module_readbacks(template: Mapping[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for module_id in template.get("required_module_ids", []):
        card = get_plant_review_module_card_by_id(module_id)
        if card is not None:
            cards.append(card)
    return cards


def _module_card_summaries(cards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "module_id": _text(card.get("module_id")),
            "display_name": _text(card.get("display_name")),
            "required_inputs": _plain_value(card.get("required_inputs") or []),
            "required_slots": _plain_value(card.get("required_slots") or []),
            "evidence_fields": _plain_value(card.get("evidence_fields") or []),
            "gap_rules": _plain_value(card.get("gap_rules") or []),
            "manual_review_rules": _plain_value(card.get("manual_review_rules") or []),
            "package_section": _text(card.get("package_section")),
            "boundary_notes": _plain_value(card.get("boundary_notes") or []),
        }
        for card in cards
    ]


def _route_template_metadata(template: Mapping[str, Any]) -> dict[str, Any]:
    if not template:
        return {}
    return {
        "route_id": _text(template.get("route_id")),
        "display_name": _text(template.get("display_name")),
        "route_type": _text(template.get("route_type")),
        "trigger_terms": _plain_value(template.get("trigger_terms") or []),
        "supported_host_contexts": _plain_value(template.get("supported_host_contexts") or []),
        "evidence_requirements": _plain_value(template.get("evidence_requirements") or []),
        "gap_rules": _plain_value(template.get("gap_rules") or []),
        "manual_review_rules": _plain_value(template.get("manual_review_rules") or []),
        "package_sections": _plain_value(template.get("package_sections") or []),
        "boundary_notes": _plain_value(template.get("boundary_notes") or []),
    }


def _intent_summary(intent: Mapping[str, Any]) -> dict[str, str]:
    blob = _intent_blob(intent)
    target = _text(intent.get("target_name")) or _extract_target_from_text(_text(intent.get("intent_text")))
    host = _text(intent.get("plant_host")) or _infer_host_plant(blob)
    tissue = _text(intent.get("tissue_context")) or _infer_tissue_context(blob)
    expression_context = _text(intent.get("expression_context")) or _infer_expression_context(blob)
    return {
        "target_or_product_terms": target,
        "host_plant_terms": host,
        "tissue_context_terms": tissue,
        "expression_context_terms": expression_context,
        "route_candidate": _text(intent.get("route_candidate")),
    }


def _manual_review_items(
    *,
    intent: Mapping[str, Any],
    template: Mapping[str, Any],
    required_slots: Sequence[Mapping[str, Any]],
    empty_input: bool,
    non_plant_scope: bool,
    mixed_scope: bool,
    unknown_route_context: bool,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if empty_input:
        items.append(
            {
                "review_type": "input_needed",
                "field": "intent",
                "note": "Add plant target, host/context, source, component, and evidence pointers for documentation review.",
            }
        )
    if non_plant_scope:
        items.append(
            {
                "review_type": "unsupported_scope_review",
                "field": "plant_host_or_context",
                "note": "Provided terms are outside the plant-only expression-vector route scope; active route draft output is blocked pending manual review.",
            }
        )
    if mixed_scope:
        items.append(
            {
                "review_type": "mixed_scope_review",
                "field": "plant_host_or_context",
                "note": "Plant and non-plant platform terms appear together; active route draft output is blocked pending manual review.",
            }
        )
    if unknown_route_context:
        items.append(
            {
                "review_type": "missing_route_context",
                "field": "plant_route_context",
                "note": "Add plant host, tissue/context, target, and expression-vector review context before selecting a registry route template.",
            }
        )
    for slot in required_slots:
        if slot["status"] == "missing":
            items.append(
                {
                    "review_type": "missing_required_slot",
                    "field": str(slot["slot_name"]),
                    "note": f"Required slot from {template['route_id']} needs a source-backed documentation value.",
                }
            )
    if _text(intent.get("localization_context")) and "signal_peptide_localization" not in template.get(
        "required_module_ids", []
    ):
        items.append(
            {
                "review_type": "localization_context_review",
                "field": "localization_context",
                "note": "Localization context was provided and should remain visible in manual documentation review.",
            }
        )
    return items


def _draft_status(empty_input: bool, missing_fields: Sequence[str]) -> str:
    if empty_input:
        return DRAFT_STATUS_NEEDS_INPUT
    return DRAFT_STATUS_MANUAL_REVIEW_REQUIRED


def _blocked_route_draft(
    *,
    intent_data: Mapping[str, Any],
    route_id: str,
    route_name: str,
    scope_status: str,
    route_match_status: str,
    missing_fields: Sequence[str],
    manual_review_type: str,
    manual_review_note: str,
    draft_status: str = DRAFT_STATUS_BLOCKED_UNSUPPORTED,
) -> dict[str, Any]:
    return {
        "draft_id": _draft_id(route_id),
        "draft_status": draft_status,
        "manual_review_required": True,
        "final_design_present": False,
        "active_design_route": False,
        "route_id": route_id,
        "route_name": route_name,
        "route_type": route_id,
        "selected_template": {},
        "route_template_metadata": {},
        "route_match": {
            "route_match_status": route_match_status,
            "candidate_route_id": "",
            "candidate_route_name": "",
            "score": "0",
            "matched_trigger_terms": [],
            "matched_host_context_terms": [],
            "matched_route_terms": [],
            "candidate_routes": [],
        },
        "plant_context": {
            "provided_host": _text(intent_data.get("plant_host")),
            "provided_context": _text(intent_data.get("plant_context")),
            "selected_context": "",
            "scope_status": scope_status,
        },
        "target_summary": {
            "target_name": _text(intent_data.get("target_name")),
            "target_type": _text(intent_data.get("target_type")),
            "expression_purpose": _text(intent_data.get("expression_purpose")),
            "known_cds_source": _text(intent_data.get("known_cds_source")),
            "known_vector_or_backbone": _text(intent_data.get("known_vector_or_backbone")),
            "localization_context": _text(intent_data.get("localization_context")),
            "notes": _text(intent_data.get("notes")),
        },
        "intent_summary": _intent_summary(intent_data),
        "required_modules": [],
        "module_card_summaries": [],
        "required_slots": [],
        "required_construct_slots": [],
        "provided_fields": _provided_fields(intent_data),
        "missing_fields": list(missing_fields),
        "missing_inputs": list(missing_fields),
        "evidence_summary": _evidence_summary(intent_data),
        "evidence_requirements": [],
        "manual_review_items": [
            {
                "review_type": manual_review_type,
                "field": "plant_route_context",
                "note": manual_review_note,
            }
        ],
        "manual_review_reasons": [manual_review_note],
        "blocked_outputs": list(BLOCKED_OUTPUT_CATEGORIES),
        "boundary_note": BOUNDARY_NOTE,
        "package_preview_sections": [],
    }


def build_plant_expression_route_draft(intent: Mapping[str, Any] | str) -> dict[str, Any]:
    """Build a deterministic plant expression route draft from user-provided intent data."""
    intent_data = _normalize_intent_input(intent)
    empty_input = not any(_has_value(value) for value in intent_data.values())
    non_plant_scope = _is_non_plant_scope(intent_data)
    mixed_scope = _has_mixed_scope(intent_data)
    selected_template, route_match = _select_route_template(intent_data)
    unknown_route_context = not selected_template

    if non_plant_scope or mixed_scope:
        return _blocked_route_draft(
            intent_data=intent_data,
            route_id="unsupported_non_plant_expression_context",
            route_name="Unsupported Non-Plant Expression Context",
            scope_status="unsupported_non_plant_scope" if non_plant_scope else "mixed_scope_manual_review",
            route_match_status="unsupported_non_plant_scope" if non_plant_scope else "mixed_scope_manual_review",
            missing_fields=("plant_route_context",),
            manual_review_type="unsupported_scope_review" if non_plant_scope else "mixed_scope_review",
            manual_review_note="The intent is outside the plant-only expression-vector route scope and remains blocked for manual review.",
        )

    if unknown_route_context:
        return _blocked_route_draft(
            intent_data=intent_data,
            route_id="unknown_plant_expression_context",
            route_name="Unknown Plant Expression Context",
            scope_status="missing_plant_route_context",
            route_match_status="unknown_or_ambiguous",
            missing_fields=("plant_route_context",),
            manual_review_type="missing_route_context",
            manual_review_note="Plant route context is missing or ambiguous; provide plant host, target, and expression-vector review context.",
            draft_status=DRAFT_STATUS_NEEDS_INPUT if empty_input else DRAFT_STATUS_MANUAL_REVIEW_REQUIRED,
        )

    slot_values = _slot_values(intent_data)
    required_slots = _required_slots(selected_template, slot_values)
    missing_fields = [slot["slot_name"] for slot in required_slots if slot["status"] == "missing"]
    required_modules = _required_module_readbacks(selected_template)
    route_id = selected_template.get("route_id", DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID)

    return {
        "draft_id": _draft_id(route_id),
        "draft_status": _draft_status(empty_input, missing_fields),
        "manual_review_required": True,
        "final_design_present": False,
        "active_design_route": False,
        "route_id": route_id,
        "route_name": selected_template.get("route_name", ""),
        "route_type": selected_template.get("route_type", "plant_expression_vector"),
        "selected_template": selected_template,
        "route_template_metadata": _route_template_metadata(selected_template),
        "route_match": route_match,
        "plant_context": {
            "provided_host": _text(intent_data.get("plant_host")),
            "provided_context": _text(intent_data.get("plant_context")),
            "selected_context": selected_template.get("plant_context", ""),
            "scope_status": "plant_scope_review",
        },
        "target_summary": {
            "target_name": _text(intent_data.get("target_name")),
            "target_type": _text(intent_data.get("target_type")),
            "expression_purpose": _text(intent_data.get("expression_purpose")),
            "known_cds_source": _text(intent_data.get("known_cds_source")),
            "known_vector_or_backbone": _text(intent_data.get("known_vector_or_backbone")),
            "localization_context": _text(intent_data.get("localization_context")),
            "notes": _text(intent_data.get("notes")),
        },
        "intent_summary": _intent_summary(intent_data),
        "required_modules": required_modules,
        "module_card_summaries": _module_card_summaries(required_modules),
        "required_slots": required_slots,
        "required_construct_slots": required_slots,
        "provided_fields": _provided_fields(intent_data),
        "missing_fields": missing_fields,
        "missing_inputs": missing_fields,
        "evidence_summary": _evidence_summary(intent_data),
        "evidence_requirements": selected_template.get("evidence_requirements", []),
        "manual_review_items": _manual_review_items(
            intent=intent_data,
            template=selected_template,
            required_slots=required_slots,
            empty_input=empty_input,
            non_plant_scope=non_plant_scope,
            mixed_scope=mixed_scope,
            unknown_route_context=unknown_route_context,
        ),
        "manual_review_reasons": selected_template.get("manual_review_rules", []),
        "blocked_outputs": selected_template.get("blocked_outputs", []),
        "boundary_note": BOUNDARY_NOTE,
        "package_preview_sections": selected_template.get("package_sections", []),
    }
