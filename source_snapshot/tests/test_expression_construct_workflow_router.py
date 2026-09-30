# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import expression_construct_workflow_router as router


def _payload_text(value) -> str:
    if isinstance(value, dict):
        return "\n".join(_payload_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_payload_text(item) for item in value)
    return str(value)


def _assert_mainline(result: dict[str, object]) -> None:
    assert result["route_category"] == router.ROUTE_CATEGORY_ACTIVE
    assert result["manual_review_required"] is True
    assert result["matched_workflow_route"] in {
        router.ACTIVE_MAINLINE_ROUTE,
        router.PLANT_MAINLINE_ROUTE,
        router.HOST_MAINLINE_ROUTE,
    }
    assert "target_identity" in result["required_information_slots"]
    assert "host_system" in result["required_information_slots"]
    assert "construct_or_vector_context" in result["required_information_slots"]
    assert "source_or_provenance" in result["required_information_slots"]


def test_chinese_plant_expression_routes_to_expression_construct_mainline() -> None:
    result = router.route_expression_construct_workflow("我要做水稻白蛋白表达")

    _assert_mainline(result)
    assert result["matched_workflow_route"] == router.PLANT_MAINLINE_ROUTE
    assert result["confidence_category"] == router.CONFIDENCE_HIGH
    assert any("plant context noted" in note for note in result["documentation_only_boundary_notes"])
    assert "construct_or_vector_context" in result["missing_information_slots"]
    assert "source_or_provenance" in result["missing_information_slots"]
    assert "target_identity" not in result["missing_information_slots"]


def test_yeast_recombinant_protein_expression_routes_to_same_mainline() -> None:
    result = router.route_expression_construct_workflow("yeast recombinant protein expression")

    _assert_mainline(result)
    assert result["matched_workflow_route"] == router.HOST_MAINLINE_ROUTE
    assert any("yeast" in note for note in result["documentation_only_boundary_notes"])
    assert "host context noted: yeast" in " | ".join(result["documentation_only_boundary_notes"]).lower()


def test_ecoli_enzyme_expression_vector_routes_to_same_mainline() -> None:
    result = router.route_expression_construct_workflow("E. coli enzyme expression vector")

    _assert_mainline(result)
    assert result["matched_workflow_route"] == router.HOST_MAINLINE_ROUTE
    assert any("e. coli" in note.lower() for note in result["documentation_only_boundary_notes"])
    assert "source_or_provenance" in result["missing_information_slots"]


def test_plant_expression_vector_review_routes_to_same_mainline_with_plant_context() -> None:
    result = router.route_expression_construct_workflow("plant expression vector review")

    _assert_mainline(result)
    assert result["matched_workflow_route"] == router.PLANT_MAINLINE_ROUTE
    assert result["confidence_category"] == router.CONFIDENCE_HIGH
    assert "plant context review" in result["suggested_review_stages"]


def test_vague_input_uses_safe_fallback() -> None:
    result = router.route_expression_construct_workflow("help")

    assert result["route_category"] == router.ROUTE_CATEGORY_FALLBACK
    assert result["matched_workflow_route"] == router.FALLBACK_ROUTE
    assert result["confidence_category"] == router.CONFIDENCE_LOW
    assert result["missing_information_slots"] == [
        "target_identity",
        "host_system",
        "construct_or_vector_context",
        "source_or_provenance",
    ]
    assert "collect target, host, construct/vector, and source/provenance information" in result[
        "safe_next_review_action"
    ].lower()


def test_metabolic_pathway_intent_is_marked_future_route_candidate() -> None:
    result = router.route_expression_construct_workflow("metabolic pathway product biosynthesis review")

    assert result["route_category"] == router.ROUTE_CATEGORY_FUTURE
    assert result["matched_workflow_route"] == router.FUTURE_METABOLIC_ROUTE
    assert "future route candidate only" in " ".join(result["documentation_only_boundary_notes"]).lower()
    assert "manual_review_context" in result["required_information_slots"]


def test_genetic_circuit_intent_is_marked_future_route_candidate() -> None:
    result = router.route_expression_construct_workflow("genetic circuit regulatory module review")

    assert result["route_category"] == router.ROUTE_CATEGORY_FUTURE
    assert result["matched_workflow_route"] == router.FUTURE_CIRCUIT_ROUTE
    assert "circuit_or_module_goal" in result["required_information_slots"]
    assert result["safe_next_review_action"].startswith("Keep this as a future route candidate")


def test_router_copy_avoids_unsafe_claims() -> None:
    payload = {
        "plant": router.route_expression_construct_workflow("我要做水稻白蛋白表达"),
        "yeast": router.route_expression_construct_workflow("yeast recombinant protein expression"),
        "ecoli": router.route_expression_construct_workflow("E. coli enzyme expression vector"),
        "plant_review": router.route_expression_construct_workflow("plant expression vector review"),
        "fallback": router.route_expression_construct_workflow("help"),
        "pathway": router.route_expression_construct_workflow("metabolic pathway product biosynthesis review"),
        "circuit": router.route_expression_construct_workflow("genetic circuit regulatory module review"),
    }
    combined = _payload_text(payload).lower()
    forbidden = [
        "recommended component",
        "recommend biological",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "experiment-ready",
        "wet-lab-ready",
        "build-ready construct",
        "biological feasibility claim",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_router_is_pure_python_and_deterministic() -> None:
    source = inspect.getsource(router)

    assert "streamlit" not in source.lower()
    kwargs = {
        "user_intent_text": "yeast recombinant protein expression",
        "context": {"source": "lab notebook", "host_system": "yeast"},
    }

    assert router.route_expression_construct_workflow(**kwargs) == router.route_expression_construct_workflow(**kwargs)
