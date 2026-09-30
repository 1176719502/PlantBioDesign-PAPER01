from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_evidence_review_worksheet_presenter import (
    build_plant_evidence_review_worksheet_payload,
    build_followup_queue_filter_view,
)
from services.plant_route_construct_traceability_readback import (
    build_plant_route_construct_traceability_readback,
)


HANDOFF_SCHEMA_VERSION = "plant_review_handoff_data_adapter.v2.7.r79"
HANDOFF_BATCH = "v2.7-r79"
WORKSHEET_HANDOFF_READBACK_BATCH = "v2.7-r125"
ROUTE_CONSTRUCT_TRACEABILITY_MOUNT_BATCH = "v2.7-r129"

MISSING_INFORMATION_CATEGORIES = {
    "component_gap",
    "evidence_gap",
    "required_slot_gap",
    "route_context_gap",
    "unsupported_scope",
}

BLOCKED_STATUSES = {"blocked", "blocked_unsupported"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _presenter_from_source(source: Mapping[str, Any]) -> dict[str, Any]:
    presenter = source.get("readback_presenter")
    if isinstance(presenter, Mapping):
        return dict(presenter)
    if "package_header" in source and "review_queue_section" in source:
        return dict(source)
    return {}


def _chain_from_source(source: Mapping[str, Any]) -> dict[str, Any]:
    return dict(source) if "chain_schema_version" in source else {}


def _normal_item(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    category = _text(item.get("category")) or "manual_review"
    item_id = _text(item.get("item_id")) or f"handoff-review-item-{index:03d}"
    return {
        "item_id": item_id,
        "category": category,
        "title": _text(item.get("title")) or category.replace("_", " ").title(),
        "severity": _text(item.get("severity")) or "review_required",
        "priority": int(item.get("priority") or 0),
        "route_id": _text(item.get("route_id")),
        "module_id": _text(item.get("module_id")),
        "slot_id": _text(item.get("slot_id")),
        "reason": _text(item.get("reason") or item.get("note")),
        "reviewer_action_hint": _text(item.get("reviewer_action_hint")),
        "evidence_ids": [_plain_value(value) for value in _list(item.get("evidence_ids"))],
        "component_ids": [_plain_value(value) for value in _list(item.get("component_ids"))],
        "source_references": [_plain_value(value) for value in _list(item.get("source_references"))],
        "provenance_references": [_plain_value(value) for value in _list(item.get("provenance_references"))],
    }


def _queue_items(chain: Mapping[str, Any], presenter: Mapping[str, Any]) -> list[dict[str, Any]]:
    queue_result = _mapping(chain.get("gap_manual_review_queue_result"))
    source_items = _list(queue_result.get("review_items") or queue_result.get("queue"))
    if not source_items:
        review_queue_section = _mapping(presenter.get("review_queue_section"))
        source_items = _list(review_queue_section.get("rows"))
    return [
        _normal_item(item, index)
        for index, item in enumerate(source_items, start=1)
        if isinstance(item, Mapping)
    ]


def _package_header(chain: Mapping[str, Any], presenter: Mapping[str, Any]) -> dict[str, Any]:
    header = _mapping(presenter.get("package_header"))
    package = _mapping(chain.get("plant_review_package"))
    if not header and package:
        route_summary = _mapping(package.get("route_summary"))
        header = {
            "package_id": _text(package.get("package_id")),
            "package_status": _text(package.get("package_status")),
            "package_schema_version": _text(package.get("package_schema_version")),
            "package_type": _text(package.get("package_type")),
            "route_id": _text(route_summary.get("route_id")),
            "route_label": _text(route_summary.get("route_label")),
            "manual_review_required": bool(package.get("manual_review_required")),
        }
    return header


def _reviewer_summary(chain: Mapping[str, Any], presenter: Mapping[str, Any], queue_items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_summary = _mapping(presenter.get("status_summary_card"))
    categories: dict[str, int] = {}
    for item in queue_items:
        category = _text(item.get("category")) or "manual_review"
        categories[category] = categories.get(category, 0) + 1
    return {
        "chain_status": _text(chain.get("chain_status")),
        "status_label": _text(status_summary.get("status_label")),
        "manual_review_required": bool(chain.get("manual_review_required")) or bool(status_summary),
        "blocked": bool(chain.get("blocked")) or _text(status_summary.get("status_label")) in BLOCKED_STATUSES,
        "review_item_count": len(queue_items),
        "review_item_categories": categories,
        "safe_boundary_note": _text(status_summary.get("safe_boundary_note")),
    }


def _traceability_section(chain: Mapping[str, Any], presenter: Mapping[str, Any]) -> dict[str, Any]:
    traceability = _mapping(chain.get("traceability"))
    presenter_traceability = _mapping(presenter.get("traceability_section"))
    if presenter_traceability:
        return presenter_traceability
    readback_traceability = _mapping(traceability.get("readback_traceability"))
    package_traceability = _mapping(traceability.get("package_traceability"))
    return readback_traceability or package_traceability


def _traceability_items(traceability: Mapping[str, Any], key: str, label: str) -> list[dict[str, Any]]:
    return [
        {f"{label}_id": _plain_value(value), "traceability_source": "readback_traceability"}
        for value in _list(traceability.get(key))
    ]


def _blocked_output_boundaries(chain: Mapping[str, Any], presenter: Mapping[str, Any]) -> list[str]:
    boundary_section = _mapping(presenter.get("blocked_output_boundary_section"))
    values = _list(boundary_section.get("blocked_output_categories"))
    if not values:
        package = _mapping(chain.get("plant_review_package"))
        values = _list(package.get("blocked_output_boundaries"))
    return [_text(value) for value in values if _text(value)]


def _manual_evidence_review_queue_readback(presenter: Mapping[str, Any]) -> dict[str, Any]:
    section = _mapping(presenter.get("manual_evidence_review_queue_section"))
    if section:
        return section
    return {}


def _design_slot_completion_readback(presenter: Mapping[str, Any]) -> dict[str, Any]:
    section = _mapping(presenter.get("design_slot_completion_section"))
    if not section:
        return {}
    summary = _mapping(section.get("summary"))
    return {
        "summary": {
            "completed_slots": [_plain_value(value) for value in _list(summary.get("completed_slots"))],
            "missing_slots": [_plain_value(value) for value in _list(summary.get("missing_slots"))],
            "completed_slot_count": int(summary.get("completed_slot_count") or 0),
            "missing_slot_count": int(summary.get("missing_slot_count") or 0),
            "completion_status": _text(summary.get("completion_status")) or "information_completion_needed",
            "manual_review_required": bool(summary.get("manual_review_required", True)),
        },
        "rows": [_plain_value(row) for row in _list(section.get("rows")) if isinstance(row, Mapping)],
        "boundary_note": _text(section.get("boundary_note"))
        or "Design slot completion is documentation-only manual review readback.",
    }


def _worksheet_handoff_readback(worksheet: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(worksheet.get("summary"))
    followup_section = _mapping(worksheet.get("followup_queue_section"))
    followup_view = build_followup_queue_filter_view(followup_section)
    boundary_section = _mapping(worksheet.get("boundary_section"))
    warnings = [_text(value) for value in _list(worksheet.get("warnings")) if _text(value)]
    return {
        "readback_batch": WORKSHEET_HANDOFF_READBACK_BATCH,
        "read_only": True,
        "reuse_source": "plant_evidence_review_worksheet_presenter",
        "worksheet_schema_version": _text(worksheet.get("worksheet_schema_version")),
        "worksheet_status": _text(worksheet.get("worksheet_status")) or "empty_manual_review_required",
        "summary": {
            "overall_review_state": _text(summary.get("overall_review_state")) or "evidence incomplete",
            "total_evidence_rows": int(summary.get("total_evidence_rows") or 0),
            "linked_component_slot_count": int(summary.get("linked_component_slot_count") or 0),
            "missing_source_or_provenance_count": int(summary.get("missing_source_or_provenance_count") or 0),
            "weak_or_unreviewed_evidence_count": int(summary.get("weak_or_unreviewed_evidence_count") or 0),
            "manual_review_required_count": int(summary.get("manual_review_required_count") or 0),
            "blocked_boundary_category_count": int(summary.get("blocked_boundary_category_count") or 0),
            "followup_queue_count": int(summary.get("followup_queue_count") or 0),
            "followup_queue_type_counts": _mapping(summary.get("followup_queue_type_counts")),
            "empty_input": bool(summary.get("empty_input")),
        },
        "followup_queue_status": {
            "filter_key": _text(followup_view.get("filter_key")),
            "selected_followup_type": _text(followup_view.get("selected_followup_type")),
            "followup_type_options": [_text(value) for value in _list(followup_view.get("followup_type_options"))],
            "total_count": int(followup_view.get("total_count") or 0),
            "filtered_count": int(followup_view.get("filtered_count") or 0),
            "group_by_type": bool(followup_view.get("group_by_type")),
            "group_counts": _mapping(followup_view.get("group_counts")),
            "empty_state": _text(followup_view.get("empty_state")),
            "boundary_note": _text(followup_view.get("boundary_note")),
        },
        "blocked_output_boundary_categories": sorted(
            [_text(value) for value in _list(boundary_section.get("blocked_output_categories")) if _text(value)],
            key=str.casefold,
        ),
        "warnings": warnings,
        "boundary_note": (
            "Evidence worksheet handoff readback is documentation-only review context. It shows gaps, "
            "manual-review needs, and boundary categories without selecting components, ordering components "
            "by importance, confirming experimental status, route improvement guidance, or downstream-use judgment."
        ),
    }


def _handoff_status(
    *,
    chain: Mapping[str, Any],
    header: Mapping[str, Any],
    reviewer_summary: Mapping[str, Any],
    malformed: bool,
) -> str:
    if malformed:
        return "manual_review_required"
    if bool(reviewer_summary.get("blocked")):
        return "blocked"
    package_status = _text(header.get("package_status"))
    chain_status = _text(chain.get("chain_status"))
    if package_status in BLOCKED_STATUSES or chain_status in BLOCKED_STATUSES:
        return "blocked"
    if bool(reviewer_summary.get("manual_review_required")):
        return "manual_review_required"
    return package_status or chain_status or "manual_review_required"


def build_plant_review_handoff_payload(
    source_payload: Mapping[str, Any] | None,
    handoff_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert a Plant review chain/readback payload into a read-only handoff payload."""
    context = _mapping(handoff_context)
    warnings: list[str] = []
    if not isinstance(source_payload, Mapping):
        source = {}
        warnings.append("handoff input warning: source payload is missing or malformed")
    else:
        source = dict(source_payload)

    chain = _chain_from_source(source)
    presenter = _presenter_from_source(source)
    if not chain and not presenter:
        warnings.append("handoff input warning: no chain result or readback presenter sections were found")

    review_items = _queue_items(chain, presenter)
    header = _package_header(chain, presenter)
    reviewer_summary = _reviewer_summary(chain, presenter, review_items)
    traceability = _traceability_section(chain, presenter)
    blocked_boundaries = _blocked_output_boundaries(chain, presenter)
    manual_evidence_readback = _manual_evidence_review_queue_readback(presenter)
    design_slot_completion_readback = _design_slot_completion_readback(presenter)
    missing_items = [
        dict(item)
        for item in review_items
        if _text(item.get("category")) in MISSING_INFORMATION_CATEGORIES
    ]
    evidence_items = _traceability_items(traceability, "evidence_ids", "evidence")
    component_items = _traceability_items(traceability, "component_ids", "component")
    route_items = _traceability_items(traceability, "route_ids", "route")
    worksheet_source = source if isinstance(source, Mapping) else {}
    evidence_review_worksheet = build_plant_evidence_review_worksheet_payload(
        worksheet_source,
        worksheet_context={
            "mount_batch": WORKSHEET_HANDOFF_READBACK_BATCH,
            "mount_surface": "plant_review_handoff_preview",
            "source_handoff_schema_version": HANDOFF_SCHEMA_VERSION,
        },
    )
    evidence_worksheet_handoff_readback = _worksheet_handoff_readback(evidence_review_worksheet)
    route_construct_traceability_readback = build_plant_route_construct_traceability_readback(
        worksheet_source,
        evidence_worksheet=evidence_review_worksheet,
        handoff_review_items=review_items,
        readback_context={
            "mount_batch": ROUTE_CONSTRUCT_TRACEABILITY_MOUNT_BATCH,
            "mount_surface": "plant_review_handoff_preview",
            "source_handoff_schema_version": HANDOFF_SCHEMA_VERSION,
        },
    )

    malformed = not bool(chain or presenter)
    status = _handoff_status(
        chain=chain,
        header=header,
        reviewer_summary=reviewer_summary,
        malformed=malformed,
    )
    manual_review_required = status in {"manual_review_required", "blocked"} or bool(
        reviewer_summary.get("manual_review_required")
    )

    return _plain_value(
        {
            "handoff_schema_version": HANDOFF_SCHEMA_VERSION,
            "handoff_batch": HANDOFF_BATCH,
            "handoff_status": status,
            "package_header": header,
            "reviewer_summary": reviewer_summary,
            "required_review_items": review_items,
            "missing_information_items": missing_items,
            "evidence_traceability_items": evidence_items,
            "component_traceability_items": component_items,
            "plant_evidence_review_worksheet": evidence_review_worksheet,
            "evidence_worksheet_handoff_readback": evidence_worksheet_handoff_readback,
            "route_construct_traceability_readback": route_construct_traceability_readback,
            "manual_evidence_review_queue_readback": manual_evidence_readback,
            "design_slot_completion_readback": design_slot_completion_readback,
            "blocked_output_boundaries": blocked_boundaries,
            "warnings": warnings,
            "source_traceability": {
                "source_kind": "chain_result" if chain else "readback_presenter" if presenter else "malformed",
                "source_schema_version": _text(chain.get("chain_schema_version") or presenter.get("presenter_schema_version")),
                "package_traceability": _mapping(_mapping(chain.get("traceability")).get("package_traceability")),
                "readback_traceability": traceability,
                "route_traceability_items": route_items,
                "manual_evidence_queue_row_count": _mapping(
                    manual_evidence_readback.get("summary")
                ).get("row_count", 0),
                "design_slot_missing_count": _mapping(
                    design_slot_completion_readback.get("summary")
                ).get("missing_slot_count", 0),
                "handoff_context": context,
            },
            "manual_review_required": manual_review_required,
        }
    )
