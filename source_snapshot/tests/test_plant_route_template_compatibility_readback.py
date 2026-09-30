from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_route_template_compatibility_readback import (
    build_known_plant_route_template_compatibility_readbacks,
    build_plant_route_template_compatibility_readback,
)
from services.plant_review_module_card_schema import BLOCKED_OUTPUT_CATEGORIES


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


def _readback_copy_blob(readback: dict[str, Any]) -> str:
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)
        else:
            values.append(str(value))

    collect(readback)
    return "\n".join(values).casefold()


def test_canonical_route_id_readback_resolves_to_stored_legacy_default() -> None:
    readback = build_plant_route_template_compatibility_readback(
        "plant_expression_construct_review"
    )

    assert readback["requested_route_id"] == "plant_expression_construct_review"
    assert readback["resolved_canonical_route_id"] == "plant_expression_construct_review"
    assert readback["resolved_legacy_route_id"] == "plant_expression_vector"
    assert readback["alias_status"] == "canonical_alias_to_stored_legacy_route_id"
    assert readback["route_template_found"] is True
    assert readback["route_template_status"] == "resolved_readback_only"
    assert readback["module_card_resolution"]["status"] == "all_resolved"
    _assert_plain_dict_list(readback)


def test_legacy_default_route_id_readback_resolves_without_aliasing() -> None:
    readback = build_plant_route_template_compatibility_readback(
        " generic_plant_expression_vector_route "
    )

    assert readback["requested_route_id"] == "generic_plant_expression_vector_route"
    assert readback["resolved_canonical_route_id"] == "plant_expression_construct_review"
    assert readback["resolved_legacy_route_id"] == "plant_expression_vector"
    assert readback["alias_status"] == "route_id_alias"
    assert readback["is_alias"] is True
    assert readback["plant_context"] == "generic_plant_expression_vector"
    assert readback["module_card_resolution"]["resolved_required_count"] == 8


def test_context_specific_legacy_route_id_preserves_stored_route_id() -> None:
    readback = build_plant_route_template_compatibility_readback(
        "rice_expression_vector_context_route"
    )

    assert readback["resolved_canonical_route_id"] == "plant_expression_construct_review"
    assert readback["resolved_legacy_route_id"] == "rice_seed_protein_expression"
    assert readback["alias_status"] == "route_id_alias"
    assert readback["plant_context"] == "rice_expression_vector"
    assert readback["module_card_resolution"]["status"] == "all_resolved"
    assert readback["module_card_resolution"]["resolved_required_count"] == 10


def test_legacy_route_type_id_maps_to_default_template_as_compatibility_metadata() -> None:
    readback = build_plant_route_template_compatibility_readback("plant_expression_vector")

    assert readback["requested_route_id"] == "plant_expression_vector"
    assert readback["resolved_canonical_route_id"] == "plant_expression_construct_review"
    assert readback["resolved_legacy_route_id"] == "plant_expression_vector"
    assert readback["alias_status"] == "legacy_route_type_alias_to_default_stored_route_id"
    assert readback["is_alias"] is True
    assert readback["route_template_found"] is True


def test_unknown_route_id_fails_safe_to_empty_blocked_manual_review_status() -> None:
    readback = build_plant_route_template_compatibility_readback("unknown_route")

    assert readback["requested_route_id"] == "unknown_route"
    assert readback["resolved_canonical_route_id"] == ""
    assert readback["resolved_legacy_route_id"] == ""
    assert readback["alias_status"] == "unknown_route_id_blocked"
    assert readback["route_template_found"] is False
    assert readback["route_template_status"] == "blocked_manual_review_required"
    assert readback["route_name"] == ""
    assert readback["module_card_resolution"] == {
        "status": "blocked_unknown_route_id",
        "required_module_cards": [],
        "optional_module_cards": [],
        "missing_module_cards": [],
        "resolved_required_count": 0,
        "resolved_optional_count": 0,
    }
    assert readback["blocked_output_categories"]
    assert "manual review" in _readback_copy_blob(readback)
    _assert_plain_dict_list(readback)


def test_empty_route_id_fails_safe_without_default_fallback() -> None:
    readback = build_plant_route_template_compatibility_readback("")

    assert readback["alias_status"] == "empty_route_id_blocked"
    assert readback["route_template_found"] is False
    assert readback["resolved_legacy_route_id"] == ""
    assert readback["module_card_resolution"]["status"] == "blocked_unknown_route_id"


def test_readback_preserves_documentation_only_manual_review_and_blocked_outputs() -> None:
    readback = build_plant_route_template_compatibility_readback(
        "plant_expression_construct_review"
    )
    copy_blob = _readback_copy_blob(readback)

    assert "documentation-only" in copy_blob
    assert "manual review" in copy_blob
    assert "not a biological recommendation" in copy_blob
    assert readback["blocked_output_categories"] == list(BLOCKED_OUTPUT_CATEGORIES)


def test_known_route_template_compatibility_readbacks_are_plain_list() -> None:
    readbacks = build_known_plant_route_template_compatibility_readbacks()

    assert [item["requested_route_id"] for item in readbacks] == [
        "plant_expression_construct_review",
        "generic_plant_expression_vector_route",
        "plant_expression_vector",
    ]
    assert all(item["route_template_found"] is True for item in readbacks)
    _assert_plain_dict_list(readbacks)


def test_helper_does_not_introduce_generation_recommendation_or_runtime_hooks() -> None:
    source = Path("services/plant_route_template_compatibility_readback.py").read_text(
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
    readback = build_plant_route_template_compatibility_readback(
        "rice_expression_vector_context_route"
    )
    copy_blob = _readback_copy_blob(readback)
    for blocked_category in readback["blocked_output_categories"]:
        copy_blob = copy_blob.replace(str(blocked_category).casefold(), "")

    disallowed_positive_phrases = [
        "wet-lab ready",
        "guaranteed expression",
        "high-yield",
    ]
    for phrase in disallowed_positive_phrases:
        assert phrase not in copy_blob
