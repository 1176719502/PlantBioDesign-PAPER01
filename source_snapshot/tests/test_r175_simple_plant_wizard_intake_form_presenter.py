from __future__ import annotations

from typing import Any

from services.plant_simple_wizard_intake_form_presenter import (
    build_simple_plant_wizard_intake_form_presenter,
)


PLAIN_TYPES = (dict, list, str, bool, int, float, type(None))

EXPECTED_GOAL_TYPES = {
    "protein_expression",
    "metabolic_pathway",
    "multigene_construct",
    "regulatory_module",
}
EXPECTED_MATERIALS = {
    "target_gene_or_cds",
    "target_product",
    "host_plant",
    "promoter_or_vector",
    "literature_evidence",
    "none",
}
FORBIDDEN_FRAGMENTS = (
    "validated",
    "optimized",
    "experiment-ready",
    "protocol",
    "yield prediction",
    "best component",
    "wet-lab ready",
    "final package",
    "exported package",
)


def _walk_plain_values(value: Any) -> None:
    assert isinstance(value, PLAIN_TYPES)
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for item in value.values():
            _walk_plain_values(item)
    elif isinstance(value, list):
        for item in value:
            _walk_plain_values(item)


def _text_blob(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text_blob(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text_blob(item) for item in value)
    return "" if value is None else str(value)


def _option_ids(payload: dict[str, Any], key: str) -> set[str]:
    return {str(option["option_id"]) for option in payload[key]}


def test_intake_form_presenter_returns_required_labels_and_options() -> None:
    payload = build_simple_plant_wizard_intake_form_presenter()

    for key in (
        "page_title_zh",
        "page_subtitle_zh",
        "goal_input_label_zh",
        "goal_input_placeholder_zh",
        "selected_goal_type_options",
        "available_material_options",
        "submit_label_zh",
        "example_goals",
        "safe_boundary_notes_zh",
        "advanced_detail_hint_zh",
    ):
        assert payload[key]


def test_selected_goal_type_options_include_all_r168_supported_categories() -> None:
    payload = build_simple_plant_wizard_intake_form_presenter()

    assert EXPECTED_GOAL_TYPES == _option_ids(payload, "selected_goal_type_options")


def test_available_material_options_include_all_r168_supported_materials() -> None:
    payload = build_simple_plant_wizard_intake_form_presenter()

    assert EXPECTED_MATERIALS == _option_ids(payload, "available_material_options")


def test_example_goals_cover_four_entry_route_families() -> None:
    payload = build_simple_plant_wizard_intake_form_presenter()

    assert {
        example["route_family"] for example in payload["example_goals"]
    } == EXPECTED_GOAL_TYPES


def test_payload_is_deterministic_across_repeated_calls() -> None:
    first = build_simple_plant_wizard_intake_form_presenter()
    second = build_simple_plant_wizard_intake_form_presenter()

    assert first == second


def test_payload_contains_only_plain_python_types() -> None:
    payload = build_simple_plant_wizard_intake_form_presenter()

    _walk_plain_values(payload)


def test_safety_copy_does_not_contain_forbidden_claims() -> None:
    payload = build_simple_plant_wizard_intake_form_presenter()
    blob = _text_blob(payload).casefold()

    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in blob
