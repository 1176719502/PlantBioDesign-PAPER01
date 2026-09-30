from __future__ import annotations

from pathlib import Path

from services.plant_component_candidate_match_readback import build_plant_component_candidate_match_readback
from services.plant_route_draft_presenter import present_plant_route_draft
from services.plant_route_gap_manual_review_queue import (
    QUEUE_SECTION_KEYS,
    build_plant_route_gap_manual_review_queue,
)
from services.plant_user_intent_route_draft_builder import build_plant_expression_route_draft


FORBIDDEN_FIELD_NAMES = {
    "recommendation",
    "optimization",
    "feasibility_score",
    "yield_prediction",
    "protocol",
    "wet_lab_ready",
    "validated",
    "build_ready",
    "best",
}


def _rice_route_draft() -> dict[str, object]:
    return build_plant_expression_route_draft(
        {
            "target_name": "OsALB gap queue target",
            "target_type": "source-backed plant expression target",
            "plant_host": "Oryza sativa rice",
            "plant_context": "rice seed expression documentation context",
            "expression_purpose": "local documentation review",
            "known_cds_source": "SRC-CDS-385",
            "known_component_ids": {
                "promoter": "SRC-PROMOTER-385",
            },
            "known_vector_or_backbone": "SRC-BACKBONE-385",
            "evidence_sources": {"SRC-RICE-385": "rice host context source pointer"},
            "notes": "Manual documentation review note.",
        }
    )


def _candidate_payload() -> dict[str, object]:
    return build_plant_component_candidate_match_readback(
        _rice_route_draft(),
        [
            {
                "component_id": "COMP-PROMOTER-385",
                "component_name": "Rice promoter candidate record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "plant_context": "rice seed expression documentation context",
            }
        ],
    )


def _full_queue() -> dict[str, object]:
    draft = _rice_route_draft()
    return build_plant_route_gap_manual_review_queue(
        route_draft=draft,
        route_presenter_payload=present_plant_route_draft(draft),
        candidate_match_payload=_candidate_payload(),
    )


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for nested in value.values():
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _walk_dicts(value: object) -> list[dict[str, object]]:
    dicts: list[dict[str, object]] = []
    if isinstance(value, dict):
        dicts.append(value)
        for nested in value.values():
            dicts.extend(_walk_dicts(nested))
    elif isinstance(value, list):
        for nested in value:
            dicts.extend(_walk_dicts(nested))
    return dicts


def test_route_draft_missing_fields_become_queue_items() -> None:
    queue = build_plant_route_gap_manual_review_queue(route_draft=_rice_route_draft())

    missing_items = [item for item in queue["queue_items"] if item["gap_type"] == "missing_field"]  # type: ignore[index]
    assert missing_items
    assert {item["field_name"] for item in missing_items} >= {"terminator_slot"}  # type: ignore[index]
    assert all(item["source_section"] == "route_draft" for item in missing_items)  # type: ignore[index]
    assert all(item["manual_review_required"] is True for item in missing_items)  # type: ignore[index]


def test_presenter_missing_field_rows_become_queue_items() -> None:
    draft = _rice_route_draft()
    queue = build_plant_route_gap_manual_review_queue(route_presenter_payload=present_plant_route_draft(draft))

    assert any(
        item["source_section"] == "route_presenter.missing_field_rows"
        and item["gap_type"] == "missing_field"
        for item in queue["queue_items"]  # type: ignore[index]
    )


def test_candidate_unmatched_slot_rows_become_queue_items() -> None:
    queue = build_plant_route_gap_manual_review_queue(candidate_match_payload=_candidate_payload())

    unmatched = queue["unmatched_slot_items"]
    assert unmatched
    assert all(item["gap_type"] == "unmatched_slot" for item in unmatched)  # type: ignore[index]
    assert all(item["severity"] == "blocked" for item in unmatched)  # type: ignore[index]


def test_evidence_coverage_gaps_become_evidence_gap_queue_items() -> None:
    queue = build_plant_route_gap_manual_review_queue(candidate_match_payload=_candidate_payload())

    evidence_gaps = queue["evidence_gap_items"]
    assert evidence_gaps
    assert any(item["component_id"] == "COMP-PROMOTER-385" for item in evidence_gaps)  # type: ignore[index]
    assert all(item["manual_review_required"] is True for item in evidence_gaps)  # type: ignore[index]


def test_manual_review_checklist_rows_are_preserved() -> None:
    queue = _full_queue()

    assert any(
        item["source_section"] == "route_presenter.manual_review_checklist_rows"
        for item in queue["manual_review_items"]  # type: ignore[index]
    )
    assert any(
        item["source_section"] == "candidate_match.manual_review_items"
        for item in queue["manual_review_items"]  # type: ignore[index]
    )


def test_duplicate_looking_gaps_are_handled_deterministically() -> None:
    draft = _rice_route_draft()
    first = build_plant_route_gap_manual_review_queue(
        route_draft=draft,
        route_presenter_payload=present_plant_route_draft(draft),
    )
    second = build_plant_route_gap_manual_review_queue(
        route_presenter_payload=present_plant_route_draft(draft),
        route_draft=draft,
    )

    assert first == second
    assert len({item["gap_id"] for item in first["queue_items"]}) == len(first["queue_items"])  # type: ignore[index]


def test_queue_summary_counts_are_deterministic() -> None:
    queue = _full_queue()
    summary = queue["queue_summary"]

    assert summary["total_items"] == len(queue["queue_items"])  # type: ignore[index]
    assert summary["manual_review_required_items"] == len(queue["queue_items"])  # type: ignore[index]
    assert summary["counts_by_gap_type"]["missing_field"] >= 1  # type: ignore[index]
    assert summary["counts_by_source_section"]["route_draft"] >= 1  # type: ignore[index]
    assert _full_queue()["queue_summary"] == summary


def test_empty_input_returns_safe_empty_state() -> None:
    queue = build_plant_route_gap_manual_review_queue()

    assert list(queue) == list(QUEUE_SECTION_KEYS)
    assert queue["empty_state"]["is_empty"] is True  # type: ignore[index]
    assert queue["queue_items"] == []
    assert queue["queue_summary"]["total_items"] == 0  # type: ignore[index]
    assert "documentation-only" in queue["boundary_notice"]["notice"].casefold()  # type: ignore[index]


def test_route_summary_preserves_route_identity_context_and_status() -> None:
    draft = _rice_route_draft()
    queue = build_plant_route_gap_manual_review_queue(route_draft=draft)
    summary = queue["route_summary"]

    assert summary["route_id"] == draft["route_id"]  # type: ignore[index]
    assert summary["route_name"] == draft["route_name"]  # type: ignore[index]
    assert summary["route_type"] == draft["route_type"]  # type: ignore[index]
    assert summary["plant_context"] == draft["plant_context"]  # type: ignore[index]
    assert summary["draft_status"] == draft["draft_status"]  # type: ignore[index]


def test_boundary_notice_and_blocked_outputs_notice_are_present() -> None:
    queue = _full_queue()

    assert "documentation-only" in queue["boundary_notice"]["notice"].casefold()  # type: ignore[index]
    assert "blocked output" in queue["blocked_outputs_notice"]["title"].casefold()  # type: ignore[index]


def test_output_is_plain_dict_list_only() -> None:
    _assert_plain_data(_full_queue())


def test_no_unsafe_fields_are_present_anywhere_in_output() -> None:
    queue = _full_queue()

    for item in _walk_dicts(queue):
        assert FORBIDDEN_FIELD_NAMES.isdisjoint(item)


def test_no_ui_db_import_export_package_expression_wizard_or_runtime_behavior_is_introduced() -> None:
    source = Path("services/plant_route_gap_manual_review_queue.py").read_text(encoding="utf-8").casefold()

    disallowed_runtime_markers = [
        "streamlit",
        "sqlite",
        "project_export",
        "project_import",
        "package_export",
        "expression_wizard",
        "component_library",
        "openai",
        "requests",
        "httpx",
        "agent_runtime",
        "cloud_runtime",
        "generate_sequence",
        "sequence_output",
        "recommend_component",
        "optimize_sequence",
        "score_feasibility",
        "wet_lab_ready",
    ]
    for marker in disallowed_runtime_markers:
        assert marker not in source
