# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from tests.helpers.fake_streamlit import FakeStreamlit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.plant_construct_task_readback_gate import build_construct_task_readback_gate
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
    ROOT / "services" / "plant_construct_task_readback_gate.py",
    ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py",
    ROOT / "tests" / "test_r222_construct_task_readback_gate.py",
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
    _term("lab", "-ready"),
    _term("proven ", "construct"),
    _term("validated ", "pathway"),
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
        "evidence_label": "R222_PANEL_LABEL_PLACEHOLDER",
        "source_note": "R222_PANEL_SOURCE_NOTE_PLACEHOLDER",
        "evidence_type": "evidence_note",
        "review_note": "R222_PANEL_REVIEW_NOTE_PLACEHOLDER",
        "traceability_label": "R222_PANEL_TRACE_LABEL_PLACEHOLDER",
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


def _candidate_payload(
    draft: dict[str, Any] | None,
    panel: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    panel_payload = panel if panel is not None else section.build_manual_evidence_entry_panel_payload({})
    gate = section.build_project_review_completion_gate_payload(
        project_draft_payload=draft,
        workflow=_workflow(),
        manual_evidence_panel_payload=panel_payload,
    )
    candidate = build_candidate_route_review_draft(
        project_draft_payload=draft,
        workflow=_workflow(),
        manual_evidence_panel_payload=panel_payload,
        completion_gate_payload=gate,
    )
    return candidate, gate


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


def test_empty_candidate_route_blocks_construct_task_readback() -> None:
    candidate, gate = _candidate_payload(None)
    payload = build_construct_task_readback_gate(
        candidate_route_review_draft=candidate,
        completion_gate_payload=gate,
    )

    assert payload["can_enter_construct_task_draft_readback"] is False
    assert payload["construct_task_created"] is False
    assert payload["construct_draft_created"] is False
    assert any(row["Reason code"] == "missing_candidate_route" for row in payload["blocked_reasons"])


def test_missing_design_slots_are_next_completion_items() -> None:
    candidate, gate = _candidate_payload(_project_draft())
    payload = build_construct_task_readback_gate(
        candidate_route_review_draft=candidate,
        completion_gate_payload=gate,
    )

    assert payload["gate_status"] == "construct_task_draft_readback_blocked"
    assert any(row["Reason code"] == "missing_required_design_slot" for row in payload["blocked_reasons"])
    assert any(row["Action"] == "Fill required design information." for row in payload["next_completion_items"])


def test_manual_evidence_blocker_blocks_construct_task_readback() -> None:
    panel = section.build_manual_evidence_entry_panel_payload(_panel_record(source_note=""))
    candidate, gate = _candidate_payload(_draft_with_slots(), panel)
    payload = build_construct_task_readback_gate(
        candidate_route_review_draft=candidate,
        completion_gate_payload=gate,
    )

    assert payload["can_enter_construct_task_draft_readback"] is False
    assert any(row["Reason code"] == "missing_source_notes" for row in payload["blocked_reasons"])
    assert any(row["Action"] == "Add source note." for row in payload["next_completion_items"])


def test_completed_slots_without_evidence_blockers_allow_readback_only_entry() -> None:
    candidate, gate = _candidate_payload(_draft_with_slots())
    payload = build_construct_task_readback_gate(
        candidate_route_review_draft=candidate,
        completion_gate_payload=gate,
    )

    assert payload["can_enter_construct_task_draft_readback"] is True
    assert payload["gate_status"] == "construct_task_draft_readback_available"
    assert payload["blocked_reasons"] == []
    assert payload["sequence_generated"] is False


def test_construct_task_readback_gate_renders_in_plant_review_workflow(monkeypatch) -> None:
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

    assert "Construct Task Readback Gate" in rendered
    assert "Construct Task Readback Gate blockers" in rendered
    assert "construct_task_readback_gate" in workflow
    assert workflow["construct_task_readback_gate"]["construct_task_created"] is False


def test_construct_task_readback_gate_copy_avoids_unsafe_claims() -> None:
    candidate, gate = _candidate_payload(_draft_with_slots())
    payload = build_construct_task_readback_gate(
        candidate_route_review_draft=candidate,
        completion_gate_payload=gate,
    )
    changed_text = "\n".join(path.read_text(encoding="utf-8") for path in CHANGED_FILES if path.exists())
    lowered = f"{payload!r}\n{changed_text}".casefold()

    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in lowered
    assert "documentation" in lowered
    assert "read-only" in lowered
