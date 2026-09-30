from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


BOUNDARY_NOTICE = (
    "Documentation-only plant route gap queue for manual review. It aggregates existing route "
    "draft, presenter, and candidate-match readback gaps without resolving them, choosing "
    "components, generating sequences, producing experiment procedures, scoring outcomes, or "
    "judging downstream use."
)
BLOCKED_OUTPUTS_NOTICE = (
    "Blocked output families remain outside this queue layer: automatic gap resolution, final "
    "component selection, biological part advice, sequence generation, outcome scoring, "
    "experiment procedure generation, and downstream-use judgments."
)

QUEUE_SECTION_KEYS: tuple[str, ...] = (
    "route_summary",
    "queue_summary",
    "queue_items",
    "queue_items_by_source",
    "queue_items_by_gap_type",
    "unresolved_items",
    "evidence_gap_items",
    "unmatched_slot_items",
    "manual_review_items",
    "boundary_notice",
    "blocked_outputs_notice",
    "empty_state",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_")


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray, str)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _as_plain_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [_plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return [_plain_value(value)]


def _route_summary(
    route_draft: Mapping[str, Any],
    route_presenter_payload: Mapping[str, Any],
    candidate_match_payload: Mapping[str, Any],
) -> dict[str, Any]:
    presenter_summary = _mapping_or_empty(route_presenter_payload.get("route_summary_card"))
    candidate_summary = _mapping_or_empty(candidate_match_payload.get("route_summary"))
    plant_context = (
        route_draft.get("plant_context")
        if "plant_context" in route_draft
        else route_presenter_payload.get("plant_context_card")
        if "plant_context_card" in route_presenter_payload
        else candidate_summary.get("plant_context")
    )
    return {
        "route_id": _text(route_draft.get("route_id") or presenter_summary.get("route_id") or candidate_summary.get("route_id")),
        "route_name": _text(
            route_draft.get("route_name") or presenter_summary.get("route_name") or candidate_summary.get("route_name")
        ),
        "route_type": _text(
            route_draft.get("route_type") or presenter_summary.get("route_type") or candidate_summary.get("route_type")
        ),
        "plant_context": _plain_value(plant_context),
        "draft_status": _text(
            route_draft.get("draft_status")
            or presenter_summary.get("draft_status")
            or candidate_summary.get("draft_status")
        ),
        "boundary_note": _text(
            route_draft.get("boundary_note")
            or presenter_summary.get("boundary_note")
            or candidate_summary.get("boundary_note")
        ),
    }


def _source_payload(row: Any) -> Any:
    return _plain_value(row)


def _base_item(
    *,
    gap_type: str,
    source_section: str,
    field_name: str = "",
    slot_type: str = "",
    severity: str = "review",
    status: str = "unresolved",
    message: str,
    evidence_status: str = "",
    component_id: str = "",
    component_name: str = "",
    source_payload: Any = None,
    boundary_note: str = "",
) -> dict[str, Any]:
    return {
        "gap_id": "",
        "gap_type": gap_type,
        "source_section": source_section,
        "slot_type": slot_type,
        "field_name": field_name,
        "severity": severity,
        "status": status,
        "message": message,
        "evidence_status": evidence_status,
        "component_id": component_id,
        "component_name": component_name,
        "manual_review_required": True,
        "source_payload": _source_payload(source_payload),
        "boundary_note": boundary_note,
    }


def _route_draft_missing_items(route_draft: Mapping[str, Any], boundary_note: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for field in _as_plain_list(route_draft.get("missing_fields")):
        field_name = _text(field)
        if not field_name:
            continue
        items.append(
            _base_item(
                gap_type="missing_field",
                source_section="route_draft",
                field_name=field_name,
                slot_type=field_name,
                severity="missing",
                message=f"Route draft field {field_name} is missing and needs manual documentation review.",
                source_payload={"field": field_name},
                boundary_note=boundary_note,
            )
        )
    return items


def _presenter_missing_items(route_presenter_payload: Mapping[str, Any], boundary_note: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in _mapping_list(route_presenter_payload.get("missing_field_rows")):
        field_name = _text(row.get("field") or row.get("field_name") or row.get("slot_name"))
        if not field_name:
            continue
        items.append(
            _base_item(
                gap_type="missing_field",
                source_section="route_presenter.missing_field_rows",
                field_name=field_name,
                slot_type=field_name,
                severity="missing",
                status=_text(row.get("status")) or "unresolved",
                message=f"Presenter row reports missing field {field_name} for manual documentation review.",
                source_payload=row,
                boundary_note=boundary_note,
            )
        )
    return items


def _candidate_unmatched_items(candidate_match_payload: Mapping[str, Any], boundary_note: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in _mapping_list(candidate_match_payload.get("unmatched_slot_rows")):
        slot_type = _text(row.get("slot_type") or row.get("field") or row.get("slot_name"))
        if not slot_type:
            continue
        items.append(
            _base_item(
                gap_type="unmatched_slot",
                source_section="candidate_match.unmatched_slot_rows",
                field_name=slot_type,
                slot_type=slot_type,
                severity="blocked",
                status=_text(row.get("candidate_status")) or "unresolved",
                message=_text(row.get("note")) or f"Construct slot {slot_type} has no candidate row in readback.",
                source_payload=row,
                boundary_note=boundary_note,
            )
        )
    return items


def _candidate_evidence_items(candidate_match_payload: Mapping[str, Any], boundary_note: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in _mapping_list(candidate_match_payload.get("evidence_coverage_rows")):
        evidence_status = _text(row.get("evidence_context_status") or row.get("evidence_status"))
        if evidence_status and evidence_status != "candidate_evidence_context_not_recorded":
            continue
        slot_type = _text(row.get("slot_type"))
        component_id = _text(row.get("component_id"))
        component_name = _text(row.get("component_name"))
        label = component_id or component_name or slot_type or "candidate row"
        items.append(
            _base_item(
                gap_type="evidence_gap",
                source_section="candidate_match.evidence_coverage_rows",
                field_name="evidence_context",
                slot_type=slot_type,
                severity="review",
                message=f"Evidence/source context is not recorded for {label}; keep it in manual review.",
                evidence_status=evidence_status or "not_recorded",
                component_id=component_id,
                component_name=component_name,
                source_payload=row,
                boundary_note=boundary_note,
            )
        )
    return items


def _manual_review_items(
    route_draft: Mapping[str, Any],
    route_presenter_payload: Mapping[str, Any],
    candidate_match_payload: Mapping[str, Any],
    boundary_note: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    sources: tuple[tuple[str, Sequence[Mapping[str, Any]]], ...] = (
        ("route_draft.manual_review_items", _mapping_list(route_draft.get("manual_review_items"))),
        (
            "route_presenter.manual_review_checklist_rows",
            _mapping_list(route_presenter_payload.get("manual_review_checklist_rows")),
        ),
        ("candidate_match.manual_review_items", _mapping_list(candidate_match_payload.get("manual_review_items"))),
    )
    for source_section, rows in sources:
        for row in rows:
            review_type = _text(row.get("review_type") or row.get("status") or "manual_review")
            field_name = _text(row.get("field") or row.get("slot_type"))
            items.append(
                _base_item(
                    gap_type="manual_review",
                    source_section=source_section,
                    field_name=field_name,
                    slot_type=field_name,
                    severity="review",
                    status=_text(row.get("status")) or "manual_review",
                    message=_text(row.get("note")) or f"Manual review item {review_type} remains open.",
                    source_payload=row,
                    boundary_note=boundary_note,
                )
            )
    return items


def _with_gap_ids(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keyed_items = sorted(
        (_plain_value(item) for item in items),
        key=lambda item: (
            _key(item.get("source_section")),
            _key(item.get("gap_type")),
            _key(item.get("slot_type")),
            _key(item.get("field_name")),
            _key(item.get("component_id")),
            _key(item.get("message")),
            str(item.get("source_payload")),
        ),
    )
    return [
        {
            **item,
            "gap_id": f"plant-route-gap-{index:03d}-{_key(item.get('source_section')) or 'source'}-{_key(item.get('gap_type')) or 'gap'}",
        }
        for index, item in enumerate(keyed_items, start=1)
    ]


def _group_items(items: Sequence[Mapping[str, Any]], key_name: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        group_key = _text(item.get(key_name)) or "unspecified"
        grouped.setdefault(group_key, []).append(_plain_value(item))
    return {key: grouped[key] for key in sorted(grouped, key=lambda item: item.casefold())}


def _counter(items: Sequence[Mapping[str, Any]], key_name: str) -> dict[str, int]:
    counts = Counter(_text(item.get(key_name)) or "unspecified" for item in items)
    return {key: counts[key] for key in sorted(counts, key=lambda item: item.casefold())}


def _queue_summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "total_items": len(items),
        "manual_review_required_items": sum(1 for item in items if item.get("manual_review_required") is True),
        "counts_by_gap_type": _counter(items, "gap_type"),
        "counts_by_severity": _counter(items, "severity"),
        "counts_by_source_section": _counter(items, "source_section"),
        "counts_by_status": _counter(items, "status"),
    }


def _empty_queue() -> dict[str, Any]:
    return {
        "route_summary": {
            "route_id": "",
            "route_name": "",
            "route_type": "",
            "plant_context": {},
            "draft_status": "",
            "boundary_note": "",
        },
        "queue_summary": _queue_summary([]),
        "queue_items": [],
        "queue_items_by_source": {},
        "queue_items_by_gap_type": {},
        "unresolved_items": [],
        "evidence_gap_items": [],
        "unmatched_slot_items": [],
        "manual_review_items": [],
        "boundary_notice": {
            "title": "Documentation-only boundary",
            "notice": BOUNDARY_NOTICE,
        },
        "blocked_outputs_notice": {
            "title": "Blocked output families",
            "notice": BLOCKED_OUTPUTS_NOTICE,
        },
        "empty_state": {
            "is_empty": True,
            "title": "No plant route gaps available",
            "message": "Provide route draft, presenter, or candidate-match readback data to build a manual review queue.",
        },
    }


def build_plant_route_gap_manual_review_queue(
    route_draft: dict[str, Any] | None = None,
    route_presenter_payload: dict[str, Any] | None = None,
    candidate_match_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate plant route gaps into a deterministic documentation-only manual review queue."""
    route_draft_map = _mapping_or_empty(route_draft)
    presenter_map = _mapping_or_empty(route_presenter_payload)
    candidate_map = _mapping_or_empty(candidate_match_payload)
    if not route_draft_map and not presenter_map and not candidate_map:
        return _empty_queue()

    summary = _route_summary(route_draft_map, presenter_map, candidate_map)
    boundary_note = _text(summary.get("boundary_note")) or BOUNDARY_NOTICE
    queue_items = _with_gap_ids(
        [
            *_route_draft_missing_items(route_draft_map, boundary_note),
            *_presenter_missing_items(presenter_map, boundary_note),
            *_candidate_unmatched_items(candidate_map, boundary_note),
            *_candidate_evidence_items(candidate_map, boundary_note),
            *_manual_review_items(route_draft_map, presenter_map, candidate_map, boundary_note),
        ]
    )
    result = {
        "route_summary": summary,
        "queue_summary": _queue_summary(queue_items),
        "queue_items": queue_items,
        "queue_items_by_source": _group_items(queue_items, "source_section"),
        "queue_items_by_gap_type": _group_items(queue_items, "gap_type"),
        "unresolved_items": [item for item in queue_items if item["status"] in {"unresolved", "missing_candidate"}],
        "evidence_gap_items": [item for item in queue_items if item["gap_type"] == "evidence_gap"],
        "unmatched_slot_items": [item for item in queue_items if item["gap_type"] == "unmatched_slot"],
        "manual_review_items": [item for item in queue_items if item["manual_review_required"] is True],
        "boundary_notice": {
            "title": "Documentation-only boundary",
            "notice": boundary_note,
        },
        "blocked_outputs_notice": {
            "title": "Blocked output families",
            "notice": BLOCKED_OUTPUTS_NOTICE,
        },
        "empty_state": {
            "is_empty": False,
            "title": "",
            "message": "",
        },
    }
    return {key: result[key] for key in QUEUE_SECTION_KEYS}
