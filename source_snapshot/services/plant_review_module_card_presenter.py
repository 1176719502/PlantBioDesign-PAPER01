from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_review_module_card_registry import get_active_plant_expression_review_cards
from services.plant_review_readback_helpers import coerce_list, coerce_mapping_list, coerce_text


PAGE_TITLE = "Plant Review Module Card Registry Readback"
SUBTITLE = "Documentation-only module card summary for manual review."
BOUNDARY_NOTICE = (
    "Documentation-only plant review module card presenter for manual review. It formats existing "
    "module card records without choosing components, generating sequences, closing gaps, writing "
    "packages, or judging downstream use."
)
EMPTY_STATE_MESSAGE = "No plant review module card records are available for read-only review."

PRESENTER_KEYS: tuple[str, ...] = (
    "page_title",
    "subtitle",
    "summary_card",
    "module_rows",
    "package_section_rows",
    "review_rule_rows",
    "boundary_notice",
    "empty_state",
)


def _text(value: Any) -> str:
    return coerce_text(value)


def _sequence(value: Any) -> list[Any]:
    return coerce_list(value)


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    return coerce_mapping_list(value)


def _module_rows(cards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, card in enumerate(cards, start=1):
        rows.append(
            {
                "row_id": f"module-card-{index:02d}",
                "module_id": _text(card.get("module_id")),
                "display_name": _text(card.get("display_name")),
                "route_type": _text(card.get("route_type")),
                "required_input_count": len(_sequence(card.get("required_inputs"))),
                "required_slot_count": len(_sequence(card.get("required_slots"))),
                "evidence_field_count": len(_sequence(card.get("evidence_fields"))),
                "gap_rule_count": len(_sequence(card.get("gap_rules"))),
                "manual_review_rule_count": len(_sequence(card.get("manual_review_rules"))),
                "package_section": _text(card.get("package_section")),
            }
        )
    return rows


def _package_section_rows(cards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in cards:
        section_id = _text(card.get("package_section"))
        if not section_id:
            continue
        rows.append(
            {
                "row_id": f"module-package-section-{len(rows) + 1:03d}",
                "module_id": _text(card.get("module_id")),
                "section_id": section_id,
                "section_role": "module review readback",
            }
        )
    return rows


def _review_rule_rows(cards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in cards:
        rows.append(
            {
                "row_id": f"module-review-rule-{len(rows) + 1:03d}",
                "module_id": _text(card.get("module_id")),
                "gap_rule_count": len(_sequence(card.get("gap_rules"))),
                "manual_review_rule_count": len(_sequence(card.get("manual_review_rules"))),
                "manual_review_required": True,
            }
        )
    return rows


def present_plant_review_module_cards(
    cards: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return deterministic plain readback sections for plant review module cards."""
    source_cards = _mapping_list(cards if cards is not None else get_active_plant_expression_review_cards())
    module_rows = _module_rows(source_cards)
    package_rows = _package_section_rows(source_cards)
    review_rows = _review_rule_rows(source_cards)
    route_types = sorted({_text(card.get("route_type")) for card in source_cards if _text(card.get("route_type"))})
    return {
        "page_title": PAGE_TITLE,
        "subtitle": SUBTITLE,
        "summary_card": {
            "module_card_count": len(module_rows),
            "package_section_count": len(package_rows),
            "review_rule_row_count": len(review_rows),
            "route_types": route_types,
            "manual_review_required": True,
        },
        "module_rows": module_rows,
        "package_section_rows": package_rows,
        "review_rule_rows": review_rows,
        "boundary_notice": BOUNDARY_NOTICE,
        "empty_state": {
            "is_empty": not bool(module_rows),
            "message": EMPTY_STATE_MESSAGE if not module_rows else "",
        },
    }
