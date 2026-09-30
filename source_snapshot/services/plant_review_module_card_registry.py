from __future__ import annotations

from typing import Any

from services.plant_review_module_card_schema import (
    BLOCKED_OUTPUT_CATEGORIES,
    CANONICAL_CARD_FIELDS,
    COMMON_BOUNDARY_NOTE,
    CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
    normalize_plant_review_module_card,
    validate_plant_review_module_card,
)


REGISTRY_TITLE = "Plant Review Module Card Registry"
REGISTRY_SUBTITLE = (
    "Read-only Plant Expression Vector review card skeletons for documentation-only manual review."
)

_ROUTE_SCOPE = "plant expression vector documentation review"
_ALLOWED_REVIEW_OUTPUTS: tuple[str, ...] = (
    "candidate route intake summary",
    "required slot readback",
    "source evidence request",
    "missing field note",
    "manual review item",
    "package section draft",
    "documentation-only boundary note",
)
_BOUNDARY_NOTES: tuple[str, ...] = (
    COMMON_BOUNDARY_NOTE,
    "Manual review is required before any downstream documentation handoff; this card is not a biological recommendation or experiment validation claim.",
)


def _card(
    *,
    module_id: str,
    display_name: str,
    trigger_terms: tuple[str, ...],
    required_inputs: tuple[str, ...],
    required_slots: tuple[str, ...],
    evidence_fields: tuple[str, ...],
    gap_rules: tuple[str, ...],
    manual_review_rules: tuple[str, ...],
    package_section: str,
) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "display_name": display_name,
        "route_type": CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
        "route_scope": _ROUTE_SCOPE,
        "trigger_terms": trigger_terms,
        "required_inputs": required_inputs,
        "required_slots": required_slots,
        "allowed_outputs": _ALLOWED_REVIEW_OUTPUTS,
        "blocked_outputs": BLOCKED_OUTPUT_CATEGORIES,
        "evidence_fields": evidence_fields,
        "gap_rules": gap_rules,
        "manual_review_rules": manual_review_rules,
        "package_section": package_section,
        "boundary_notes": _BOUNDARY_NOTES,
    }


_PLANT_REVIEW_MODULE_CARD_DEFINITIONS: tuple[dict[str, Any], ...] = (
    _card(
        module_id="plant_target_intake",
        display_name="Plant Target Intake",
        trigger_terms=("plant goal", "target record", "plant expression vector"),
        required_inputs=("plant goal note", "target identity note", "source evidence pointer"),
        required_slots=("target_name", "plant_context", "documentation_goal"),
        evidence_fields=("target_source_reference", "plant_context_note", "traceability_note"),
        gap_rules=("flag missing target source evidence", "flag missing plant context note"),
        manual_review_rules=("route target context to manual review", "preserve unresolved target gaps"),
        package_section="plant_target_intake_review",
    ),
    _card(
        module_id="plant_host_context",
        display_name="Plant Host Context",
        trigger_terms=("plant host", "plant chassis", "species context"),
        required_inputs=("host plant note", "tissue or context note", "host source evidence"),
        required_slots=("plant_species", "host_context_note", "source_reference"),
        evidence_fields=("host_source_reference", "species_context_note", "reviewer_note"),
        gap_rules=("flag missing host source evidence", "flag unresolved plant context"),
        manual_review_rules=("keep host context as review context", "do not infer biological suitability"),
        package_section="plant_host_context_review",
    ),
    _card(
        module_id="cds_source_review",
        display_name="CDS Source Review",
        trigger_terms=("cds source", "coding sequence source", "gene source"),
        required_inputs=("CDS identity note", "source evidence pointer", "version or accession note"),
        required_slots=("cds_label", "source_reference", "sequence_source_note"),
        evidence_fields=("source_reference", "identity_note", "curation_note"),
        gap_rules=("flag missing CDS source evidence", "flag unclear identity or version note"),
        manual_review_rules=("preserve source uncertainty for manual review", "do not rewrite or generate sequences"),
        package_section="cds_source_review",
    ),
    _card(
        module_id="plant_expression_cassette",
        display_name="Plant Expression Cassette",
        trigger_terms=("plant cassette", "expression cassette", "cassette slots"),
        required_inputs=("cassette slot list", "plant expression context", "slot source notes"),
        required_slots=("promoter_slot", "coding_sequence_slot", "terminator_slot"),
        evidence_fields=("slot_source_note", "slot_provenance_note", "manual_review_note"),
        gap_rules=("flag missing slot provenance", "flag unresolved cassette context"),
        manual_review_rules=("show cassette gaps for manual review", "keep slot source notes traceable"),
        package_section="plant_expression_cassette_review",
    ),
    _card(
        module_id="promoter_leader_review",
        display_name="Promoter And Leader Review",
        trigger_terms=("plant promoter", "leader record", "regulatory slot"),
        required_inputs=("promoter record", "leader record if present", "source evidence pointers"),
        required_slots=("promoter_slot", "promoter_source_reference", "manual_review_note"),
        evidence_fields=("promoter_source_note", "leader_source_note", "context_note"),
        gap_rules=("flag missing promoter provenance", "flag missing leader provenance when listed"),
        manual_review_rules=("record regulatory context for review", "do not rank or choose regulatory elements"),
        package_section="promoter_leader_review",
    ),
    _card(
        module_id="signal_peptide_localization",
        display_name="Signal Peptide Localization",
        trigger_terms=("signal peptide", "localization note", "targeting sequence record"),
        required_inputs=("localization intent note", "signal peptide source note", "plant context"),
        required_slots=("localization_note", "signal_peptide_slot", "source_reference"),
        evidence_fields=("source_reference", "localization_context_note", "manual_review_note"),
        gap_rules=("flag missing signal peptide source evidence", "flag unresolved localization context"),
        manual_review_rules=("preserve localization claims as source notes", "do not infer expression outcome"),
        package_section="signal_peptide_localization_review",
    ),
    _card(
        module_id="terminator_marker_review",
        display_name="Terminator And Marker Review",
        trigger_terms=("terminator record", "plant marker", "selection marker record"),
        required_inputs=("terminator record", "marker record if present", "source evidence pointers"),
        required_slots=("terminator_slot", "terminator_source_reference", "manual_review_note"),
        evidence_fields=("terminator_source_note", "marker_source_note", "context_note"),
        gap_rules=("flag missing terminator provenance", "flag missing marker provenance when listed"),
        manual_review_rules=("record terminator and marker context for review", "do not infer performance or use status"),
        package_section="terminator_marker_review",
    ),
    _card(
        module_id="vector_backbone_context",
        display_name="Vector Backbone Context",
        trigger_terms=("vector backbone", "plant vector record", "backbone context"),
        required_inputs=("backbone record", "source evidence pointer", "project context note"),
        required_slots=("backbone_label", "source_reference", "context_note"),
        evidence_fields=("backbone_source_note", "context_note", "manual_review_note"),
        gap_rules=("flag missing backbone source evidence", "flag unresolved vector context"),
        manual_review_rules=("keep backbone context as documentation readback", "do not create assembly instructions"),
        package_section="vector_backbone_context_review",
    ),
    _card(
        module_id="component_provenance",
        display_name="Component Provenance",
        trigger_terms=("component provenance", "source traceability", "component record"),
        required_inputs=("component records", "source labels", "review notes"),
        required_slots=("component_name", "component_type", "source_reference"),
        evidence_fields=("source_reference", "curation_note", "traceability_note"),
        gap_rules=("flag missing provenance", "flag unclear component category"),
        manual_review_rules=("require human source review", "preserve traceability gaps"),
        package_section="component_provenance_review",
    ),
    _card(
        module_id="codon_usage_readonly",
        display_name="Codon Usage Read-Only",
        trigger_terms=("codon usage note", "plant codon usage", "read-only codon review"),
        required_inputs=("codon usage source note", "CDS source note", "plant context"),
        required_slots=("cds_label", "codon_usage_source_note", "manual_review_note"),
        evidence_fields=("codon_usage_source_note", "species_context_note", "manual_review_note"),
        gap_rules=("flag missing codon usage source note", "flag unresolved plant species context"),
        manual_review_rules=("treat codon usage as read-only documentation context", "do not alter sequence content"),
        package_section="codon_usage_readonly_review",
    ),
    _card(
        module_id="gap_queue",
        display_name="Gap Queue",
        trigger_terms=("gap queue", "manual follow-up", "missing source note"),
        required_inputs=("gap list", "review notes", "source status notes"),
        required_slots=("gap_label", "gap_source", "manual_review_status"),
        evidence_fields=("gap_note", "source_status_note", "reviewer_note"),
        gap_rules=("preserve unresolved gaps", "flag missing source status"),
        manual_review_rules=("keep gaps visible for manual review", "do not close gaps automatically"),
        package_section="gap_queue_review",
    ),
    _card(
        module_id="plant_review_package",
        display_name="Plant Review Package",
        trigger_terms=("review package", "package readback", "plant review summary"),
        required_inputs=("card readbacks", "gap queue", "boundary notes"),
        required_slots=("module_card_list", "gap_summary", "boundary_note"),
        evidence_fields=("card_summary_note", "gap_summary_note", "boundary_note"),
        gap_rules=("flag missing card readback", "flag missing boundary note"),
        manual_review_rules=("summarize only documented review state", "do not certify biological or lab use status"),
        package_section="plant_review_package_review",
    ),
)

_LEGACY_MODULE_ID_ALIASES: dict[str, str] = {
    "plant_expression_cassette_slot_review": "plant_expression_cassette",
    "plant_promoter_leader_review": "promoter_leader_review",
    "plant_signal_peptide_localization_review": "signal_peptide_localization",
    "signal_peptide_localization_review": "signal_peptide_localization",
    "plant_terminator_marker_review": "terminator_marker_review",
    "plant_vector_backbone_context": "vector_backbone_context",
    "plant_component_provenance_review": "component_provenance",
    "component_provenance_review": "component_provenance",
    "plant_codon_usage_readonly_review": "codon_usage_readonly",
    "codon_usage_readonly_review": "codon_usage_readonly",
    "plant_gap_queue_review": "gap_queue",
    "gap_queue_review": "gap_queue",
    "plant_review_package_review": "plant_review_package",
}


def _canonical_card(card: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_plant_review_module_card(card)
    return {field: normalized[field] for field in CANONICAL_CARD_FIELDS}


def _registry_cards() -> list[dict[str, Any]]:
    return [_canonical_card(card) for card in _PLANT_REVIEW_MODULE_CARD_DEFINITIONS]


def get_plant_review_module_cards() -> list[dict[str, Any]]:
    """Return all Plant Review Module Cards as normalized canonical dicts."""
    return _registry_cards()


def get_active_plant_expression_review_cards() -> list[dict[str, Any]]:
    """Return active Plant Expression Vector review cards only."""
    return [
        card
        for card in _registry_cards()
        if card["route_type"] == CURRENT_ACTIVE_PLANT_ROUTE_TYPE
    ]


def get_plant_review_module_card_by_id(module_id: str) -> dict[str, Any] | None:
    module_id_text = str(module_id or "").strip()
    if not module_id_text:
        return None
    module_id_text = _LEGACY_MODULE_ID_ALIASES.get(module_id_text, module_id_text)
    for card in _registry_cards():
        if card["module_id"] == module_id_text:
            return card
    return None


def validate_plant_review_module_card_registry() -> dict[str, Any]:
    card_results: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for card in _registry_cards():
        result = validate_plant_review_module_card(card)
        card_result = {
            "module_id": card["module_id"],
            "ok": bool(result["ok"]),
            "errors": list(result["errors"]),
            "warnings": list(result["warnings"]),
        }
        card_results.append(card_result)
        errors.extend(f"{card['module_id']}: {error}" for error in result["errors"])
        warnings.extend(f"{card['module_id']}: {warning}" for warning in result["warnings"])

    return {
        "ok": not errors,
        "card_count": len(card_results),
        "errors": errors,
        "warnings": warnings,
        "card_results": card_results,
    }


def build_plant_review_module_card_registry_readback() -> dict[str, Any]:
    cards = get_active_plant_expression_review_cards()
    boundary_notes = [
        "Documentation-only registry readback for Plant Expression Vector review cards.",
        "Manual review remains required; registry cards do not provide biological recommendations, scoring, or lab-use judgments.",
    ]
    return {
        "title": REGISTRY_TITLE,
        "subtitle": REGISTRY_SUBTITLE,
        "active_route_type": CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
        "card_count": len(cards),
        "cards": cards,
        "boundary_notes": boundary_notes,
        "empty_state": "No active Plant Expression Vector review cards are registered." if not cards else "",
    }


# Compatibility aliases for already-merged read-only callers. New R401 callers should
# use the helpers above.
CURRENT_PRIORITY_ROUTE_TYPE = CURRENT_ACTIVE_PLANT_ROUTE_TYPE


def get_all_plant_review_module_cards() -> list[dict[str, Any]]:
    return get_plant_review_module_cards()


def get_plant_review_module_cards_by_route_type(route_type: str) -> list[dict[str, Any]]:
    route_type_text = str(route_type or "").strip()
    if not route_type_text:
        return []
    return [card for card in _registry_cards() if card["route_type"] == route_type_text]


def get_plant_review_module_cards_by_trigger_term(trigger_term: str) -> list[dict[str, Any]]:
    trigger_term_text = str(trigger_term or "").strip().casefold()
    if not trigger_term_text:
        return []
    return [
        card
        for card in _registry_cards()
        if any(term.casefold() == trigger_term_text for term in card["trigger_terms"])
    ]


def get_plant_review_module_cards_by_required_slot(required_slot: str) -> list[dict[str, Any]]:
    required_slot_text = str(required_slot or "").strip()
    if not required_slot_text:
        return []
    return [
        card
        for card in _registry_cards()
        if required_slot_text in card["required_slots"]
    ]


def get_plant_review_module_cards_by_package_section(package_section: str) -> list[dict[str, Any]]:
    package_section_text = str(package_section or "").strip()
    if not package_section_text:
        return []
    return [
        card
        for card in _registry_cards()
        if card["package_section"] == package_section_text
    ]


def get_current_expression_vector_module_cards() -> list[dict[str, Any]]:
    return get_active_plant_expression_review_cards()


def get_plant_review_module_card_registry_summary() -> dict[str, Any]:
    readback = build_plant_review_module_card_registry_readback()
    return {
        "total_cards": readback["card_count"],
        "route_types": [readback["active_route_type"]],
        "current_priority_route_type": CURRENT_PRIORITY_ROUTE_TYPE,
        "current_priority_card_count": readback["card_count"],
        "current_priority_module_ids": [card["module_id"] for card in readback["cards"]],
        "boundary_notes": list(readback["boundary_notes"]),
    }
