from __future__ import annotations

from collections.abc import Iterable, Mapping
from re import fullmatch
from typing import Any


CANONICAL_CARD_FIELDS: tuple[str, ...] = (
    "module_id",
    "display_name",
    "route_type",
    "route_scope",
    "trigger_terms",
    "required_inputs",
    "required_slots",
    "allowed_outputs",
    "blocked_outputs",
    "evidence_fields",
    "gap_rules",
    "manual_review_rules",
    "package_section",
    "boundary_notes",
)

CANONICAL_LIST_FIELDS: tuple[str, ...] = (
    "trigger_terms",
    "required_inputs",
    "required_slots",
    "allowed_outputs",
    "blocked_outputs",
    "evidence_fields",
    "gap_rules",
    "manual_review_rules",
    "boundary_notes",
)

CANONICAL_STRING_FIELDS: tuple[str, ...] = (
    "module_id",
    "display_name",
    "route_type",
    "route_scope",
    "package_section",
)

CURRENT_ACTIVE_PLANT_ROUTE_TYPE = "plant_expression_vector"
SUPPORTED_PLANT_ROUTE_TYPES: tuple[str, ...] = (
    CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
)

# Existing read-only registry code imports PLANT_ROUTE_TYPES. Keep the legacy
# name stable while R400 exposes the frozen route metadata through the new helper.
PLANT_ROUTE_TYPES: tuple[str, ...] = (
    "plant_expression_vector",
    "plant_pathway_review",
    "plant_regulatory_module",
)
LEGACY_PLANT_ROUTE_TYPES: tuple[str, ...] = tuple(
    route_type for route_type in PLANT_ROUTE_TYPES if route_type not in SUPPORTED_PLANT_ROUTE_TYPES
)
VALIDATION_ROUTE_TYPES: tuple[str, ...] = tuple(dict.fromkeys((*SUPPORTED_PLANT_ROUTE_TYPES, *PLANT_ROUTE_TYPES)))

BLOCKED_OUTPUT_CATEGORIES: tuple[str, ...] = (
    "protocol",
    "optimized_sequence",
    "wet_lab_readiness",
    "experimental_validation",
    "yield_prediction",
    "build_ready_claim",
    "final_biological_solution",
    "experimental_decision",
    "build_readiness_claim",
    "experimental_validation_claim",
    "expression_success_claim",
    "yield_or_production_claim",
    "optimization_output",
    "wet_lab_procedure",
    "protocol_generation",
    "cloning_instructions",
    "primer_design",
    "restriction_enzyme_design",
    "codon_optimization_output",
    "feasibility_scoring",
    "automatic_component_recommendation",
)

REQUIRED_BLOCKED_OUTPUT_CATEGORIES: tuple[str, ...] = (
    "protocol",
    "optimized_sequence",
    "wet_lab_readiness",
    "experimental_validation",
    "yield_prediction",
    "build_ready_claim",
)

UNSAFE_ALLOWED_OUTPUT_CATEGORIES: tuple[str, ...] = (
    *BLOCKED_OUTPUT_CATEGORIES,
    "biological_recommendation",
    "sequence_generation",
    "pathway_optimization",
    "wet_lab_readiness_judgment",
    "feasibility_score",
    "yield_prediction",
)

COMMON_BLOCKED_OUTPUTS: tuple[str, ...] = (
    "biological_recommendation",
    "sequence_generation",
    "pathway_optimization",
    "wet_lab_readiness_judgment",
    "feasibility_score",
    "yield_prediction",
)
COMMON_BOUNDARY_NOTE = (
    "Documentation-only Plant Review Module Card for manual review. It records "
    "route context, source gaps, and traceability notes without biological recommendation, "
    "route generation, feasibility scoring, or wet-lab readiness judgment."
)

# Compatibility fields are retained for already-merged read-only registry callers.
# They are derived from canonical fields or sanitized legacy input and are not part
# of the R400 canonical schema contract returned by get_plant_review_module_card_schema().
COMPATIBILITY_CARD_FIELDS: tuple[str, ...] = (
    "module_name",
    "route_priority",
    "optional_slots",
    "boundary_note",
)

CARD_FIELDS: tuple[str, ...] = (*CANONICAL_CARD_FIELDS, *COMPATIBILITY_CARD_FIELDS)
CARD_LIST_FIELDS: tuple[str, ...] = (
    "trigger_terms",
    "required_inputs",
    "required_slots",
    "evidence_fields",
    "gap_rules",
    "manual_review_rules",
    "allowed_outputs",
    "blocked_outputs",
    "optional_slots",
    "boundary_notes",
)

_FIELD_DESCRIPTIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "module_id",
        "value_type": "string",
        "required": True,
        "description": "Safe slug-like card identifier for documentation records.",
    },
    {
        "name": "display_name",
        "value_type": "string",
        "required": True,
        "description": "Human-readable card name for review surfaces.",
    },
    {
        "name": "route_type",
        "value_type": "string",
        "required": True,
        "description": "Plant route family identifier from supported route metadata.",
    },
    {
        "name": "route_scope",
        "value_type": "string",
        "required": True,
        "description": "Short plant workflow scope for the card, kept as documentation context.",
    },
    {
        "name": "trigger_terms",
        "value_type": "list[string]",
        "required": False,
        "description": "Terms that may help locate a card in later manual review workflows.",
    },
    {
        "name": "required_inputs",
        "value_type": "list[string]",
        "required": False,
        "description": "Input documentation fields expected before review.",
    },
    {
        "name": "required_slots",
        "value_type": "list[string]",
        "required": False,
        "description": "Named documentation slots expected in the card.",
    },
    {
        "name": "allowed_outputs",
        "value_type": "list[string]",
        "required": False,
        "description": "Documentation readback categories the card may emit later.",
    },
    {
        "name": "blocked_outputs",
        "value_type": "list[string]",
        "required": True,
        "description": "Conservative output categories the card must not provide.",
    },
    {
        "name": "evidence_fields",
        "value_type": "list[string]",
        "required": False,
        "description": "Traceability and source-review fields retained for manual review.",
    },
    {
        "name": "gap_rules",
        "value_type": "list[string]",
        "required": False,
        "description": "Plain documentation gap labels; no automatic closure behavior.",
    },
    {
        "name": "manual_review_rules",
        "value_type": "list[string]",
        "required": True,
        "description": "Human review framing required before downstream use.",
    },
    {
        "name": "package_section",
        "value_type": "string",
        "required": True,
        "description": "Documentation package section label for future readback grouping.",
    },
    {
        "name": "boundary_notes",
        "value_type": "list[string]",
        "required": True,
        "description": "Documentation-only and manual-review boundary notes.",
    },
)


class PlantReviewModuleCardValidationError(ValueError):
    """Raised by compatibility helpers when a card fails R400 validation."""


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


def _route_priority(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _category_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def _has_documentation_only_framing(notes: list[str]) -> bool:
    blob = " ".join(notes).casefold()
    return "documentation-only" in blob or "documentation only" in blob


def _has_manual_review_framing(notes: list[str]) -> bool:
    blob = " ".join(notes).casefold()
    return "manual review" in blob or "human review" in blob


def _normalized_boundary_notes(card: Mapping[str, Any]) -> list[str]:
    notes = _stable_list(card.get("boundary_notes"))
    if not notes:
        legacy_note = _clean_text(card.get("boundary_note"))
        if legacy_note:
            notes = [legacy_note]
    return notes


def _base_normalized_card(card: Mapping[str, Any]) -> dict[str, Any]:
    display_name = _clean_text(card.get("display_name")) or _clean_text(card.get("module_name"))
    boundary_notes = _normalized_boundary_notes(card)
    route_scope = _clean_text(card.get("route_scope")) or _clean_text(card.get("route_type"))
    normalized: dict[str, Any] = {
        "module_id": _clean_text(card.get("module_id")),
        "display_name": display_name,
        "route_type": _clean_text(card.get("route_type")),
        "route_scope": route_scope,
        "trigger_terms": _stable_list(card.get("trigger_terms")),
        "required_inputs": _stable_list(card.get("required_inputs")),
        "required_slots": _stable_list(card.get("required_slots")),
        "allowed_outputs": _stable_list(card.get("allowed_outputs")),
        "blocked_outputs": _stable_list(card.get("blocked_outputs")),
        "evidence_fields": _stable_list(card.get("evidence_fields")),
        "gap_rules": _stable_list(card.get("gap_rules")),
        "manual_review_rules": _stable_list(card.get("manual_review_rules")),
        "package_section": _clean_text(card.get("package_section")),
        "boundary_notes": boundary_notes,
    }
    normalized.update(
        {
            "module_name": display_name,
            "route_priority": _route_priority(card.get("route_priority")),
            "optional_slots": _stable_list(card.get("optional_slots")),
            "boundary_note": boundary_notes[0] if boundary_notes else "",
        }
    )
    return normalized


def get_plant_review_module_card_schema() -> dict[str, Any]:
    return {
        "schema_name": "plant_review_module_card",
        "schema_version": "v2.7-r66",
        "canonical_fields": list(CANONICAL_CARD_FIELDS),
        "list_fields": list(CANONICAL_LIST_FIELDS),
        "string_fields": list(CANONICAL_STRING_FIELDS),
        "field_descriptions": [dict(field) for field in _FIELD_DESCRIPTIONS],
        "blocked_output_categories": list(BLOCKED_OUTPUT_CATEGORIES),
        "required_blocked_output_categories": list(REQUIRED_BLOCKED_OUTPUT_CATEGORIES),
        "validation_boundary": {
            "documentation_only_required": True,
            "manual_review_required": True,
            "runtime_hooks": [],
        },
    }


def get_supported_plant_route_types() -> dict[str, Any]:
    return {
        "current_active_route_type": CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
        "route_types": [
            {
                "route_type": CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
                "display_name": "Plant Expression Vector",
                "status": "current_active",
                "active": True,
            },
        ],
    }


def normalize_plant_review_module_card(card: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(card, Mapping):
        card = {}
    return _base_normalized_card(card)


def validate_plant_review_module_card(card: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_plant_review_module_card(card)
    errors: list[str] = []
    warnings: list[str] = []

    module_id = normalized["module_id"]
    if not module_id:
        errors.append("module_id is required")
    elif not fullmatch(r"[a-z][a-z0-9_-]*", module_id):
        errors.append("module_id must be a safe slug-like identifier")

    for field in ("display_name", "route_type", "route_scope", "package_section"):
        if not normalized[field]:
            errors.append(f"{field} is required")

    route_type = normalized["route_type"]
    if route_type and route_type not in VALIDATION_ROUTE_TYPES:
        errors.append(f"route_type is not supported: {route_type}")
    elif route_type in LEGACY_PLANT_ROUTE_TYPES:
        warnings.append(f"route_type uses legacy read-only registry label: {route_type}")

    blocked_outputs = normalized["blocked_outputs"]
    if not blocked_outputs:
        errors.append("blocked_outputs must be present and non-empty")
    else:
        blocked_keys = {_category_key(item) for item in blocked_outputs}
        missing_required_blocked = [
            item
            for item in REQUIRED_BLOCKED_OUTPUT_CATEGORIES
            if _category_key(item) not in blocked_keys
        ]
        if missing_required_blocked:
            errors.append(
                "blocked_outputs missing required safety categories: "
                + ", ".join(missing_required_blocked)
            )

    manual_review_rules = normalized["manual_review_rules"]
    if not manual_review_rules:
        errors.append("manual_review_rules must be present and non-empty")

    allowed_category_keys = {_category_key(item) for item in normalized["allowed_outputs"]}
    unsafe_category_keys = {_category_key(item) for item in UNSAFE_ALLOWED_OUTPUT_CATEGORIES}
    unsafe_allowed_outputs = sorted(allowed_category_keys.intersection(unsafe_category_keys))
    if unsafe_allowed_outputs:
        errors.append("allowed_outputs contains blocked or unsafe output categories: " + ", ".join(unsafe_allowed_outputs))

    blocked_category_keys = {_category_key(item) for item in BLOCKED_OUTPUT_CATEGORIES}
    if allowed_category_keys.intersection(blocked_category_keys):
        errors.append("allowed_outputs overlaps with blocked output categories")

    boundary_notes = normalized["boundary_notes"]
    if not boundary_notes:
        errors.append("boundary_notes must be present and non-empty")
    else:
        if not _has_documentation_only_framing(boundary_notes):
            errors.append("boundary_notes must include documentation-only framing")
        if not _has_manual_review_framing(boundary_notes):
            errors.append("boundary_notes must include manual-review framing")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "normalized_card": normalized,
    }


def is_valid_plant_review_module_card(card: Mapping[str, Any]) -> bool:
    return bool(validate_plant_review_module_card(card)["ok"])


def plant_review_module_sample_cards() -> list[dict[str, Any]]:
    return [normalize_plant_review_module_card(card) for card in _SAMPLE_CARD_DEFINITIONS]


_SAMPLE_CARD_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "module_id": "plant_expression_vector_intake",
        "display_name": "Plant Expression Vector Intake",
        "route_type": CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
        "route_scope": "plant expression vector documentation",
        "trigger_terms": ("plant expression", "vector record", "review card"),
        "required_inputs": ("plant context note", "construct goal note", "source reference note"),
        "required_slots": ("plant_context", "construct_goal", "source_reference"),
        "allowed_outputs": ("documentation_readback", "gap_notes", "manual_review_status"),
        "blocked_outputs": BLOCKED_OUTPUT_CATEGORIES,
        "evidence_fields": ("source_reference", "traceability_note", "reviewer_note"),
        "gap_rules": ("flag missing source reference", "preserve unresolved review gaps"),
        "manual_review_rules": ("manual review required before downstream use",),
        "package_section": "plant_expression_vector_review",
        "boundary_notes": (COMMON_BOUNDARY_NOTE,),
    }
)
