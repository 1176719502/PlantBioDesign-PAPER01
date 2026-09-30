from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from services.plant_review_module_card_registry import get_plant_review_module_card_by_id
from services.plant_review_module_card_schema import (
    BLOCKED_OUTPUT_CATEGORIES,
    CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
    REQUIRED_BLOCKED_OUTPUT_CATEGORIES,
)


CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID = "plant_expression_construct_review"
PLANT_EXPRESSION_ROUTE_TEMPLATE_TYPE = CURRENT_ACTIVE_PLANT_ROUTE_TYPE
DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID = "plant_expression_vector"

ROUTE_TEMPLATE_ID_ALIASES: dict[str, str] = {
    CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID: DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
    "generic_plant_expression_vector_route": DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
    "rice_expression_vector_context_route": "rice_seed_protein_expression",
    "n_benthamiana_expression_context_route": "plant_transient_expression_review",
    "plant_secretion_localization_route": "plant_secreted_protein_expression",
    "chloroplast_expression_review_route": "plant_localization_tagged_expression",
    "plant_reporter_construct_review_route": "plant_reporter_expression_review",
}

ROUTE_TEMPLATE_FIELDS: tuple[str, ...] = (
    "route_id",
    "route_type",
    "display_name",
    "trigger_terms",
    "supported_host_contexts",
    "required_module_cards",
    "optional_module_cards",
    "required_slots",
    "evidence_requirements",
    "gap_rules",
    "manual_review_rules",
    "blocked_outputs",
    "package_sections",
    "boundary_notes",
    "route_name",
    "plant_context",
    "required_module_ids",
    "optional_module_ids",
    "boundary_note",
)

_BOUNDARY_NOTES: tuple[str, ...] = (
    "Documentation-only Plant Expression Route Template Registry for manual review.",
    "Templates organize R66 Plant Review Module Cards and source-review slots without route generation, sequence generation, biological recommendations, scoring, or lab-use judgments.",
)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _stable_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items: Iterable[Any] = (value,)
    elif isinstance(value, Mapping):
        raw_items = sorted(value.keys(), key=lambda item: str(item))
    elif isinstance(value, (set, frozenset)):
        raw_items = sorted(value, key=lambda item: str(item))
    else:
        try:
            raw_items = list(value)
        except TypeError:
            raw_items = (value,)

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _clean_text(item)
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _route_template(
    *,
    route_id: str,
    display_name: str,
    trigger_terms: tuple[str, ...],
    supported_host_contexts: tuple[str, ...],
    required_module_cards: tuple[str, ...],
    optional_module_cards: tuple[str, ...],
    required_slots: tuple[str, ...],
    evidence_requirements: tuple[str, ...],
    gap_rules: tuple[str, ...],
    manual_review_rules: tuple[str, ...],
    package_sections: tuple[str, ...],
    plant_context: str,
) -> dict[str, Any]:
    required_cards = _stable_list(required_module_cards)
    optional_cards = _stable_list(optional_module_cards)
    boundary_notes = list(_BOUNDARY_NOTES)
    return {
        "route_id": _clean_text(route_id),
        "route_type": PLANT_EXPRESSION_ROUTE_TEMPLATE_TYPE,
        "display_name": _clean_text(display_name),
        "trigger_terms": _stable_list(trigger_terms),
        "supported_host_contexts": _stable_list(supported_host_contexts),
        "required_module_cards": required_cards,
        "optional_module_cards": optional_cards,
        "required_slots": _stable_list(required_slots),
        "evidence_requirements": _stable_list(evidence_requirements),
        "gap_rules": _stable_list(gap_rules),
        "manual_review_rules": _stable_list(manual_review_rules),
        "blocked_outputs": list(BLOCKED_OUTPUT_CATEGORIES),
        "package_sections": _stable_list(package_sections),
        "boundary_notes": boundary_notes,
        "route_name": _clean_text(display_name),
        "plant_context": _clean_text(plant_context),
        "required_module_ids": list(required_cards),
        "optional_module_ids": list(optional_cards),
        "boundary_note": boundary_notes[0],
    }


_CORE_REQUIRED_CARDS: tuple[str, ...] = (
    "plant_target_intake",
    "plant_host_context",
    "cds_source_review",
    "plant_expression_cassette",
    "vector_backbone_context",
    "component_provenance",
    "gap_queue",
    "plant_review_package",
)

_CORE_OPTIONAL_CARDS: tuple[str, ...] = (
    "promoter_leader_review",
    "signal_peptide_localization",
    "terminator_marker_review",
    "codon_usage_readonly",
)

_CORE_REQUIRED_SLOTS: tuple[str, ...] = (
    "target_name",
    "plant_context",
    "documentation_goal",
    "plant_species",
    "cds_label",
    "promoter_slot",
    "coding_sequence_slot",
    "terminator_slot",
    "backbone_label",
    "source_reference",
)

_CORE_PACKAGE_SECTIONS: tuple[str, ...] = (
    "plant_target_intake_review",
    "plant_host_context_review",
    "cds_source_review",
    "plant_expression_cassette_review",
    "vector_backbone_context_review",
    "component_provenance_review",
    "gap_queue_review",
    "plant_review_package_review",
)

_PLANT_EXPRESSION_ROUTE_TEMPLATE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    _route_template(
        route_id="plant_expression_vector",
        display_name="Plant Expression Vector",
        trigger_terms=(
            "plant expression vector",
            "plant vector",
            "expression cassette",
            "plant construct review",
        ),
        supported_host_contexts=(
            "plant",
            "plant expression vector",
            "generic plant expression",
            "plant molecular farming",
        ),
        required_module_cards=_CORE_REQUIRED_CARDS,
        optional_module_cards=_CORE_OPTIONAL_CARDS,
        required_slots=_CORE_REQUIRED_SLOTS,
        evidence_requirements=(
            "source references for target, plant host context, CDS, cassette slots, backbone, and component records",
            "traceability notes for unresolved documentation gaps",
            "manual review notes for local project workspace readback",
        ),
        gap_rules=(
            "flag missing plant context or target source reference",
            "flag unresolved cassette slot provenance",
            "flag missing backbone or component source reference",
            "preserve unresolved gaps for manual review",
        ),
        manual_review_rules=(
            "route unresolved source gaps to manual documentation review",
            "keep route output as readback data only",
            "do not infer biological suitability or lab-use status",
        ),
        package_sections=_CORE_PACKAGE_SECTIONS,
        plant_context="generic_plant_expression_vector",
    ),
    _route_template(
        route_id="rice_seed_protein_expression",
        display_name="Rice Seed Protein Expression",
        trigger_terms=(
            "rice seed protein",
            "rice expression",
            "oryza sativa",
            "seed protein expression",
        ),
        supported_host_contexts=("rice", "oryza", "oryza sativa", "rice seed", "cereal seed"),
        required_module_cards=(
            "plant_target_intake",
            "plant_host_context",
            "cds_source_review",
            "plant_expression_cassette",
            "promoter_leader_review",
            "terminator_marker_review",
            "vector_backbone_context",
            "component_provenance",
            "gap_queue",
            "plant_review_package",
        ),
        optional_module_cards=("codon_usage_readonly", "signal_peptide_localization"),
        required_slots=(
            "target_name",
            "plant_species",
            "host_context_note",
            "cds_label",
            "promoter_slot",
            "promoter_source_reference",
            "terminator_slot",
            "terminator_source_reference",
            "backbone_label",
            "source_reference",
        ),
        evidence_requirements=(
            "rice host context source reference",
            "seed-context source note when recorded",
            "promoter and terminator provenance notes",
            "CDS identity and source review notes",
        ),
        gap_rules=(
            "flag missing rice host source reference",
            "flag missing promoter or terminator provenance",
            "flag unclear CDS identity or version note",
            "preserve rice-context gaps for manual review",
        ),
        manual_review_rules=(
            "keep rice seed context as documentation readback",
            "do not rank regulatory elements",
            "do not infer expression outcome",
        ),
        package_sections=(
            "plant_target_intake_review",
            "plant_host_context_review",
            "cds_source_review",
            "promoter_leader_review",
            "terminator_marker_review",
            "vector_backbone_context_review",
            "component_provenance_review",
            "gap_queue_review",
            "plant_review_package_review",
        ),
        plant_context="rice_expression_vector",
    ),
    _route_template(
        route_id="plant_transient_expression_review",
        display_name="Plant Transient Expression Review",
        trigger_terms=(
            "transient expression",
            "leaf transient",
            "nicotiana benthamiana",
            "n benthamiana",
        ),
        supported_host_contexts=(
            "nicotiana benthamiana",
            "n benthamiana",
            "n. benthamiana",
            "plant leaf",
            "transient plant expression",
        ),
        required_module_cards=_CORE_REQUIRED_CARDS,
        optional_module_cards=_CORE_OPTIONAL_CARDS,
        required_slots=(
            "target_name",
            "plant_species",
            "host_context_note",
            "cds_label",
            "promoter_slot",
            "coding_sequence_slot",
            "terminator_slot",
            "backbone_label",
            "source_reference",
        ),
        evidence_requirements=(
            "plant host context source reference",
            "cassette slot source notes",
            "backbone context source reference",
            "manual review notes for transient-expression context claims in source material",
        ),
        gap_rules=(
            "flag missing host source reference",
            "flag unresolved cassette context",
            "flag missing signal peptide source reference when localization is listed",
            "preserve source uncertainty for manual review",
        ),
        manual_review_rules=(
            "record transient plant context without choosing a route for the user",
            "keep localization claims as source notes when present",
            "do not infer expression outcome",
        ),
        package_sections=_CORE_PACKAGE_SECTIONS,
        plant_context="n_benthamiana_expression_vector",
    ),
    _route_template(
        route_id="stable_plant_expression_review",
        display_name="Stable Plant Expression Review",
        trigger_terms=(
            "stable plant expression",
            "stable transformation context",
            "stable plant line",
            "plant line review",
        ),
        supported_host_contexts=(
            "stable plant",
            "plant line",
            "arabidopsis",
            "rice",
            "maize",
            "soybean",
        ),
        required_module_cards=(
            "plant_target_intake",
            "plant_host_context",
            "cds_source_review",
            "plant_expression_cassette",
            "promoter_leader_review",
            "terminator_marker_review",
            "vector_backbone_context",
            "component_provenance",
            "gap_queue",
            "plant_review_package",
        ),
        optional_module_cards=("signal_peptide_localization", "codon_usage_readonly"),
        required_slots=(
            "target_name",
            "plant_species",
            "host_context_note",
            "cds_label",
            "promoter_slot",
            "coding_sequence_slot",
            "terminator_slot",
            "backbone_label",
            "source_reference",
        ),
        evidence_requirements=(
            "stable plant context source notes",
            "cassette slot provenance notes",
            "backbone context source reference",
            "manual follow-up notes for unresolved stable-context documentation gaps",
        ),
        gap_rules=(
            "flag missing host or line context source note",
            "flag missing regulatory slot provenance",
            "flag unresolved backbone context",
            "preserve stable-context gaps for manual review",
        ),
        manual_review_rules=(
            "keep stable plant context as documentation readback",
            "do not certify downstream lab use status",
            "do not infer expression outcome",
        ),
        package_sections=(
            "plant_target_intake_review",
            "plant_host_context_review",
            "cds_source_review",
            "plant_expression_cassette_review",
            "promoter_leader_review",
            "terminator_marker_review",
            "vector_backbone_context_review",
            "component_provenance_review",
            "gap_queue_review",
            "plant_review_package_review",
        ),
        plant_context="stable_plant_expression_review",
    ),
    _route_template(
        route_id="plant_secreted_protein_expression",
        display_name="Plant Secreted Protein Expression",
        trigger_terms=(
            "secreted protein",
            "secretion",
            "signal peptide",
            "apoplast",
            "extracellular protein",
        ),
        supported_host_contexts=(
            "plant secretion",
            "plant secreted protein",
            "leaf expression",
            "rice seed",
            "plant cell wall or apoplast",
        ),
        required_module_cards=(
            "plant_target_intake",
            "plant_host_context",
            "cds_source_review",
            "plant_expression_cassette",
            "signal_peptide_localization",
            "component_provenance",
            "gap_queue",
            "plant_review_package",
        ),
        optional_module_cards=(
            "promoter_leader_review",
            "terminator_marker_review",
            "vector_backbone_context",
            "codon_usage_readonly",
        ),
        required_slots=(
            "target_name",
            "plant_context",
            "cds_label",
            "promoter_slot",
            "coding_sequence_slot",
            "terminator_slot",
            "localization_note",
            "signal_peptide_slot",
            "source_reference",
        ),
        evidence_requirements=(
            "localization intent note",
            "signal peptide source reference",
            "cassette slot source notes",
            "manual notes for unresolved secretion-context documentation gaps",
        ),
        gap_rules=(
            "flag missing signal peptide source reference",
            "flag unresolved localization context",
            "flag missing slot provenance",
            "preserve localization uncertainty for manual review",
        ),
        manual_review_rules=(
            "preserve localization claims as source notes",
            "do not infer secretion outcome",
            "keep package output as documentation readback",
        ),
        package_sections=(
            "plant_target_intake_review",
            "plant_host_context_review",
            "cds_source_review",
            "plant_expression_cassette_review",
            "signal_peptide_localization_review",
            "component_provenance_review",
            "gap_queue_review",
            "plant_review_package_review",
        ),
        plant_context="plant_secretion_localization",
    ),
    _route_template(
        route_id="plant_localization_tagged_expression",
        display_name="Plant Localization Tagged Expression",
        trigger_terms=(
            "localization tag",
            "subcellular localization",
            "chloroplast",
            "plastid",
            "er retention",
        ),
        supported_host_contexts=(
            "plant localization",
            "chloroplast",
            "plastid",
            "endoplasmic reticulum",
            "plant organelle",
        ),
        required_module_cards=(
            "plant_target_intake",
            "plant_host_context",
            "cds_source_review",
            "plant_expression_cassette",
            "signal_peptide_localization",
            "component_provenance",
            "gap_queue",
            "plant_review_package",
        ),
        optional_module_cards=(
            "promoter_leader_review",
            "terminator_marker_review",
            "vector_backbone_context",
            "codon_usage_readonly",
        ),
        required_slots=(
            "target_name",
            "plant_context",
            "host_context_note",
            "cds_label",
            "promoter_slot",
            "coding_sequence_slot",
            "terminator_slot",
            "localization_note",
            "source_reference",
        ),
        evidence_requirements=(
            "localization tag source note",
            "plant compartment context source note",
            "cassette slot source notes",
            "manual follow-up notes for unresolved compartment context",
        ),
        gap_rules=(
            "flag missing localization source note",
            "flag missing slot provenance",
            "flag unresolved plant species context",
            "preserve unresolved compartment gaps for manual review",
        ),
        manual_review_rules=(
            "keep localization context as source-backed documentation",
            "do not create assembly instructions",
            "do not infer biological suitability",
        ),
        package_sections=(
            "plant_target_intake_review",
            "plant_host_context_review",
            "cds_source_review",
            "plant_expression_cassette_review",
            "signal_peptide_localization_review",
            "component_provenance_review",
            "gap_queue_review",
            "plant_review_package_review",
        ),
        plant_context="chloroplast_expression_review",
    ),
    _route_template(
        route_id="plant_reporter_expression_review",
        display_name="Plant Reporter Expression Review",
        trigger_terms=(
            "plant reporter",
            "reporter expression",
            "gfp",
            "luciferase",
            "fluorescent reporter",
        ),
        supported_host_contexts=(
            "plant reporter",
            "plant expression vector",
            "leaf expression",
            "stable plant",
            "rice",
        ),
        required_module_cards=(
            "plant_target_intake",
            "plant_host_context",
            "cds_source_review",
            "plant_expression_cassette",
            "component_provenance",
            "gap_queue",
            "plant_review_package",
        ),
        optional_module_cards=(
            "promoter_leader_review",
            "signal_peptide_localization",
            "terminator_marker_review",
            "vector_backbone_context",
        ),
        required_slots=(
            "target_name",
            "plant_context",
            "cds_label",
            "promoter_slot",
            "coding_sequence_slot",
            "terminator_slot",
            "reporter_slot",
            "source_reference",
        ),
        evidence_requirements=(
            "reporter slot source note",
            "cassette slot provenance notes",
            "component source references",
            "manual follow-up notes for unresolved reporter context",
        ),
        gap_rules=(
            "flag missing reporter source reference",
            "flag missing cassette slot provenance",
            "flag unclear component category",
            "preserve reporter-context gaps for manual review",
        ),
        manual_review_rules=(
            "record reporter context as documentation readback",
            "do not infer measurement outcome",
            "do not certify biological use status",
        ),
        package_sections=(
            "plant_target_intake_review",
            "plant_host_context_review",
            "cds_source_review",
            "plant_expression_cassette_review",
            "component_provenance_review",
            "gap_queue_review",
            "plant_review_package_review",
        ),
        plant_context="plant_reporter_construct_review",
    ),
)


def normalize_plant_expression_route_template(template: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(template, Mapping):
        template = {}

    required_cards = _stable_list(
        template.get("required_module_cards", template.get("required_module_ids"))
    )
    optional_cards = _stable_list(
        template.get("optional_module_cards", template.get("optional_module_ids"))
    )
    display_name = _clean_text(template.get("display_name")) or _clean_text(template.get("route_name"))
    boundary_notes = _stable_list(template.get("boundary_notes"))
    if not boundary_notes:
        boundary_note = _clean_text(template.get("boundary_note"))
        boundary_notes = [boundary_note] if boundary_note else list(_BOUNDARY_NOTES)

    normalized = {
        "route_id": _clean_text(template.get("route_id")),
        "route_type": _clean_text(template.get("route_type")) or PLANT_EXPRESSION_ROUTE_TEMPLATE_TYPE,
        "display_name": display_name,
        "trigger_terms": _stable_list(template.get("trigger_terms")),
        "supported_host_contexts": _stable_list(template.get("supported_host_contexts")),
        "required_module_cards": required_cards,
        "optional_module_cards": optional_cards,
        "required_slots": _stable_list(template.get("required_slots")),
        "evidence_requirements": _stable_list(template.get("evidence_requirements")),
        "gap_rules": _stable_list(template.get("gap_rules")),
        "manual_review_rules": _stable_list(template.get("manual_review_rules")),
        "blocked_outputs": _stable_list(template.get("blocked_outputs")),
        "package_sections": _stable_list(template.get("package_sections")),
        "boundary_notes": boundary_notes,
        "route_name": display_name,
        "plant_context": _clean_text(template.get("plant_context")),
        "required_module_ids": list(required_cards),
        "optional_module_ids": list(optional_cards),
        "boundary_note": boundary_notes[0] if boundary_notes else "",
    }
    return {field: normalized[field] for field in ROUTE_TEMPLATE_FIELDS}


def _registry_templates() -> list[dict[str, Any]]:
    return [
        normalize_plant_expression_route_template(template)
        for template in _PLANT_EXPRESSION_ROUTE_TEMPLATE_DEFINITIONS
    ]


def _category_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def _matches_text(query: str, candidates: Iterable[str]) -> bool:
    query_key = _clean_text(query).casefold()
    if not query_key:
        return False
    for candidate in candidates:
        candidate_key = _clean_text(candidate).casefold()
        if query_key == candidate_key or query_key in candidate_key or candidate_key in query_key:
            return True
    return False


def _matches_context(query: str, candidates: Iterable[str]) -> bool:
    query_key = _clean_text(query).casefold()
    if not query_key:
        return False
    for candidate in candidates:
        candidate_key = _clean_text(candidate).casefold()
        if query_key == candidate_key or query_key in candidate_key:
            return True
    return False


def validate_plant_expression_route_template(template: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_plant_expression_route_template(template)
    errors: list[str] = []

    if not normalized["route_id"]:
        errors.append("route_id is required")
    if normalized["route_type"] != PLANT_EXPRESSION_ROUTE_TEMPLATE_TYPE:
        errors.append("route_type must be plant_expression_vector")
    if not normalized["display_name"]:
        errors.append("display_name is required")
    if not normalized["required_module_cards"]:
        errors.append("required_module_cards must be present and non-empty")
    if not normalized["required_slots"]:
        errors.append("required_slots must be present and non-empty")
    if not normalized["manual_review_rules"]:
        errors.append("manual_review_rules must be present and non-empty")
    if not normalized["package_sections"]:
        errors.append("package_sections must be present and non-empty")

    missing_required_cards = [
        module_id
        for module_id in normalized["required_module_cards"]
        if get_plant_review_module_card_by_id(module_id) is None
    ]
    if missing_required_cards:
        errors.append("required_module_cards missing from R66 registry: " + ", ".join(missing_required_cards))

    missing_optional_cards = [
        module_id
        for module_id in normalized["optional_module_cards"]
        if get_plant_review_module_card_by_id(module_id) is None
    ]
    if missing_optional_cards:
        errors.append("optional_module_cards missing from R66 registry: " + ", ".join(missing_optional_cards))

    blocked_keys = {_category_key(item) for item in normalized["blocked_outputs"]}
    missing_blocked = [
        item
        for item in REQUIRED_BLOCKED_OUTPUT_CATEGORIES
        if _category_key(item) not in blocked_keys
    ]
    if missing_blocked:
        errors.append("blocked_outputs missing required route safety categories: " + ", ".join(missing_blocked))

    notes_blob = " ".join(normalized["boundary_notes"]).casefold()
    if "documentation-only" not in notes_blob and "documentation only" not in notes_blob:
        errors.append("boundary_notes must include documentation-only framing")
    if "manual review" not in notes_blob:
        errors.append("boundary_notes must include manual-review framing")

    return {
        "ok": not errors,
        "errors": errors,
        "normalized_template": normalized,
    }


def validate_plant_expression_route_template_registry() -> dict[str, Any]:
    templates = _registry_templates()
    template_results: list[dict[str, Any]] = []
    errors: list[str] = []

    route_ids = [template["route_id"] for template in templates]
    duplicate_route_ids = sorted({route_id for route_id in route_ids if route_ids.count(route_id) > 1})
    for route_id in duplicate_route_ids:
        errors.append(f"duplicate route_id: {route_id}")

    for template in templates:
        result = validate_plant_expression_route_template(template)
        template_result = {
            "route_id": template["route_id"],
            "ok": bool(result["ok"]),
            "errors": list(result["errors"]),
        }
        template_results.append(template_result)
        errors.extend(f"{template['route_id']}: {error}" for error in result["errors"])

    return {
        "ok": not errors,
        "route_count": str(len(templates)),
        "errors": errors,
        "template_results": template_results,
    }


def get_all_plant_expression_route_templates() -> list[dict[str, Any]]:
    return _registry_templates()


def get_plant_expression_route_template_by_id(route_id: str) -> dict[str, Any]:
    route_id_text = _clean_text(route_id)
    if not route_id_text:
        return {}
    route_id_text = ROUTE_TEMPLATE_ID_ALIASES.get(route_id_text, route_id_text)
    for template in _registry_templates():
        if template["route_id"] == route_id_text:
            return template
    return {}


def get_plant_expression_route_templates_by_route_type(route_type: str) -> list[dict[str, Any]]:
    route_type_text = _clean_text(route_type)
    if not route_type_text:
        return []
    return [
        template
        for template in _registry_templates()
        if template["route_type"] == route_type_text
    ]


def get_plant_expression_route_templates_by_trigger_term(trigger_term: str) -> list[dict[str, Any]]:
    if not _clean_text(trigger_term):
        return []
    return [
        template
        for template in _registry_templates()
        if _matches_text(trigger_term, template["trigger_terms"])
    ]


def get_plant_expression_route_templates_by_host_context(host_context: str) -> list[dict[str, Any]]:
    if not _clean_text(host_context):
        return []
    return [
        template
        for template in _registry_templates()
        if _matches_context(host_context, template["supported_host_contexts"])
    ]


def get_plant_expression_route_templates_by_required_slot(required_slot: str) -> list[dict[str, Any]]:
    required_slot_text = _clean_text(required_slot)
    if not required_slot_text:
        return []
    return [
        template
        for template in _registry_templates()
        if required_slot_text in template["required_slots"]
    ]


def get_plant_expression_route_templates_by_package_section(package_section: str) -> list[dict[str, Any]]:
    package_section_text = _clean_text(package_section)
    if not package_section_text:
        return []
    return [
        template
        for template in _registry_templates()
        if package_section_text in template["package_sections"]
    ]


def get_plant_expression_route_templates_by_context(plant_context: str) -> list[dict[str, Any]]:
    return get_plant_expression_route_templates_by_host_context(plant_context)


def get_default_plant_expression_route_template() -> dict[str, Any]:
    return get_plant_expression_route_template_by_id(DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID)


def get_plant_expression_route_template_registry_summary() -> dict[str, Any]:
    templates = _registry_templates()
    return {
        "total_route_templates": str(len(templates)),
        "route_types": [PLANT_EXPRESSION_ROUTE_TEMPLATE_TYPE],
        "canonical_route_template_id": CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
        "default_route_id": DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
        "route_id_aliases": dict(ROUTE_TEMPLATE_ID_ALIASES),
        "route_ids": [template["route_id"] for template in templates],
        "supported_host_contexts": sorted(
            {
                host_context
                for template in templates
                for host_context in template["supported_host_contexts"]
            }
        ),
        "boundary_notes": list(_BOUNDARY_NOTES),
    }
