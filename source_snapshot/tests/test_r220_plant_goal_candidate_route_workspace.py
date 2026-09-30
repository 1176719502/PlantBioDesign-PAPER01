# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from tests.helpers.fake_streamlit import FakeStreamlit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.plant_candidate_route_review_draft import build_candidate_route_review_draft
from services.plant_simple_wizard_route_checklist_presenter import (
    build_simple_plant_wizard_route_checklist_presenter,
)
from services.plant_simple_wizard_route_confirmation_presenter import (
    build_simple_plant_wizard_route_confirmation_presenter,
)
from views.pathway_workspace_sections import plant_review_workflow_section as section


GOAL_TEXT = "Document a rice seed protein expression design draft for manual review."
ROUTE_ID = "plant_protein_expression_review"
CHANGED_FILES = (
    ROOT / "services" / "plant_candidate_route_review_draft.py",
    ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py",
    ROOT / "tests" / "test_r220_plant_goal_candidate_route_workspace.py",
    ROOT / "docs" / "qa" / "V2_7_R220_PLANT_GOAL_CANDIDATE_ROUTE_WORKSPACE_QA.md",
)


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
    _term("export ", "permission"),
    _term("approved ", "evidence"),
)

REALISTIC_IDENTIFIER_FRAGMENTS = (
    _term("PM", "ID"),
    _term("NC", "BI"),
    _term("Gen", "Bank"),
    _term("Add", "gene"),
    _term("XP", "_"),
    _term("NP", "_"),
    _term("NM", "_"),
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
        "evidence_label": "R220_PANEL_LABEL_PLACEHOLDER",
        "source_note": "R220_PANEL_SOURCE_NOTE_PLACEHOLDER",
        "evidence_type": "evidence_note",
        "review_note": "R220_PANEL_REVIEW_NOTE_PLACEHOLDER",
        "traceability_label": "R220_PANEL_TRACE_LABEL_PLACEHOLDER",
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


def _candidate(
    draft: dict[str, Any] | None,
    panel: dict[str, Any] | None = None,
    workflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    panel_payload = panel if panel is not None else section.build_manual_evidence_entry_panel_payload({})
    return build_candidate_route_review_draft(
        project_draft_payload=draft,
        workflow=workflow or _workflow(),
        manual_evidence_panel_payload=panel_payload,
        completion_gate_payload=_gate(draft, panel_payload, workflow),
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


def test_empty_no_project_draft_shows_safe_candidate_route_state() -> None:
    payload = _candidate(None, workflow={})

    assert payload["read_only"] is True
    assert payload["documentation_only"] is True
    assert payload["current_plant_goal"] == "No plant goal is recorded."
    assert payload["route_readback"]["route_review_status"] == "safe_empty_candidate_route_draft"
    assert payload["construct_task_created"] is False


def test_r205_route_confirmed_draft_appears_in_candidate_route_readback() -> None:
    payload = _candidate(_project_draft())

    assert payload["current_plant_goal"] == GOAL_TEXT
    assert payload["route_readback"]["route_id"] == ROUTE_ID
    assert payload["route_readback"]["route_confirmation_status"] == "route_confirmed_for_review"
    assert "Plant Protein Expression Review" in payload["route_readback"]["route_label"]


def test_r206_completed_design_slots_affect_route_review_status() -> None:
    payload = _candidate(_draft_with_slots())

    assert payload["required_design_slots"]["completed_slot_count"] == 8
    assert payload["required_design_slots"]["missing_slot_count"] == 0
    assert payload["route_readback"]["route_review_status"] == "reviewable_draft_only"
    assert payload["draft_only"] is True


def test_missing_required_design_slots_appear_as_blockers() -> None:
    payload = _candidate(_project_draft())
    blocker_types = {row["Type"] for row in payload["blocker_rows"]}

    assert payload["required_design_slots"]["missing_slot_count"] == 8
    assert "missing_required_design_slots" in blocker_types
    assert payload["route_readback"]["route_review_status"] == "blocked_by_required_design_slots"


def test_manual_evidence_blocked_state_appears_as_evidence_blocker() -> None:
    panel = section.build_manual_evidence_entry_panel_payload(_panel_record(source_note=""))
    payload = _candidate(_draft_with_slots(), panel)
    blocker_types = {row["Type"] for row in payload["evidence_blockers"]}

    assert "missing_source_notes" in blocker_types
    assert payload["manual_evidence"]["blocked_count"] == 1
    assert payload["route_readback"]["route_review_status"] == "blocked_by_manual_evidence"


def test_manual_evidence_preview_only_state_remains_preview_readback_only() -> None:
    panel = section.build_manual_evidence_entry_panel_payload(_panel_record(beginner_preview=True))
    payload = _candidate(_draft_with_slots(), panel)
    actions = {row["Action"] for row in payload["safe_next_actions"]}

    assert payload["manual_evidence"]["preview_only_count"] == 1
    assert any(row["Type"] == "preview_only_evidence" for row in payload["evidence_blockers"])
    assert "Review manual evidence gaps" in actions
    assert payload["can_advance_to_construct_task"] is False


def test_candidate_route_draft_does_not_create_construct_task_or_package_handoff() -> None:
    payload = _candidate(_draft_with_slots())

    assert payload["construct_task_created"] is False
    assert payload["construct_draft_created"] is False
    assert payload["can_advance_to_construct_task"] is False
    assert payload["package_handoff_readback"]["status"] in {"manual_review_readback_only", "not recorded"}


def test_safe_next_actions_point_to_slots_and_manual_evidence_gap_assistant() -> None:
    panel = section.build_manual_evidence_entry_panel_payload(_panel_record(source_note="", evidence_type=""))
    payload = _candidate(_project_draft(), panel)
    actions_by_area = {(row["Area"], row["Action"]) for row in payload["safe_next_actions"]}

    assert ("Required design slots", "Fill required design information") in actions_by_area
    assert ("Manual evidence gap assistant", "Review manual evidence gaps") in actions_by_area
    assert any(action == "Add source note" for _area, action in actions_by_area)


def test_existing_plant_review_sections_still_render_with_candidate_route(monkeypatch) -> None:
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

    assert "Current project draft" in rendered
    assert section.R207_PROJECT_REVIEW_COMPLETION_GATE_TITLE in rendered
    assert section.R206_REQUIRED_DESIGN_SLOT_PANEL_TITLE in rendered
    assert "Manual Evidence Entry / Preview" in rendered
    assert "Manual Evidence Gap Assistant" in rendered
    assert "Candidate Route Review Draft" in rendered
    assert section.R208_PACKAGE_HANDOFF_ENTRY_TITLE in rendered
    assert "candidate_route_review_draft" in workflow


def test_candidate_route_copy_does_not_imply_unsafe_claims() -> None:
    panel = section.build_manual_evidence_entry_panel_payload(
        _panel_record(beginner_preview=True, conflict_deprecated=True)
    )
    payload = _candidate(_project_draft(), panel)
    changed_text = "\n".join(path.read_text(encoding="utf-8") for path in CHANGED_FILES if path.exists())
    lowered = f"{payload!r}\n{changed_text}".casefold()

    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in lowered
    for fragment in REALISTIC_IDENTIFIER_FRAGMENTS:
        assert fragment not in changed_text
    assert "documentation-only" in lowered
    assert "read-only" in lowered
    assert payload["manual_review_required"] is True
