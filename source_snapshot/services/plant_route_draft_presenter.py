from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


PAGE_TITLE = "Plant Route Draft Readback"
SUBTITLE = "Documentation-only construct slot plan for manual review."
BOUNDARY_NOTICE = (
    "Documentation-only plant route draft presenter for manual review readback. It formats "
    "existing route draft data into plain sections without choosing components, generating "
    "sequences, producing final constructs, scoring outcomes, or judging lab-use status."
)
BLOCKED_OUTPUTS_NOTICE = (
    "Blocked output families remain blocked in this readback layer and are shown only as "
    "documentation boundary reminders."
)

PRESENTER_SECTION_KEYS: tuple[str, ...] = (
    "page_title",
    "subtitle",
    "route_summary_card",
    "target_summary_card",
    "plant_context_card",
    "route_template_card",
    "required_module_rows",
    "construct_slot_plan_rows",
    "provided_field_rows",
    "missing_field_rows",
    "evidence_summary_rows",
    "manual_review_checklist_rows",
    "package_preview_sections",
    "boundary_notice",
    "blocked_outputs_notice",
    "empty_state",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _title(value: Any) -> str:
    return _text(value).replace("_", " ").title()


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _as_plain_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [_plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return [_plain_value(value)]


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray, str)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _empty_presenter() -> dict[str, Any]:
    return {
        "page_title": PAGE_TITLE,
        "subtitle": SUBTITLE,
        "route_summary_card": {},
        "target_summary_card": {},
        "plant_context_card": {},
        "route_template_card": {},
        "required_module_rows": [],
        "construct_slot_plan_rows": [],
        "provided_field_rows": [],
        "missing_field_rows": [],
        "evidence_summary_rows": [],
        "manual_review_checklist_rows": [],
        "package_preview_sections": [],
        "boundary_notice": {
            "title": "Documentation-only boundary",
            "notice": BOUNDARY_NOTICE,
        },
        "blocked_outputs_notice": {
            "title": "Blocked output families",
            "notice": BLOCKED_OUTPUTS_NOTICE,
            "blocked_output_families": [],
        },
        "empty_state": {
            "is_empty": True,
            "title": "No route draft available",
            "message": (
                "Provide a plant route draft from the route draft builder to display a "
                "documentation-only readback."
            ),
        },
    }


def _route_summary(route_draft: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "draft_id": _text(route_draft.get("draft_id")),
        "draft_status": _text(route_draft.get("draft_status")),
        "route_id": _text(route_draft.get("route_id")),
        "route_name": _text(route_draft.get("route_name")),
        "route_type": _text(route_draft.get("route_type")),
        "boundary_note": _text(route_draft.get("boundary_note")),
    }


def _route_template_card(route_draft: Mapping[str, Any]) -> dict[str, Any]:
    template = route_draft.get("selected_template")
    if not isinstance(template, Mapping):
        return {}
    return {
        "route_id": _text(template.get("route_id")),
        "route_name": _text(template.get("route_name")),
        "route_type": _text(template.get("route_type")),
        "route_priority": _plain_value(template.get("route_priority")),
        "plant_context": _text(template.get("plant_context")),
        "route_description": _text(template.get("route_description")),
        "evidence_requirements": _as_plain_list(template.get("evidence_requirements")),
        "gap_rules": _as_plain_list(template.get("gap_rules")),
        "manual_review_rules": _as_plain_list(template.get("manual_review_rules")),
        "boundary_note": _text(template.get("boundary_note")),
    }


def _required_module_rows(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, module in enumerate(_mapping_list(route_draft.get("required_modules")), start=1):
        rows.append(
            {
                "row_id": f"module-{index:02d}",
                "module_id": _text(module.get("module_id")),
                "module_name": _text(module.get("module_name")),
                "route_type": _text(module.get("route_type")),
                "route_priority": _plain_value(module.get("route_priority")),
                "package_section": _text(module.get("package_section")),
                "required_slots": _as_plain_list(module.get("required_slots")),
                "evidence_fields": _as_plain_list(module.get("evidence_fields")),
                "manual_review_rules": _as_plain_list(module.get("manual_review_rules")),
                "boundary_note": _text(module.get("boundary_note")),
            }
        )
    return rows


def _construct_slot_plan_rows(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, slot in enumerate(_mapping_list(route_draft.get("required_slots")), start=1):
        slot_name = _text(slot.get("slot_name"))
        rows.append(
            {
                "row_id": f"slot-{index:02d}",
                "slot_name": slot_name,
                "slot_label": _title(slot_name),
                "status": _text(slot.get("status")) or "missing",
                "value": _plain_value(slot.get("value")),
                "manual_review_required": bool(slot.get("manual_review_required", True)),
            }
        )
    return rows


def _provided_field_rows(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, field in enumerate(_mapping_list(route_draft.get("provided_fields")), start=1):
        rows.append(
            {
                "row_id": f"provided-{index:02d}",
                "field": _text(field.get("field")),
                "field_label": _title(field.get("field")),
                "value": _plain_value(field.get("value")),
            }
        )
    return rows


def _missing_field_rows(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, field in enumerate(_as_plain_list(route_draft.get("missing_fields")), start=1):
        field_name = _text(field)
        rows.append(
            {
                "row_id": f"missing-{index:02d}",
                "field": field_name,
                "field_label": _title(field_name),
                "status": "missing",
                "manual_review_required": True,
            }
        )
    return rows


def _evidence_summary_rows(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, evidence in enumerate(_mapping_list(route_draft.get("evidence_summary")), start=1):
        rows.append(
            {
                "row_id": f"evidence-{index:02d}",
                "source_id": _text(evidence.get("source_id")),
                "value": _plain_value(evidence.get("value")),
            }
        )
    return rows


def _manual_review_checklist_rows(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(_mapping_list(route_draft.get("manual_review_items")), start=1):
        rows.append(
            {
                "row_id": f"review-{index:02d}",
                "review_type": _text(item.get("review_type")),
                "field": _text(item.get("field")),
                "note": _text(item.get("note")),
                "status": "manual_review",
            }
        )
    return rows


def _package_preview_sections(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, section in enumerate(_as_plain_list(route_draft.get("package_preview_sections")), start=1):
        section_id = _text(section)
        rows.append(
            {
                "row_id": f"package-section-{index:02d}",
                "section_id": section_id,
                "section_label": _title(section_id),
                "status": "preview_only",
            }
        )
    return rows


def present_plant_route_draft(route_draft: dict[str, Any] | None) -> dict[str, Any]:
    """Return deterministic plain readback sections for an existing plant route draft."""
    if not isinstance(route_draft, Mapping) or not route_draft:
        return _empty_presenter()

    presented = _empty_presenter()
    presented.update(
        {
            "route_summary_card": _route_summary(route_draft),
            "target_summary_card": _plain_value(route_draft.get("target_summary") or {}),
            "plant_context_card": _plain_value(route_draft.get("plant_context") or {}),
            "route_template_card": _route_template_card(route_draft),
            "required_module_rows": _required_module_rows(route_draft),
            "construct_slot_plan_rows": _construct_slot_plan_rows(route_draft),
            "provided_field_rows": _provided_field_rows(route_draft),
            "missing_field_rows": _missing_field_rows(route_draft),
            "evidence_summary_rows": _evidence_summary_rows(route_draft),
            "manual_review_checklist_rows": _manual_review_checklist_rows(route_draft),
            "package_preview_sections": _package_preview_sections(route_draft),
            "boundary_notice": {
                "title": "Documentation-only boundary",
                "notice": _text(route_draft.get("boundary_note")) or BOUNDARY_NOTICE,
            },
            "blocked_outputs_notice": {
                "title": "Blocked output families",
                "notice": BLOCKED_OUTPUTS_NOTICE,
                "blocked_output_families": _as_plain_list(route_draft.get("blocked_outputs")),
            },
            "empty_state": {
                "is_empty": False,
                "title": "",
                "message": "",
            },
        }
    )
    return {key: presented[key] for key in PRESENTER_SECTION_KEYS}
