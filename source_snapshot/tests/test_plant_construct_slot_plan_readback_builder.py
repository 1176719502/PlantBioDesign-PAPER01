from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_construct_slot_plan_readback_builder import (
    SLOT_PLAN_STATUS_BLOCKED_MANUAL_REVIEW,
    SLOT_PLAN_STATUS_EMPTY_READBACK,
    SLOT_PLAN_STATUS_READY_FOR_MANUAL_REVIEW,
    build_plant_construct_slot_plan_readback,
)


def _term(*parts: str) -> str:
    return "".join(parts)


def _assert_plain_dict_list(value: Any) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            _assert_plain_dict_list(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_dict_list(nested)
    else:
        assert value is None or isinstance(value, (str, int, bool))


def _copy_blob(value: Any) -> str:
    values: list[str] = []

    def collect(nested: Any) -> None:
        if isinstance(nested, dict):
            for item in nested.values():
                collect(item)
        elif isinstance(nested, list):
            for item in nested:
                collect(item)
        else:
            values.append(str(nested))

    collect(value)
    return "\n".join(values).casefold()


def _slot_by_id(readback: dict[str, Any], slot_id: str) -> dict[str, Any]:
    return {row["slot_id"]: row for row in readback["slot_rows"]}[slot_id]


def test_canonical_route_template_builds_plain_slot_plan_readback() -> None:
    readback = build_plant_construct_slot_plan_readback(
        {"route_template_id": "plant_expression_construct_review"}
    )

    assert readback["slot_plan_status"] == SLOT_PLAN_STATUS_READY_FOR_MANUAL_REVIEW
    assert readback["route_template_id"] == "plant_expression_vector"
    assert readback["canonical_route_template_id"] == "plant_expression_construct_review"
    assert readback["compatibility"]["alias_status"] == "canonical_alias_to_stored_legacy_route_id"
    assert readback["manual_review_state"] == "manual_review_required"
    assert readback["blocked_output_categories"]
    assert len(readback["slot_rows"]) == 10

    promoter = _slot_by_id(readback, "promoter_slot")
    assert promoter["module_id"] == "plant_expression_cassette"
    assert promoter["module_label"] == "Plant Expression Cassette"
    assert promoter["slot_type"] == "component_context_slot"
    assert promoter["required_or_optional"] == "required"
    assert promoter["expected_evidence_type"] == "slot_source_note"
    assert promoter["current_evidence_status"] == "missing_manual_review_required"
    assert promoter["manual_review_state"] == "manual_review_required"
    assert promoter["route_template_id"] == readback["route_template_id"]
    assert promoter["canonical_route_template_id"] == readback["canonical_route_template_id"]
    _assert_plain_dict_list(readback)


def test_legacy_route_type_alias_is_metadata_only() -> None:
    readback = build_plant_construct_slot_plan_readback(
        {"route_id": "plant_expression_vector"}
    )
    blob = _copy_blob(readback)

    assert readback["compatibility"]["is_alias"] is True
    assert readback["compatibility"]["alias_status"] == "legacy_route_type_alias_to_default_stored_route_id"
    assert readback["slot_plan_status"] == SLOT_PLAN_STATUS_READY_FOR_MANUAL_REVIEW
    assert "compatibility aliases are metadata only" in blob
    assert "not completed construct records" in blob
    assert "not a biological recommendation" in blob


def test_fixture_like_route_template_and_module_summary_are_supported() -> None:
    readback = build_plant_construct_slot_plan_readback(
        {
            "route_id": "generic_plant_expression_vector_route",
            "required_slots": ["custom_source_reference"],
            "optional_slots": ["custom_context_note"],
        },
        [
            {
                "module_id": "fixture_module",
                "module_label": "Fixture Module",
                "required_slots": ["custom_source_reference", "custom_context_note"],
                "evidence_fields": ["fixture_source_reference"],
                "gap_rules": ["flag fixture source gap"],
                "boundary_notes": ["Documentation-only fixture module for manual review."],
            }
        ],
    )

    required = _slot_by_id(readback, "custom_source_reference")
    optional = _slot_by_id(readback, "custom_context_note")

    assert required["module_id"] == "fixture_module"
    assert required["module_label"] == "Fixture Module"
    assert required["slot_type"] == "evidence_reference_slot"
    assert required["required_or_optional"] == "required"
    assert required["expected_evidence_type"] == "fixture_source_reference"
    assert required["gap_reason"] == "flag fixture source gap"
    assert optional["required_or_optional"] == "optional"


def test_missing_module_rows_fail_safe_to_blocked_manual_review_status() -> None:
    readback = build_plant_construct_slot_plan_readback(
        {
            "route_id": "generic_plant_expression_vector_route",
            "required_module_ids": ["missing_module_card"],
            "required_slots": ["unresolved_construct_slot"],
            "optional_slots": [],
            "blocked_outputs": ["biological_recommendation"],
        }
    )

    row = _slot_by_id(readback, "unresolved_construct_slot")
    assert readback["slot_plan_status"] == SLOT_PLAN_STATUS_BLOCKED_MANUAL_REVIEW
    assert readback["current_evidence_status"] == "blocked_missing_module_card"
    assert row["module_id"] == ""
    assert row["module_label"] == "Missing module card"
    assert row["manual_review_state"] == "module_missing_manual_review_required"
    assert row["blocked_output_categories"]


def test_unknown_route_fails_safe_to_empty_blocked_readback() -> None:
    readback = build_plant_construct_slot_plan_readback({"route_id": "unknown_route"})

    assert readback["slot_plan_status"] == SLOT_PLAN_STATUS_BLOCKED_MANUAL_REVIEW
    assert readback["route_template_id"] == "unknown_route"
    assert readback["compatibility"]["alias_status"] == "unknown_route_id_blocked"
    assert readback["slot_rows"] == []
    assert readback["current_evidence_status"] == "blocked_no_slot_rows"
    assert readback["manual_review_state"] == "manual_review_required"
    _assert_plain_dict_list(readback)


def test_empty_input_fails_safe_without_default_route_fallback() -> None:
    readback = build_plant_construct_slot_plan_readback()

    assert readback["slot_plan_status"] == SLOT_PLAN_STATUS_EMPTY_READBACK
    assert readback["route_template_id"] == ""
    assert readback["canonical_route_template_id"] == ""
    assert readback["slot_rows"] == []
    assert readback["gap_reason"] == "empty route template input"


def test_builder_does_not_import_runtime_or_generation_surfaces() -> None:
    source = Path("services/plant_construct_slot_plan_readback_builder.py").read_text(
        encoding="utf-8"
    ).casefold()
    blocked_markers = [
        "streamlit",
        "sqlite",
        "project_import",
        "project_export",
        "package_export",
        "expression_wizard",
        "openai",
        "requests.",
        "httpx",
        "agent_runtime",
        "generate_route",
        "generated_route",
        "generate_sequence",
        "recommend_component",
        "recommend_route",
        "select_promoter",
        "select_vector",
        "codon_optimization",
        "score_feasibility",
    ]

    for marker in blocked_markers:
        assert marker not in source


def test_no_positive_claim_copy_is_introduced_outside_blocked_categories() -> None:
    readback = build_plant_construct_slot_plan_readback(
        {"route_template_id": "rice_expression_vector_context_route"}
    )
    blob = _copy_blob(readback)
    for blocked_category in readback["blocked_output_categories"]:
        blob = blob.replace(str(blocked_category).casefold(), "")

    disallowed_positive_phrases = [
        "final design",
        "optimized design",
        "validated design",
        _term("wet", "-lab ", "ready design"),
        _term("ready ", "for execution"),
        _term("experiment", "-ready"),
        _term("production", "-ready"),
        _term("yield ", "prediction"),
    ]
    for phrase in disallowed_positive_phrases:
        assert phrase not in blob
