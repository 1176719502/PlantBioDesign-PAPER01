# -*- coding: utf-8 -*-
from __future__ import annotations

from services.plant_ai_guided_domain_chain import build_rice_albumin_like_domain_chain
from services.plant_ai_intake_mock_parser import RICE_ALBUMIN_LIKE_REQUEST


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_CONTENT = (
    _term("final ", "sequence"),
    _term("primer ", "design"),
    _term("operational ", "protocol"),
    _term("final construct ", "recommendation"),
    _term("culture ", "conditions"),
    _term("transformation ", "parameters"),
    _term("success ", "claim"),
    _term("yield ", "claim"),
    _term("readiness ", "claim"),
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


def test_domain_chain_contains_required_top_level_sections() -> None:
    bundle = build_rice_albumin_like_domain_chain()

    assert list(bundle) == [
        "chain_version",
        "batch",
        "input_request",
        "scope_decision",
        "design_intent",
        "plant_context",
        "evidence_placeholders",
        "component_placeholders",
        "construct_draft",
        "construct_slots",
        "review_gap_items",
        "report_block_placeholders",
        "handoff_package_skeleton",
        "boundary_statements",
        "status",
    ]


def test_domain_chain_starts_from_fixed_raw_request() -> None:
    bundle = build_rice_albumin_like_domain_chain(RICE_ALBUMIN_LIKE_REQUEST)

    assert bundle["input_request"] == RICE_ALBUMIN_LIKE_REQUEST
    assert bundle["scope_decision"]["raw_user_request"] == RICE_ALBUMIN_LIKE_REQUEST
    assert bundle["scope_decision"]["scope_category"] == "company_handoff_request"


def test_domain_chain_builds_intent_and_plant_context() -> None:
    bundle = build_rice_albumin_like_domain_chain()

    assert bundle["design_intent"]["target_name"] == "albumin-like protein"
    assert bundle["design_intent"]["plant_host"] == "rice"
    assert bundle["design_intent"]["tissue_or_context"] == "seed"
    assert bundle["plant_context"]["plant_species"] == "rice"
    assert bundle["plant_context"]["tissue_or_organ"] == "seed"


def test_domain_chain_builds_evidence_components_construct_and_reports() -> None:
    bundle = build_rice_albumin_like_domain_chain()

    assert len(bundle["evidence_placeholders"]) == 3
    assert len(bundle["component_placeholders"]) == 3
    assert len(bundle["construct_slots"]) == 6
    assert bundle["construct_draft"]["slot_ids"] == [slot["slot_id"] for slot in bundle["construct_slots"]]
    assert len(bundle["report_block_placeholders"]) == 3
    assert bundle["handoff_package_skeleton"]["report_block_ids"] == [
        block["report_block_id"] for block in bundle["report_block_placeholders"]
    ]


def test_domain_chain_review_items_and_status_are_manual_review_framed() -> None:
    bundle = build_rice_albumin_like_domain_chain()

    assert bundle["review_gap_items"]
    assert all(item["manual_review_required"] is True for item in bundle["review_gap_items"])
    assert bundle["construct_draft"]["draft_status"] == "manual_review_required"
    assert bundle["handoff_package_skeleton"]["package_status"] == "manual_review_required"
    assert bundle["status"] == {
        "draft": True,
        "manual_review_required": True,
        "company_review_draft": True,
    }


def test_domain_chain_returns_plain_data_only() -> None:
    bundle = build_rice_albumin_like_domain_chain()

    _assert_plain_data(bundle)


def test_domain_chain_boundaries_are_present_and_sanitized() -> None:
    bundle = build_rice_albumin_like_domain_chain()
    text = " ".join(bundle["boundary_statements"]).casefold()

    assert "documentation-only" in text
    assert "manual review" in text
    assert "completed sequence content" in text
    assert _term("final ", "sequence") not in text


def test_domain_chain_does_not_output_blocked_operational_content() -> None:
    bundle = build_rice_albumin_like_domain_chain()
    text = str(bundle).casefold()

    for phrase in FORBIDDEN_CONTENT:
        assert phrase not in text
    assert all(slot["selected_component_id"] == "" for slot in bundle["construct_slots"])
    assert "final_construct_recommendation" in bundle["scope_decision"]["blocked_outputs"]
    assert "primer_design" in bundle["scope_decision"]["blocked_outputs"]
