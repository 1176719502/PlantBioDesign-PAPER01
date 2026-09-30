from __future__ import annotations

from pathlib import Path

import pytest

from services.plant_walkthrough_chain_runner import (
    CHAIN_OUTPUT_KEYS,
    run_all_plant_walkthrough_chains,
    run_plant_walkthrough_chain_by_fixture_id,
    run_plant_walkthrough_chain_for_fixture,
)
from services.plant_walkthrough_fixture_library import (
    get_all_plant_walkthrough_review_fixtures,
    get_plant_walkthrough_review_fixture_by_id,
)


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
    "selected_component",
    "final_component",
}

UNSAFE_NON_BLOCKED_COPY = (
    "ready to build",
    "experiment-ready",
    "guaranteed expression",
    "high-yield",
    "successful production",
    "wet-lab ready",
)


def _fixture(fixture_id: str) -> dict[str, object]:
    fixture = get_plant_walkthrough_review_fixture_by_id(fixture_id)
    assert fixture is not None
    return fixture


def _run(fixture_id: str) -> dict[str, object]:
    result = run_plant_walkthrough_chain_by_fixture_id(fixture_id)
    assert result is not None
    return result


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


def test_rice_albumin_fixture_runs_end_to_end() -> None:
    result = _run("rice_albumin_expression_review")

    assert list(result) == list(CHAIN_OUTPUT_KEYS)
    assert result["fixture_id"] == "rice_albumin_expression_review"
    assert result["chain_summary"]["chain_status"] == "workflow_chain_completed"  # type: ignore[index]
    assert result["chain_summary"]["expected_route_context_matched"] is True  # type: ignore[index]
    assert result["route_draft"]["route_id"] == "rice_seed_protein_expression"  # type: ignore[index]
    assert result["markdown_readback"]["markdown_text"]  # type: ignore[index]


def test_artemisinin_precursor_fixture_runs_as_review_planning_not_production_claim() -> None:
    result = _run("artemisinin_precursor_plant_pathway_review")
    text = str(result).casefold()

    assert result["chain_summary"]["chain_status"] == "workflow_chain_completed"  # type: ignore[index]
    assert result["route_draft"]["route_id"] == "plant_expression_vector"  # type: ignore[index]
    assert "documentation-only" in text
    assert "manual review" in text
    assert "successful production" not in text


def test_n_benthamiana_fixture_runs_end_to_end() -> None:
    result = _run("n_benthamiana_expression_context_review")

    assert result["route_draft"]["route_id"] == "plant_transient_expression_review"  # type: ignore[index]
    assert result["chain_summary"]["expected_route_context_matched"] is True  # type: ignore[index]
    assert result["chain_summary"]["candidate_rows"] >= 3  # type: ignore[index]
    assert result["package_snapshot"]["empty_state"]["is_empty"] is False  # type: ignore[index]


def test_missing_fields_fixture_produces_gaps_and_manual_review_items() -> None:
    result = _run("generic_plant_expression_missing_fields")

    assert result["route_draft"]["missing_fields"]  # type: ignore[index]
    assert result["gap_queue_payload"]["queue_summary"]["total_items"] > 0  # type: ignore[index]
    assert result["chain_summary"]["manual_review_items"] > 0  # type: ignore[index]
    assert result["chain_summary"]["unmatched_slots"] > 0  # type: ignore[index]


def test_non_plant_fixture_stays_out_of_scope_manual_review() -> None:
    result = _run("non_plant_out_of_scope_guard")

    assert result["route_draft"]["route_id"] == "unsupported_non_plant_expression_context"  # type: ignore[index]
    assert result["route_draft"]["plant_context"]["scope_status"] == "mixed_scope_manual_review"  # type: ignore[index]
    assert result["chain_summary"]["out_of_scope_guard"] is True  # type: ignore[index]
    assert result["candidate_match_payload"]["candidate_match_summary"]["manual_review_required"] is True  # type: ignore[index]
    assert result["candidate_match_payload"]["candidate_match_summary"]["total_candidate_rows"] == 0  # type: ignore[index]
    assert result["gap_queue_payload"]["queue_summary"]["total_items"] > 0  # type: ignore[index]


def test_all_outputs_are_plain_data_and_all_fixtures_run_deterministically() -> None:
    first = run_all_plant_walkthrough_chains()
    second = run_all_plant_walkthrough_chains()

    assert len(first) == len(get_all_plant_walkthrough_review_fixtures()) == 5
    assert first == second
    _assert_plain_data(first)


def test_invalid_fixture_input_and_missing_lookup_are_safe() -> None:
    with pytest.raises(TypeError, match="fixture must be a mapping"):
        run_plant_walkthrough_chain_for_fixture(["not", "mapping"])  # type: ignore[arg-type]

    assert run_plant_walkthrough_chain_by_fixture_id("missing") is None


def test_no_unsafe_output_fields_or_final_biological_recommendation_are_produced() -> None:
    for result in run_all_plant_walkthrough_chains():
        for item in _walk_dicts(result):
            assert FORBIDDEN_FIELD_NAMES.isdisjoint(item)

        runner_notice_text = str(result["boundary_notice"]).casefold()
        chain_summary_text = str(result["chain_summary"]).casefold()
        assert "final biological recommendation" not in runner_notice_text
        assert "biological recommendation" not in runner_notice_text
        assert "final biological recommendation" not in chain_summary_text
        assert "biological recommendation" not in chain_summary_text
        for unsafe in UNSAFE_NON_BLOCKED_COPY:
            assert unsafe not in runner_notice_text
            assert unsafe not in chain_summary_text


def test_no_ui_db_import_export_package_export_or_runtime_behavior_is_introduced() -> None:
    source = Path("services/plant_walkthrough_chain_runner.py").read_text(encoding="utf-8").casefold()

    disallowed_runtime_markers = [
        "streamlit",
        "sqlite",
        "project_export",
        "project_import",
        "package_export_service",
        "expression_wizard",
        "component_library_mutation",
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
