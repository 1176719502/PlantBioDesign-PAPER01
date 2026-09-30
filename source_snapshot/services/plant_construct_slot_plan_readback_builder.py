from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_expression_route_template_registry import (
    CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
    get_plant_expression_route_template_by_id,
)
from services.plant_review_module_card_registry import get_plant_review_module_card_by_id
from services.plant_review_module_card_schema import COMMON_BLOCKED_OUTPUTS
from services.plant_route_template_compatibility_readback import (
    build_plant_route_template_compatibility_readback,
)


SLOT_PLAN_STATUS_READY_FOR_MANUAL_REVIEW = "readback_ready_for_manual_review"
SLOT_PLAN_STATUS_BLOCKED_MANUAL_REVIEW = "blocked_manual_review_required"
SLOT_PLAN_STATUS_EMPTY_READBACK = "empty_readback_manual_review_required"
SLOT_EVIDENCE_STATUS_MISSING = "missing_manual_review_required"
SLOT_EVIDENCE_STATUS_PRESENT = "source_context_present_manual_review_required"

_BOUNDARY_NOTES: tuple[str, ...] = (
    "Documentation-only construct slot plan readback for manual review.",
    "Slot rows are documentation placeholders, not completed construct records or build-use instructions.",
    "Compatibility aliases are metadata only and must not be treated as biological recommendations.",
    "This builder does not generate constructs, sequences, routes, components, promoters, vectors, or wet-lab protocols.",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return list(value)
    return [value]


def _string_list(value: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in _as_list(value):
        text = _text(item)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _first_present(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _route_id_from_input(route_template_summary: Mapping[str, Any]) -> str:
    return _text(
        _first_present(
            route_template_summary,
            (
                "route_template_id",
                "route_id",
                "requested_route_id",
                "canonical_route_template_id",
            ),
        )
    )


def _template_from_input(
    route_template_summary: Mapping[str, Any],
    compatibility_readback: Mapping[str, Any],
) -> dict[str, Any] | None:
    route_id = _route_id_from_input(route_template_summary)
    if not route_id:
        return None
    lookup_route_id = _text(compatibility_readback.get("resolved_legacy_route_id")) or route_id
    if "required_slots" in route_template_summary or "optional_slots" in route_template_summary:
        registry_template = get_plant_expression_route_template_by_id(lookup_route_id) or {}
        return {
            "route_id": _text(registry_template.get("route_id")) or route_id,
            "required_module_ids": _string_list(
                route_template_summary.get(
                    "required_module_ids",
                    registry_template.get("required_module_ids"),
                )
            ),
            "optional_module_ids": _string_list(
                route_template_summary.get(
                    "optional_module_ids",
                    registry_template.get("optional_module_ids"),
                )
            ),
            "required_slots": _string_list(route_template_summary.get("required_slots")),
            "optional_slots": _string_list(route_template_summary.get("optional_slots")),
            "evidence_requirements": _string_list(
                route_template_summary.get(
                    "evidence_requirements",
                    registry_template.get("evidence_requirements"),
                )
            ),
            "gap_rules": _string_list(
                route_template_summary.get("gap_rules", registry_template.get("gap_rules"))
            ),
            "manual_review_rules": _string_list(
                route_template_summary.get(
                    "manual_review_rules",
                    registry_template.get("manual_review_rules"),
                )
            ),
            "boundary_note": _text(
                route_template_summary.get("boundary_note", registry_template.get("boundary_note"))
            ),
            "blocked_outputs": _string_list(
                route_template_summary.get("blocked_outputs", registry_template.get("blocked_outputs"))
            )
            or list(COMMON_BLOCKED_OUTPUTS),
        }
    template = get_plant_expression_route_template_by_id(lookup_route_id)
    if template:
        return template
    return None


def _module_card_id(module_card_summary: Mapping[str, Any]) -> str:
    return _text(_first_present(module_card_summary, ("module_id", "requested_module_id", "card_id")))


def _module_card_lookup(module_card_summary: Mapping[str, Any]) -> dict[str, Any] | None:
    module_id = _module_card_id(module_card_summary)
    if not module_id:
        return None
    registry_card = get_plant_review_module_card_by_id(module_id)
    if registry_card is not None:
        return registry_card
    if module_card_summary:
        return {
            "module_id": module_id,
            "display_name": _text(
                _first_present(module_card_summary, ("module_label", "display_name", "module_name"))
            )
            or module_id.replace("_", " ").title(),
            "required_slots": _string_list(module_card_summary.get("required_slots")),
            "evidence_fields": _string_list(module_card_summary.get("evidence_fields")),
            "gap_rules": _string_list(module_card_summary.get("gap_rules")),
            "manual_review_rules": _string_list(module_card_summary.get("manual_review_rules")),
            "boundary_notes": _string_list(module_card_summary.get("boundary_notes")),
            "blocked_outputs": _string_list(module_card_summary.get("blocked_outputs")) or list(COMMON_BLOCKED_OUTPUTS),
        }
    return None


def _module_card_index(
    module_card_summaries: Sequence[Mapping[str, Any]],
    template: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for summary in module_card_summaries:
        requested_module_id = _module_card_id(summary)
        card = _module_card_lookup(summary)
        if card is not None:
            cards[_text(card.get("module_id"))] = card
            if requested_module_id:
                cards[requested_module_id] = card
    for module_id in [
        *_string_list(template.get("required_module_ids")),
        *_string_list(template.get("optional_module_ids")),
    ]:
        card = get_plant_review_module_card_by_id(module_id)
        if card is not None:
            cards.setdefault(_text(card.get("module_id")), card)
            cards.setdefault(module_id, card)
    return cards


def _required_or_optional(slot_id: str, template: Mapping[str, Any]) -> str:
    required_slots = set(_string_list(template.get("required_slots")))
    optional_slots = set(_string_list(template.get("optional_slots")))
    if slot_id in required_slots:
        return "required"
    if slot_id in optional_slots:
        return "optional"
    return "unspecified_manual_review"


def _expected_evidence_type(slot_id: str, card: Mapping[str, Any] | None, template: Mapping[str, Any]) -> str:
    evidence_fields = _string_list(card.get("evidence_fields") if card else None)
    if evidence_fields:
        return evidence_fields[0]
    template_evidence = _string_list(template.get("evidence_requirements"))
    if template_evidence:
        return template_evidence[0]
    if "source" in slot_id or "reference" in slot_id:
        return "source_reference"
    return "source_or_traceability_note"


def _gap_reason(slot_id: str, card: Mapping[str, Any] | None, template: Mapping[str, Any]) -> str:
    gap_rules = _string_list(card.get("gap_rules") if card else None) or _string_list(template.get("gap_rules"))
    if gap_rules:
        return gap_rules[0]
    return f"{slot_id} requires source context or manual review note"


def _manual_review_state(card: Mapping[str, Any] | None) -> str:
    if card is None:
        return "module_missing_manual_review_required"
    return "manual_review_required"


def _slot_type(slot_id: str) -> str:
    if "source" in slot_id or "reference" in slot_id:
        return "evidence_reference_slot"
    if "note" in slot_id or "context" in slot_id:
        return "documentation_context_slot"
    if "promoter" in slot_id or "terminator" in slot_id or "marker" in slot_id:
        return "component_context_slot"
    if "sequence" in slot_id or slot_id.startswith("cds"):
        return "sequence_source_review_slot"
    return "documentation_slot"


def _card_for_slot(
    slot_id: str,
    required_or_optional: str,
    cards: Mapping[str, Mapping[str, Any]],
    template: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    template_module_ids = (
        _string_list(template.get("required_module_ids"))
        if required_or_optional == "required"
        else _string_list(template.get("optional_module_ids"))
    )
    for module_id in template_module_ids:
        card = cards.get(module_id)
        if card and slot_id in _string_list(card.get("required_slots")):
            return card
    for card in cards.values():
        if slot_id in _string_list(card.get("required_slots")):
            return card
    for module_id in template_module_ids:
        card = cards.get(module_id)
        if card is not None:
            return card
    return None


def _boundary_notes_for_slot(card: Mapping[str, Any] | None, template: Mapping[str, Any]) -> list[str]:
    notes = list(_BOUNDARY_NOTES)
    notes.extend(_string_list(card.get("boundary_notes") if card else None))
    template_note = _text(template.get("boundary_note"))
    if template_note:
        notes.append(template_note)
    return _string_list(notes)


def _blocked_outputs_for_slot(card: Mapping[str, Any] | None, template: Mapping[str, Any]) -> list[str]:
    return _string_list(
        [
            *list(COMMON_BLOCKED_OUTPUTS),
            *_string_list(template.get("blocked_outputs")),
            *_string_list(card.get("blocked_outputs") if card else None),
        ]
    )


def _slot_row(
    *,
    route_template_id: str,
    canonical_route_template_id: str,
    compatibility: Mapping[str, Any],
    slot_id: str,
    required_or_optional: str,
    card: Mapping[str, Any] | None,
    template: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "route_template_id": route_template_id,
        "canonical_route_template_id": canonical_route_template_id,
        "compatibility": dict(compatibility),
        "module_id": _text(card.get("module_id") if card else ""),
        "module_label": _text(card.get("display_name") if card else "") or "Missing module card",
        "slot_id": slot_id,
        "slot_type": _slot_type(slot_id),
        "required_or_optional": required_or_optional,
        "expected_evidence_type": _expected_evidence_type(slot_id, card, template),
        "current_evidence_status": SLOT_EVIDENCE_STATUS_MISSING,
        "gap_reason": _gap_reason(slot_id, card, template),
        "manual_review_state": _manual_review_state(card),
        "boundary_notes": _boundary_notes_for_slot(card, template),
        "blocked_output_categories": _blocked_outputs_for_slot(card, template),
    }


def _empty_plan(
    route_id: str,
    compatibility_readback: Mapping[str, Any],
    status: str,
    reason: str,
) -> dict[str, Any]:
    canonical_route_id = _text(compatibility_readback.get("resolved_canonical_route_id"))
    return {
        "slot_plan_status": status,
        "route_template_id": route_id,
        "canonical_route_template_id": canonical_route_id,
        "compatibility": {
            "requested_route_id": _text(compatibility_readback.get("requested_route_id")) or route_id,
            "resolved_canonical_route_id": canonical_route_id,
            "resolved_legacy_route_id": _text(compatibility_readback.get("resolved_legacy_route_id")),
            "alias_status": _text(compatibility_readback.get("alias_status")),
            "is_alias": bool(compatibility_readback.get("is_alias")),
            "route_template_found": bool(compatibility_readback.get("route_template_found")),
        },
        "module_id": "",
        "module_label": "",
        "slot_id": "",
        "slot_type": "",
        "required_or_optional": "",
        "expected_evidence_type": "",
        "current_evidence_status": "blocked_no_slot_rows",
        "gap_reason": reason,
        "manual_review_state": "manual_review_required",
        "boundary_notes": list(_BOUNDARY_NOTES),
        "blocked_output_categories": list(COMMON_BLOCKED_OUTPUTS),
        "slot_rows": [],
    }


def build_plant_construct_slot_plan_readback(
    route_template_summary: Mapping[str, Any] | None = None,
    module_card_summaries: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a plain dict/list construct slot plan readback from route and module summaries."""
    route_summary = route_template_summary if isinstance(route_template_summary, Mapping) else {}
    route_id = _route_id_from_input(route_summary)
    compatibility_readback = build_plant_route_template_compatibility_readback(route_id)

    if not route_summary and not route_id:
        return _empty_plan(
            "",
            compatibility_readback,
            SLOT_PLAN_STATUS_EMPTY_READBACK,
            "empty route template input",
        )

    template = _template_from_input(route_summary, compatibility_readback)
    if template is None or not compatibility_readback.get("route_template_found"):
        return _empty_plan(
            route_id,
            compatibility_readback,
            SLOT_PLAN_STATUS_BLOCKED_MANUAL_REVIEW,
            "unknown route template requires manual review",
        )

    module_summaries = [
        summary
        for summary in _as_list(module_card_summaries)
        if isinstance(summary, Mapping)
    ]
    cards = _module_card_index(module_summaries, template)
    compatibility = {
        "requested_route_id": _text(compatibility_readback.get("requested_route_id")),
        "resolved_canonical_route_id": _text(compatibility_readback.get("resolved_canonical_route_id")),
        "resolved_legacy_route_id": _text(compatibility_readback.get("resolved_legacy_route_id")),
        "alias_status": _text(compatibility_readback.get("alias_status")),
        "is_alias": bool(compatibility_readback.get("is_alias")),
        "route_template_found": bool(compatibility_readback.get("route_template_found")),
    }
    route_template_id = _text(template.get("route_id")) or route_id
    canonical_route_template_id = (
        _text(compatibility_readback.get("resolved_canonical_route_id"))
        or CANONICAL_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID
    )

    slot_rows: list[dict[str, Any]] = []
    for slot_id in _string_list(template.get("required_slots")):
        card = _card_for_slot(slot_id, "required", cards, template)
        slot_rows.append(
            _slot_row(
                route_template_id=route_template_id,
                canonical_route_template_id=canonical_route_template_id,
                compatibility=compatibility,
                slot_id=slot_id,
                required_or_optional="required",
                card=card,
                template=template,
            )
        )
    for slot_id in _string_list(template.get("optional_slots")):
        card = _card_for_slot(slot_id, "optional", cards, template)
        slot_rows.append(
            _slot_row(
                route_template_id=route_template_id,
                canonical_route_template_id=canonical_route_template_id,
                compatibility=compatibility,
                slot_id=slot_id,
                required_or_optional="optional",
                card=card,
                template=template,
            )
        )

    if not slot_rows:
        return _empty_plan(
            route_template_id,
            compatibility_readback,
            SLOT_PLAN_STATUS_EMPTY_READBACK,
            "route template has no construct slot rows",
        )

    missing_module_rows = [
        row for row in slot_rows if row["manual_review_state"] == "module_missing_manual_review_required"
    ]
    return {
        "slot_plan_status": (
            SLOT_PLAN_STATUS_BLOCKED_MANUAL_REVIEW
            if missing_module_rows
            else SLOT_PLAN_STATUS_READY_FOR_MANUAL_REVIEW
        ),
        "route_template_id": route_template_id,
        "canonical_route_template_id": canonical_route_template_id,
        "compatibility": compatibility,
        "module_id": "",
        "module_label": "",
        "slot_id": "",
        "slot_type": "construct_slot_plan_readback",
        "required_or_optional": "",
        "expected_evidence_type": "source_or_traceability_note",
        "current_evidence_status": (
            "blocked_missing_module_card" if missing_module_rows else SLOT_EVIDENCE_STATUS_PRESENT
        ),
        "gap_reason": (
            "one or more module cards could not be resolved"
            if missing_module_rows
            else "slot plan requires manual evidence review"
        ),
        "manual_review_state": "manual_review_required",
        "boundary_notes": list(_BOUNDARY_NOTES),
        "blocked_output_categories": list(COMMON_BLOCKED_OUTPUTS),
        "slot_rows": slot_rows,
    }
