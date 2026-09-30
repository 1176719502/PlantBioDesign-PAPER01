from __future__ import annotations

import copy
from pathlib import Path

from tests.helpers.fake_streamlit import FakeStreamlit

from services.plant_expression_workspace_prototype_presenter import (
    SECTION_ORDER,
    build_plant_expression_workspace_prototype_presenter,
)
from services.plant_walkthrough_chain_runner import run_plant_walkthrough_chain_by_fixture_id
import views.Plant_Expression_Workspace as workspace_view


ROOT = Path(__file__).resolve().parents[1]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_UI_COPY = (
    _term("auto", "matically generate"),
    _term("auto", "matically recommend"),
    _term("auto", "matic recommendation"),
    _term("experimental ", "validation"),
    _term("wet-lab ", "readiness"),
    _term("ready for ", "execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("yield ", "prediction"),
)

ALLOWED_NEGATIVE_BOUNDARY_COPY = "wet-lab readiness judgment."


def _default_chain_output() -> dict:
    output = run_plant_walkthrough_chain_by_fixture_id("rice_albumin_expression_review")
    assert isinstance(output, dict)
    return output


def _rendered_text(fake_st: FakeStreamlit) -> str:
    expander_text = "\n".join(call["label"] for call in fake_st.expander_calls)
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.warning_messages
        + fake_st.error_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + expander_text.splitlines()
    )


def test_r223_populated_workspace_presenter_summarizes_rice_albumin_fixture() -> None:
    presenter = build_plant_expression_workspace_prototype_presenter(_default_chain_output())

    summary = presenter["workspace_summary"]
    assert presenter["page_title"] == "Plant Expression Workspace"
    assert presenter["empty_state"]["is_empty"] is False
    assert summary["project_name"] == "Rice albumin expression review"
    assert summary["target_product"] == "rice albumin source record"
    assert summary["plant_host"] == "Oryza sativa rice"
    assert summary["current_stage"] == "Construct draft review"
    assert summary["overall_status"] == "Documentation review in progress"
    assert presenter["section_order"] == list(SECTION_ORDER)
    assert [row["label"] for row in presenter["construct_components"]] == [
        "Promoter",
        "5' UTR",
        "CDS",
        "Tag / Signal",
        "Terminator",
        "Vector / Backbone",
    ]


def test_r223_missing_component_is_visible_without_component_choice() -> None:
    output = copy.deepcopy(_default_chain_output())
    rows = output["package_snapshot"]["construct_slot_plan_section"]["construct_slot_rows"]
    output["package_snapshot"]["construct_slot_plan_section"]["construct_slot_rows"] = [
        row
        for row in rows
        if row.get("slot_name") not in {"terminator_slot", "terminator_source_reference"}
    ]

    presenter = build_plant_expression_workspace_prototype_presenter(output)
    terminator = next(row for row in presenter["construct_components"] if row["label"] == "Terminator")

    assert terminator["name"] == "Not recorded"
    assert terminator["status"] == "Needs documentation"
    assert "not shown" in terminator["note"]
    assert "choose" not in terminator["note"].casefold()


def test_r223_review_required_component_stays_manual_confirmation() -> None:
    presenter = build_plant_expression_workspace_prototype_presenter(_default_chain_output())
    promoter = next(row for row in presenter["construct_components"] if row["label"] == "Promoter")

    assert promoter["status"] == "Manual review needed"
    assert "manual confirmation" in promoter["note"]
    assert "Rice seed promoter source record" not in promoter["name"]
    assert promoter["name"] == "SRC-RICE-SEED-PROMOTER"


def test_r223_gap_priority_ordering_keeps_top_three_readable() -> None:
    output = copy.deepcopy(_default_chain_output())
    output["package_snapshot"]["gap_queue_section"]["queue_items"] = [
        {"field_name": "backbone_label", "message": "Vector information is incomplete."},
        {"field_name": "promoter_source_reference", "message": "Promoter evidence needs manual confirmation."},
        {"field_name": "terminator_source_reference", "message": "Terminator source is not recorded."},
    ]

    presenter = build_plant_expression_workspace_prototype_presenter(output)
    gap_titles = [row["title"] for row in presenter["gaps"]]

    assert gap_titles[:3] == [
        "Terminator source needs documentation review",
        "Promoter evidence needs manual confirmation",
        "Vector / backbone information needs documentation review",
    ]


def test_r223_safe_empty_state_has_no_core_cards() -> None:
    presenter = build_plant_expression_workspace_prototype_presenter({})

    assert presenter["empty_state"]["is_empty"] is True
    assert presenter["workspace_summary"] == {}
    assert presenter["construct_components"] == []
    assert presenter["gaps"] == []
    assert "Select or prepare a plant design record" in presenter["next_action"]


def test_r223_page_structure_keeps_advanced_details_after_core_sections(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.radio_values["r224_plant_expression_workspace_source_mode"] = "Example read-only demonstration"
    monkeypatch.setattr(workspace_view, "st", fake_st)

    presenter = workspace_view.render()
    rendered = _rendered_text(fake_st)

    assert presenter["section_order"] == [
        "Workspace Header",
        "Expression Construct Overview",
        "Current Gaps and Next Action",
        "Detailed Review",
    ]
    assert rendered.index("Plant Expression Workspace") < rendered.index("Expression Construct Overview")
    assert rendered.index("Expression Construct Overview") < rendered.index("Current Gaps and Next Action")
    assert rendered.index("Current Gaps and Next Action") < rendered.index("Detailed Review")
    assert fake_st.expander_calls == [{"label": "Advanced details", "expanded": False}]


def test_r223_page_and_presenter_copy_avoid_unsafe_claims() -> None:
    source_text = "\n".join(
        [
            (ROOT / "services" / "plant_expression_workspace_prototype_presenter.py").read_text(encoding="utf-8"),
            (ROOT / "views" / "Plant_Expression_Workspace.py").read_text(encoding="utf-8"),
            str(build_plant_expression_workspace_prototype_presenter(_default_chain_output())),
        ]
    ).casefold()

    assert source_text.count(ALLOWED_NEGATIVE_BOUNDARY_COPY) == 2
    source_text = source_text.replace(ALLOWED_NEGATIVE_BOUNDARY_COPY, "")
    assert [phrase for phrase in FORBIDDEN_UI_COPY if phrase in source_text] == []
    assert "documentation-only" in source_text
    assert "manual review" in source_text


def test_r223_old_plant_review_modules_remain_retained_but_not_formally_mounted() -> None:
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    registry = (ROOT / "core" / "module_registry.py").read_text(encoding="utf-8")

    assert (ROOT / "views" / "PlantDesignWorkspace.py").is_file()
    assert (ROOT / "views" / "Plant_Expression_Workspace.py").is_file()
    assert '"route_key": "Plant Design Workspace"' in registry
    assert '"route_key": "Plant Expression Workspace"' in registry
    assert "Plant Design Workspace" not in app
    assert "Plant Expression Workspace" not in app
    assert "PlantDesignWorkspace" not in app
    assert "Plant_Expression_Workspace" not in app
