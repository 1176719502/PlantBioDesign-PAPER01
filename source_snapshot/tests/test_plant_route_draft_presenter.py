from __future__ import annotations

from pathlib import Path

from services.plant_route_draft_presenter import (
    PRESENTER_SECTION_KEYS,
    present_plant_route_draft,
)
from services.plant_review_module_card_schema import BLOCKED_OUTPUT_CATEGORIES
from services.plant_user_intent_route_draft_builder import build_plant_expression_route_draft


FORBIDDEN_FIELD_NAMES = {
    "recommendation",
    "optimization",
    "feasibility_score",
    "yield_prediction",
    "protocol",
    "wet_lab_ready",
    "validated",
    "build_ready",
}


def _rice_route_draft() -> dict[str, object]:
    return build_plant_expression_route_draft(
        {
            "target_name": "OsALB route draft target",
            "target_type": "source-backed plant expression target",
            "plant_host": "Oryza sativa rice",
            "plant_context": "rice seed expression documentation context",
            "expression_purpose": "local documentation review",
            "known_cds_source": "SRC-CDS-383",
            "known_component_ids": {
                "promoter": "SRC-PROMOTER-383",
                "terminator": "SRC-TERMINATOR-383",
            },
            "known_vector_or_backbone": "SRC-BACKBONE-383",
            "localization_context": "source note only",
            "evidence_sources": {
                "SRC-RICE-383": "rice host context source pointer",
                "SRC-CDS-383": "target CDS source pointer",
            },
            "notes": "Manual documentation review note.",
        }
    )


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for nested in value.values():
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _walk_dicts(value: object) -> list[dict[str, object]]:
    dicts: list[dict[str, object]] = []
    if isinstance(value, dict):
        dicts.append(value)
        for nested in value.values():
            dicts.extend(_walk_dicts(nested))
    elif isinstance(value, list):
        for nested in value:
            dicts.extend(_walk_dicts(nested))
    return dicts


def test_presenter_handles_normal_rice_route_draft_from_r382() -> None:
    draft = _rice_route_draft()
    presented = present_plant_route_draft(draft)

    assert list(presented) == list(PRESENTER_SECTION_KEYS)
    assert presented["page_title"] == "Plant Route Draft Readback"
    assert presented["subtitle"] == "Documentation-only construct slot plan for manual review."
    assert presented["empty_state"]["is_empty"] is False  # type: ignore[index]
    assert presented["route_summary_card"]["route_id"] == "rice_seed_protein_expression"  # type: ignore[index]
    assert presented["target_summary_card"]["target_name"] == "OsALB route draft target"  # type: ignore[index]
    assert presented["plant_context_card"]["provided_host"] == "Oryza sativa rice"  # type: ignore[index]
    assert presented["route_template_card"]["plant_context"] == "rice_expression_vector"  # type: ignore[index]
    assert presented["required_module_rows"]
    assert presented["construct_slot_plan_rows"]
    assert presented["package_preview_sections"]


def test_presenter_handles_generic_empty_intent_route_draft_from_r382() -> None:
    draft = build_plant_expression_route_draft({})
    presented = present_plant_route_draft(draft)

    assert presented["empty_state"]["is_empty"] is False  # type: ignore[index]
    assert presented["route_summary_card"]["draft_status"] == "needs_input"  # type: ignore[index]
    assert presented["route_summary_card"]["route_id"] == "unknown_plant_expression_context"  # type: ignore[index]
    assert presented["missing_field_rows"]
    assert presented["manual_review_checklist_rows"][0]["review_type"] == "missing_route_context"  # type: ignore[index]
    assert "documentation-only" in presented["boundary_notice"]["notice"].casefold()  # type: ignore[index]
    assert presented["blocked_outputs_notice"]["blocked_output_families"]  # type: ignore[index]


def test_presenter_handles_none_or_empty_dict_with_safe_empty_state() -> None:
    for empty_input in (None, {}):
        presented = present_plant_route_draft(empty_input)

        assert list(presented) == list(PRESENTER_SECTION_KEYS)
        assert presented["empty_state"] == {
            "is_empty": True,
            "title": "No route draft available",
            "message": (
                "Provide a plant route draft from the route draft builder to display a "
                "documentation-only readback."
            ),
        }
        assert presented["route_summary_card"] == {}
        assert presented["construct_slot_plan_rows"] == []
        assert presented["blocked_outputs_notice"]["blocked_output_families"] == []  # type: ignore[index]


def test_presenter_output_is_deterministic_for_identical_input() -> None:
    draft = _rice_route_draft()

    assert present_plant_route_draft(draft) == present_plant_route_draft(draft)


def test_route_summary_preserves_route_identity_and_status() -> None:
    draft = _rice_route_draft()
    presented = present_plant_route_draft(draft)
    summary = presented["route_summary_card"]

    assert summary["route_id"] == draft["route_id"]  # type: ignore[index]
    assert summary["route_name"] == draft["route_name"]  # type: ignore[index]
    assert summary["route_type"] == draft["route_type"]  # type: ignore[index]
    assert summary["draft_status"] == draft["draft_status"]  # type: ignore[index]


def test_construct_slot_rows_are_generated_from_required_slots() -> None:
    draft = _rice_route_draft()
    presented = present_plant_route_draft(draft)

    slot_rows = presented["construct_slot_plan_rows"]
    assert [row["slot_name"] for row in slot_rows] == [  # type: ignore[index]
        slot["slot_name"] for slot in draft["required_slots"]  # type: ignore[index]
    ]
    assert {row["status"] for row in slot_rows} == {"provided"}  # type: ignore[index]
    assert all(row["row_id"].startswith("slot-") for row in slot_rows)  # type: ignore[index]


def test_module_rows_are_generated_from_required_modules() -> None:
    draft = _rice_route_draft()
    presented = present_plant_route_draft(draft)

    module_rows = presented["required_module_rows"]
    assert [row["module_id"] for row in module_rows] == [  # type: ignore[index]
        module["module_id"] for module in draft["required_modules"]  # type: ignore[index]
    ]
    assert all(row["package_section"] for row in module_rows)  # type: ignore[index]
    assert all(isinstance(row["required_slots"], list) for row in module_rows)  # type: ignore[index]


def test_missing_field_rows_and_manual_review_checklist_rows_are_preserved() -> None:
    draft = _rice_route_draft()
    presented = present_plant_route_draft(draft)

    assert [row["field"] for row in presented["missing_field_rows"]] == draft["missing_fields"]  # type: ignore[index]
    assert [row["field"] for row in presented["manual_review_checklist_rows"]] == [  # type: ignore[index]
        item["field"] for item in draft["manual_review_items"]  # type: ignore[index]
    ]
    assert all(row["status"] == "manual_review" for row in presented["manual_review_checklist_rows"])  # type: ignore[index]


def test_evidence_summary_rows_preserve_evidence_pointers() -> None:
    draft = _rice_route_draft()
    presented = present_plant_route_draft(draft)

    assert presented["evidence_summary_rows"] == [
        {
            "row_id": "evidence-01",
            "source_id": "SRC-CDS-383",
            "value": "target CDS source pointer",
        },
        {
            "row_id": "evidence-02",
            "source_id": "SRC-RICE-383",
            "value": "rice host context source pointer",
        },
    ]


def test_boundary_notice_and_blocked_outputs_notice_are_present() -> None:
    presented = present_plant_route_draft(_rice_route_draft())

    assert "documentation-only" in presented["boundary_notice"]["notice"].casefold()  # type: ignore[index]
    assert "manual review" in presented["boundary_notice"]["notice"].casefold()  # type: ignore[index]
    assert set(presented["blocked_outputs_notice"]["blocked_output_families"]) == set(BLOCKED_OUTPUT_CATEGORIES)  # type: ignore[index]


def test_output_is_plain_dict_list_only() -> None:
    _assert_plain_data(present_plant_route_draft(_rice_route_draft()))


def test_no_unsafe_field_names_are_present_anywhere_in_presenter_output() -> None:
    presented = present_plant_route_draft(_rice_route_draft())

    for item in _walk_dicts(presented):
        assert FORBIDDEN_FIELD_NAMES.isdisjoint(item)


def test_presenter_does_not_add_runtime_or_high_risk_integrations() -> None:
    source = Path("services/plant_route_draft_presenter.py").read_text(encoding="utf-8").casefold()

    disallowed_runtime_markers = [
        "streamlit",
        "sqlite",
        "project_export",
        "project_import",
        "component_library",
        "openai",
        "requests",
        "httpx",
        "agent_runtime",
        "cloud_runtime",
        "generate_sequence",
        "sequence_output",
        "recommend_route",
        "recommend_component",
        "optimize_sequence",
        "score_feasibility",
        "wet_lab_ready",
    ]
    for marker in disallowed_runtime_markers:
        assert marker not in source
