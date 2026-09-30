from __future__ import annotations

from pathlib import Path

from services.plant_walkthrough_fixture_library import (
    FIXTURE_FIELDS,
    artemisinin_precursor_plant_pathway_review_fixture,
    generic_plant_expression_missing_fields_fixture,
    get_all_plant_walkthrough_review_fixtures,
    get_plant_walkthrough_fixture_library_summary,
    get_plant_walkthrough_review_fixture_by_id,
    n_benthamiana_expression_context_review_fixture,
    non_plant_out_of_scope_guard_fixture,
    rice_albumin_expression_review_fixture,
)


EXPECTED_FIXTURE_IDS = [
    "rice_albumin_expression_review",
    "artemisinin_precursor_plant_pathway_review",
    "n_benthamiana_expression_context_review",
    "generic_plant_expression_missing_fields",
    "non_plant_out_of_scope_guard",
]

UNSAFE_NON_BLOCKED_COPY = (
    "ready to build",
    "experiment-ready",
    "guaranteed expression",
    "high-yield",
    "successful production",
    "wet-lab ready",
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


def test_fixture_library_contains_required_representative_walkthroughs() -> None:
    fixtures = get_all_plant_walkthrough_review_fixtures()

    assert [fixture["fixture_id"] for fixture in fixtures] == EXPECTED_FIXTURE_IDS
    assert [rice_albumin_expression_review_fixture()["fixture_id"]] == [EXPECTED_FIXTURE_IDS[0]]
    assert [artemisinin_precursor_plant_pathway_review_fixture()["fixture_id"]] == [EXPECTED_FIXTURE_IDS[1]]
    assert [n_benthamiana_expression_context_review_fixture()["fixture_id"]] == [EXPECTED_FIXTURE_IDS[2]]
    assert [generic_plant_expression_missing_fields_fixture()["fixture_id"]] == [EXPECTED_FIXTURE_IDS[3]]
    assert [non_plant_out_of_scope_guard_fixture()["fixture_id"]] == [EXPECTED_FIXTURE_IDS[4]]


def test_each_fixture_has_expected_plain_review_shape() -> None:
    for fixture in get_all_plant_walkthrough_review_fixtures():
        assert list(fixture) == list(FIXTURE_FIELDS)
        assert fixture["fixture_id"]
        assert fixture["fixture_name"]
        assert isinstance(fixture["user_intent"], dict)
        assert isinstance(fixture["component_records"], list)
        assert isinstance(fixture["expected_route_context"], dict)
        assert isinstance(fixture["expected_missing_fields"], list)
        assert isinstance(fixture["expected_manual_review_focus"], list)
        assert isinstance(fixture["expected_blocked_claims"], list)
        assert "documentation-only" in fixture["boundary_note"].casefold()
        _assert_plain_data(fixture)


def test_fixture_lookup_and_summary_are_deterministic() -> None:
    first = get_all_plant_walkthrough_review_fixtures()
    second = get_all_plant_walkthrough_review_fixtures()
    summary = get_plant_walkthrough_fixture_library_summary()

    assert first == second
    assert get_plant_walkthrough_review_fixture_by_id("n_benthamiana_expression_context_review") == first[2]
    assert get_plant_walkthrough_review_fixture_by_id("") is None
    assert get_plant_walkthrough_review_fixture_by_id("missing") is None
    assert summary["total_fixtures"] == 5
    assert summary["fixture_ids"] == EXPECTED_FIXTURE_IDS


def test_expected_route_contexts_cover_plant_and_out_of_scope_review() -> None:
    fixtures = {fixture["fixture_id"]: fixture for fixture in get_all_plant_walkthrough_review_fixtures()}

    assert fixtures["rice_albumin_expression_review"]["expected_route_context"]["route_id"] == (
        "rice_seed_protein_expression"
    )
    assert fixtures["n_benthamiana_expression_context_review"]["expected_route_context"]["route_id"] == (
        "plant_transient_expression_review"
    )
    assert fixtures["generic_plant_expression_missing_fields"]["expected_missing_fields"]
    assert fixtures["non_plant_out_of_scope_guard"]["expected_route_context"]["scope_status"] == (
        "mixed_scope_manual_review"
    )


def test_fixtures_do_not_contain_final_design_or_runtime_behavior() -> None:
    source = Path("services/plant_walkthrough_fixture_library.py").read_text(encoding="utf-8").casefold()

    disallowed_runtime_markers = [
        "streamlit",
        "sqlite",
        "project_export",
        "project_import",
        "expression_wizard",
        "component_library_mutation",
        "openai",
        "requests",
        "httpx",
        "agent_runtime",
        "cloud_runtime",
        "generate_sequence",
        "sequence_output",
        "select_final_component",
        "score_feasibility",
    ]
    for marker in disallowed_runtime_markers:
        assert marker not in source


def test_no_unsafe_copy_claims_outside_blocked_claim_metadata() -> None:
    for fixture in get_all_plant_walkthrough_review_fixtures():
        text_without_blocked_claims = str(
            {
                key: value
                for key, value in fixture.items()
                if key != "expected_blocked_claims"
            }
        ).casefold()
        for unsafe in UNSAFE_NON_BLOCKED_COPY:
            assert unsafe not in text_without_blocked_claims
