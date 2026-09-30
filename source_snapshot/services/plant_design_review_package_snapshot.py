from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


BOUNDARY_NOTICE = (
    "Documentation-only Plant Expression Vector Design Review Package snapshot for manual "
    "review. It combines existing route draft, presenter, candidate-match, and gap queue "
    "payloads without modifying export behavior, choosing components, generating sequences, "
    "producing experiment procedures, scoring outcomes, or judging downstream use."
)
BLOCKED_OUTPUTS_NOTICE = (
    "Blocked output families remain outside this snapshot layer: package export mutation, final "
    "component selection, biological part advice, sequence generation, outcome scoring, "
    "experiment procedure generation, and downstream-use judgments."
)

PACKAGE_SCOPE = "plant_expression_vector_design_review_snapshot"
PACKAGE_SECTION_KEYS: tuple[str, ...] = (
    "route_summary",
    "design_intent_section",
    "plant_context_section",
    "construct_slot_plan_section",
    "component_candidate_section",
    "evidence_summary_section",
    "gap_queue_section",
    "manual_review_section",
    "boundary_section",
)
SNAPSHOT_KEYS: tuple[str, ...] = (
    "package_id",
    "package_title",
    "package_status",
    "package_scope",
    "identity_payload",
    "identity_md5",
    "route_summary",
    "design_intent_section",
    "plant_context_section",
    "construct_slot_plan_section",
    "component_candidate_section",
    "evidence_summary_section",
    "gap_queue_section",
    "manual_review_section",
    "boundary_section",
    "package_sections",
    "package_warnings",
    "empty_state",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_")


def _slug(value: Any) -> str:
    clean = "".join(char.lower() if char.isalnum() else "-" for char in _text(value))
    return "-".join(part for part in clean.split("-") if part)


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


def _plain_list(value: Any) -> list[Any]:
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
    gap_queue_payload: Mapping[str, Any],
) -> dict[str, Any]:
    gap_summary = _mapping_or_empty(gap_queue_payload.get("route_summary"))
    presenter_summary = _mapping_or_empty(route_presenter_payload.get("route_summary_card"))
    candidate_summary = _mapping_or_empty(candidate_match_payload.get("route_summary"))
    plant_context = (
        route_draft.get("plant_context")
        if "plant_context" in route_draft
        else gap_summary.get("plant_context")
        if "plant_context" in gap_summary
        else route_presenter_payload.get("plant_context_card")
        if "plant_context_card" in route_presenter_payload
        else candidate_summary.get("plant_context")
    )
    return {
        "route_id": _text(
            route_draft.get("route_id")
            or gap_summary.get("route_id")
            or presenter_summary.get("route_id")
            or candidate_summary.get("route_id")
        ),
        "route_name": _text(
            route_draft.get("route_name")
            or gap_summary.get("route_name")
            or presenter_summary.get("route_name")
            or candidate_summary.get("route_name")
        ),
        "route_type": _text(
            route_draft.get("route_type")
            or gap_summary.get("route_type")
            or presenter_summary.get("route_type")
            or candidate_summary.get("route_type")
        ),
        "plant_context": _plain_value(plant_context),
        "draft_status": _text(
            route_draft.get("draft_status")
            or gap_summary.get("draft_status")
            or presenter_summary.get("draft_status")
            or candidate_summary.get("draft_status")
        ),
        "boundary_note": _text(
            route_draft.get("boundary_note")
            or gap_summary.get("boundary_note")
            or presenter_summary.get("boundary_note")
            or candidate_summary.get("boundary_note")
        ),
    }


def _design_intent_section(route_draft: Mapping[str, Any], route_presenter_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "target_summary": _plain_value(
            route_draft.get("target_summary") or route_presenter_payload.get("target_summary_card") or {}
        ),
        "provided_field_rows": _plain_value(
            route_presenter_payload.get("provided_field_rows") or route_draft.get("provided_fields") or []
        ),
        "missing_fields": _plain_value(route_draft.get("missing_fields") or []),
        "section_status": "manual_review_required",
    }


def _plant_context_section(route_draft: Mapping[str, Any], route_presenter_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "plant_context": _plain_value(
            route_draft.get("plant_context") or route_presenter_payload.get("plant_context_card") or {}
        ),
        "route_template": _plain_value(
            route_presenter_payload.get("route_template_card") or route_draft.get("selected_template") or {}
        ),
        "required_modules": _plain_value(
            route_presenter_payload.get("required_module_rows") or route_draft.get("required_modules") or []
        ),
    }


def _construct_slot_plan_section(
    route_draft: Mapping[str, Any],
    route_presenter_payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "construct_slot_rows": _plain_value(
            route_presenter_payload.get("construct_slot_plan_rows") or route_draft.get("required_slots") or []
        ),
        "package_preview_sections": _plain_value(
            route_presenter_payload.get("package_preview_sections") or route_draft.get("package_preview_sections") or []
        ),
        "section_status": "manual_review_required",
    }


def _component_candidate_section(candidate_match_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_match_summary": _plain_value(candidate_match_payload.get("candidate_match_summary") or {}),
        "slot_candidate_rows": _plain_value(candidate_match_payload.get("slot_candidate_rows") or []),
        "unmatched_slot_rows": _plain_value(candidate_match_payload.get("unmatched_slot_rows") or []),
        "section_status": "candidate_readback_only",
        "selection_status": "candidate_readback_no_selection",
    }


def _evidence_summary_section(
    route_draft: Mapping[str, Any],
    route_presenter_payload: Mapping[str, Any],
    candidate_match_payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "route_evidence_rows": _plain_value(
            route_presenter_payload.get("evidence_summary_rows") or route_draft.get("evidence_summary") or []
        ),
        "candidate_evidence_rows": _plain_value(candidate_match_payload.get("evidence_coverage_rows") or []),
        "section_status": "source_context_review",
    }


def _gap_queue_section(gap_queue_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "queue_summary": _plain_value(gap_queue_payload.get("queue_summary") or {}),
        "queue_items": _plain_value(gap_queue_payload.get("queue_items") or []),
        "unresolved_items": _plain_value(gap_queue_payload.get("unresolved_items") or []),
        "evidence_gap_items": _plain_value(gap_queue_payload.get("evidence_gap_items") or []),
        "unmatched_slot_items": _plain_value(gap_queue_payload.get("unmatched_slot_items") or []),
        "section_status": "manual_review_required",
    }


def _manual_review_section(
    route_draft: Mapping[str, Any],
    route_presenter_payload: Mapping[str, Any],
    candidate_match_payload: Mapping[str, Any],
    gap_queue_payload: Mapping[str, Any],
) -> dict[str, Any]:
    rows = [
        *_plain_list(route_draft.get("manual_review_items") or []),
        *_plain_list(route_presenter_payload.get("manual_review_checklist_rows") or []),
        *_plain_list(candidate_match_payload.get("manual_review_items") or []),
        *_plain_list(gap_queue_payload.get("manual_review_items") or []),
    ]
    return {
        "manual_review_items": rows,
        "manual_review_required": bool(rows) or True,
        "section_status": "manual_review_required",
    }


def _boundary_section(
    route_draft: Mapping[str, Any],
    route_presenter_payload: Mapping[str, Any],
    candidate_match_payload: Mapping[str, Any],
    gap_queue_payload: Mapping[str, Any],
) -> dict[str, Any]:
    notices = [
        _plain_value(route_presenter_payload.get("boundary_notice") or {}),
        _plain_value(candidate_match_payload.get("boundary_notice") or {}),
        _plain_value(gap_queue_payload.get("boundary_notice") or {}),
    ]
    blocked = [
        _plain_value(route_presenter_payload.get("blocked_outputs_notice") or {}),
        _plain_value(candidate_match_payload.get("blocked_outputs_notice") or {}),
        _plain_value(gap_queue_payload.get("blocked_outputs_notice") or {}),
    ]
    return {
        "boundary_notice": {
            "title": "Documentation-only boundary",
            "notice": _text(route_draft.get("boundary_note")) or BOUNDARY_NOTICE,
        },
        "blocked_outputs_notice": {
            "title": "Blocked output families",
            "notice": BLOCKED_OUTPUTS_NOTICE,
        },
        "source_boundary_notices": [notice for notice in notices if notice],
        "source_blocked_outputs_notices": [notice for notice in blocked if notice],
    }


def _package_sections(sections: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, key in enumerate(PACKAGE_SECTION_KEYS, start=1):
        section = _mapping_or_empty(sections.get(key))
        rows.append(
            {
                "section_id": key,
                "section_label": key.replace("_", " ").title(),
                "display_order": index,
                "status": _text(section.get("section_status")) or "included",
            }
        )
    return rows


def _package_status(
    route_summary: Mapping[str, Any],
    gap_queue_section: Mapping[str, Any],
    manual_review_section: Mapping[str, Any],
) -> str:
    if not _text(route_summary.get("route_id")):
        return "needs_input"
    queue_summary = _mapping_or_empty(gap_queue_section.get("queue_summary"))
    if queue_summary.get("total_items") or manual_review_section.get("manual_review_items"):
        return "manual_review_required"
    return "draft_readback_only"


def _identity_payload(
    route_summary: Mapping[str, Any],
    package_metadata: Mapping[str, Any],
    sections: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "package_scope": PACKAGE_SCOPE,
        "route_id": _text(route_summary.get("route_id")),
        "route_name": _text(route_summary.get("route_name")),
        "route_type": _text(route_summary.get("route_type")),
        "draft_status": _text(route_summary.get("draft_status")),
        "metadata": _plain_value(package_metadata),
        "section_fingerprints": {
            "construct_slot_plan_section": _plain_value(sections.get("construct_slot_plan_section")),
            "component_candidate_section": _plain_value(sections.get("component_candidate_section")),
            "gap_queue_section": _plain_value(sections.get("gap_queue_section")),
        },
    }


def _identity_md5(identity_payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(_plain_value(identity_payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()


def _package_warnings(gap_queue_section: Mapping[str, Any], component_candidate_section: Mapping[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    queue_summary = _mapping_or_empty(gap_queue_section.get("queue_summary"))
    if queue_summary.get("total_items"):
        warnings.append(
            {
                "warning_type": "manual_review_queue_open",
                "message": "Gap queue contains unresolved documentation review items.",
            }
        )
    unmatched_rows = _plain_list(component_candidate_section.get("unmatched_slot_rows") or [])
    if unmatched_rows:
        warnings.append(
            {
                "warning_type": "unmatched_slots_recorded",
                "message": "One or more construct slots have no candidate readback row.",
            }
        )
    return warnings


def _empty_snapshot() -> dict[str, Any]:
    route_summary: dict[str, Any] = {
        "route_id": "",
        "route_name": "",
        "route_type": "",
        "plant_context": {},
        "draft_status": "",
        "boundary_note": "",
    }
    sections = {
        "route_summary": route_summary,
        "design_intent_section": {"target_summary": {}, "provided_field_rows": [], "missing_fields": [], "section_status": "needs_input"},
        "plant_context_section": {"plant_context": {}, "route_template": {}, "required_modules": []},
        "construct_slot_plan_section": {"construct_slot_rows": [], "package_preview_sections": [], "section_status": "needs_input"},
        "component_candidate_section": {
            "candidate_match_summary": {},
            "slot_candidate_rows": [],
            "unmatched_slot_rows": [],
            "section_status": "candidate_readback_only",
            "selection_status": "candidate_readback_no_selection",
        },
        "evidence_summary_section": {"route_evidence_rows": [], "candidate_evidence_rows": [], "section_status": "needs_input"},
        "gap_queue_section": {
            "queue_summary": {},
            "queue_items": [],
            "unresolved_items": [],
            "evidence_gap_items": [],
            "unmatched_slot_items": [],
            "section_status": "needs_input",
        },
        "manual_review_section": {"manual_review_items": [], "manual_review_required": True, "section_status": "needs_input"},
        "boundary_section": {
            "boundary_notice": {"title": "Documentation-only boundary", "notice": BOUNDARY_NOTICE},
            "blocked_outputs_notice": {"title": "Blocked output families", "notice": BLOCKED_OUTPUTS_NOTICE},
            "source_boundary_notices": [],
            "source_blocked_outputs_notices": [],
        },
    }
    identity = _identity_payload(route_summary, {}, sections)
    package_id = "plant-design-review-package-empty"
    result = {
        "package_id": package_id,
        "package_title": "Plant Design Review Package Snapshot",
        "package_status": "needs_input",
        "package_scope": PACKAGE_SCOPE,
        "identity_payload": identity,
        "identity_md5": _identity_md5(identity),
        **sections,
        "package_sections": _package_sections(sections),
        "package_warnings": [],
        "empty_state": {
            "is_empty": True,
            "title": "No plant design review package snapshot available",
            "message": "Provide route draft, readback, candidate-match, or gap queue data to build a documentation review snapshot.",
        },
    }
    return {key: result[key] for key in SNAPSHOT_KEYS}


def build_plant_design_review_package_snapshot(
    route_draft: dict[str, Any] | None = None,
    route_presenter_payload: dict[str, Any] | None = None,
    candidate_match_payload: dict[str, Any] | None = None,
    gap_queue_payload: dict[str, Any] | None = None,
    package_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic documentation-only Plant Design Review Package snapshot."""
    route_draft_map = _mapping_or_empty(route_draft)
    presenter_map = _mapping_or_empty(route_presenter_payload)
    candidate_map = _mapping_or_empty(candidate_match_payload)
    gap_queue_map = _mapping_or_empty(gap_queue_payload)
    metadata_map = _mapping_or_empty(package_metadata)
    if not route_draft_map and not presenter_map and not candidate_map and not gap_queue_map and not metadata_map:
        return _empty_snapshot()

    route_summary = _route_summary(route_draft_map, presenter_map, candidate_map, gap_queue_map)
    sections = {
        "route_summary": route_summary,
        "design_intent_section": _design_intent_section(route_draft_map, presenter_map),
        "plant_context_section": _plant_context_section(route_draft_map, presenter_map),
        "construct_slot_plan_section": _construct_slot_plan_section(route_draft_map, presenter_map),
        "component_candidate_section": _component_candidate_section(candidate_map),
        "evidence_summary_section": _evidence_summary_section(route_draft_map, presenter_map, candidate_map),
        "gap_queue_section": _gap_queue_section(gap_queue_map),
        "manual_review_section": _manual_review_section(route_draft_map, presenter_map, candidate_map, gap_queue_map),
        "boundary_section": _boundary_section(route_draft_map, presenter_map, candidate_map, gap_queue_map),
    }
    identity = _identity_payload(route_summary, metadata_map, sections)
    package_id = f"plant-design-review-package-{_slug(route_summary.get('route_id')) or 'draft'}-{_identity_md5(identity)[:12]}"
    package_title = _text(metadata_map.get("package_title")) or "Plant Design Review Package Snapshot"
    result = {
        "package_id": package_id,
        "package_title": package_title,
        "package_status": _package_status(
            route_summary,
            sections["gap_queue_section"],
            sections["manual_review_section"],
        ),
        "package_scope": PACKAGE_SCOPE,
        "identity_payload": identity,
        "identity_md5": _identity_md5(identity),
        **sections,
        "package_sections": _package_sections(sections),
        "package_warnings": _package_warnings(
            sections["gap_queue_section"],
            sections["component_candidate_section"],
        ),
        "empty_state": {
            "is_empty": False,
            "title": "",
            "message": "",
        },
    }
    return {key: result[key] for key in SNAPSHOT_KEYS}
