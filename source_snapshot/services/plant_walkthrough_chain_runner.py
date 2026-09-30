from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_component_candidate_match_readback import build_plant_component_candidate_match_readback
from services.plant_design_review_package_markdown_readback import build_plant_design_review_package_markdown_readback
from services.plant_design_review_package_snapshot import build_plant_design_review_package_snapshot
from services.plant_route_draft_presenter import present_plant_route_draft
from services.plant_route_gap_manual_review_queue import build_plant_route_gap_manual_review_queue
from services.plant_user_intent_route_draft_builder import build_plant_expression_route_draft
from services.plant_walkthrough_fixture_library import (
    get_all_plant_walkthrough_review_fixtures,
    get_plant_walkthrough_review_fixture_by_id,
)


CHAIN_OUTPUT_KEYS: tuple[str, ...] = (
    "fixture_id",
    "route_draft",
    "presenter_payload",
    "candidate_match_payload",
    "gap_queue_payload",
    "package_snapshot",
    "markdown_readback",
    "chain_summary",
    "boundary_notice",
    "blocked_outputs_notice",
)

BOUNDARY_NOTICE = (
    "Documentation-only plant walkthrough chain runner. It passes review fixtures through the "
    "existing route draft, presenter, candidate match readback, gap queue, package snapshot, and "
    "Markdown readback services without UI, database, import/export, package export, agent, LLM, "
    "cloud, sequence generation, final component selection, biological decision behavior, outcome "
    "scoring, experiment procedure generation, or lab-use judgment."
)

BLOCKED_OUTPUTS_NOTICE = (
    "Blocked outputs remain outside this chain runner: final biological recommendations, final "
    "component selections, sequence outputs, outcome scoring, experiment procedures, and lab-use "
    "readiness judgments."
)

OUT_OF_SCOPE_GUARD_STATUSES: tuple[str, ...] = (
    "unsupported_non_plant_scope",
    "mixed_scope_manual_review",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def _plain_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [_plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return [_plain_value(value)]


def _route_context_status(route_draft: Mapping[str, Any]) -> str:
    plant_context = _mapping_or_empty(route_draft.get("plant_context"))
    return _text(plant_context.get("scope_status")) or "not_recorded"


def _chain_summary(
    *,
    fixture: Mapping[str, Any],
    route_draft: Mapping[str, Any],
    candidate_match_payload: Mapping[str, Any],
    gap_queue_payload: Mapping[str, Any],
    package_snapshot: Mapping[str, Any],
    markdown_readback: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_summary = _mapping_or_empty(candidate_match_payload.get("candidate_match_summary"))
    queue_summary = _mapping_or_empty(gap_queue_payload.get("queue_summary"))
    expected_context = _mapping_or_empty(fixture.get("expected_route_context"))
    route_id = _text(route_draft.get("route_id"))
    scope_status = _route_context_status(route_draft)
    return {
        "fixture_id": _text(fixture.get("fixture_id")),
        "fixture_scope": _text(fixture.get("fixture_scope")),
        "chain_status": "workflow_chain_completed",
        "route_id": route_id,
        "route_context_status": scope_status,
        "expected_route_id": _text(expected_context.get("route_id")),
        "expected_scope_status": _text(expected_context.get("scope_status")),
        "expected_route_context_matched": (
            route_id == _text(expected_context.get("route_id"))
            and scope_status == _text(expected_context.get("scope_status"))
        ),
        "draft_status": _text(route_draft.get("draft_status")),
        "package_status": _text(package_snapshot.get("package_status")),
        "markdown_readback_available": bool(_text(markdown_readback.get("markdown_text"))),
        "candidate_rows": int(candidate_summary.get("total_candidate_rows") or 0),
        "unmatched_slots": int(candidate_summary.get("unmatched_slots") or 0),
        "gap_queue_items": int(queue_summary.get("total_items") or 0),
        "manual_review_items": len(_plain_list(gap_queue_payload.get("manual_review_items"))),
        "boundary_status": "documentation_only_manual_review",
        "out_of_scope_guard": scope_status in OUT_OF_SCOPE_GUARD_STATUSES,
        "blocked_outputs_preserved": True,
    }


def run_plant_walkthrough_chain_for_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Run one R389 fixture through the existing R382-R387 pure-Python chain."""
    if not isinstance(fixture, Mapping):
        raise TypeError("fixture must be a mapping")

    fixture_id = _text(fixture.get("fixture_id"))
    user_intent = _mapping_or_empty(fixture.get("user_intent"))
    component_records = [
        record
        for record in _plain_list(fixture.get("component_records"))
        if isinstance(record, Mapping)
    ]

    route_draft = build_plant_expression_route_draft(user_intent)
    presenter_payload = present_plant_route_draft(route_draft)
    candidate_match_payload = build_plant_component_candidate_match_readback(
        route_draft,
        [dict(record) for record in component_records],
    )
    gap_queue_payload = build_plant_route_gap_manual_review_queue(
        route_draft,
        presenter_payload,
        candidate_match_payload,
    )
    package_snapshot = build_plant_design_review_package_snapshot(
        route_draft,
        presenter_payload,
        candidate_match_payload,
        gap_queue_payload,
        package_metadata={
            "fixture_id": fixture_id,
            "package_title": f"Plant Walkthrough Review Snapshot - {fixture_id or 'fixture'}",
        },
    )
    markdown_readback = build_plant_design_review_package_markdown_readback(package_snapshot)
    result = {
        "fixture_id": fixture_id,
        "route_draft": route_draft,
        "presenter_payload": presenter_payload,
        "candidate_match_payload": candidate_match_payload,
        "gap_queue_payload": gap_queue_payload,
        "package_snapshot": package_snapshot,
        "markdown_readback": markdown_readback,
        "chain_summary": _chain_summary(
            fixture=fixture,
            route_draft=route_draft,
            candidate_match_payload=candidate_match_payload,
            gap_queue_payload=gap_queue_payload,
            package_snapshot=package_snapshot,
            markdown_readback=markdown_readback,
        ),
        "boundary_notice": {
            "title": "Documentation-only boundary",
            "notice": BOUNDARY_NOTICE,
        },
        "blocked_outputs_notice": {
            "title": "Blocked output families",
            "notice": BLOCKED_OUTPUTS_NOTICE,
            "blocked_claims": _plain_value(fixture.get("expected_blocked_claims") or []),
        },
    }
    return {key: _plain_value(result[key]) for key in CHAIN_OUTPUT_KEYS}


def run_plant_walkthrough_chain_by_fixture_id(fixture_id: str) -> dict[str, Any] | None:
    fixture = get_plant_walkthrough_review_fixture_by_id(fixture_id)
    if fixture is None:
        return None
    return run_plant_walkthrough_chain_for_fixture(fixture)


def run_all_plant_walkthrough_chains() -> list[dict[str, Any]]:
    return [
        run_plant_walkthrough_chain_for_fixture(fixture)
        for fixture in get_all_plant_walkthrough_review_fixtures()
    ]
