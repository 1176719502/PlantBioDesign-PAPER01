# -*- coding: utf-8 -*-
from __future__ import annotations

from services.plant_ai_intake_mock_parser import (
    MISSING_FIELDS,
    RICE_ALBUMIN_LIKE_REQUEST,
    parse_rice_albumin_like_intake,
)


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_CONTENT = (
    _term("final construct ", "recommendation"),
    _term("final ", "sequence"),
    _term("primer ", "design"),
    _term("protocol ", "steps"),
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


def test_parser_extracts_fixed_rice_albumin_like_fields() -> None:
    parsed = parse_rice_albumin_like_intake(RICE_ALBUMIN_LIKE_REQUEST)

    assert parsed["parsed_fields"] == {
        "plant_host": "rice",
        "tissue_or_context": "seed",
        "target": "albumin-like protein",
        "handoff_goal": "company-facing design evaluation package",
    }
    assert parsed["design_intent"]["plant_host"] == "rice"
    assert parsed["design_intent"]["target_name"] == "albumin-like protein"
    assert parsed["design_intent"]["handoff_goal"] == "company-facing design evaluation package"
    assert parsed["plant_design_context"]["tissue_or_organ"] == "seed"


def test_parser_uses_r99_scope_decision_for_company_handoff() -> None:
    parsed = parse_rice_albumin_like_intake()

    assert parsed["scope_decision"]["scope_category"] == "company_handoff_request"
    assert parsed["design_intent"]["scope_status"] == "company_handoff_request"
    assert "company_handoff_draft" in parsed["scope_decision"]["allowed_outputs"]


def test_parser_records_required_missing_fields() -> None:
    parsed = parse_rice_albumin_like_intake()

    assert parsed["missing_fields"] == list(MISSING_FIELDS)
    for expected in [
        "CDS/source/version",
        "exact tissue/development context if needed",
        "subcellular localization",
        "evidence references",
        "component provenance",
        "vector/backbone context",
    ]:
        assert expected in parsed["design_intent"]["missing_fields"]


def test_parser_builds_construct_slot_scaffold_placeholders() -> None:
    parsed = parse_rice_albumin_like_intake()
    slots = parsed["construct_slot_scaffold"]

    assert [slot["slot_type"] for slot in slots] == [
        "coding_sequence_source",
        "plant_host_context",
        "subcellular_localization",
        "evidence_references",
        "component_provenance",
        "vector_backbone_context",
    ]
    assert all(slot["selected_component_id"] == "" for slot in slots)
    assert all(slot["manual_review_required"] is True for slot in slots)


def test_parser_marks_manual_review_status_and_boundaries() -> None:
    parsed = parse_rice_albumin_like_intake()

    assert parsed["review_status"] == {
        "status": "manual_review_required",
        "manual_review_required": True,
        "ai_output_status": "needs_manual_review",
    }
    assert parsed["boundary_statements"]
    assert "documentation-only" in " ".join(parsed["boundary_statements"]).casefold()


def test_parser_returns_plain_dict_and_list_structures() -> None:
    parsed = parse_rice_albumin_like_intake()

    assert isinstance(parsed, dict)
    _assert_plain_data(parsed)


def test_parser_preserves_raw_user_request() -> None:
    parsed = parse_rice_albumin_like_intake(RICE_ALBUMIN_LIKE_REQUEST)

    assert parsed["raw_user_request"] == RICE_ALBUMIN_LIKE_REQUEST
    assert parsed["scope_decision"]["raw_user_request"] == RICE_ALBUMIN_LIKE_REQUEST


def test_parser_does_not_output_blocked_operational_content() -> None:
    parsed = parse_rice_albumin_like_intake()
    text = str(parsed).casefold()

    for phrase in FORBIDDEN_CONTENT:
        assert phrase not in text
    assert "final_construct_recommendation" in parsed["scope_decision"]["blocked_outputs"]
    assert "primer_design" in parsed["scope_decision"]["blocked_outputs"]
