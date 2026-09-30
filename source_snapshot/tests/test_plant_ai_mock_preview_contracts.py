# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from services.plant_ai_handoff_preview_presenter import build_rice_albumin_handoff_preview_payload
from services.plant_ai_intake_mock_parser import parse_rice_albumin_like_intake
from services.plant_ai_intake_safety_router import route_ai_intake_request
from services.plant_ai_mock_preview_contracts import (
    ALLOWED_OUTPUT_BOUNDARY_DOCUMENTATION,
    BLOCKED_OUTPUT_BOUNDARY,
    HANDOFF_BOUNDARY_LABELS,
    STABLE_PREVIEW_CONTRACT_KEYS,
)
from services.plant_ai_user_input_mock_preview import build_user_input_mock_preview_payload
import views.PlantDesignWorkspace as workspace


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_INPUT = "Prepare a company handoff draft for an albumin-like protein in rice seed."
BLOCKED_INPUT = "Give me a rice transformation protocol with cloning steps."
NON_PLANT_INPUT = "Build a yeast expression workflow for a protein."
MIXED_INPUT = "Prepare a company handoff draft for rice seed albumin-like expression and include cloning protocol steps."


def _field_map(rows: list[dict[str, str]]) -> dict[str, str]:
    return {row["Field"]: row["Readback"] for row in rows}


def _output_values(rows: list[dict[str, str]]) -> list[str]:
    return [row["Output"] for row in rows]


def _strip_user_request_and_blocked_labels(value: object) -> str:
    text = str(value).casefold()
    for removable in [
        SUPPORTED_INPUT.casefold(),
        BLOCKED_INPUT.casefold(),
        NON_PLANT_INPUT.casefold(),
        MIXED_INPUT.casefold(),
        "wet lab protocol",
        "cloning steps",
        "transformation steps",
        "culture conditions",
        "primer design",
        "synthesis ready sequence",
        "final construct recommendation",
        "component ranking",
        "yield prediction",
        "success guarantee",
        "wet lab readiness claim",
        "not an experimental protocol",
        "not a final construct design",
    ]:
        text = text.replace(removable, "")
    return text


def test_r112_supported_input_keeps_stable_contract_keys() -> None:
    payload = build_user_input_mock_preview_payload(SUPPORTED_INPUT)
    request_scope = _field_map(payload["request_scope_rows"])

    assert set(STABLE_PREVIEW_CONTRACT_KEYS).issubset(payload)
    assert payload["scope_category"] == "company_handoff_request"
    assert payload["preview_status"] == "supported plant mock preview"
    assert payload["allowed_outputs"] == [
        "design_intent",
        "plant_design_context",
        "evidence_placeholders",
        "component_slots",
        "construct_draft_slots",
        "review_items",
        "report_blocks",
        "company_handoff_draft",
    ]
    assert payload["blocked_outputs"] == [
        "wet_lab_protocol",
        "cloning_steps",
        "transformation_steps",
        "culture_conditions",
        "primer_design",
        "synthesis_ready_sequence",
        "final_construct_recommendation",
        "component_ranking",
        "yield_prediction",
        "success_guarantee",
        "wet_lab_readiness_claim",
    ]
    assert payload["persistent"] is False
    assert request_scope["Workflow route"] == "Supported plant review mock preview."
    assert any("documentation-only" in statement.casefold() for statement in payload["boundary_statements"])
    assert any("manual review" in statement.casefold() for statement in payload["boundary_statements"])
    assert any("blocked" in statement.casefold() for statement in payload["boundary_statements"])
    assert any(row["Readback"] == "rice" for row in payload["parsed_intent_rows"])


def test_r112_blocked_and_non_plant_inputs_keep_consistent_route_wording() -> None:
    blocked = build_user_input_mock_preview_payload(BLOCKED_INPUT)
    non_plant = build_user_input_mock_preview_payload(NON_PLANT_INPUT)

    assert blocked["scope_category"] == "blocked_wet_lab_execution"
    assert blocked["preview_status"] == "blocked input"
    assert blocked["allowed_outputs"] == ["safe_conceptual_summary"]
    assert {row["Preview boundary"] for row in blocked["blocked_output_rows"]} == {BLOCKED_OUTPUT_BOUNDARY}
    assert _field_map(blocked["blocked_notice_rows"])["Blocked status"] == "blocked input"

    assert non_plant["scope_category"] == "non_plant_out_of_scope"
    assert non_plant["preview_status"] == "non-plant input routed out"
    assert non_plant["allowed_outputs"] == ["safe_conceptual_summary"]
    assert _field_map(non_plant["route_out_rows"])["Non-plant route"] == "out of Plant Design Workspace"
    assert non_plant["parsed_intent_rows"] == []


def test_r112_non_plant_input_does_not_enter_plant_workflow() -> None:
    routed = route_ai_intake_request(NON_PLANT_INPUT)
    payload = build_user_input_mock_preview_payload(NON_PLANT_INPUT)

    assert routed["scope_category"] == "non_plant_out_of_scope"
    assert payload["scope_category"] == "non_plant_out_of_scope"
    assert payload["workflow_route"] == "Route out of Plant Design Workspace; show conceptual context only."
    assert any(badge["value"] == "out of plant workflow" for badge in payload["status_badges"])


def test_r112_mixed_input_preserves_safe_and_blocked_outputs() -> None:
    routed = route_ai_intake_request(MIXED_INPUT)
    payload = build_user_input_mock_preview_payload(MIXED_INPUT)

    assert routed["scope_category"] == "mixed_scope_needs_routing"
    assert payload["scope_category"] == "mixed_scope_needs_routing"
    assert "company_handoff_draft" in payload["allowed_outputs"]
    assert "safe_conceptual_summary" in payload["allowed_outputs"]
    assert "wet_lab_protocol" in payload["blocked_outputs"]
    assert "final_construct_recommendation" in payload["blocked_outputs"]
    assert _output_values(payload["allowed_output_rows"]) == [
        "design intent",
        "plant design context",
        "evidence placeholders",
        "component slots",
        "construct draft slots",
        "review items",
        "report blocks",
        "company handoff draft",
        "safe conceptual summary",
    ]
    assert any(row["Review item"] == "blocked request fragment" for row in payload["review_gap_rows"])


def test_r112_presenter_and_workspace_consume_same_normalized_keys() -> None:
    parsed = parse_rice_albumin_like_intake(SUPPORTED_INPUT)
    presenter = build_rice_albumin_handoff_preview_payload()
    model = workspace.build_plant_design_workspace_shell_model()
    mounted = model["ai_handoff_preview"]

    assert set(STABLE_PREVIEW_CONTRACT_KEYS).issubset(presenter)
    assert set(STABLE_PREVIEW_CONTRACT_KEYS).issubset(mounted)
    assert presenter["scope_category"] == parsed["scope_decision"]["scope_category"]
    assert presenter["preview_status"] == "supported plant mock preview"
    assert presenter["persistent"] is False
    assert presenter["allowed_outputs"] == mounted["allowed_outputs"]
    assert presenter["blocked_outputs"] == mounted["blocked_outputs"]
    assert presenter["boundary_statements"] == mounted["boundary_statements"]
    assert presenter["parsed_intent_rows"] == mounted["parsed_intent_rows"]
    assert {row["Preview boundary"] for row in presenter["allowed_output_rows"]} == {
        ALLOWED_OUTPUT_BOUNDARY_DOCUMENTATION
    }


def test_r112_boundary_wording_stays_consistent_across_router_presenter_and_qa() -> None:
    routed = route_ai_intake_request(SUPPORTED_INPUT)
    presenter = build_rice_albumin_handoff_preview_payload()
    qa_note = (ROOT / "docs" / "qa" / "V2_7_R112_PLANT_AI_MOCK_PREVIEW_CONTRACT_HARDENING_QA.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join(
        [
            *routed["boundary_statements"],
            *presenter["boundary_statements"],
            qa_note,
        ]
    ).casefold()

    assert "documentation-only" in combined
    assert "manual review required" in combined
    assert "blocked; not generated by this read-only preview" in combined
    for label in HANDOFF_BOUNDARY_LABELS:
        assert label in combined


def test_r112_generated_contract_text_stays_non_operational_outside_blocked_labels() -> None:
    supported = build_user_input_mock_preview_payload(SUPPORTED_INPUT)
    presenter = build_rice_albumin_handoff_preview_payload()
    combined = _strip_user_request_and_blocked_labels([supported, presenter])

    for phrase in [
        "step-by-step",
        "incubate",
        "transformation efficiency",
        "ready for execution",
        "validated construct",
        "optimized pathway",
        "experiment-ready",
        "production-ready",
    ]:
        assert phrase not in combined
