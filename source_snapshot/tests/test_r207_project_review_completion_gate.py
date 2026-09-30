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
    _term("vali", "dated ", "construct"),
    _term("optimized ", "pathway"),
    _term("yield ", "prediction"),
    _term("wet", "-lab ", "ready"),
    _term("source ", "verification"),
    _term("appro", "val ", "workflow"),
    _term("export ", "permission"),
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


def _filled_values(**overrides: str) -> dict[str, str]:
    values = {
        "target_protein": "rice albumin-like protein",
        "target_gene_or_cds": "albumin-like CDS documentation note",
        "host_plant": "rice host documentation context",
        "expression_context": "seed expression documentation context",
        "promoter_or_regulatory_element": "promoter documentation note",
        "terminator": "terminator documentation note",
        "marker_or_reporter": "marker documentation note",
        "vector_or_backbone": "vector documentation note",
        "notes": "",
    }
    values.update(overrides)
    return values


def _draft_with_slots(**overrides: str) -> dict[str, Any]:
    draft = _project_draft()
    completion = section.build_required_design_slot_completion_payload(
        project_draft_payload=draft,
        slot_values=_filled_values(**overrides),
    )
    draft["design_slot_completion"] = completion
    draft["design_slot_completion_summary"] = completion["completion_summary"]
    return draft


def _panel_record(**overrides: Any) -> dict[str, Any]:
    record = {
        "evidence_label": "R207_PANEL_LABEL_PLACEHOLDER",
        "source_note": "R207_PANEL_SOURCE_NOTE_PLACEHOLDER",
        "evidence_type": "evidence_note",
        "review_note": "R207_PANEL_REVIEW_NOTE_PLACEHOLDER",
        "traceability_label": "R207_PANEL_TRACE_LABEL_PLACEHOLDER",
        "beginner_preview": False,
        "demo_example": False,
        "conflict_deprecated": False,
    }
    record.update(overrides)
    return record


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
            "missing_information_items": [],
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


def _gate(
    draft: dict[str, Any] | None,
    panel: dict[str, Any] | None = None,
    workflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return section.build_project_review_completion_gate_payload(
        project_draft_payload=draft,
        workflow=workflow or _workflow(),
        manual_evidence_panel_payload=panel,
    )


def test_no_route_project_draft_shows_safe_empty_completion_state() -> None:
    payload = section.build_project_review_completion_gate_payload(
        project_draft_payload=None,
        workflow=None,
        manual_evidence_panel_payload=None,
    )

    assert payload["read_only"] is True
    assert payload["session_state_only"] is True
    assert payload["route_confirmation"]["status"] == "no_current_project_draft"
    assert payload["design_slot_completion"]["completed_slot_count"] == 0
    assert payload["design_slot_completion"]["missing_slot_count"] == 0
    assert payload["package_handoff_readback"]["status"] == "safe_empty_readback"


def test_r205_route_handoff_shows_route_confirmed_but_design_slots_missing() -> None:
    payload = _gate(_project_draft())

    assert payload["route_confirmation"]["status"] == "route_confirmed_for_review"
    assert payload["design_slot_completion"]["status"] == "required_design_slots_missing"
    assert payload["design_slot_completion"]["missing_slot_count"] == 8
    assert payload["package_handoff_readback"]["status"] == "blocked_readback_only"


def test_r206_filled_slots_update_completed_and_missing_counts() -> None:
    payload = _gate(_draft_with_slots(promoter_or_regulatory_element=""))

    assert payload["design_slot_completion"]["completed_slot_count"] == 7
    assert payload["design_slot_completion"]["missing_slot_count"] == 1
    assert payload["design_slot_completion"]["total_required_slot_count"] == 8


def test_missing_required_slots_appear_as_top_blockers() -> None:
    payload = _gate(_project_draft())
    blockers = payload["top_blockers"]

    assert blockers[0]["Type"] == "missing_required_design_slots"
    assert blockers[0]["Count"] == 8
    assert "Target protein" in blockers[0]["Blocker"]


def test_manual_evidence_missing_source_row_appears_as_evidence_blocker() -> None:
    panel = section.build_manual_evidence_entry_panel_payload(
        _panel_record(source_note="")
    )
    payload = _gate(_draft_with_slots(), panel)
    blocker_types = {row["Type"] for row in payload["top_blockers"]}

    assert "missing_source_notes" in blocker_types
    assert payload["manual_evidence"]["blocked_count"] == 1
    assert payload["manual_evidence"]["next_action"] == "Add source note."


def test_beginner_preview_manual_evidence_row_appears_as_preview_only_blocker() -> None:
    panel = section.build_manual_evidence_entry_panel_payload(
        _panel_record(beginner_preview=True)
    )
    payload = _gate(_draft_with_slots(), panel)
    blocker_types = {row["Type"] for row in payload["top_blockers"]}

    assert "preview_only_evidence" in blocker_types
    assert payload["manual_evidence"]["preview_only_count"] == 1


def test_completed_design_slots_plus_blocked_manual_evidence_keeps_package_status_blocked() -> None:
    panel = section.build_manual_evidence_entry_panel_payload(
        _panel_record(conflict_deprecated=True)
    )
    payload = _gate(_draft_with_slots(), panel)

    assert payload["design_slot_completion"]["missing_slot_count"] == 0
    assert payload["manual_evidence"]["blocked_count"] == 1
    assert payload["package_handoff_readback"]["status"] == "blocked_readback_only"
    assert any(row["Type"] == "conflict_deprecated_markers" for row in payload["top_blockers"])


def test_safe_next_actions_point_to_slot_completion_and_manual_evidence_gaps() -> None:
    panel = section.build_manual_evidence_entry_panel_payload(
        _panel_record(source_note="", evidence_type="")
    )
    payload = _gate(_project_draft(), panel)
    actions = {row["Action"] for row in payload["safe_next_actions"]}

    assert "Fill required design information" in actions
    assert "Add source note" in actions
    assert "Add evidence type" in actions
    assert "Refresh package readback" in actions


def test_manual_evidence_entry_panel_still_renders_with_completion_gate(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.session_state[section.SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY] = _project_draft()
    fake_st.checkbox_values[section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(section, "st", fake_st)
    monkeypatch.setattr(section, "render_plant_goal_review_package_draft_visible_mvp", lambda: {})
    monkeypatch.setattr(section, "render_plant_review_handoff_preview_section", lambda _payload: None)
    monkeypatch.setattr(section, "render_rice_albumin_seed_review_visible_mount", lambda: None)

    workflow = section.render_plant_review_workflow_section(
        project={},
        steps=[],
        expression_links=[],
        test_records=[],
        review_signals=[],
        build_workflow=lambda _state: _workflow(),
    )
    rendered = _rendered_text(fake_st)

    assert "Manual Evidence Entry / Preview" in rendered
    assert section.R207_PROJECT_REVIEW_COMPLETION_GATE_TITLE in rendered
    assert "Project Review Completion status" in rendered
    assert workflow["project_review_completion_gate"]["schema_version"] == (
        section.R207_PROJECT_REVIEW_COMPLETION_GATE_SCHEMA_VERSION
    )


def test_changed_copy_does_not_imply_unsafe_completion_claims() -> None:
    panel = section.build_manual_evidence_entry_panel_payload(
        _panel_record(beginner_preview=True, conflict_deprecated=True)
    )
    payload = _gate(_project_draft(), panel)
    lowered = repr(payload).casefold()

    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in lowered
    assert "documentation-only" in lowered
    assert "readback-only" in lowered
    assert payload["documentation_only"] is True
    assert payload["manual_review_required"] is True
