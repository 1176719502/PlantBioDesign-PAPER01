from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_review_module_card_presenter import (
    BOUNDARY_NOTICE,
    PRESENTER_KEYS,
    present_plant_review_module_cards,
)
from services.plant_review_module_card_registry import get_active_plant_expression_review_cards


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


def test_presenter_formats_current_module_cards() -> None:
    cards = get_active_plant_expression_review_cards()
    presented = present_plant_review_module_cards()

    assert list(presented) == list(PRESENTER_KEYS)
    assert presented["page_title"] == "Plant Review Module Card Registry Readback"
    assert presented["summary_card"]["module_card_count"] == len(cards)  # type: ignore[index]
    assert presented["summary_card"]["package_section_count"] == len(cards)  # type: ignore[index]
    assert presented["summary_card"]["review_rule_row_count"] == len(cards)  # type: ignore[index]
    assert presented["summary_card"]["route_types"] == ["plant_expression_vector"]  # type: ignore[index]
    assert presented["empty_state"]["is_empty"] is False  # type: ignore[index]
    assert [row["module_id"] for row in presented["module_rows"]] == [card["module_id"] for card in cards]  # type: ignore[index]


def test_presenter_preserves_package_section_links_and_review_counts() -> None:
    presented = present_plant_review_module_cards()

    assert any(row["module_id"] == "plant_target_intake" for row in presented["module_rows"])  # type: ignore[index]
    assert any(
        row["section_id"] == "plant_target_intake_review"
        for row in presented["package_section_rows"]  # type: ignore[index]
    )
    assert all(row["gap_rule_count"] > 0 for row in presented["review_rule_rows"])  # type: ignore[index]
    assert all(row["manual_review_required"] is True for row in presented["review_rule_rows"])  # type: ignore[index]


def test_empty_input_returns_safe_empty_state() -> None:
    presented = present_plant_review_module_cards([])

    assert presented["summary_card"]["module_card_count"] == 0  # type: ignore[index]
    assert presented["module_rows"] == []
    assert presented["package_section_rows"] == []
    assert presented["review_rule_rows"] == []
    assert presented["empty_state"]["is_empty"] is True  # type: ignore[index]


def test_presenter_output_is_deterministic_and_plain_data() -> None:
    assert present_plant_review_module_cards() == present_plant_review_module_cards()
    _assert_plain_dict_list(present_plant_review_module_cards())


def test_boundary_copy_is_present_without_positive_claims() -> None:
    presented = present_plant_review_module_cards()
    blob = _copy_blob(presented)

    assert BOUNDARY_NOTICE in presented["boundary_notice"]
    assert "documentation-only" in blob
    disallowed_phrases = [
        _term("ready ", "for execution"),
        _term("experiment", "-ready"),
        _term("production", "-ready"),
        _term("valid", "ated ", "con", "struct"),
        _term("optimized ", "pathway"),
        _term("yield ", "pre", "diction"),
        _term("wet", "-lab ", "ready"),
        _term("recom", "mended"),
        _term("be", "st"),
        _term("rank", "ing"),
        _term("scor", "ing"),
    ]
    for phrase in disallowed_phrases:
        assert phrase not in blob


def test_service_does_not_import_runtime_or_high_risk_surfaces() -> None:
    source = Path("services/plant_review_module_card_presenter.py").read_text(
        encoding="utf-8"
    ).casefold()
    disallowed_markers = [
        "streamlit",
        "sqlite",
        "project_import",
        "project_export",
        "package_export",
        "expression_wizard",
        "openai",
        "requests",
        "httpx",
        "agent_runtime",
        "generate_sequence",
        "recommend_component",
        "recommend_route",
        "select_promoter",
        "select_vector",
        "codon_optimization",
        "score_feasibility",
        "wet_lab_ready",
    ]
    for marker in disallowed_markers:
        assert marker not in source
