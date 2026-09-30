from __future__ import annotations

import os
import sys
from typing import Any


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.plant_simple_wizard_intent_intake_presenter import (
    build_simple_plant_wizard_intent_intake_presenter,
)
from services.plant_simple_wizard_route_schema import (
    HANDOFF_STAGE_ID,
    get_simple_plant_wizard_route,
)


PLAIN_TYPES = (dict, list, str, bool, int, float, type(None))


def _walk_plain_values(value: Any) -> None:
    assert isinstance(value, PLAIN_TYPES)
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for item in value.values():
            _walk_plain_values(item)
    elif isinstance(value, list):
        for item in value:
            _walk_plain_values(item)


def _text_blob(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text_blob(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text_blob(item) for item in value)
    return "" if value is None else str(value)


def _candidate(payload: dict[str, Any], route_id: str) -> dict[str, Any]:
    for candidate in payload["route_candidates"]:
        if candidate["route_id"] == route_id:
            return candidate
    raise AssertionError(f"missing candidate {route_id}")


def test_protein_expression_text_recommends_protein_route_with_confirmation() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter(
        "Express a target protein enzyme in tobacco leaves",
        available_materials=["target_gene_or_cds", "host_plant"],
    )

    assert payload["recommended_route_id"] == "plant_protein_expression_review"
    assert payload["decision_state"] == "ready_for_user_confirmation"
    assert _candidate(payload, "plant_protein_expression_review")[
        "requires_user_confirmation"
    ] is True


def test_artemisinin_pathway_broad_goal_keeps_clarification_questions() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter("在植物里做青蒿素")

    assert payload["recommended_route_id"] == "plant_metabolic_pathway_review"
    assert payload["confidence"] in {"medium", "low"}
    assert payload["decision_state"] == "needs_clarification"
    assert payload["clarification_questions_zh"]
    assert {
        "plant_metabolic_pathway_review",
        "plant_protein_expression_review",
        "plant_multigene_construct_review",
    }.issubset({candidate["route_id"] for candidate in payload["route_candidates"]})


def test_chinese_rice_seed_protein_expression_goal_is_high_confidence() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter(
        "我想在水稻中表达一个种子蛋白"
    )

    assert payload["recommended_route_id"] == "plant_protein_expression_review"
    assert payload["confidence"] == "high"
    assert payload["decision_state"] == "ready_for_user_confirmation"
    protein_candidate = _candidate(payload, "plant_protein_expression_review")
    reason_blob = " ".join(protein_candidate["match_reasons_zh"])
    assert "表达" in reason_blob
    assert "蛋白" in reason_blob
    assert "植物宿主" in reason_blob


def test_chinese_plant_albumin_expression_goal_is_high_confidence() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter(
        "我想在植物中表达白蛋白"
    )

    assert payload["recommended_route_id"] == "plant_protein_expression_review"
    assert payload["confidence"] == "high"
    assert payload["decision_state"] == "ready_for_user_confirmation"


def test_chinese_tobacco_antigen_protein_expression_goal_is_high_confidence() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter(
        "我想在烟草中表达一个抗原蛋白"
    )

    assert payload["recommended_route_id"] == "plant_protein_expression_review"
    assert payload["confidence"] == "high"
    assert payload["decision_state"] == "ready_for_user_confirmation"


def test_chinese_artemisinin_product_goal_is_not_forced_high_confidence() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter("我想做青蒿素")

    assert payload["confidence"] in {"medium", "low"}
    assert payload["decision_state"] == "needs_clarification"


def test_multigene_multi_cassette_text_recommends_multigene_route() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter(
        "Plan a multi-cassette construct with multiple genes and stacked expression"
    )

    assert payload["recommended_route_id"] == "plant_multigene_construct_review"


def test_promoter_tf_cis_element_text_recommends_regulatory_module_route() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter(
        "Review a stress response promoter, TF, and cis-element reporter module"
    )

    assert payload["recommended_route_id"] == "plant_regulatory_module_review"


def test_empty_input_returns_low_confidence_and_needs_clarification() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter()

    assert payload["confidence"] == "low"
    assert payload["decision_state"] == "needs_clarification"
    assert payload["clarification_questions_zh"]
    assert len(payload["route_candidates"]) == 4


def test_selected_goal_type_is_strong_but_not_absolute_when_text_conflicts() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter(
        "promoter TF cis-element reporter module",
        selected_goal_type="protein_expression",
    )

    candidate_ids = [candidate["route_id"] for candidate in payload["route_candidates"]]
    assert candidate_ids[0] == "plant_protein_expression_review"
    assert "plant_regulatory_module_review" in candidate_ids
    assert _candidate(payload, "plant_regulatory_module_review")["uncertainties_zh"]


def test_candidate_routes_include_labels_from_r167_schema() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter(
        "terpenoid natural product pathway"
    )
    route = get_simple_plant_wizard_route("plant_metabolic_pathway_review")
    candidate = _candidate(payload, "plant_metabolic_pathway_review")

    assert candidate["label_zh"] == route["label_zh"]
    assert candidate["button_label_zh"] == route["button_label_zh"]


def test_handoff_stage_id_is_shared_r167_stage() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter("flavonoid pathway")

    assert payload["handoff_stage_id"] == HANDOFF_STAGE_ID


def test_output_is_deterministic_across_repeated_calls() -> None:
    first = build_simple_plant_wizard_intent_intake_presenter(
        "multiple enzymes for alkaloid pathway",
        selected_goal_type="metabolic_pathway",
        available_materials=["target_product", "literature_evidence"],
    )
    second = build_simple_plant_wizard_intent_intake_presenter(
        "multiple enzymes for alkaloid pathway",
        selected_goal_type="metabolic_pathway",
        available_materials=["target_product", "literature_evidence"],
    )

    assert first == second


def test_returned_data_is_plain_values_only() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter("目标蛋白表达")

    _walk_plain_values(payload)


def test_safety_notes_and_generated_text_do_not_contain_forbidden_claims() -> None:
    payload = build_simple_plant_wizard_intent_intake_presenter(
        "promoter and pathway review"
    )
    forbidden_fragments = [
        "valid" + "ated",
        "optim" + "ized",
        "experiment" + "-ready",
        "proto" + "col",
        "yield" + " prediction",
        "best" + " component",
        "wet" + "-lab ready",
    ]
    blob = _text_blob(payload).casefold()

    for fragment in forbidden_fragments:
        assert fragment not in blob
