# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from tests.helpers.fake_streamlit import FakeStreamlit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.plant_review_handoff_data_adapter import build_plant_review_handoff_payload
from services.plant_review_package_readback_presenter import build_plant_review_package_readback_presenter
from services.plant_simple_wizard_route_checklist_presenter import (
    build_simple_plant_wizard_route_checklist_presenter,
)
from services.plant_simple_wizard_route_confirmation_presenter import (
    build_simple_plant_wizard_route_confirmation_presenter,
)
from views.pathway_workspace_sections import plant_review_workflow_section as section


GOAL_TEXT = "Document a rice seed protein expression design draft for manual review."
ROUTE_ID = "plant_protein_expression_review"


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_OUTPUT_FRAGMENTS = (
    _term("auto", " component selection"),
    _term("recommended ", "component"),
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("export ", "permission", " granted"),
)


def _confirmation_payload() -> dict[str, Any]:
    return build_simple_plant_wizard_route_confirmation_presenter(
        options={
            "user_goal_text": GOAL_TEXT,
            "available_materials": ["target_gene_or_cds", "host_plant"],
        }
    )


def _checklist_payload() -> dict[str, Any]:
    return build_simple_plant_wizard_route_checklist_presenter(ROUTE_ID)


def _project_draft() -> dict[str, Any]:
    return section.build_simple_plant_wizard_project_draft_payload(
        goal_text=GOAL_TEXT,
        confirmation_payload=_confirmation_payload(),
        checklist_payload=_checklist_payload(),
    )


def _rendered_text(fake_st: FakeStreamlit) -> str:
    frame_text = [
        frame.to_string(index=False)
        for frame in fake_st.dataframes
        if hasattr(frame, "to_string")
    ]
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.info_messages
        + fake_st.success_messages
        + fake_st.warning_messages
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + frame_text
    )


def _workflow() -> dict[str, Any]:
    return {
        "workflow_status": "manual_review_required",
        "manual_review_required": True,
        "warnings": [],
        "adapter_input": {"evidence_records": [], "component_records": []},
        "chain_result": {
            "plant_review_package": {
                "package_status": "manual_review_required",
                "route_summary": {
                    "route_id": ROUTE_ID,
                    "route_label": "Plant Protein Expression Review",
                    "route_type": "simple_plant_wizard_handoff",
                },
                "construct_slot_summary": {"slots": []},
            },
            "route_draft": {"draft_status": "manual_review_required", "route_id": ROUTE_ID},
        },
        "handoff_preview_payload": {
            "handoff_status": "manual_review_required",
            "missing_information_items": [
                {
                    "item_id": "r206-gap-target",
                    "category": "required_slot_gap",
                    "slot_id": "target_protein",
                    "reason": "Manual design slot remains blank.",
                }
            ],
        },
        "traceability": {
            "upstream_statuses": {
                "extractor": "manual_review_required",
                "adapter": "manual_review_required",
                "chain": "manual_review_required",
                "handoff": "manual_review_required",
            },
            "adapter_traceability": {"evidence_record_ids": [], "component_record_ids": []},
            "extractor_traceability": {"source_keys_used": ["simple_plant_wizard_project_draft"]},
        },
    }


def _package_with_completion(completion: dict[str, Any]) -> dict[str, Any]:
    return {
        "package_id": "r206-readback-package",
        "package_schema_version": "r206-test",
        "package_type": "plant_review_package",
        "package_status": "manual_review_required",
        "manual_review_required": True,
        "route_summary": {"route_id": ROUTE_ID, "route_label": "Plant Protein Expression Review"},
        "design_intent_summary": {},
        "module_card_summary": {"modules": []},
        "construct_slot_summary": {"slots": []},
        "evidence_summary": {"slots": []},
        "component_candidate_summary": {"slots": []},
        "gap_manual_review_summary": {},
        "review_queue": [],
        "traceability": {},
        "blocked_output_boundaries": [],
        "design_slot_completion": completion,
    }


def _filled_values(**overrides: str) -> dict[str, str]:
    values = {
        "target_protein": "",
        "target_gene_or_cds": "",
        "host_plant": "",
        "expression_context": "",
        "promoter_or_regulatory_element": "",
        "terminator": "",
        "marker_or_reporter": "",
        "vector_or_backbone": "",
        "notes": "",
    }
    values.update(overrides)
    return values


def test_r205_handoff_draft_renders_required_design_slot_panel(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_area_values[section.SIMPLE_PLANT_WIZARD_GOAL_TEXT_KEY] = GOAL_TEXT
    fake_st.button_values["r180_simple_plant_wizard_start_analysis"] = True
    fake_st.button_values["r180_simple_plant_wizard_confirm_route"] = True
    monkeypatch.setattr(section, "st", fake_st)

    workflow = section.render_simple_plant_design_wizard_landing()
    rendered = _rendered_text(fake_st)
    draft = fake_st.session_state[section.SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY]

    assert workflow["current_project_draft"] == draft
    assert section.R206_REQUIRED_DESIGN_SLOT_PANEL_TITLE in rendered
    assert draft["goal_description"] == GOAL_TEXT
    assert draft["selected_route"]["route_id"] == ROUTE_ID
    assert draft["missing_information_checklist"]
    assert draft["design_slot_completion"]["panel_title"] == section.R206_REQUIRED_DESIGN_SLOT_PANEL_TITLE


def test_empty_slot_panel_shows_missing_required_slots(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_required_design_information_completion_panel(_project_draft())
    rendered = _rendered_text(fake_st)
    summary = payload["design_slot_completion_summary"]

    assert summary["completed_slot_count"] == 0
    assert summary["missing_slot_count"] == 8
    assert "Target protein" in rendered
    assert "Promoter or regulatory element" in rendered


def test_entered_target_protein_is_preserved_in_session_project_draft(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_input_values["r206_required_design_slot_target_protein"] = "rice albumin-like protein"
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_required_design_information_completion_panel(_project_draft())

    assert payload["target_protein"] == "rice albumin-like protein"
    assert fake_st.session_state[section.SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY]["target_protein"] == (
        "rice albumin-like protein"
    )


def test_entered_host_plant_is_preserved_in_session_project_draft(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_input_values["r206_required_design_slot_host_plant"] = "Oryza sativa"
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_required_design_information_completion_panel(_project_draft())

    assert payload["host_plant"] == "Oryza sativa"
    assert payload["design_slot_completion"]["slots"]["host_plant"] == "Oryza sativa"


def test_entered_target_gene_or_cds_is_preserved_in_session_project_draft(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_input_values["r206_required_design_slot_target_gene_or_cds"] = "OsAlbumin-like CDS note"
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_required_design_information_completion_panel(_project_draft())

    assert payload["target_gene_or_cds"] == "OsAlbumin-like CDS note"
    assert payload["design_slot_completion"]["slots"]["target_gene_or_cds"] == "OsAlbumin-like CDS note"


def test_completion_summary_updates_completed_and_missing_counts() -> None:
    completion = section.build_required_design_slot_completion_payload(
        project_draft_payload=_project_draft(),
        slot_values=_filled_values(
            target_protein="rice albumin-like protein",
            target_gene_or_cds="OsAlbumin-like CDS note",
            host_plant="Oryza sativa",
        ),
    )
    summary = completion["completion_summary"]

    assert summary["completed_slot_count"] == 3
    assert summary["missing_slot_count"] == 5
    assert summary["completed_slots"] == ["target_protein", "target_gene_or_cds", "host_plant"]
    assert "promoter_or_regulatory_element" in summary["missing_slots"]
    assert summary["manual_review_required"] is True


def test_missing_slots_remain_visible_after_partial_entry(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_input_values["r206_required_design_slot_target_protein"] = "rice albumin-like protein"
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_required_design_information_completion_panel(_project_draft())
    rendered = _rendered_text(fake_st)

    assert "Promoter or regulatory element" in rendered
    assert "missing manual entry" in rendered
    assert "promoter_or_regulatory_element" in payload["design_slot_completion_summary"]["missing_slots"]


def test_manual_review_and_readback_only_boundary_copy_remains_visible(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    section.render_required_design_information_completion_panel(_project_draft())
    rendered = _rendered_text(fake_st)

    assert "Documentation-only design slot completion" in rendered
    assert "manual review notes" in rendered
    assert "does not choose components" in rendered


def test_manual_evidence_entry_panel_still_renders_with_required_design_panel(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    draft = _project_draft()
    fake_st.session_state[section.SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY] = draft
    fake_st.checkbox_values[section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(section, "st", fake_st)

    captured_state: dict[str, Any] = {}

    def _build_workflow(workspace_state: dict[str, Any]) -> dict[str, Any]:
        captured_state.update(workspace_state)
        return _workflow()

    monkeypatch.setattr(section, "render_plant_goal_review_package_draft_visible_mvp", lambda: {})
    monkeypatch.setattr(section, "render_plant_review_handoff_preview_section", lambda _payload: None)
    monkeypatch.setattr(section, "render_rice_albumin_seed_review_visible_mount", lambda: None)

    workflow = section.render_plant_review_workflow_section(
        project={},
        steps=[],
        expression_links=[],
        test_records=[],
        review_signals=[],
        build_workflow=_build_workflow,
    )
    rendered = _rendered_text(fake_st)

    assert section.R206_REQUIRED_DESIGN_SLOT_PANEL_TITLE in rendered
    assert "Manual Evidence Entry / Preview" in rendered
    assert "Manual Evidence Review Queue" in rendered
    assert captured_state["design_slot_completion"]["slot_completion_schema_version"] == (
        section.R206_DESIGN_SLOT_COMPLETION_SCHEMA_VERSION
    )
    assert workflow["current_project_draft"]["design_slot_completion_summary"]["missing_slot_count"] == 8


def test_package_and_handoff_readback_consume_slot_completion_summary() -> None:
    completion = section.build_required_design_slot_completion_payload(
        project_draft_payload=_project_draft(),
        slot_values=_filled_values(target_protein="rice albumin-like protein", host_plant="Oryza sativa"),
    )
    presenter = build_plant_review_package_readback_presenter(_package_with_completion(completion))
    handoff = build_plant_review_handoff_payload(presenter)

    presenter_summary = presenter["design_slot_completion_section"]["summary"]
    handoff_summary = handoff["design_slot_completion_readback"]["summary"]

    assert presenter_summary["completed_slot_count"] == 2
    assert presenter_summary["missing_slot_count"] == 6
    assert handoff_summary == presenter_summary
    assert handoff["source_traceability"]["design_slot_missing_count"] == 6


def test_slot_completion_output_does_not_imply_component_choice_or_readiness_claims() -> None:
    completion = section.build_required_design_slot_completion_payload(
        project_draft_payload=_project_draft(),
        slot_values=_filled_values(target_protein="rice albumin-like protein", host_plant="Oryza sativa"),
    )
    presenter = build_plant_review_package_readback_presenter(_package_with_completion(completion))
    handoff = build_plant_review_handoff_payload(presenter)
    lowered = repr({"completion": completion, "presenter": presenter, "handoff": handoff}).casefold()

    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in lowered
    assert "documentation-only" in lowered
    assert "manual review" in lowered


def test_slot_completion_output_is_deterministic() -> None:
    draft = _project_draft()
    values = _filled_values(target_protein="rice albumin-like protein", host_plant="Oryza sativa")

    first = section.build_required_design_slot_completion_payload(project_draft_payload=draft, slot_values=values)
    second = section.build_required_design_slot_completion_payload(project_draft_payload=draft, slot_values=values)

    assert first == second
