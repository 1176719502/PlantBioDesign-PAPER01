# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import expression_construct_workflow_router as router
from services import expression_construct_workflow_router_presenter as presenter


def _with_intent(intent: str, result: dict[str, object]) -> dict[str, object]:
    payload = dict(result)
    payload["matched_intent_text"] = intent
    return payload


def _present(intent: str, context: dict[str, object] | None = None) -> dict[str, object]:
    routed = router.route_expression_construct_workflow(intent, context=context)
    return presenter.build_expression_construct_workflow_router_presenter(_with_intent(intent, routed))


def _payload_text(value: object) -> str:
    if isinstance(value, dict):
        return "\n".join(_payload_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_payload_text(item) for item in value)
    return str(value)


def _phrase(*parts: str) -> str:
    return "".join(parts)


def test_active_expression_construct_route_builds_ui_safe_readback_payload() -> None:
    payload = _present("expression construct vector source review for target protein")

    assert payload["status"] == presenter.PRESENTER_STATUS_AVAILABLE
    assert payload["page_title"] == "Expression Construct Workflow Route"
    assert payload["route_status"]["active_mainline"] is True
    assert payload["route_status"]["future_candidate"] is False
    assert payload["route_status"]["fallback"] is False
    assert payload["route_summary_card"]["route_status_label"] == "Active expression construct review mainline"
    assert payload["matched_intent_text"] == "expression construct vector source review for target protein"
    assert "intent review" in payload["suggested_review_stages"]
    assert payload["required_information_slots"] == [
        "target_identity",
        "host_system",
        "construct_or_vector_context",
        "source_or_provenance",
    ]
    assert "host_system" in payload["missing_or_unknown_slots"]
    assert payload["required_information_slot_rows"][0] == {
        "slot_key": "target_identity",
        "review_status": "present in router result",
    }
    assert payload["safe_next_review_action"]
    assert "documentation-only route readback" in payload["documentation_only_boundary_notes"]


def test_plant_expression_context_keeps_same_mainline_with_plant_review_stage() -> None:
    payload = _present("plant expression vector review")

    assert payload["route_status"]["active_mainline"] is True
    assert payload["route_summary_card"]["matched_workflow_route"] == router.PLANT_MAINLINE_ROUTE
    assert "plant context review" in payload["suggested_review_stages"]
    assert any("plant context noted" in note for note in payload["documentation_only_boundary_notes"])
    assert payload["route_summary_card"]["confidence_category"] == router.CONFIDENCE_HIGH


def test_yeast_and_ecoli_expression_contexts_keep_host_mainline_without_host_judgment() -> None:
    yeast_payload = _present("yeast recombinant protein expression")
    ecoli_payload = _present("E. coli enzyme expression vector")

    assert yeast_payload["route_status"]["active_mainline"] is True
    assert ecoli_payload["route_status"]["active_mainline"] is True
    assert yeast_payload["route_summary_card"]["matched_workflow_route"] == router.HOST_MAINLINE_ROUTE
    assert ecoli_payload["route_summary_card"]["matched_workflow_route"] == router.HOST_MAINLINE_ROUTE
    assert any("yeast" in note.casefold() for note in yeast_payload["documentation_only_boundary_notes"])
    assert any("e. coli" in note.casefold() for note in ecoli_payload["documentation_only_boundary_notes"])
    assert "host_system" not in yeast_payload["missing_or_unknown_slots"]
    assert "host_system" not in ecoli_payload["missing_or_unknown_slots"]


def test_future_metabolic_pathway_route_candidate_is_not_active_mainline() -> None:
    payload = _present("metabolic pathway product biosynthesis review")

    assert payload["route_status"]["active_mainline"] is False
    assert payload["route_status"]["future_candidate"] is True
    assert payload["route_status"]["fallback"] is False
    assert payload["route_summary_card"]["matched_workflow_route"] == router.FUTURE_METABOLIC_ROUTE
    assert payload["route_summary_card"]["route_status_label"] == "Future route candidate for manual triage"
    assert "target_pathway_or_product" in payload["required_information_slots"]
    assert "future route review" in payload["suggested_review_stages"]


def test_future_genetic_circuit_route_candidate_is_not_active_mainline() -> None:
    payload = _present("genetic circuit regulatory module review")

    assert payload["route_status"]["future_candidate"] is True
    assert payload["route_summary_card"]["matched_workflow_route"] == router.FUTURE_CIRCUIT_ROUTE
    assert "circuit_or_module_goal" in payload["required_information_slots"]
    assert payload["safe_next_review_action"].startswith("Keep this as a future route candidate")


def test_vague_fallback_exposes_warning_and_missing_slot_readback() -> None:
    payload = _present("help")

    assert payload["route_status"]["fallback"] is True
    assert payload["route_status"]["tone"] == "attention"
    assert payload["route_summary_card"]["matched_workflow_route"] == router.FALLBACK_ROUTE
    assert payload["warnings"] == ["Router result used the fallback clarification route."]
    assert payload["missing_or_unknown_slots"] == [
        "target_identity",
        "host_system",
        "construct_or_vector_context",
        "source_or_provenance",
    ]
    assert all(row["review_status"] == "missing or unknown" for row in payload["required_information_slot_rows"])


def test_invalid_or_empty_router_result_returns_safe_empty_state() -> None:
    payload = presenter.build_expression_construct_workflow_router_presenter({})

    assert payload["status"] == presenter.PRESENTER_STATUS_EMPTY
    assert payload["route_status"]["fallback"] is True
    assert payload["route_status"]["active_mainline"] is False
    assert payload["empty_state"] == {
        "is_empty": True,
        "message": "Invalid or empty expression construct workflow router result.",
        "manual_review_required": True,
    }
    assert payload["warnings"] == ["Invalid or empty expression construct workflow router result."]
    assert payload["required_information_slots"] == []
    assert payload["missing_or_unknown_slots"] == []


def test_presenter_copy_avoids_unsafe_biological_and_downstream_use_wording() -> None:
    payloads = [
        _present("expression construct vector source review for target protein"),
        _present("plant expression vector review"),
        _present("yeast recombinant protein expression"),
        _present("E. coli enzyme expression vector"),
        _present("metabolic pathway product biosynthesis review"),
        _present("genetic circuit regulatory module review"),
        _present("help"),
        presenter.build_expression_construct_workflow_router_presenter({}),
    ]
    combined = _payload_text(payloads).casefold()
    forbidden = [
        _phrase("successful ", "import"),
        _phrase("project ", "imported"),
        _phrase("ready for ", "execution"),
        _phrase("experiment", "-ready"),
        _phrase("production", "-ready"),
        _phrase("validated ", "construct"),
        _phrase("optimized ", "pathway"),
        _phrase("yield ", "prediction"),
        _phrase("build", "-ready"),
        _phrase("component ", "recommendation"),
        _phrase("protocol ", "generation"),
        _phrase("biological ", "feasibility"),
        _phrase("experimental ", "validation"),
        _phrase("wet-lab", "-ready"),
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_presenter_is_pure_python_and_deterministic() -> None:
    source = inspect.getsource(presenter)
    payload = _with_intent(
        "plant expression vector review",
        router.route_expression_construct_workflow("plant expression vector review"),
    )

    assert "streamlit" not in source.casefold()
    assert "st." not in source.casefold()
    assert "sqlite" not in source.casefold()
    assert presenter.build_expression_construct_workflow_router_presenter(payload) == (
        presenter.build_expression_construct_workflow_router_presenter(payload)
    )
