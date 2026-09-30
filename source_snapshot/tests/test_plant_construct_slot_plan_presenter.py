from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_construct_slot_plan_presenter import (
    BOUNDARY_NOTICE,
    PRESENTER_KEYS,
    format_construct_slot_plan_markdown,
    present_construct_slot_plan_readback,
)
from services.plant_construct_slot_plan_readback_builder import (
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


def test_presenter_handles_canonical_slot_plan_readback() -> None:
    readback = build_plant_construct_slot_plan_readback(
        {"route_template_id": "plant_expression_construct_review"}
    )
    presented = present_construct_slot_plan_readback(readback)

    assert list(presented) == list(PRESENTER_KEYS)
    assert presented["page_title"] == "Plant Construct Slot Plan Readback"
    assert presented["subtitle"] == "Documentation-only slot plan summary for manual review."
    assert presented["empty_state"]["is_empty"] is False  # type: ignore[index]
    assert presented["summary_card"]["slot_row_count"] == 10  # type: ignore[index]
    assert presented["summary_card"]["required_slot_count"] == 10  # type: ignore[index]
    assert presented["summary_card"]["optional_slot_count"] == 0  # type: ignore[index]
    assert presented["summary_card"]["manual_review_row_count"] == 10  # type: ignore[index]
    assert presented["compatibility_card"]["alias_status"] == "canonical_alias_to_stored_legacy_route_id"  # type: ignore[index]
    assert presented["slot_rows"][0]["row_id"] == "slot-plan-01"  # type: ignore[index]
    assert presented["gap_rows"]
    assert presented["blocked_output_rows"]
    assert "# Plant Construct Slot Plan Readback Snapshot" in presented["markdown_snapshot"]
    assert "does not save records, export packages, or create construct outputs" in presented["markdown_snapshot"]


def test_presenter_preserves_slot_row_identity_without_component_choice_claim() -> None:
    readback = build_plant_construct_slot_plan_readback(
        {
            "route_id": "generic_plant_expression_vector_route",
            "required_slots": ["promoter_slot"],
            "optional_slots": ["context_note"],
        }
    )
    presented = present_construct_slot_plan_readback(readback)

    assert [row["slot_id"] for row in presented["slot_rows"]] == [  # type: ignore[index]
        "promoter_slot",
        "context_note",
    ]
    assert [row["required_or_optional"] for row in presented["slot_rows"]] == [  # type: ignore[index]
        "required",
        "optional",
    ]
    assert "biological suitability" in presented["compatibility_card"]["note"]  # type: ignore[index]
    assert "choose components" not in _copy_blob(presented)
    assert "component choice" not in _copy_blob(presented)


def test_presenter_handles_unknown_or_empty_readback_with_safe_empty_state() -> None:
    for readback in ({}, None):
        presented = present_construct_slot_plan_readback(readback)

        assert list(presented) == list(PRESENTER_KEYS)
        assert presented["empty_state"] == {
            "is_empty": True,
            "message": (
                "No construct slot plan rows are available. Build or provide a slot plan readback before "
                "using this presenter for manual documentation review."
            ),
        }
        assert presented["summary_card"]["slot_row_count"] == 0  # type: ignore[index]
        assert presented["slot_rows"] == []
        assert presented["markdown_snapshot"] == ""


def test_presenter_handles_blocked_unknown_route_readback() -> None:
    readback = build_plant_construct_slot_plan_readback({"route_id": "unknown_route"})
    presented = present_construct_slot_plan_readback(readback)

    assert presented["empty_state"]["is_empty"] is True  # type: ignore[index]
    assert presented["summary_card"]["slot_plan_status"] == "blocked_manual_review_required"  # type: ignore[index]
    assert presented["summary_card"]["route_template_id"] == "unknown_route"  # type: ignore[index]
    assert presented["compatibility_card"]["alias_status"] == "unknown_route_id_blocked"  # type: ignore[index]
    assert "No construct slot plan rows are available" in presented["markdown_snapshot"]


def test_markdown_formatter_includes_summary_compatibility_gaps_and_boundary() -> None:
    readback = build_plant_construct_slot_plan_readback(
        {"route_template_id": "plant_expression_construct_review"}
    )
    presented = present_construct_slot_plan_readback(readback)
    markdown = format_construct_slot_plan_markdown(presented)

    assert markdown.startswith("# Plant Construct Slot Plan Readback Snapshot")
    assert "## Summary" in markdown
    assert "## Compatibility metadata" in markdown
    assert "## Slot rows" in markdown
    assert "## Gap rows" in markdown
    assert BOUNDARY_NOTICE in markdown


def test_presenter_output_is_deterministic_and_plain_data() -> None:
    readback = build_plant_construct_slot_plan_readback(
        {"route_template_id": "plant_expression_construct_review"}
    )

    assert present_construct_slot_plan_readback(readback) == present_construct_slot_plan_readback(readback)
    _assert_plain_dict_list(present_construct_slot_plan_readback(readback))


def test_no_positive_claim_copy_is_introduced_outside_blocked_categories() -> None:
    readback = build_plant_construct_slot_plan_readback(
        {"route_template_id": "plant_expression_construct_review"}
    )
    presented = present_construct_slot_plan_readback(readback)
    blob = _copy_blob(presented)
    for row in presented["blocked_output_rows"]:  # type: ignore[index]
        blob = blob.replace(str(row["blocked_output_category"]).casefold(), "")

    disallowed_positive_phrases = [
        _term("ready ", "for execution"),
        _term("experiment", "-ready"),
        _term("production", "-ready"),
        _term("valid", "ated ", "con", "struct"),
        _term("optimized ", "pathway"),
        _term("yield ", "pre", "diction"),
        _term("wet", "-lab ", "ready"),
        _term("recom", "mended"),
        _term("best"),
        _term("rank", "ing"),
        _term("scor", "ing"),
    ]
    for phrase in disallowed_positive_phrases:
        assert phrase not in blob


def test_presenter_does_not_import_runtime_or_high_risk_integrations() -> None:
    source = Path("services/plant_construct_slot_plan_presenter.py").read_text(
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
        "generate_route",
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
