# -*- coding: utf-8 -*-
from __future__ import annotations

from services.plant_ai_intake_safety_router import BLOCKED_OUTPUTS, route_ai_intake_request


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_OPERATIONAL_TEXT = (
    _term("step", "-by-", "step"),
    _term("incu", "bate"),
    _term("transformation ", "efficiency"),
    _term("yield ", "prediction"),
    _term("success ", "guaran", "tee"),
    _term("synthesis", "-ready"),
    _term("wet lab ", "ready"),
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


def _assert_no_forbidden_operational_text(payload: dict[str, object]) -> None:
    text = str(payload).casefold()
    for phrase in FORBIDDEN_OPERATIONAL_TEXT:
        assert phrase not in text


def test_rice_albumin_company_request_is_company_handoff_scope() -> None:
    request = "I want to express an albumin-like protein in rice seed and prepare a company-facing design evaluation package."

    routed = route_ai_intake_request(request)

    assert routed["scope_category"] == "company_handoff_request"
    assert routed["raw_user_request"] == request
    assert "company_handoff_draft" in routed["allowed_outputs"]
    assert "design_intent" in routed["allowed_outputs"]
    assert routed["manual_review_required"] is True


def test_wet_lab_protocol_request_is_blocked() -> None:
    routed = route_ai_intake_request("Give me a rice transformation protocol with cloning steps.")

    assert routed["scope_category"] in {"blocked_wet_lab_execution", "mixed_scope_needs_routing"}
    assert "wet_lab_protocol" in routed["blocked_outputs"]
    assert "transformation_steps" in routed["blocked_outputs"]
    assert routed["manual_review_required"] is True


def test_final_sequence_or_primer_request_is_blocked() -> None:
    routed = route_ai_intake_request("Design primers and a final sequence for rice seed expression.")

    assert routed["scope_category"] in {"blocked_final_sequence_or_primer", "mixed_scope_needs_routing"}
    assert "primer_design" in routed["blocked_outputs"]
    assert "synthesis_ready_sequence" in routed["blocked_outputs"]


def test_yeast_or_ecoli_design_workflow_is_non_plant_out_of_scope() -> None:
    yeast = route_ai_intake_request("Build a yeast design workflow for protein expression.")
    ecoli = route_ai_intake_request("Create an E. coli expression design workflow.")

    assert yeast["scope_category"] == "non_plant_out_of_scope"
    assert ecoli["scope_category"] == "non_plant_out_of_scope"
    assert yeast["allowed_outputs"] == ["safe_conceptual_summary"]
    assert ecoli["allowed_outputs"] == ["safe_conceptual_summary"]


def test_mixed_request_allows_safe_outputs_and_blocks_operational_outputs() -> None:
    routed = route_ai_intake_request(
        "Prepare a company handoff package for rice seed albumin-like expression and include cloning protocol steps."
    )

    assert routed["scope_category"] == "mixed_scope_needs_routing"
    assert "company_handoff_draft" in routed["allowed_outputs"]
    assert "review_items" in routed["allowed_outputs"]
    assert set(BLOCKED_OUTPUTS).issubset(set(routed["blocked_outputs"]))
    assert "wet_lab_protocol" in routed["blocked_outputs"]


def test_conceptual_comparison_is_safe_conceptual_explanation_only() -> None:
    routed = route_ai_intake_request("Compare rice seed expression context with leaf expression context conceptually.")

    assert routed["scope_category"] == "safe_conceptual_explanation"
    assert routed["allowed_outputs"] == ["safe_conceptual_summary"]
    assert routed["manual_review_required"] is True


def test_router_returns_plain_dict_and_list_structures() -> None:
    routed = route_ai_intake_request("Rice seed albumin-like company handoff review.")

    assert isinstance(routed, dict)
    _assert_plain_data(routed)


def test_boundary_statements_are_present() -> None:
    routed = route_ai_intake_request("Rice seed albumin-like company handoff review.")

    assert routed["boundary_statements"]
    text = " ".join(routed["boundary_statements"]).casefold()
    assert "documentation-only" in text
    assert "manual review" in text
    assert "blocked" in text


def test_outputs_do_not_contain_forbidden_operational_content() -> None:
    examples = [
        route_ai_intake_request("Rice seed albumin-like company handoff review."),
        route_ai_intake_request("Give me a rice transformation protocol."),
        route_ai_intake_request("Design primers for a rice seed target."),
        route_ai_intake_request("Create a yeast expression workflow."),
    ]

    for routed in examples:
        _assert_no_forbidden_operational_text(routed)
