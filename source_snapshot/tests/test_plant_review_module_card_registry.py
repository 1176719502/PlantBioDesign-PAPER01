from __future__ import annotations

from pathlib import Path
from typing import Any

from services import plant_review_module_card_registry as registry
from services.plant_review_module_card_registry import (
    build_plant_review_module_card_registry_readback,
    get_active_plant_expression_review_cards,
    get_plant_review_module_card_by_id,
    get_plant_review_module_cards,
    get_plant_review_module_cards_by_package_section,
    get_plant_review_module_cards_by_required_slot,
    get_plant_review_module_cards_by_route_type,
    get_plant_review_module_cards_by_trigger_term,
    validate_plant_review_module_card_registry,
)
from services.plant_review_module_card_schema import (
    BLOCKED_OUTPUT_CATEGORIES,
    CANONICAL_CARD_FIELDS,
    CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
    validate_plant_review_module_card,
)


EXPECTED_CORE_CARD_IDS = [
    "plant_target_intake",
    "plant_host_context",
    "cds_source_review",
    "plant_expression_cassette",
    "promoter_leader_review",
    "signal_peptide_localization",
    "terminator_marker_review",
    "vector_backbone_context",
    "component_provenance",
    "codon_usage_readonly",
    "gap_queue",
    "plant_review_package",
]


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
        assert value is None or isinstance(value, (str, int, bool))


def _card_text_without_blocked_categories() -> str:
    values: list[str] = []
    for card in get_plant_review_module_cards():
        for field, value in card.items():
            if field == "blocked_outputs":
                continue
            if isinstance(value, list):
                values.extend(str(item) for item in value)
            else:
                values.append(str(value))
    return "\n".join(values).casefold()


def test_registry_returns_non_empty_plain_dict_cards() -> None:
    cards = get_plant_review_module_cards()

    assert cards
    assert [card["module_id"] for card in cards] == EXPECTED_CORE_CARD_IDS
    for card in cards:
        assert isinstance(card, dict)
        assert list(card) == list(CANONICAL_CARD_FIELDS)
    _assert_plain_json_like(cards)


def test_all_cards_validate_through_r66_schema() -> None:
    for card in get_plant_review_module_cards():
        result = validate_plant_review_module_card(card)

        assert result["ok"] is True
        assert result["errors"] == []
        assert result["warnings"] == []
        assert result["normalized_card"]["module_id"] == card["module_id"]


def test_all_cards_use_supported_active_route_type() -> None:
    cards = get_plant_review_module_cards()

    assert {card["route_type"] for card in cards} == {CURRENT_ACTIVE_PLANT_ROUTE_TYPE}
    assert CURRENT_ACTIVE_PLANT_ROUTE_TYPE == "plant_expression_vector"


def test_active_expression_helper_returns_only_expression_vector_cards() -> None:
    cards = get_active_plant_expression_review_cards()

    assert [card["module_id"] for card in cards] == EXPECTED_CORE_CARD_IDS
    assert all(card["route_type"] == "plant_expression_vector" for card in cards)


def test_each_expected_core_card_id_exists() -> None:
    by_id = {card["module_id"]: card for card in get_plant_review_module_cards()}

    assert set(by_id) == set(EXPECTED_CORE_CARD_IDS)
    assert list(by_id) == EXPECTED_CORE_CARD_IDS


def test_lookup_by_id_returns_normalized_card_and_unknown_id_returns_none() -> None:
    card = get_plant_review_module_card_by_id(" plant_host_context ")

    assert card is not None
    assert card["module_id"] == "plant_host_context"
    assert card["display_name"] == "Plant Host Context"
    assert list(card) == list(CANONICAL_CARD_FIELDS)
    _assert_plain_json_like(card)

    assert get_plant_review_module_card_by_id("unknown_card") is None
    assert get_plant_review_module_card_by_id("") is None


def test_legacy_module_id_aliases_resolve_to_r66_canonical_ids() -> None:
    assert get_plant_review_module_card_by_id(
        "plant_signal_peptide_localization_review"
    )["module_id"] == "signal_peptide_localization"
    assert get_plant_review_module_card_by_id(
        "component_provenance_review"
    )["module_id"] == "component_provenance"
    assert get_plant_review_module_card_by_id(
        "codon_usage_readonly_review"
    )["module_id"] == "codon_usage_readonly"
    assert get_plant_review_module_card_by_id("gap_queue_review")["module_id"] == "gap_queue"


def test_lookup_by_route_type_trigger_term_required_slot_and_package_section() -> None:
    by_route = get_plant_review_module_cards_by_route_type(" plant_expression_vector ")
    by_trigger = get_plant_review_module_cards_by_trigger_term(" Plant Host ")
    by_slot = get_plant_review_module_cards_by_required_slot("source_reference")
    by_section = get_plant_review_module_cards_by_package_section(
        "plant_expression_cassette_review"
    )

    assert [card["module_id"] for card in by_route] == EXPECTED_CORE_CARD_IDS
    assert [card["module_id"] for card in by_trigger] == ["plant_host_context"]
    assert {card["module_id"] for card in by_slot} >= {
        "plant_host_context",
        "cds_source_review",
        "signal_peptide_localization",
        "vector_backbone_context",
        "component_provenance",
    }
    assert [card["module_id"] for card in by_section] == ["plant_expression_cassette"]

    assert get_plant_review_module_cards_by_route_type("bacterial_expression") == []
    assert get_plant_review_module_cards_by_trigger_term("") == []
    assert get_plant_review_module_cards_by_required_slot("") == []
    assert get_plant_review_module_cards_by_package_section("") == []


def test_registry_validation_result_is_plain_json_like_data() -> None:
    result = validate_plant_review_module_card_registry()

    assert result["ok"] is True
    assert result["card_count"] == len(EXPECTED_CORE_CARD_IDS)
    assert result["errors"] == []
    assert result["warnings"] == []
    assert [card["module_id"] for card in result["card_results"]] == EXPECTED_CORE_CARD_IDS
    assert all(card["ok"] is True for card in result["card_results"])
    _assert_plain_json_like(result)


def test_readback_helper_includes_expected_summary_fields() -> None:
    readback = build_plant_review_module_card_registry_readback()

    assert readback["title"] == "Plant Review Module Card Registry"
    assert "documentation-only" in readback["subtitle"].casefold()
    assert "manual review" in readback["subtitle"].casefold()
    assert readback["active_route_type"] == "plant_expression_vector"
    assert readback["card_count"] == len(EXPECTED_CORE_CARD_IDS)
    assert [card["module_id"] for card in readback["cards"]] == EXPECTED_CORE_CARD_IDS
    assert readback["boundary_notes"]
    assert "empty_state" in readback
    _assert_plain_json_like(readback)


def test_every_card_has_manual_review_rules_and_blocked_outputs() -> None:
    for card in get_plant_review_module_cards():
        assert card["manual_review_rules"]
        assert card["blocked_outputs"] == list(BLOCKED_OUTPUT_CATEGORIES)
        assert set(card["blocked_outputs"]) >= {
            "protocol",
            "optimized_sequence",
            "wet_lab_readiness",
            "experimental_validation",
            "yield_prediction",
            "build_ready_claim",
        }


def test_every_card_has_documentation_only_and_manual_review_boundary_notes() -> None:
    for card in get_plant_review_module_cards():
        boundary_text = " ".join(card["boundary_notes"]).casefold()

        assert "documentation-only" in boundary_text
        assert "manual review" in boundary_text
        assert "biological recommendation" in boundary_text


def test_no_unknown_fields_leak_from_registry_cards() -> None:
    unknown_fields = {
        "module_name",
        "route_priority",
        "optional_slots",
        "boundary_note",
        "agent_runtime",
        "route_generation",
        "sequence_generation",
        "recommendation",
        "optimization_score",
        "readiness_score",
        "wet_lab_readiness",
    }

    for card in get_plant_review_module_cards():
        assert set(card) == set(CANONICAL_CARD_FIELDS)
        assert unknown_fields.isdisjoint(card)


def test_no_ui_database_import_export_or_package_export_behavior_is_introduced() -> None:
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
        "component_library",
        "plant_design_workspace",
        "expression_wizard",
    ]

    for marker in blocked_markers:
        assert marker not in source


def test_no_ai_api_llm_agent_cloud_runtime_hooks_are_introduced() -> None:
    source = Path(registry.__file__).read_text(encoding="utf-8").casefold()
    blocked_markers = [
        "openai",
        "anthropic",
        "langchain",
        "llm_runtime",
        "agent_runtime",
        "cloud_runtime",
        "requests.",
        "httpx",
    ]

    for marker in blocked_markers:
        assert marker not in source


def test_no_route_generation_behavior_is_introduced() -> None:
    source = Path(registry.__file__).read_text(encoding="utf-8").casefold()
    blocked_markers = [
        "generate_route",
        "generated_route",
        "route_generation",
        "route_generator",
        "select_route",
        "score_route",
    ]

    for marker in blocked_markers:
        assert marker not in source


def test_no_positive_biological_recommendation_or_readiness_copy_is_introduced() -> None:
    safe_copy_blob = _card_text_without_blocked_categories()
    disallowed_positive_phrases = [
        "validated construct",
        "optimized pathway",
        "best",
        "ready to build",
        "experiment-ready",
        "guaranteed expression",
        "high-yield",
        "successful production",
        "wet-lab ready",
    ]

    for phrase in disallowed_positive_phrases:
        assert phrase not in safe_copy_blob

    assert "documentation-only" in safe_copy_blob
    assert "manual review" in safe_copy_blob
