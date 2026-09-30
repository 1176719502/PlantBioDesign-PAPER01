from __future__ import annotations

from pathlib import Path

from services import plant_review_module_card_schema as schema
from services.plant_review_module_card_schema import (
    BLOCKED_OUTPUT_CATEGORIES,
    CANONICAL_CARD_FIELDS,
    CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
    REQUIRED_BLOCKED_OUTPUT_CATEGORIES,
    get_plant_review_module_card_schema,
    get_supported_plant_route_types,
    normalize_plant_review_module_card,
    validate_plant_review_module_card,
)


def _valid_card() -> dict[str, object]:
    return {
        "module_id": " plant_expression_vector_intake ",
        "display_name": " Plant Expression Vector Intake ",
        "route_type": "plant_expression_vector",
        "route_scope": " plant expression vector documentation ",
        "trigger_terms": [" expression ", "expression", "construct"],
        "required_inputs": ("plant context note", "source reference note"),
        "required_slots": {"construct_goal", "plant_context"},
        "allowed_outputs": ["documentation_readback", "manual_review_status"],
        "blocked_outputs": BLOCKED_OUTPUT_CATEGORIES,
        "evidence_fields": ["source reference", ""],
        "gap_rules": "preserve unresolved review gaps",
        "manual_review_rules": ["manual review required before downstream use"],
        "package_section": " plant_expression_vector_review ",
        "boundary_notes": [
            "Documentation-only Plant Review Module Card for manual review and traceability."
        ],
        "unknown_runtime_field": "must not leak",
    }


def _assert_plain_json_like(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for nested in value.values():
            _assert_plain_json_like(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_json_like(nested)
    else:
        assert value is None or isinstance(value, (str, int, bool))


def test_canonical_schema_fields_are_present() -> None:
    schema_contract = get_plant_review_module_card_schema()

    assert schema_contract["schema_name"] == "plant_review_module_card"
    assert schema_contract["schema_version"] == "v2.7-r66"
    assert schema_contract["canonical_fields"] == list(CANONICAL_CARD_FIELDS)
    assert set(CANONICAL_CARD_FIELDS) == {
        "module_id",
        "display_name",
        "route_type",
        "route_scope",
        "trigger_terms",
        "required_inputs",
        "required_slots",
        "allowed_outputs",
        "blocked_outputs",
        "evidence_fields",
        "gap_rules",
        "manual_review_rules",
        "package_section",
        "boundary_notes",
    }
    assert len(schema_contract["field_descriptions"]) == len(CANONICAL_CARD_FIELDS)
    assert set(schema_contract["blocked_output_categories"]) >= set(BLOCKED_OUTPUT_CATEGORIES)
    assert schema_contract["required_blocked_output_categories"] == list(
        REQUIRED_BLOCKED_OUTPUT_CATEGORIES
    )
    _assert_plain_json_like(schema_contract)


def test_supported_route_types_mark_expression_vector_active_only() -> None:
    route_metadata = get_supported_plant_route_types()
    route_types = route_metadata["route_types"]
    by_type = {item["route_type"]: item for item in route_types}

    assert route_metadata["current_active_route_type"] == "plant_expression_vector"
    assert CURRENT_ACTIVE_PLANT_ROUTE_TYPE == "plant_expression_vector"
    assert set(by_type) == {"plant_expression_vector"}
    assert by_type["plant_expression_vector"]["active"] is True
    assert by_type["plant_expression_vector"]["status"] == "current_active"
    _assert_plain_json_like(route_metadata)


def test_normalization_returns_plain_dict_list_values_and_ignores_unknown_fields() -> None:
    normalized = normalize_plant_review_module_card(_valid_card())

    assert isinstance(normalized, dict)
    for field in CANONICAL_CARD_FIELDS:
        assert field in normalized
    assert normalized["module_id"] == "plant_expression_vector_intake"
    assert normalized["display_name"] == "Plant Expression Vector Intake"
    assert normalized["route_scope"] == "plant expression vector documentation"
    assert normalized["trigger_terms"] == ["expression", "construct"]
    assert normalized["required_slots"] == ["construct_goal", "plant_context"]
    assert normalized["gap_rules"] == ["preserve unresolved review gaps"]
    assert "unknown_runtime_field" not in normalized
    _assert_plain_json_like(normalized)


def test_normalization_fills_missing_list_fields_with_empty_lists() -> None:
    card = {
        "module_id": "plant_expression_vector_minimal",
        "display_name": "Plant Expression Vector Minimal",
        "route_type": "plant_expression_vector",
        "route_scope": "plant expression vector documentation",
        "package_section": "plant_expression_vector_review",
    }

    normalized = normalize_plant_review_module_card(card)

    for field in (
        "trigger_terms",
        "required_inputs",
        "required_slots",
        "allowed_outputs",
        "blocked_outputs",
        "evidence_fields",
        "gap_rules",
        "manual_review_rules",
        "boundary_notes",
    ):
        assert normalized[field] == []


def test_missing_required_fields_fail_validation_without_raise() -> None:
    result = validate_plant_review_module_card({})

    assert result["ok"] is False
    assert "module_id is required" in result["errors"]
    assert "display_name is required" in result["errors"]
    assert "route_type is required" in result["errors"]
    assert "route_scope is required" in result["errors"]
    assert "package_section is required" in result["errors"]
    assert isinstance(result["normalized_card"], dict)


def test_unsupported_route_type_fails_validation() -> None:
    card = _valid_card()
    card["route_type"] = "microbial_fermentation"

    result = validate_plant_review_module_card(card)

    assert result["ok"] is False
    assert result["errors"] == ["route_type is not supported: microbial_fermentation"]


def test_unsafe_or_blocked_allowed_output_categories_fail_validation() -> None:
    card = _valid_card()
    card["allowed_outputs"] = ["documentation_readback", "primer_design"]

    result = validate_plant_review_module_card(card)

    assert result["ok"] is False
    assert any("allowed_outputs contains blocked or unsafe output categories" in error for error in result["errors"])


def test_valid_minimal_card_passes_validation() -> None:
    result = validate_plant_review_module_card(_valid_card())

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["normalized_card"]["module_id"] == "plant_expression_vector_intake"
    assert result["normalized_card"]["blocked_outputs"] == list(BLOCKED_OUTPUT_CATEGORIES)


def test_required_safety_blocked_outputs_must_be_present() -> None:
    card = _valid_card()
    card["blocked_outputs"] = ["protocol", "optimized_sequence"]

    result = validate_plant_review_module_card(card)

    assert result["ok"] is False
    assert any(
        "blocked_outputs missing required safety categories" in error
        for error in result["errors"]
    )


def test_blocked_outputs_include_required_r66_claim_families() -> None:
    assert set(BLOCKED_OUTPUT_CATEGORIES) >= {
        "protocol",
        "optimized_sequence",
        "wet_lab_readiness",
        "experimental_validation",
        "yield_prediction",
        "build_ready_claim",
    }


def test_valid_card_requires_manual_review_framing() -> None:
    card = _valid_card()
    card["boundary_notes"] = ["Documentation-only Plant Review Module Card for traceability."]

    result = validate_plant_review_module_card(card)

    assert result["ok"] is False
    assert "boundary_notes must include manual-review framing" in result["errors"]


def test_valid_card_requires_documentation_only_framing() -> None:
    card = _valid_card()
    card["boundary_notes"] = ["Manual review is required for this card."]

    result = validate_plant_review_module_card(card)

    assert result["ok"] is False
    assert "boundary_notes must include documentation-only framing" in result["errors"]


def test_manual_review_rules_and_blocked_outputs_are_required() -> None:
    missing_manual = _valid_card()
    missing_manual["manual_review_rules"] = []
    missing_blocked = _valid_card()
    missing_blocked["blocked_outputs"] = []

    manual_result = validate_plant_review_module_card(missing_manual)
    blocked_result = validate_plant_review_module_card(missing_blocked)

    assert manual_result["ok"] is False
    assert "manual_review_rules must be present and non-empty" in manual_result["errors"]
    assert blocked_result["ok"] is False
    assert "blocked_outputs must be present and non-empty" in blocked_result["errors"]


def test_module_id_must_be_safe_slug_like_identifier() -> None:
    card = _valid_card()
    card["module_id"] = "Plant Construct Intake"

    result = validate_plant_review_module_card(card)

    assert result["ok"] is False
    assert "module_id must be a safe slug-like identifier" in result["errors"]


def test_output_remains_plain_json_like_data_not_ui_or_database_objects() -> None:
    validation = validate_plant_review_module_card(_valid_card())

    _assert_plain_json_like(validation)
    assert validation["normalized_card"]["module_id"] == "plant_expression_vector_intake"


def test_no_ai_api_llm_agent_cloud_runtime_hooks_are_introduced() -> None:
    source = Path(schema.__file__).read_text(encoding="utf-8").casefold()
    blocked_runtime_markers = [
        "openai",
        "anthropic",
        "langchain",
        "llm_runtime",
        "agent_runtime",
        "cloud_runtime",
        "requests.",
        "httpx",
        "streamlit",
        "sqlite",
        "sqlalchemy",
    ]

    for marker in blocked_runtime_markers:
        assert marker not in source


def test_no_import_export_package_export_behavior_is_introduced() -> None:
    source = Path(schema.__file__).read_text(encoding="utf-8").casefold()
    blocked_behavior_markers = [
        "project_import",
        "project_export",
        "package_export",
        "export_package",
        "import_package",
        "write_package",
        "read_database",
        "create_engine",
    ]

    for marker in blocked_behavior_markers:
        assert marker not in source
