# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_workflow_section as section


ROOT = Path(__file__).resolve().parents[1]
CHANGED_FILES = [
    ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py",
    ROOT / "services" / "plant_manual_evidence_input_adapter.py",
    ROOT / "tests" / "test_r203_manual_evidence_entry_panel.py",
    ROOT / "docs" / "qa" / "V2_7_R203_MANUAL_EVIDENCE_ENTRY_PANEL_QA.md",
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
    _term("source ", "verification workflow"),
    _term("approval ", "workflow"),
)

REALISTIC_IDENTIFIER_FRAGMENTS = (
    _term("1", "0."),
    _term("PM", "ID"),
    _term("NC", "BI"),
    _term("Gen", "Bank"),
    _term("Add", "gene"),
    _term("XP", "_"),
    _term("NP", "_"),
    _term("NM", "_"),
)


def _panel_record(**overrides: Any) -> dict[str, Any]:
    record = {
        "evidence_label": "R203_PANEL_LABEL_PLACEHOLDER",
        "source_note": "R203_PANEL_SOURCE_NOTE_PLACEHOLDER",
        "evidence_type": "evidence_note",
        "review_note": "R203_PANEL_REVIEW_NOTE_PLACEHOLDER",
        "traceability_label": "R203_PANEL_TRACE_LABEL_PLACEHOLDER",
        "beginner_preview": False,
        "demo_example": False,
        "conflict_deprecated": False,
    }
    record.update(overrides)
    return record


def _row(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["queue_payload"]["rows"][0]


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


def test_plant_review_renders_manual_evidence_entry_preview_panel(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_manual_evidence_entry_preview_panel(project={}, workflow={})
    rendered = _rendered_text(fake_st)

    assert payload["read_only"] is True
    assert "Manual Evidence Entry / Preview" in rendered
    assert "preflight/readback" in rendered
    assert fake_st.text_input_calls
    assert fake_st.text_area_calls
    assert fake_st.selectbox_calls
    assert fake_st.checkbox_calls
    assert fake_st.download_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_empty_input_shows_safe_empty_preflight_state() -> None:
    payload = section.build_manual_evidence_entry_panel_payload({})

    assert payload["adapter_payload"]["input_summary"]["empty_input"] is True
    assert payload["queue_payload"]["summary"]["row_count"] == 0
    assert payload["package_readback"]["section_status"] == "empty_manual_evidence_queue_readback"
    assert payload["handoff_manual_readback"]["summary"]["row_count"] == 0


def test_source_present_placeholder_entry_becomes_review_needed_not_confirmed() -> None:
    payload = section.build_manual_evidence_entry_panel_payload(_panel_record())
    row = _row(payload)

    assert row["queue_state"] == "review_needed"
    assert row["source_status"]["status"] == "source_present_needs_manual_review"
    assert row["package_draft_support_preview"]["supported"] is False
    assert row["imports_evidence"] is False
    assert row["approval_allowed"] is False


def test_missing_source_entry_becomes_blocked_with_visible_reason() -> None:
    payload = section.build_manual_evidence_entry_panel_payload(_panel_record(source_note=""))
    row = _row(payload)

    assert row["queue_state"] == "blocked"
    assert row["source_status"]["status"] == "missing_source"
    assert "missing source trail" in row["visible_blocking_reasons"]


def test_beginner_preview_entry_becomes_preview_only() -> None:
    payload = section.build_manual_evidence_entry_panel_payload(
        _panel_record(beginner_preview=True)
    )
    row = _row(payload)

    assert row["queue_state"] == "preview_only"
    assert row["admission_gate_alignment"]["beginner_preview_allowed"] is True
    assert row["package_support_readback"]["supported"] is False


def test_demo_example_entry_remains_blocked_for_package_support() -> None:
    payload = section.build_manual_evidence_entry_panel_payload(
        _panel_record(demo_example=True)
    )
    row = _row(payload)

    assert row["queue_state"] == "blocked"
    assert row["package_support_readback"]["supported"] is False
    assert row["placeholder_demo_example_status"]["has_placeholder_values"] is True


def test_conflict_deprecated_entry_remains_blocked() -> None:
    payload = section.build_manual_evidence_entry_panel_payload(
        _panel_record(conflict_deprecated=True)
    )
    row = _row(payload)

    assert row["queue_state"] == "blocked"
    assert row["package_support_readback"]["supported"] is False
    assert "conflict_status is unresolved" in row["visible_blocking_reasons"]
    assert "record or source is deprecated" in row["visible_blocking_reasons"]


def test_traceability_label_and_review_note_are_preserved() -> None:
    payload = section.build_manual_evidence_entry_panel_payload(_panel_record())
    normalized = payload["adapter_payload"]["normalized_manual_evidence_records"][0]

    assert normalized["adapter_traceability"]["traceability_label"] == "R203_PANEL_TRACE_LABEL_PLACEHOLDER"
    assert normalized["evidence_entry_metadata"]["notes_for_curator"] == "R203_PANEL_REVIEW_NOTE_PLACEHOLDER"
    assert normalized["provenance_and_review"]["reviewer_note"] == "R203_PANEL_REVIEW_NOTE_PLACEHOLDER"


def test_plant_review_queue_renders_populated_rows_from_panel_input(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_input_values[section.R203_MANUAL_EVIDENCE_ENTRY_KEYS["evidence_label"]] = (
        "R203_PANEL_LABEL_PLACEHOLDER"
    )
    fake_st.text_area_values[section.R203_MANUAL_EVIDENCE_ENTRY_KEYS["source_note"]] = (
        "R203_PANEL_SOURCE_NOTE_PLACEHOLDER"
    )
    fake_st.text_area_values[section.R203_MANUAL_EVIDENCE_ENTRY_KEYS["review_note"]] = (
        "R203_PANEL_REVIEW_NOTE_PLACEHOLDER"
    )
    fake_st.text_input_values[section.R203_MANUAL_EVIDENCE_ENTRY_KEYS["traceability_label"]] = (
        "R203_PANEL_TRACE_LABEL_PLACEHOLDER"
    )
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_manual_evidence_entry_preview_panel(project={}, workflow={})
    rendered = _rendered_text(fake_st)

    assert payload["queue_payload"]["summary"]["row_count"] == 1
    assert "R203_PANEL_LABEL_PLACEHOLDER" in rendered
    assert "review needed" in rendered
    assert "supported: no" in rendered


def test_package_and_handoff_readback_consume_panel_derived_adapter_output() -> None:
    payload = section.build_manual_evidence_entry_panel_payload(_panel_record())

    assert payload["package_readback"]["summary"]["row_count"] == 1
    assert payload["package_presenter_manual_readback"]["summary"]["row_count"] == 1
    assert payload["handoff_manual_readback"]["summary"]["row_count"] == 1
    assert payload["handoff_manual_readback"]["permissions"]["imports_evidence"] is False
    assert payload["handoff_manual_readback"]["permissions"]["package_export_permission"] is False


def test_ui_copy_keeps_r203_boundaries() -> None:
    payload = section.build_manual_evidence_entry_panel_payload(_panel_record())
    combined_output = repr(payload)
    changed_text = "\n".join(path.read_text(encoding="utf-8") for path in CHANGED_FILES if path.exists())
    lowered = f"{combined_output}\n{changed_text}".casefold()

    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in lowered
    for fragment in REALISTIC_IDENTIFIER_FRAGMENTS:
        assert fragment not in combined_output
        assert fragment not in changed_text
    assert _term("source", "_", "verified") not in combined_output
    assert _term("source", "_", "verified") not in changed_text
    assert "documentation-only" in changed_text
    assert payload["adapter_payload"]["permissions"]["database_write_allowed"] is False
    assert payload["queue_payload"]["automatic_import_allowed"] is False


def test_output_remains_deterministic_and_plain_dict_list() -> None:
    first = section.build_manual_evidence_entry_panel_payload(_panel_record())
    second = section.build_manual_evidence_entry_panel_payload(_panel_record())

    assert first == second
    _assert_plain(first)
