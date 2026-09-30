from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_expression_route_template_registry import get_all_plant_expression_route_templates
from services.plant_review_readback_helpers import coerce_list, coerce_mapping_list, coerce_text


PAGE_TITLE = "Plant Route Template Registry Readback"
SUBTITLE = "Documentation-only route template summary for manual review."
BOUNDARY_NOTICE = (
    "Documentation-only plant route template presenter for manual review. It formats existing "
    "route template records without ordering routes as choices, choosing components, generating routes, "
    "generating sequences, or judging downstream use."
)
EMPTY_STATE_MESSAGE = "No plant route template records are available for read-only review."

PRESENTER_KEYS: tuple[str, ...] = (
    "page_title",
    "subtitle",
    "summary_card",
    "template_rows",
    "module_link_rows",
    "package_section_rows",
    "boundary_notice",
    "empty_state",
)


def _text(value: Any) -> str:
    return coerce_text(value)


def _sequence(value: Any) -> list[Any]:
    return coerce_list(value)


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    return coerce_mapping_list(value)


def _template_rows(templates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, template in enumerate(templates, start=1):
        rows.append(
            {
                "row_id": f"route-template-{index:02d}",
                "route_id": _text(template.get("route_id")),
                "route_name": _text(template.get("route_name")),
                "plant_context": _text(template.get("plant_context")),
                "route_type": _text(template.get("route_type")),
                "required_module_count": len(_sequence(template.get("required_module_ids"))),
                "required_slot_count": len(_sequence(template.get("required_slots"))),
                "package_section_count": len(_sequence(template.get("package_sections"))),
            }
        )
    return rows


def _module_link_rows(templates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for template in templates:
        route_id = _text(template.get("route_id"))
        for module_id in _sequence(template.get("required_module_ids")):
            rows.append(
                {
                    "row_id": f"module-link-{len(rows) + 1:03d}",
                    "route_id": route_id,
                    "module_id": _text(module_id),
                    "required_or_optional": "required",
                }
            )
        for module_id in _sequence(template.get("optional_module_ids")):
            rows.append(
                {
                    "row_id": f"module-link-{len(rows) + 1:03d}",
                    "route_id": route_id,
                    "module_id": _text(module_id),
                    "required_or_optional": "optional",
                }
            )
    return rows


def _package_section_rows(templates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for template in templates:
        route_id = _text(template.get("route_id"))
        for index, section_id in enumerate(_sequence(template.get("package_sections")), start=1):
            rows.append(
                {
                    "row_id": f"package-section-{len(rows) + 1:03d}",
                    "route_id": route_id,
                    "section_id": _text(section_id),
                    "display_order": index,
                }
            )
    return rows


def present_plant_route_templates(
    templates: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return deterministic plain readback sections for plant route templates."""
    source_templates = _mapping_list(templates if templates is not None else get_all_plant_expression_route_templates())
    template_rows = _template_rows(source_templates)
    module_rows = _module_link_rows(source_templates)
    package_rows = _package_section_rows(source_templates)
    return {
        "page_title": PAGE_TITLE,
        "subtitle": SUBTITLE,
        "summary_card": {
            "template_count": len(template_rows),
            "module_link_count": len(module_rows),
            "package_section_link_count": len(package_rows),
            "manual_review_required": True,
        },
        "template_rows": template_rows,
        "module_link_rows": module_rows,
        "package_section_rows": package_rows,
        "boundary_notice": BOUNDARY_NOTICE,
        "empty_state": {
            "is_empty": not bool(template_rows),
            "message": EMPTY_STATE_MESSAGE if not template_rows else "",
        },
    }
