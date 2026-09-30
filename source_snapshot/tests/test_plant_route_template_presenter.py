from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_expression_route_template_registry import get_all_plant_expression_route_templates
from services.plant_route_template_presenter import (
    BOUNDARY_NOTICE,
    PRESENTER_KEYS,
    present_plant_route_templates,
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


def test_presenter_formats_current_route_templates() -> None:
    presented = present_plant_route_templates()

    assert list(presented) == list(PRESENTER_KEYS)
    assert presented["page_title"] == "Plant Route Template Registry Readback"
    assert presented["summary_card"]["template_count"] == len(get_all_plant_expression_route_templates())  # type: ignore[index]
    assert presented["summary_card"]["module_link_count"] > 0  # type: ignore[index]
    assert presented["summary_card"]["package_section_link_count"] > 0  # type: ignore[index]
    assert presented["empty_state"]["is_empty"] is False  # type: ignore[index]
    assert [row["route_id"] for row in presented["template_rows"]] == [  # type: ignore[index]
        template["route_id"] for template in get_all_plant_expression_route_templates()
    ]


def test_presenter_preserves_module_and_package_links() -> None:
    presented = present_plant_route_templates()

    assert any(row["module_id"] == "plant_target_intake" for row in presented["module_link_rows"])  # type: ignore[index]
    assert any(
        row["section_id"] == "plant_target_intake_review"
        for row in presented["package_section_rows"]  # type: ignore[index]
    )
    assert all(row["required_or_optional"] in {"required", "optional"} for row in presented["module_link_rows"])  # type: ignore[index]


def test_empty_input_returns_safe_empty_state() -> None:
    presented = present_plant_route_templates([])

    assert presented["summary_card"]["template_count"] == 0  # type: ignore[index]
    assert presented["template_rows"] == []
    assert presented["module_link_rows"] == []
    assert presented["package_section_rows"] == []
    assert presented["empty_state"]["is_empty"] is True  # type: ignore[index]


def test_presenter_output_is_deterministic_and_plain_data() -> None:
    assert present_plant_route_templates() == present_plant_route_templates()
    _assert_plain_dict_list(present_plant_route_templates())


def test_boundary_copy_is_present_without_positive_claims() -> None:
    presented = present_plant_route_templates()
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
    source = Path("services/plant_route_template_presenter.py").read_text(
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
