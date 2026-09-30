from __future__ import annotations

from typing import Any

from services.plant_expression_route_template_registry import (
    CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
    DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
    ROUTE_TEMPLATE_ID_ALIASES,
    get_plant_expression_route_template_by_id,
)
from services.plant_review_module_card_registry import get_plant_review_module_card_by_id
from services.plant_review_module_card_schema import COMMON_BLOCKED_OUTPUTS


LEGACY_PLANT_EXPRESSION_ROUTE_TYPE_ID = "plant_expression_vector"

_HELPER_BOUNDARY_NOTES: tuple[str, ...] = (
    "Documentation-only route-template compatibility readback for manual review.",
    "Alias resolution is compatibility metadata only, not a biological recommendation or final design decision.",
    "This helper does not generate routes, recommend components, generate sequences, score feasibility, or judge wet-lab readiness.",
)

_LEGACY_ROUTE_TYPE_ALIASES: dict[str, str] = {
    LEGACY_PLANT_EXPRESSION_ROUTE_TYPE_ID: DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
}


def _plain_card_resolution(module_id: str, module_role: str) -> dict[str, Any]:
    card = get_plant_review_module_card_by_id(module_id)
    if card is None:
        return {
            "requested_module_id": module_id,
            "resolved_module_id": "",
            "module_role": module_role,
            "resolved": False,
            "status": "missing_manual_review_required",
        }
    return {
        "requested_module_id": module_id,
        "resolved_module_id": card["module_id"],
        "module_role": module_role,
        "resolved": True,
        "status": "resolved",
    }


def _module_card_resolution_for_template(template: dict[str, Any]) -> dict[str, Any]:
    required = [
        _plain_card_resolution(str(module_id), "required")
        for module_id in template.get("required_module_ids", [])
    ]
    optional = [
        _plain_card_resolution(str(module_id), "optional")
        for module_id in template.get("optional_module_ids", [])
    ]
    missing = [
        item
        for item in (*required, *optional)
        if item["status"] != "resolved"
    ]
    return {
        "status": "all_resolved" if not missing else "missing_manual_review_required",
        "required_module_cards": required,
        "optional_module_cards": optional,
        "missing_module_cards": missing,
        "resolved_required_count": sum(1 for item in required if item["resolved"]),
        "resolved_optional_count": sum(1 for item in optional if item["resolved"]),
    }


def _empty_module_card_resolution() -> dict[str, Any]:
    return {
        "status": "blocked_unknown_route_id",
        "required_module_cards": [],
        "optional_module_cards": [],
        "missing_module_cards": [],
        "resolved_required_count": 0,
        "resolved_optional_count": 0,
    }


def _resolve_requested_route_id(route_id: str) -> dict[str, Any]:
    requested_route_id = str(route_id or "").strip()
    if not requested_route_id:
        return {
            "requested_route_id": requested_route_id,
            "resolved_canonical_route_id": "",
            "resolved_legacy_route_id": "",
            "lookup_route_id": "",
            "alias_status": "empty_route_id_blocked",
            "is_alias": False,
        }

    if requested_route_id == CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID:
        return {
            "requested_route_id": requested_route_id,
            "resolved_canonical_route_id": CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
            "resolved_legacy_route_id": ROUTE_TEMPLATE_ID_ALIASES[requested_route_id],
            "lookup_route_id": requested_route_id,
            "alias_status": "canonical_alias_to_stored_legacy_route_id",
            "is_alias": True,
        }

    if requested_route_id in _LEGACY_ROUTE_TYPE_ALIASES:
        return {
            "requested_route_id": requested_route_id,
            "resolved_canonical_route_id": CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
            "resolved_legacy_route_id": _LEGACY_ROUTE_TYPE_ALIASES[requested_route_id],
            "lookup_route_id": _LEGACY_ROUTE_TYPE_ALIASES[requested_route_id],
            "alias_status": "legacy_route_type_alias_to_default_stored_route_id",
            "is_alias": True,
        }

    template = get_plant_expression_route_template_by_id(requested_route_id)
    if template:
        stored_route_id = str(template["route_id"])
        return {
            "requested_route_id": requested_route_id,
            "resolved_canonical_route_id": CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
            "resolved_legacy_route_id": stored_route_id,
            "lookup_route_id": requested_route_id,
            "alias_status": "stored_legacy_route_id" if stored_route_id == requested_route_id else "route_id_alias",
            "is_alias": stored_route_id != requested_route_id,
        }

    return {
        "requested_route_id": requested_route_id,
        "resolved_canonical_route_id": "",
        "resolved_legacy_route_id": "",
        "lookup_route_id": requested_route_id,
        "alias_status": "unknown_route_id_blocked",
        "is_alias": False,
    }


def build_plant_route_template_compatibility_readback(route_id: str) -> dict[str, Any]:
    """Return read-only compatibility metadata for a plant route-template ID."""
    resolution = _resolve_requested_route_id(route_id)
    lookup_route_id = resolution["lookup_route_id"]
    template = get_plant_expression_route_template_by_id(lookup_route_id) if lookup_route_id else {}

    if not template:
        return {
            **resolution,
            "route_template_found": False,
            "route_template_status": "blocked_manual_review_required",
            "route_name": "",
            "route_type": "",
            "plant_context": "",
            "module_card_resolution": _empty_module_card_resolution(),
            "manual_review_notes": list(_HELPER_BOUNDARY_NOTES),
            "boundary_notes": list(_HELPER_BOUNDARY_NOTES),
            "blocked_output_categories": list(COMMON_BLOCKED_OUTPUTS),
        }

    module_card_resolution = _module_card_resolution_for_template(template)
    boundary_notes = [*list(_HELPER_BOUNDARY_NOTES), str(template.get("boundary_note", ""))]
    return {
        **resolution,
        "route_template_found": True,
        "route_template_status": "resolved_readback_only",
        "route_name": template["route_name"],
        "route_type": template["route_type"],
        "plant_context": template["plant_context"],
        "module_card_resolution": module_card_resolution,
        "manual_review_notes": [*list(_HELPER_BOUNDARY_NOTES), *list(template["manual_review_rules"])],
        "boundary_notes": [note for note in boundary_notes if note],
        "blocked_output_categories": list(template.get("blocked_outputs", COMMON_BLOCKED_OUTPUTS)),
    }


def build_known_plant_route_template_compatibility_readbacks() -> list[dict[str, Any]]:
    return [
        build_plant_route_template_compatibility_readback(route_id)
        for route_id in (
            CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
            "generic_plant_expression_vector_route",
            LEGACY_PLANT_EXPRESSION_ROUTE_TYPE_ID,
        )
    ]
