# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_manual_evidence_gap_assistant import (
    build_manual_evidence_gap_assistant,
)
from services.plant_manual_evidence_input_adapter import (
    build_manual_evidence_input_adapter_payload,
)
from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_workflow_section as section


ROOT = Path(__file__).resolve().parents[1]
CHANGED_FILES = [
    ROOT / "services" / "plant_manual_evidence_gap_assistant.py",
    ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py",
    ROOT / "tests" / "test_r204_manual_evidence_gap_assistant.py",
    ROOT / "docs" / "qa" / "V2_7_R204_MANUAL_EVIDENCE_GAP_ASSISTANT_QA.md",
]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY_FRAGMENTS = (
    _term("successful ", "import"),
    _term("project ", "imported"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("source", "_", "verified"),
)


def _manual_record(record_id: str = "R204_ENTRY_ALPHA", **overrides: Any) -> dict[str, Any]:
    record = {
        "record_id": record_id,
        "evidence_label": f"{record_id}_LABEL_PLACEHOLDER",
        "source_note": f"{record_id}_SOURCE_NOTE_PLACEHOLDER",
        "route_scope": "plant_protein_expression_review",
        "evidence_type": "evidence_note",
        "manual_review_status": "needs_manual_review",
        "allowed_usage_scope": "manual_review_only",
        "demo_or_real_flag": "user_supplied_unverified",
        "provenance_status": "source_present_needs_review",
        "conflict_status": "no_known_conflict",
        "review_note": f"{record_id}_REVIEW_NOTE_PLACEHOLDER",
        "traceability_label": f"{record_id}_TRACE_LABEL_PLACEHOLDER",
        "manual_evidence": True,
    }
    record.update(overrides)
    return record


def _adapter(records: list[dict[str, Any]]) -> dict[str, Any]:
    return build_manual_evidence_input_adapter_payload(
        {
            "project_id": "R204_PROJECT_PLACEHOLDER",
            "workflow_id": "R204_WORKFLOW_PLACEHOLDER",
            "manual_evidence_records": records,
        }
    )


def _first_row(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["rows"][0]


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.subheaders
        + fake_st.info_messages
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [frame.to_string(index=False) for frame in fake_st.dataframes]
    )


def _assert_plain(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            assert isinstance(key, str)
            _assert_plain(child)
        return
    if isinstance(value, list):
        for child in value:
            _assert_plain(child)
        return
    assert value is None or isinstance(value, (str, int, float, bool))


def test_empty_payload_returns_safe_empty_gap_assistant_output() -> None:
    payload = build_manual_evidence_gap_assistant([])

    assert payload["empty_state"]["is_empty"] is True
    assert payload["summary"]["row_count"] == 0
    assert payload["rows"] == []
    assert payload["permissions"]["package_export_permission"] is False
    assert payload["empty_state"]["safe_next_actions"]


def test_source_present_placeholder_evidence_returns_review_needed_not_confirmed() -> None:
    payload = build_manual_evidence_gap_assistant(_adapter([_manual_record()]))
    row = _first_row(payload)

    assert row["queue_state"] == "review_needed"
    assert "manual review readback" in row["state_explanation"]
    assert row["source_status"]["status"] == "source_present_needs_manual_review"
    assert row["package_draft_support_preview"]["supported"] is False
    assert row["experiment_confirmation"] is False


def test_missing_source_evidence_returns_missing_source_gap_and_blocked_explanation() -> None:
    payload = build_manual_evidence_gap_assistant(
        _adapter([_manual_record("R204_ENTRY_MISSING_SOURCE", source_note="")])
    )
    row = _first_row(payload)

    assert row["queue_state"] == "blocked"
    assert "source_note" in row["missing_fields"]
    assert "missing source trail" in row["blocking_reasons_preserved"]
    assert "Add a source note" in row["safe_next_data_completion_actions"][0]


def test_beginner_preview_evidence_returns_preview_only_package_support_blocker() -> None:
    payload = build_manual_evidence_gap_assistant(
        _adapter(
            [
                _manual_record(
                    "R204_ENTRY_PREVIEW",
                    readback_state="preview_only",
                    allowed_usage_scope="beginner_preview",
                )
            ]
        )
    )
    row = _first_row(payload)

    assert row["queue_state"] == "preview_only"
    assert "beginner preview" in row["state_explanation"]
    assert "Package support remains blocked/readback-only" in row["package_support_explanation"]
    assert "Keep beginner preview separate from package support." in row["safe_next_data_completion_actions"]


def test_demo_example_evidence_remains_blocked_for_package_support() -> None:
    payload = build_manual_evidence_gap_assistant(
        _adapter(
            [
                _manual_record(
                    "R204_ENTRY_DEMO",
                    demo_or_real_flag="demo_example",
                    allowed_usage_scope="demo_only",
                )
            ]
        )
    )
    row = _first_row(payload)

    assert row["queue_state"] == "blocked"
    assert row["package_draft_support_preview"]["supported"] is False
    assert "Keep demo/example material as manual-review-only context." in row["safe_next_data_completion_actions"]


def test_conflict_deprecated_evidence_returns_blocker_and_safe_action() -> None:
    payload = build_manual_evidence_gap_assistant(
        _adapter(
            [
                _manual_record(
                    "R204_ENTRY_CONFLICT",
                    conflict_status="unresolved",
                    deprecated_flag=True,
                )
            ]
        )
    )
    row = _first_row(payload)

    assert row["queue_state"] == "blocked"
    assert "conflict_status is unresolved" in row["blocking_reasons_preserved"]
    assert "record or source is deprecated" in row["blocking_reasons_preserved"]
    assert "Resolve the conflict/deprecated marker before package readback use." in row["safe_next_data_completion_actions"]


def test_missing_evidence_type_review_note_and_traceability_label_are_surfaced() -> None:
    payload = build_manual_evidence_gap_assistant(
        _adapter(
            [
                _manual_record(
                    "R204_ENTRY_FIELD_GAPS",
                    evidence_type="",
                    review_note="",
                    traceability_label="",
                )
            ]
        )
    )
    row = _first_row(payload)

    assert "evidence_type" in row["missing_fields"]
    assert "review_note" in row["missing_fields"]
    assert "traceability_label" in row["missing_fields"]
    assert "Add a safe manual evidence type." in row["safe_next_data_completion_actions"]
    assert "Add a review note for manual follow-up." in row["safe_next_data_completion_actions"]
    assert "Add a traceability label for local readback." in row["safe_next_data_completion_actions"]


def test_warnings_blocking_reasons_and_r189_alignment_are_preserved() -> None:
    adapted = _adapter([_manual_record("R204_ENTRY_WARNING")])
    adapted["manual_evidence_review_queue_payload"]["rows"][0]["visible_warnings"] = [
        "R204_WARNING_PLACEHOLDER"
    ]
    adapted["manual_evidence_review_queue_payload"]["rows"][0]["visible_blocking_reasons"] = [
        "R204_BLOCKER_PLACEHOLDER"
    ]
    payload = build_manual_evidence_gap_assistant(adapted)
    row = _first_row(payload)

    assert row["warnings_preserved"] == ["R204_WARNING_PLACEHOLDER"]
    assert row["blocking_reasons_preserved"] == ["R204_BLOCKER_PLACEHOLDER"]
    assert row["r189_admission_gate_alignment"]["r189_gate_used"] is True
    assert row["traceability_readback"]["record_id"] == "R204_ENTRY_WARNING"


def test_plant_review_renders_gap_assistant_section(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_manual_evidence_gap_assistant_preview(
        _adapter([_manual_record("R204_ENTRY_UI")])
    )
    rendered = _rendered_text(fake_st)

    assert payload["summary"]["row_count"] == 1
    assert "Manual Evidence Gap Assistant" in rendered
    assert "R204_ENTRY_UI_LABEL_PLACEHOLDER" in rendered
    assert any(call["label"] == "Full Manual Evidence Gap Assistant table" for call in fake_st.expander_calls)


def test_panel_input_queue_gap_assistant_path_is_deterministic() -> None:
    panel_record = {
        "evidence_label": "R204_PANEL_LABEL_PLACEHOLDER",
        "source_note": "R204_PANEL_SOURCE_NOTE_PLACEHOLDER",
        "evidence_type": "evidence_note",
        "review_note": "R204_PANEL_REVIEW_NOTE_PLACEHOLDER",
        "traceability_label": "R204_PANEL_TRACE_LABEL_PLACEHOLDER",
        "beginner_preview": False,
        "demo_example": False,
        "conflict_deprecated": False,
    }
    first = section.build_manual_evidence_entry_panel_payload(panel_record)
    second = section.build_manual_evidence_entry_panel_payload(panel_record)

    assert first["queue_payload"]["summary"]["row_count"] == 1
    assert first["gap_assistant_payload"] == second["gap_assistant_payload"]
    assert first["gap_assistant_payload"]["rows"][0]["evidence_label"] == "R204_PANEL_LABEL_PLACEHOLDER"
    _assert_plain(first["gap_assistant_payload"])


def test_changed_copy_keeps_manual_evidence_gap_boundaries() -> None:
    payload = build_manual_evidence_gap_assistant(_adapter([_manual_record()]))
    combined_output = repr(payload)
    changed_text = "\n".join(
        path.read_text(encoding="utf-8") for path in CHANGED_FILES if path.exists() and path.name != "plant_review_workflow_section.py"
    )
    lowered = f"{combined_output}\n{changed_text}".casefold()

    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in lowered
    assert payload["permissions"]["biological_decision_advice"] is False
    assert payload["permissions"]["downstream_use_judgment"] is False
    assert "documentation-only" in changed_text
