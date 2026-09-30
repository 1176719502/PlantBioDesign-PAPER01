# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from services import plant_review_handoff_data_adapter as handoff_adapter
from services import plant_review_workflow_contract_validator as contract_validator
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
    "final_component",
    "selected_component",
    "best_component",
    "recommended_component",
    "final_route",
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


def _assert_no_field_fragment(value: object, fragment: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if fragment in key.casefold():
                assert key.casefold().endswith("_present")
                assert nested is False
            _assert_no_field_fragment(nested, fragment)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_field_fragment(nested, fragment)


def _rice_vertical_walkthrough() -> tuple[dict, dict, dict]:
    chain = fixtures.run_plant_review_workflow_scenario_fixture(
        fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW
    )
    contract = contract_validator.validate_plant_review_workflow_contract(chain)
    handoff = handoff_adapter.build_plant_review_handoff_payload(
        chain,
        {
            "walkthrough_id": "rice_albumin_vertical_review",
            "review_surface": "local documentation review",
        },
    )
    return chain, contract, handoff


def test_rice_albumin_vertical_walkthrough_preserves_manual_review_path() -> None:
    chain, contract, handoff = _rice_vertical_walkthrough()

    assert chain["scenario_id"] == fixtures.RICE_SEED_PROTEIN_EXPRESSION_REVIEW
    assert chain["route_draft"]["route_id"] == "rice_seed_protein_expression"
    assert chain["chain_status"] == "manual_review_required"
    assert chain["manual_review_required"] is True
    assert chain["blocked"] is False

    assert contract["contract_status"] == "valid"
    assert contract["is_valid_for_review"] is True
    assert contract["manual_review_required"] is True
    assert contract["blocked"] is False
    assert contract["errors"] == []

    assert handoff["handoff_status"] == "manual_review_required"
    assert handoff["manual_review_required"] is True
    assert handoff["reviewer_summary"]["blocked"] is False
    assert handoff["package_header"]["route_id"] == "rice_seed_protein_expression"
    assert handoff["source_traceability"]["handoff_context"]["walkthrough_id"] == (
        "rice_albumin_vertical_review"
    )


def test_rice_albumin_vertical_walkthrough_keeps_evidence_component_and_gap_traceability() -> None:
    chain, contract, handoff = _rice_vertical_walkthrough()

    queue_categories = {item["category"] for item in handoff["required_review_items"]}
    evidence_ids = {item["evidence_id"] for item in handoff["evidence_traceability_items"]}
    component_ids = {item["component_id"] for item in handoff["component_traceability_items"]}

    assert "evidence_gap" in queue_categories
    assert "provenance_gap" in queue_categories
    assert "R77-RICE-EV-CDS" in evidence_ids
    assert "R77-RICE-COMP-CDS" in component_ids
    assert "R77-RICE-COMP-PROMOTER-GAP" in str(handoff["required_review_items"])
    assert contract["queue_contract"]["review_item_count"] == len(
        chain["gap_manual_review_queue_result"]["review_items"]
    )
    assert handoff["source_traceability"]["route_traceability_items"]


def test_rice_albumin_vertical_walkthrough_outputs_plain_review_data_only() -> None:
    chain, contract, handoff = _rice_vertical_walkthrough()

    _assert_plain_data(chain)
    _assert_plain_data(contract)
    _assert_plain_data(handoff)
    for payload in (chain, contract, handoff):
        for fragment in FORBIDDEN_FIELD_FRAGMENTS:
            _assert_no_field_fragment(payload, fragment)


def test_rice_albumin_vertical_walkthrough_copy_keeps_boundary_language() -> None:
    chain, contract, handoff = _rice_vertical_walkthrough()

    combined_output = f"{chain} {contract} {handoff}".casefold()
    source_text = Path(
        "tests/test_plant_review_rice_albumin_vertical_walkthrough.py"
    ).read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in combined_output
        assert phrase not in source_text

    assert "documentation-only" in combined_output
    assert "manual review" in combined_output
