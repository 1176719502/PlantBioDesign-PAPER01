from __future__ import annotations

from typing import Any

from services.target_design_router import route_target_design


PREVIEW_TOP_LEVEL_KEYS = [
    "target_summary",
    "design_route_summary",
    "construct_template_summary",
    "gene_slots_table",
    "cassette_slots_table",
    "required_parts_table",
    "missing_fields_table",
    "source_requirements_table",
    "review_notes",
    "support_status",
    "boundary_note",
    "readiness_label",
]

SAFE_BOUNDARY_NOTE = (
    "Documentation-only route preview for manual design review; "
    "not experimental validation and not a downstream use judgment."
)

PATHWAY_BOUNDARY_NOTE = (
    "This is a documentation-only pathway construct draft, not production, "
    "yield, or experimental validation."
)

ROUTE_CLARIFICATION_OPTIONS = [
    "sweet protein expression",
    "rare sugar enzyme expression",
    "steviol glycoside pathway",
    "sugar metabolism modification",
]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value:
        return [value]
    return []


def _stable_join(values: list[str]) -> str:
    return " | ".join(value for value in values if value)


def _normalize_status(status: str) -> str:
    mapping = {
        "supported": "Ready for manual design review",
        "partially_supported": "Needs source review",
        "needs_review": "Needs source review",
        "unresolved": "Needs target clarification",
        "unsupported": "Draft only",
    }
    return mapping.get(status, "Draft only")


def _target_summary(route_result: dict[str, Any]) -> dict[str, Any]:
    target = route_result.get("normalized_target") or {}
    return {
        "target_label": _text(target.get("label")) or "Unresolved target",
        "aliases": [_text(alias) for alias in _as_list(target.get("aliases")) if _text(alias)],
        "target_class": _text(route_result.get("target_class")) or "unresolved_target",
        "notes": _text(target.get("notes")),
    }


def _design_route_summary(route_result: dict[str, Any]) -> dict[str, str]:
    return {
        "design_route": _text(route_result.get("design_route")) or "needs_target_clarification",
        "route_label": "route preview",
        "review_status": "needs review",
        "support_status": _text(route_result.get("support_status")) or "unresolved",
    }


def _construct_template_summary(route_result: dict[str, Any]) -> dict[str, Any]:
    template = route_result.get("construct_template") or {}
    return {
        "template_id": _text(template.get("template_id")) or "needs_target_clarification",
        "template_label": _text(template.get("template_label")) or "Target clarification draft",
        "description": _text(template.get("description")) or "No construct draft is created until review fields are clarified.",
        "structure": [_text(item) for item in _as_list(template.get("structure")) if _text(item)],
    }


def _gene_slots_table(route_result: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, slot in enumerate(_as_list(route_result.get("gene_slots")), start=1):
        if not isinstance(slot, dict):
            continue
        gene_label = _text(slot.get("gene_label")) or f"gene slot {index}"
        rows.append(
            {
                "slot": str(index),
                "gene_label": gene_label,
                "slot_role": _text(slot.get("slot_role")) or "CDS",
                "source_requirement": _text(slot.get("source_requirement")) or f"{gene_label} CDS source required",
                "review_status": "source required",
            }
        )
    return rows


def _cassette_slots_table(route_result: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for cassette_index, cassette in enumerate(_as_list(route_result.get("cassette_slots")), start=1):
        if not isinstance(cassette, dict):
            continue
        cassette_label = _text(cassette.get("cassette_label")) or f"cassette draft {cassette_index}"
        gene_label = _text(cassette.get("gene_label"))
        for part_index, part in enumerate(_as_list(cassette.get("parts")), start=1):
            if not isinstance(part, dict):
                continue
            rows.append(
                {
                    "cassette": cassette_label,
                    "cassette_slot": str(cassette_index),
                    "part_slot": str(part_index),
                    "slot_role": _text(part.get("part_role")) or "part",
                    "slot_label": _text(part.get("part_label")) or gene_label or "user-defined part",
                    "source_status": "source required",
                    "review_status": "manual confirmation required",
                }
            )
    return rows


def _required_parts_table(route_result: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "item": _text(item),
            "status": "needs review",
            "review_action": "manual confirmation required",
        }
        for item in _as_list(route_result.get("required_parts"))
        if _text(item)
    ]


def _missing_fields_table(route_result: dict[str, Any]) -> list[dict[str, str]]:
    fields = [_text(item) for item in _as_list(route_result.get("missing_fields")) if _text(item)]
    return [
        {
            "field": field,
            "status": "missing field",
            "review_action": "manual confirmation required",
        }
        for field in fields
    ]


def _source_requirements_table(route_result: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "source_requirement": _text(item),
            "status": "source required",
            "review_action": "manual confirmation required",
        }
        for item in _as_list(route_result.get("source_requirements"))
        if _text(item)
    ]


def _review_notes(route_result: dict[str, Any]) -> list[str]:
    notes = []
    for note in _as_list(route_result.get("review_notes")):
        clean_note = _text(note)
        if not clean_note:
            continue
        if clean_note.startswith("No ") and clean_note.endswith("success claim is made."):
            notes.append("No downstream performance or use claim is made.")
        else:
            notes.append(clean_note)
    if route_result.get("design_route") == "needs_target_clarification":
        existing = "\n".join(notes).casefold()
        notes.extend(option for option in ROUTE_CLARIFICATION_OPTIONS if option not in existing)
    notes.append("Preview is documentation-only and needs review before any future documentation record is prepared.")
    return notes


def _boundary_note(route_result: dict[str, Any]) -> str:
    if route_result.get("target_class") == "multi_gene_pathway":
        return PATHWAY_BOUNDARY_NOTE
    return _text(route_result.get("boundary_note")) or SAFE_BOUNDARY_NOTE


def build_target_design_preview(route_result: dict[str, Any] | None = None, **target_inputs: Any) -> dict[str, Any]:
    """Build a deterministic UI-ready preview model from a target route draft."""
    if route_result is None:
        route_result = route_target_design(**target_inputs)
    if not isinstance(route_result, dict):
        raise TypeError("route_result must be a dictionary or target inputs must be provided")

    support_status = _text(route_result.get("support_status")) or "unresolved"
    preview = {
        "target_summary": _target_summary(route_result),
        "design_route_summary": _design_route_summary(route_result),
        "construct_template_summary": _construct_template_summary(route_result),
        "gene_slots_table": _gene_slots_table(route_result),
        "cassette_slots_table": _cassette_slots_table(route_result),
        "required_parts_table": _required_parts_table(route_result),
        "missing_fields_table": _missing_fields_table(route_result),
        "source_requirements_table": _source_requirements_table(route_result),
        "review_notes": _review_notes(route_result),
        "support_status": support_status,
        "boundary_note": _boundary_note(route_result),
        "readiness_label": _normalize_status(support_status),
    }
    return {key: preview[key] for key in PREVIEW_TOP_LEVEL_KEYS}


def preview_text(preview: dict[str, Any]) -> str:
    """Return deterministic flattened preview text for copy-safety tests."""
    if isinstance(preview, dict):
        return "\n".join(preview_text(preview[key]) for key in sorted(preview))
    if isinstance(preview, list):
        return "\n".join(preview_text(item) for item in preview)
    return _text(preview)
