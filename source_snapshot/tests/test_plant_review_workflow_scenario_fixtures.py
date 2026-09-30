# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from services import plant_review_workflow_scenario_fixtures as fixtures


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("best ", "component"),
    _term("recommended ", "component"),
)

FORBIDDEN_FIELD_FRAGMENTS = (
    "final_route",
    "final_component",
    "selected_component",
    "winner",
)

REQUIRED_READBACK_SECTIONS = (
    "package_header",
    "status_summary_card",
    "route_summary_section",
    "review_queue_section",
    "gap_manual_review_section",
)


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _queue_counts(result: dict[str, Any]) -> dict[str, int]:
    counts = result["readback_presenter"]["gap_manual_review_section"]["counts"]
    return {str(key): int(value) for key, value in counts.items()}


def _review_item_count(result: dict[str, Any]) -> int:
    return len(result["gap_manual_review_queue_result"]["review_items"])


def _assert_required_readback_sections(result: dict[str, Any]) -> None:
    presenter = result["readback_presenter"]
    for section in REQUIRED_READBACK_SECTIONS:
        assert section in presenter


def _assert_no_field_fragment(value: object, fragment: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert fragment not in key.casefold()
            _assert_no_field_fragment(nested, fragment)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_field_fragment(nested, fragment)


def _assert_no_final_design_claim(result: dict[str, Any]) -> None:
    seen = 0

    def _walk(value: object) -> None:
        nonlocal seen
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "final_design_present":
                    seen += 1
                    assert nested is False
                _walk(nested)
        elif isinstance(value, list):
            for nested in value:
                _walk(nested)

    _walk(result)
    assert seen >= 1


def test_scenario_fixture_ids_are_stable_and_ordered() -> None:
    assert fixtures.list_plant_review_workflow_scenario_ids() == [
        fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW,
        fixtures.PLANT_TRANSIENT_EXPRESSION_REVIEW,
        fixtures.GENERIC_PLANT_EXPRESSION_VECTOR_REVIEW,
        fixtures.UNSUPPORTED_NON_PLANT_SCOPE,
        fixtures.EMPTY_OR_VAGUE_INPUT,
    ]


def test_scenario_inputs_are_plain_data_and_defensive_copies() -> None:
    first = fixtures.build_plant_review_workflow_scenario_input(
        fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW
    )
    second = fixtures.build_plant_review_workflow_scenario_input(
        fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW
    )
    first["user_intent"]["target_name"] = "mutated locally"

    assert second["user_intent"]["target_name"] == "rice seed albumin-like protein"
    for scenario_input in fixtures.build_all_plant_review_workflow_scenario_inputs():
        _assert_plain_data(scenario_input)


def test_unknown_scenario_id_fails_explicitly() -> None:
    with pytest.raises(ValueError):
        fixtures.build_plant_review_workflow_scenario_input("missing")


def test_rice_seed_protein_expression_review_locks_manual_review_gaps() -> None:
    result = fixtures.run_plant_review_workflow_scenario_fixture(
        fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW
    )
    counts = _queue_counts(result)

    assert result["scenario_id"] == fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW
    assert result["route_draft"]["route_id"] == "rice_seed_protein_expression"
    assert result["chain_status"] == "manual_review_required"
    assert result["plant_review_package"]["package_status"] == "manual_review_required"
    assert result["manual_review_required"] is True
    assert result["blocked"] is False
    assert counts["evidence_gap"] >= 1
    assert counts["provenance_gap"] >= 1
    assert _review_item_count(result) >= counts["evidence_gap"] + counts["provenance_gap"]
    _assert_required_readback_sections(result)


def test_plant_transient_expression_review_locks_route_and_candidate_only_state() -> None:
    result = fixtures.run_plant_review_workflow_scenario_fixture(
        fixtures.PLANT_TRANSIENT_EXPRESSION_REVIEW
    )
    counts = _queue_counts(result)

    assert result["route_draft"]["route_id"] == "plant_transient_expression_review"
    assert result["chain_status"] == "manual_review_required"
    assert result["manual_review_required"] is True
    assert result["blocked"] is False
    assert result["component_candidate_match_result"]["candidate_component_matches_present"] is True
    assert counts["component_gap"] >= 1
    _assert_no_final_design_claim(result)
    for fragment in FORBIDDEN_FIELD_FRAGMENTS:
        _assert_no_field_fragment(result, fragment)


def test_generic_plant_expression_vector_review_assembles_package_and_presenter() -> None:
    result = fixtures.run_plant_review_workflow_scenario_fixture(
        fixtures.GENERIC_PLANT_EXPRESSION_VECTOR_REVIEW
    )
    counts = _queue_counts(result)

    assert result["route_draft"]["route_id"] == "plant_expression_vector"
    assert result["chain_status"] == "manual_review_required"
    assert result["manual_review_required"] is True
    assert result["plant_review_package"]["package_type"] == "plant_review_package"
    assert result["readback_presenter"]["package_header"]["package_id"]
    assert counts["component_gap"] >= 1
    assert counts["evidence_gap"] >= 1
    _assert_required_readback_sections(result)
    _assert_no_final_design_claim(result)
    for fragment in FORBIDDEN_FIELD_FRAGMENTS:
        _assert_no_field_fragment(result, fragment)


def test_unsupported_non_plant_scope_blocks_without_active_plant_design_claim() -> None:
    result = fixtures.run_plant_review_workflow_scenario_fixture(
        fixtures.UNSUPPORTED_NON_PLANT_SCOPE
    )
    counts = _queue_counts(result)

    assert result["route_draft"]["route_id"] == "unsupported_non_plant_expression_context"
    assert result["route_draft"]["active_design_route"] is False
    assert result["chain_status"] == "blocked"
    assert result["plant_review_package"]["package_status"] == "blocked"
    assert result["readback_presenter"]["status_summary_card"]["status_label"] == "blocked"
    assert result["blocked"] is True
    assert result["manual_review_required"] is True
    assert counts["unsupported_scope"] >= 1
    assert counts["route_context_gap"] >= 1


def test_empty_or_vague_input_returns_safe_manual_review_state_without_crash() -> None:
    result = fixtures.run_plant_review_workflow_scenario_fixture(fixtures.EMPTY_OR_VAGUE_INPUT)
    counts = _queue_counts(result)

    assert result["route_draft"]["route_id"] == "unknown_plant_expression_context"
    assert result["route_draft"]["active_design_route"] is False
    assert result["manual_review_required"] is True
    assert result["blocked"] is True
    assert result["plant_review_package"]["package_status"] == "blocked"
    assert counts["unsupported_scope"] >= 1
    _assert_required_readback_sections(result)


def test_all_scenario_outputs_are_deterministic_plain_data() -> None:
    first = fixtures.run_all_plant_review_workflow_scenario_fixtures()
    second = fixtures.run_all_plant_review_workflow_scenario_fixtures()

    assert first == second
    _assert_plain_data(first)


def test_scenario_fixture_source_and_outputs_keep_copy_safety_boundaries() -> None:
    outputs_text = str(fixtures.run_all_plant_review_workflow_scenario_fixtures()).casefold()
    source_text = Path("services/plant_review_workflow_scenario_fixtures.py").read_text(
        encoding="utf-8"
    ).casefold()
    test_text = Path("tests/test_plant_review_workflow_scenario_fixtures.py").read_text(
        encoding="utf-8"
    ).casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in outputs_text
        assert phrase not in source_text
        assert phrase not in test_text

    assert "documentation-only" in outputs_text
    assert "manual review" in outputs_text
