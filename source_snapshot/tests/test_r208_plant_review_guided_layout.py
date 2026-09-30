# -*- coding: utf-8 -*-
from __future__ import annotations

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
    _term("source ", "verification"),
    _term("approval ", "workflow"),
    _term("export ", "permission granted"),
    _term("approved ", "evidence"),
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
                    "item_id": "r208-gap-target",
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


def _markdowns(fake_st: FakeStreamlit) -> list[str]:
    return [str(call["body"]) for call in fake_st.markdown_calls]


def _index_containing(values: list[str], needle: str) -> int:
    for index, value in enumerate(values):
        if needle in value:
            return index
    raise AssertionError(f"{needle!r} was not rendered in markdown calls: {values!r}")


def _render_guided_layout(
    monkeypatch: Any,
    fake_st: FakeStreamlit,
    *,
    draft: dict[str, Any] | None = None,
    build_workflow: Any | None = None,
) -> dict[str, Any]:
    if draft is not None:
        fake_st.session_state[section.SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY] = draft
    fake_st.checkbox_values[section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(section, "st", fake_st)
    monkeypatch.setattr(
        section,
        "render_plant_goal_review_package_draft_visible_mvp",
        lambda: fake_st.markdown("**Package readback placeholder**"),
    )
    monkeypatch.setattr(section, "render_plant_review_handoff_preview_section", lambda _payload: None)
    monkeypatch.setattr(section, "render_rice_albumin_seed_review_visible_mount", lambda: None)

    return section.render_plant_review_workflow_section(
        project={},
        steps=[],
        expression_links=[],
        test_records=[],
        review_signals=[],
        build_workflow=build_workflow or (lambda _state: _workflow()),
    )


def test_plant_review_renders_guided_workflow_sections_in_order(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    _render_guided_layout(monkeypatch, fake_st, draft=_project_draft())
    markdowns = _markdowns(fake_st)

    current = _index_containing(markdowns, "Current project draft")
    completion = _index_containing(markdowns, "Project Review Completion")
    required = _index_containing(markdowns, "Required Design Information")
    entry = _index_containing(markdowns, "Manual Evidence Entry / Preview")
    queue = _index_containing(markdowns, "Manual Evidence Review Queue")
    gap = _index_containing(markdowns, "Manual Evidence Gap Assistant")
    handoff = _index_containing(markdowns, section.R208_PACKAGE_HANDOFF_ENTRY_TITLE)

    assert current < completion < required < entry < queue < gap < handoff


def test_current_project_draft_appears_before_completion_gate_and_detail_panels(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    _render_guided_layout(monkeypatch, fake_st, draft=_project_draft())
    markdowns = _markdowns(fake_st)

    current = _index_containing(markdowns, "Current project draft")
    completion = _index_containing(markdowns, "Project Review Completion")
    detail = _index_containing([call["label"] for call in fake_st.expander_calls], section.R208_GUIDED_WORKFLOW_DETAIL_TITLE)

    assert current < completion
    assert completion < len(markdowns)
    assert detail >= 0


def test_project_review_completion_appears_near_the_top(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    _render_guided_layout(monkeypatch, fake_st, draft=_project_draft())
    markdowns = _markdowns(fake_st)

    completion = _index_containing(markdowns, "Project Review Completion")
    required = _index_containing(markdowns, "Required Design Information")
    entry = _index_containing(markdowns, "Manual Evidence Entry / Preview")

    assert completion < required < entry


def test_required_design_information_appears_before_manual_evidence_entry(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    _render_guided_layout(monkeypatch, fake_st, draft=_project_draft())
    markdowns = _markdowns(fake_st)

    assert _index_containing(markdowns, "Required Design Information") < _index_containing(
        markdowns,
        "Manual Evidence Entry / Preview",
    )


def test_manual_evidence_entry_queue_and_gap_assistant_remain_visible(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    _render_guided_layout(monkeypatch, fake_st, draft=_project_draft())
    rendered = _rendered_text(fake_st)

    assert "Manual Evidence Entry / Preview" in rendered
    assert "Manual Evidence Review Queue" in rendered
    assert "Manual Evidence Gap Assistant" in rendered


def test_existing_r203_manual_evidence_panel_still_works_in_guided_layout(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_input_values[section.R203_MANUAL_EVIDENCE_ENTRY_KEYS["evidence_label"]] = (
        "R208_PANEL_LABEL_PLACEHOLDER"
    )
    fake_st.text_area_values[section.R203_MANUAL_EVIDENCE_ENTRY_KEYS["source_note"]] = (
        "R208_PANEL_SOURCE_NOTE_PLACEHOLDER"
    )
    fake_st.text_area_values[section.R203_MANUAL_EVIDENCE_ENTRY_KEYS["review_note"]] = (
        "R208_PANEL_REVIEW_NOTE_PLACEHOLDER"
    )
    fake_st.text_input_values[section.R203_MANUAL_EVIDENCE_ENTRY_KEYS["traceability_label"]] = (
        "R208_PANEL_TRACE_LABEL_PLACEHOLDER"
    )

    workflow = _render_guided_layout(monkeypatch, fake_st, draft=_project_draft())
    rendered = _rendered_text(fake_st)

    assert fake_st.text_input_calls
    assert fake_st.text_area_calls
    assert workflow["manual_evidence_entry_panel_payload"]["queue_payload"]["summary"]["row_count"] == 1
    assert "R208_PANEL_LABEL_PLACEHOLDER" in rendered
    assert "review needed" in rendered


def test_existing_r206_slot_completion_summary_still_works_in_guided_layout(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_input_values["r206_required_design_slot_target_protein"] = "rice albumin-like protein"
    captured_states: list[dict[str, Any]] = []

    def _build_workflow(workspace_state: dict[str, Any]) -> dict[str, Any]:
        captured_states.append(dict(workspace_state))
        return _workflow()

    workflow = _render_guided_layout(
        monkeypatch,
        fake_st,
        draft=_project_draft(),
        build_workflow=_build_workflow,
    )

    assert captured_states[-1]["design_slot_completion"]["slot_completion_schema_version"] == (
        section.R206_DESIGN_SLOT_COMPLETION_SCHEMA_VERSION
    )
    assert workflow["current_project_draft"]["design_slot_completion_summary"]["completed_slot_count"] == 1
    assert workflow["current_project_draft"]["design_slot_completion_summary"]["missing_slot_count"] == 7


def test_existing_r207_completion_gate_still_works_in_guided_layout(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    workflow = _render_guided_layout(monkeypatch, fake_st, draft=_project_draft())
    gate = workflow["project_review_completion_gate"]

    assert gate["schema_version"] == section.R207_PROJECT_REVIEW_COMPLETION_GATE_SCHEMA_VERSION
    assert gate["route_confirmation"]["status"] == "route_confirmed_for_review"
    assert gate["design_slot_completion"]["missing_slot_count"] == 8
    assert gate["documentation_only"] is True
    assert gate["manual_review_required"] is True


def test_empty_no_project_state_remains_safe(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    workflow = _render_guided_layout(monkeypatch, fake_st)
    rendered = _rendered_text(fake_st)

    assert workflow["advanced_details_visible"] is True
    assert workflow["project_review_completion_gate"]["route_confirmation"]["status"] == "no_current_project_draft"
    assert "no confirmed Simple Plant Wizard route is in session" in rendered
    assert "Manual Evidence Entry / Preview" in rendered
    assert "documentation-only" in rendered


def test_guided_layout_copy_does_not_imply_unsafe_claims(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    workflow = _render_guided_layout(monkeypatch, fake_st, draft=_project_draft())
    lowered = f"{_rendered_text(fake_st)}\n{workflow!r}".casefold()

    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in lowered
    assert "documentation-only" in lowered
    assert "readback-only" in lowered
