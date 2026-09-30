from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


BOUNDARY_NOTICE = (
    "Documentation-only plant evidence/package flow readback for manual review. It preserves "
    "slot, evidence, gap, package, and handoff context without resolving gaps, choosing "
    "components, generating sequences, changing package export data, or judging downstream use."
)
EMPTY_STATE_MESSAGE = (
    "No evidence/package flow input is available. Provide slot plan, gap queue, or package "
    "snapshot readback data to build documentation review records."
)

FLOW_KEYS: tuple[str, ...] = (
    "flow_status",
    "route_summary",
    "evidence_records",
    "gap_review_items",
    "package_sections",
    "handoff_summary",
    "boundary_notice",
    "empty_state",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _route_summary(
    slot_plan_readback: Mapping[str, Any],
    gap_queue_payload: Mapping[str, Any],
    package_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    gap_route = _mapping(gap_queue_payload.get("route_summary"))
    package_route = _mapping(package_snapshot.get("route_summary"))
    return {
        "route_template_id": _text(slot_plan_readback.get("route_template_id")),
        "canonical_route_template_id": _text(slot_plan_readback.get("canonical_route_template_id")),
        "route_id": _text(package_route.get("route_id") or gap_route.get("route_id")),
        "route_name": _text(package_route.get("route_name") or gap_route.get("route_name")),
        "draft_status": _text(package_route.get("draft_status") or gap_route.get("draft_status")),
        "package_status": _text(package_snapshot.get("package_status")),
    }


def _evidence_records(slot_plan_readback: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, row in enumerate(_mapping_list(slot_plan_readback.get("slot_rows")), start=1):
        slot_id = _text(row.get("slot_id")) or f"slot-{index:02d}"
        records.append(
            {
                "evidence_id": f"plant-evidence-{index:03d}-{slot_id}",
                "linked_slot_id": slot_id,
                "linked_module_id": _text(row.get("module_id")),
                "source_label": _text(row.get("module_label")) or "Missing module card",
                "source_type": "slot_plan_readback",
                "source_reference": _text(row.get("expected_evidence_type")),
                "source_excerpt_or_note": _text(row.get("gap_reason")),
                "evidence_status": _text(row.get("current_evidence_status")) or "manual_review_required",
                "manual_review_status": _text(row.get("manual_review_state")) or "manual_review_required",
                "package_section": "expression cassette slot plan",
                "boundary_notes": [BOUNDARY_NOTICE],
            }
        )
    return records


def _gap_review_items(gap_queue_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, row in enumerate(_mapping_list(gap_queue_payload.get("queue_items")), start=1):
        linked_slot_id = _text(row.get("slot_type") or row.get("field_name"))
        items.append(
            {
                "item_id": _text(row.get("gap_id")) or f"plant-gap-{index:03d}",
                "linked_slot_id": linked_slot_id,
                "linked_module_id": "",
                "gap_type": _text(row.get("gap_type")) or "manual_review",
                "missing_field": _text(row.get("field_name")),
                "review_question": _text(row.get("message")) or "Manual documentation review needed.",
                "severity": _text(row.get("severity")) or "review",
                "manual_review_status": _text(row.get("status")) or "manual_review_required",
                "resolution_note": "",
                "package_section": _text(row.get("source_section")) or "gap/manual review queue",
                "handoff_section": "manual review follow-up",
                "boundary_notes": [BOUNDARY_NOTICE],
            }
        )
    return items


def _package_sections(package_snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _mapping_list(package_snapshot.get("package_sections")):
        rows.append(
            {
                "section_id": _text(row.get("section_id")),
                "section_label": _text(row.get("section_label")),
                "display_order": int(row.get("display_order") or len(rows) + 1),
                "status": _text(row.get("status")) or "included",
            }
        )
    return rows


def _handoff_summary(
    package_snapshot: Mapping[str, Any],
    evidence_records: Sequence[Mapping[str, Any]],
    gap_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "package_id": _text(package_snapshot.get("package_id")),
        "package_scope": _text(package_snapshot.get("package_scope")),
        "identity_md5": _text(package_snapshot.get("identity_md5")),
        "evidence_record_count": len(evidence_records),
        "gap_review_item_count": len(gap_items),
        "manual_review_required": bool(gap_items) or bool(evidence_records),
        "handoff_status": "manual_review_required",
        "boundary_note": BOUNDARY_NOTICE,
    }


def _empty_flow() -> dict[str, Any]:
    return {
        "flow_status": "empty_manual_review_required",
        "route_summary": {},
        "evidence_records": [],
        "gap_review_items": [],
        "package_sections": [],
        "handoff_summary": {},
        "boundary_notice": BOUNDARY_NOTICE,
        "empty_state": {"is_empty": True, "message": EMPTY_STATE_MESSAGE},
    }


def build_plant_evidence_package_flow_readback(
    slot_plan_readback: Mapping[str, Any] | None = None,
    gap_queue_payload: Mapping[str, Any] | None = None,
    package_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a plain dict/list R406-style evidence/gap/package flow readback."""
    slot_plan = _mapping(slot_plan_readback)
    gap_queue = _mapping(gap_queue_payload)
    package = _mapping(package_snapshot)
    if not slot_plan and not gap_queue and not package:
        return _empty_flow()

    evidence_records = _evidence_records(slot_plan)
    gap_items = _gap_review_items(gap_queue)
    sections = _package_sections(package)
    result = {
        "flow_status": "manual_review_required",
        "route_summary": _route_summary(slot_plan, gap_queue, package),
        "evidence_records": evidence_records,
        "gap_review_items": gap_items,
        "package_sections": sections,
        "handoff_summary": _handoff_summary(package, evidence_records, gap_items),
        "boundary_notice": BOUNDARY_NOTICE,
        "empty_state": {"is_empty": False, "message": ""},
    }
    return {key: _plain_value(result[key]) for key in FLOW_KEYS}
