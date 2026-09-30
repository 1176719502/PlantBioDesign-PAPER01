from __future__ import annotations

from pathlib import Path
from typing import Any

from services import plant_expression_route_template_registry as registry
from services.plant_expression_route_template_registry import (
    DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID,
    PLANT_EXPRESSION_ROUTE_TEMPLATE_TYPE,
    ROUTE_TEMPLATE_FIELDS,
    get_all_plant_expression_route_templates,
    get_default_plant_expression_route_template,
    get_plant_expression_route_template_by_id,
    get_plant_expression_route_template_registry_summary,
    get_plant_expression_route_templates_by_host_context,
    get_plant_expression_route_templates_by_package_section,
    get_plant_expression_route_templates_by_required_slot,
    get_plant_expression_route_templates_by_route_type,
    get_plant_expression_route_templates_by_trigger_term,
    normalize_plant_expression_route_template,
    validate_plant_expression_route_template,
    validate_plant_expression_route_template_registry,
)
from services.plant_review_module_card_registry import get_plant_review_module_card_by_id
from services.plant_review_module_card_schema import (
    BLOCKED_OUTPUT_CATEGORIES,
    CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
    REQUIRED_BLOCKED_OUTPUT_CATEGORIES,
)


EXPECTED_ROUTE_IDS = [
    "plant_expression_vector",
    "rice_seed_protein_expression",
    "plant_transient_expression_review",
    "stable_plant_expression_review",
    "plant_secreted_protein_expression",
    "plant_localization_tagged_expression",
    "plant_reporter_expression_review",
]

NON_PLANT_MARKERS = ("bacterial", "bacteria", "yeast", "mammalian", "microbial")


def _assert_plain_json_like(value: Any) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            _assert_plain_json_like(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_json_like(nested)
    else:
        assert isinstance(value, (str, bool))


def _template_text_without_blocked_outputs() -> str:
    values: list[str] = []
    for template in get_all_plant_expression_route_templates():
        for field, value in template.items():
            if field == "blocked_outputs":
                continue
            if isinstance(value, list):
                values.extend(str(item) for item in value)
            else:
                values.append(str(value))
    return "\n".join(values).casefold()


def test_registry_returns_deterministic_r67_route_template_order() -> None:
    first = get_all_plant_expression_route_templates()
    second = get_all_plant_expression_route_templates()

    assert first == second
    assert [template["route_id"] for template in first] == EXPECTED_ROUTE_IDS
    _assert_plain_json_like(first)


def test_route_templates_have_r67_shape_and_are_plant_only() -> None:
    for template in get_all_plant_expression_route_templates():
        assert list(template) == list(ROUTE_TEMPLATE_FIELDS)
        assert template["route_type"] == PLANT_EXPRESSION_ROUTE_TEMPLATE_TYPE
        assert template["route_type"] == CURRENT_ACTIVE_PLANT_ROUTE_TYPE
        assert template["required_module_cards"] == template["required_module_ids"]
        assert template["optional_module_cards"] == template["optional_module_ids"]
        route_blob = " ".join(
            [
                template["route_id"],
                template["route_type"],
                template["plant_context"],
                *template["supported_host_contexts"],
            ]
        ).casefold()
        for marker in NON_PLANT_MARKERS:
            assert marker not in route_blob


def test_lookup_by_route_id_and_aliases_returns_plain_templates() -> None:
    template = get_plant_expression_route_template_by_id(" rice_seed_protein_expression ")
    legacy_template = get_plant_expression_route_template_by_id("rice_expression_vector_context_route")

    assert template["route_id"] == "rice_seed_protein_expression"
    assert template["display_name"] == "Rice Seed Protein Expression"
    assert legacy_template == template
    assert get_plant_expression_route_template_by_id("missing_route_id") == {}
    assert get_plant_expression_route_template_by_id("") == {}
    _assert_plain_json_like(template)


def test_default_route_uses_expression_vector_first_template() -> None:
    default_template = get_default_plant_expression_route_template()

    assert DEFAULT_PLANT_EXPRESSION_ROUTE_TEMPLATE_ID == "plant_expression_vector"
    assert default_template["route_id"] == "plant_expression_vector"
    assert default_template["required_module_cards"][0] == "plant_target_intake"
    assert "plant_expression_cassette" in default_template["required_module_cards"]


def test_lookup_by_route_type_returns_all_expression_vector_templates() -> None:
    templates = get_plant_expression_route_templates_by_route_type(" plant_expression_vector ")

    assert [template["route_id"] for template in templates] == EXPECTED_ROUTE_IDS
    assert get_plant_expression_route_templates_by_route_type("bacterial_expression") == []
    assert get_plant_expression_route_templates_by_route_type("") == []


def test_trigger_matching_is_case_insensitive_and_deterministic() -> None:
    rice = get_plant_expression_route_templates_by_trigger_term("ORYZA SATIVA")
    reporter = get_plant_expression_route_templates_by_trigger_term("luciferase reporter")

    assert [template["route_id"] for template in rice] == ["rice_seed_protein_expression"]
    assert [template["route_id"] for template in reporter] == ["plant_reporter_expression_review"]
    assert get_plant_expression_route_templates_by_trigger_term("e coli expression") == []
    assert get_plant_expression_route_templates_by_trigger_term("") == []


def test_host_context_matching_is_plant_only_and_returns_safe_empty_lists() -> None:
    rice = get_plant_expression_route_templates_by_host_context("rice seed")
    transient = get_plant_expression_route_templates_by_host_context("N. benthamiana")

    assert [template["route_id"] for template in rice] == [
        "rice_seed_protein_expression",
        "plant_secreted_protein_expression",
    ]
    assert [template["route_id"] for template in transient] == ["plant_transient_expression_review"]
    assert get_plant_expression_route_templates_by_host_context("mammalian cell") == []
    assert get_plant_expression_route_templates_by_host_context("") == []


def test_required_slot_lookup_returns_templates_that_need_the_slot() -> None:
    signal_templates = get_plant_expression_route_templates_by_required_slot("signal_peptide_slot")
    reporter_templates = get_plant_expression_route_templates_by_required_slot("reporter_slot")

    assert [template["route_id"] for template in signal_templates] == [
        "plant_secreted_protein_expression"
    ]
    assert [template["route_id"] for template in reporter_templates] == [
        "plant_reporter_expression_review"
    ]
    assert get_plant_expression_route_templates_by_required_slot("unknown_slot") == []
    assert get_plant_expression_route_templates_by_required_slot("") == []


def test_package_section_lookup_returns_deterministic_route_templates() -> None:
    promoter_templates = get_plant_expression_route_templates_by_package_section(
        "promoter_leader_review"
    )

    assert [template["route_id"] for template in promoter_templates] == [
        "rice_seed_protein_expression",
        "stable_plant_expression_review",
    ]
    assert get_plant_expression_route_templates_by_package_section("unknown_section") == []
    assert get_plant_expression_route_templates_by_package_section("") == []


def test_required_module_cards_resolve_through_r66_registry() -> None:
    for template in get_all_plant_expression_route_templates():
        assert template["required_module_cards"]
        for module_id in template["required_module_cards"]:
            card = get_plant_review_module_card_by_id(module_id)
            assert card is not None
            assert card["route_type"] == CURRENT_ACTIVE_PLANT_ROUTE_TYPE


def test_optional_module_cards_resolve_through_r66_registry() -> None:
    for template in get_all_plant_expression_route_templates():
        for module_id in template["optional_module_cards"]:
            assert get_plant_review_module_card_by_id(module_id) is not None


def test_blocked_outputs_include_required_r66_route_safety_categories() -> None:
    required_categories = set(REQUIRED_BLOCKED_OUTPUT_CATEGORIES)
    for template in get_all_plant_expression_route_templates():
        assert template["blocked_outputs"] == list(BLOCKED_OUTPUT_CATEGORIES)
        assert set(template["blocked_outputs"]) >= required_categories


def test_template_validation_reports_missing_cards_and_blocked_categories() -> None:
    template = get_default_plant_expression_route_template()
    missing_card = dict(template)
    missing_card["required_module_cards"] = ["missing_module_card"]
    missing_card["required_module_ids"] = ["missing_module_card"]
    missing_blocked = dict(template)
    missing_blocked["blocked_outputs"] = ["protocol"]

    missing_card_result = validate_plant_expression_route_template(missing_card)
    missing_blocked_result = validate_plant_expression_route_template(missing_blocked)

    assert missing_card_result["ok"] is False
    assert any("required_module_cards missing from R66 registry" in error for error in missing_card_result["errors"])
    assert missing_blocked_result["ok"] is False
    assert any("blocked_outputs missing required route safety categories" in error for error in missing_blocked_result["errors"])


def test_registry_validation_result_is_plain_and_all_templates_pass() -> None:
    result = validate_plant_expression_route_template_registry()

    assert result["ok"] is True
    assert result["route_count"] == "7"
    assert result["errors"] == []
    assert [item["route_id"] for item in result["template_results"]] == EXPECTED_ROUTE_IDS
    assert all(item["ok"] is True for item in result["template_results"])
    _assert_plain_json_like(result)


def test_normalizer_returns_plain_values_and_compatibility_aliases() -> None:
    normalized = normalize_plant_expression_route_template(
        {
            "route_id": " custom_route ",
            "route_type": "plant_expression_vector",
            "route_name": " Custom Route ",
            "required_module_ids": ("plant_target_intake",),
            "optional_module_ids": ("gap_queue",),
            "required_slots": {"target_name"},
            "manual_review_rules": ["manual review required"],
            "blocked_outputs": BLOCKED_OUTPUT_CATEGORIES,
            "package_sections": ["plant_target_intake_review"],
            "boundary_notes": ["Documentation-only template for manual review."],
            "plant_context": "custom plant context",
            "unknown_field": "ignored",
        }
    )

    assert normalized["route_id"] == "custom_route"
    assert normalized["display_name"] == "Custom Route"
    assert normalized["required_module_cards"] == ["plant_target_intake"]
    assert normalized["optional_module_cards"] == ["gap_queue"]
    assert normalized["required_module_ids"] == ["plant_target_intake"]
    assert "unknown_field" not in normalized
    _assert_plain_json_like(normalized)


def test_summary_lists_route_ids_aliases_and_host_contexts_as_plain_data() -> None:
    summary = get_plant_expression_route_template_registry_summary()

    assert summary["total_route_templates"] == "7"
    assert summary["route_types"] == ["plant_expression_vector"]
    assert summary["default_route_id"] == "plant_expression_vector"
    assert summary["route_ids"] == EXPECTED_ROUTE_IDS
    assert summary["route_id_aliases"]["generic_plant_expression_vector_route"] == "plant_expression_vector"
    assert "rice seed" in summary["supported_host_contexts"]
    _assert_plain_json_like(summary)


def test_no_ui_database_import_export_or_generation_runtime_is_introduced() -> None:
    source = Path(registry.__file__).read_text(encoding="utf-8").casefold()
    blocked_markers = [
        "streamlit",
        "sqlite",
        "sqlalchemy",
        "project_import",
        "project_export",
        "package_export",
        "export_package",
        "import_package",
        "openai",
        "requests.",
        "httpx",
        "generate_route",
        "generated_route",
        "generate_sequence",
        "optimize_sequence",
        "score_feasibility",
    ]

    for marker in blocked_markers:
        assert marker not in source


def test_route_copy_stays_documentation_only_without_positive_claims() -> None:
    safe_copy_blob = _template_text_without_blocked_outputs()
    disallowed_positive_phrases = [
        "successful import",
        "project imported",
        "validated construct",
        "optimized pathway",
        "ready to build",
        "experiment-ready",
        "production-ready",
        "guaranteed expression",
        "high-yield",
        "wet-lab ready",
    ]

    for phrase in disallowed_positive_phrases:
        assert phrase not in safe_copy_blob

    assert "documentation-only" in safe_copy_blob
    assert "manual review" in safe_copy_blob
