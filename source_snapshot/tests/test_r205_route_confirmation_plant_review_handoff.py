# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from tests.helpers.fake_streamlit import FakeStreamlit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    _term("successful ", "import"),
    _term("project ", "imported"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("source_", "verified"),
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
                "construct_slot_summary": {
                    "slots": [
                        {
                            "slot_id": "target_protein",
                            "slot_label": "Target protein",
                            "required": True,
                            "evidence_ids": [],
                            "component_ids": [],
                            "slot_status": ["missing_information"],
                            "missing_required_slot": True,
                        }
                    ]
                },
            },
            "route_draft": {"draft_status": "manual_review_required", "route_id": ROUTE_ID},
        },
        "handoff_preview_payload": {
            "handoff_status": "manual_review_required",
            "missing_information_items": [
                {
                    "item_id": "r205-gap-1",
                    "category": "missing_information",
                    "slot_id": "target_protein",
                    "reason": "Draft field remains open for manual review.",
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


def test_project_draft_payload_preserves_goal_route_confidence_and_checklist() -> None:
    checklist = _checklist_payload()
    first = section.build_simple_plant_wizard_project_draft_payload(
        goal_text=GOAL_TEXT,
        confirmation_payload=_confirmation_payload(),
        checklist_payload=checklist,
    )
    second = section.build_simple_plant_wizard_project_draft_payload(
        goal_text=GOAL_TEXT,
        confirmation_payload=_confirmation_payload(),
        checklist_payload=checklist,
    )

    assert first == second
    assert first["goal_description"] == GOAL_TEXT
    assert first["selected_route"]["route_id"] == ROUTE_ID
    assert first["selected_route"]["label_en"] == "Plant Protein Expression Review"
    assert first["confidence_readback"]["confidence"] in {"high", "medium"}
    assert first["missing_information_checklist"] == checklist["slot_rows"]
    assert first["missing_required_fields"]
    assert first["documentation_only"] is True
    assert first["manual_review_required"] is True


def test_confirm_route_click_creates_session_handoff_payload_and_visible_next_step(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_area_values[section.SIMPLE_PLANT_WIZARD_GOAL_TEXT_KEY] = GOAL_TEXT
    fake_st.button_values["r180_simple_plant_wizard_start_analysis"] = True
    fake_st.button_values["r180_simple_plant_wizard_confirm_route"] = True
    monkeypatch.setattr(section, "st", fake_st)

    workflow = section.render_simple_plant_design_wizard_landing()
    draft = fake_st.session_state[section.SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY]
    rendered = _rendered_text(fake_st)

    assert section.SIMPLE_PLANT_WIZARD_CONFIRM_ROUTE_LABEL in [call["label"] for call in fake_st.button_calls]
    assert "确认这个路线" not in [call["label"] for call in fake_st.button_calls]
    assert workflow["current_project_draft"] == draft
    assert draft["goal_description"] == GOAL_TEXT
    assert draft["selected_route"]["route_id"] == ROUTE_ID
    assert draft["missing_required_fields"]
    assert "Current project draft / 当前项目草稿" in rendered
    assert "Complete missing information in Plant Review" in repr(draft)
    assert "Manual Evidence Review Queue" in rendered


def test_plant_review_advanced_receives_handoff_and_keeps_manual_evidence_panel(monkeypatch) -> None:
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

    assert captured_state["design_goal"] == GOAL_TEXT
    assert captured_state["simple_plant_wizard_project_draft"] == draft
    assert captured_state["user_context"]["simple_plant_wizard_project_draft"] is True
    assert workflow["current_project_draft"] == draft
    assert "Current project draft / 当前项目草稿" in rendered
    assert "Manual Evidence Entry / Preview" in rendered
    assert "Manual Evidence Review Queue" in rendered
    assert "documentation notes, source/provenance context, and manual review notes" in rendered


def test_empty_project_draft_summary_remains_safe(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_current_project_draft_summary({})
    rendered = _rendered_text(fake_st)

    assert payload["draft_status"] == "no_current_project_draft"
    assert payload["documentation_only"] is True
    assert payload["manual_review_required"] is True
    assert payload["missing_required_fields"] == []
    assert "no confirmed Simple Plant Wizard route is in session" in rendered


def test_r205_handoff_output_copy_keeps_safe_boundaries() -> None:
    draft = _project_draft()
    lowered = repr(draft).casefold()

    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in lowered
    assert "documentation-only" in lowered
    assert "manual review" in lowered
    assert "biological recommendation" in lowered
    assert "package output permission" in lowered
