from __future__ import annotations

from pathlib import Path

from services.plant_walkthrough_chain_runner import run_all_plant_walkthrough_chains
from services.plant_walkthrough_validation_summary import (
    VALIDATION_SUMMARY_KEYS,
    build_plant_walkthrough_validation_summary,
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
}

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


def test_validation_summary_contains_required_top_level_sections() -> None:
    summary = build_plant_walkthrough_validation_summary()

    assert list(summary) == list(VALIDATION_SUMMARY_KEYS)
    assert summary["total_fixtures"] == 5
    assert summary["completed_chain_count"] == 5
    assert summary["out_of_scope_count"] == 1


def test_summary_counts_route_status_package_status_and_markdown_availability() -> None:
    summary = build_plant_walkthrough_validation_summary()

    assert summary["route_draft_status_summary"]["manual_review_required"] >= 1  # type: ignore[index]
    assert summary["package_snapshot_status_summary"]["manual_review_required"] == 5  # type: ignore[index]
    assert summary["markdown_readback_availability"] == {"available_count": 5, "missing_count": 0}


def test_summary_counts_missing_fields_candidates_gaps_and_manual_review_items() -> None:
    summary = build_plant_walkthrough_validation_summary()

    assert summary["missing_field_counts"]["total_missing_fields"] > 0  # type: ignore[index]
    assert summary["candidate_match_counts"]["total_candidate_rows"] > 0  # type: ignore[index]
    assert summary["unresolved_gap_counts"]["total_unresolved_gaps"] > 0  # type: ignore[index]
    assert summary["manual_review_item_counts"]["total_manual_review_items"] > 0  # type: ignore[index]
    assert summary["missing_field_counts"]["by_fixture"]["generic_plant_expression_missing_fields"] > 0  # type: ignore[index]


def test_boundary_compliance_and_blocked_claim_scan_are_review_safe() -> None:
    summary = build_plant_walkthrough_validation_summary()

    assert summary["boundary_compliance_summary"]["documentation_only_rows"] == 5  # type: ignore[index]
    assert summary["boundary_compliance_summary"]["non_compliant_rows"] == 0  # type: ignore[index]
    assert summary["blocked_claim_scan_summary"]["scan_status"] == "review_passed"  # type: ignore[index]
    assert summary["blocked_claim_scan_summary"]["non_blocked_context_hits"] == {}  # type: ignore[index]
    assert "not biological validation" in summary["boundary_notice"]["notice"].casefold()  # type: ignore[index]


def test_fixture_level_summary_rows_are_stable_and_plain() -> None:
    first = build_plant_walkthrough_validation_summary()
    second = build_plant_walkthrough_validation_summary()
    rows = first["fixture_level_summary_rows"]

    assert first == second
    assert [row["fixture_id"] for row in rows] == [  # type: ignore[index]
        "rice_albumin_expression_review",
        "artemisinin_precursor_plant_pathway_review",
        "n_benthamiana_expression_context_review",
        "generic_plant_expression_missing_fields",
        "non_plant_out_of_scope_guard",
    ]
    _assert_plain_data(first)


def test_summary_accepts_explicit_chain_outputs() -> None:
    outputs = run_all_plant_walkthrough_chains()
    summary = build_plant_walkthrough_validation_summary(outputs[:2])

    assert summary["total_fixtures"] == 2
    assert summary["completed_chain_count"] == 2
    assert len(summary["fixture_level_summary_rows"]) == 2  # type: ignore[arg-type]


def test_no_unsafe_fields_or_product_claims_appear_in_summary() -> None:
    summary = build_plant_walkthrough_validation_summary()
    text_without_scan_terms = str(
        {
            key: value
            for key, value in summary.items()
            if key != "blocked_claim_scan_summary"
        }
    ).casefold()

    for item in _walk_dicts(summary):
        assert FORBIDDEN_FIELD_NAMES.isdisjoint(item)
    assert "workflow_chain_completed" in text_without_scan_terms
    assert "readback" in text_without_scan_terms
    for unsafe in UNSAFE_NON_BLOCKED_COPY:
        assert unsafe not in text_without_scan_terms


def test_no_ui_db_import_export_package_export_or_runtime_behavior_is_introduced() -> None:
    source = Path("services/plant_walkthrough_validation_summary.py").read_text(encoding="utf-8").casefold()

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
