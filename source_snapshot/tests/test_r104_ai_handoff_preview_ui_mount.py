# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect

from tests.helpers.fake_streamlit import FakeStreamlit
import views.PlantDesignWorkspace as workspace
import views.tool_typography as tool_typography


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.expander_calls]
        + [f"{call['label']}: {call['value']}" for call in fake_st.metric_calls]
    )


def test_r104_ai_handoff_preview_is_in_workspace_model() -> None:
    model = workspace.build_plant_design_workspace_shell_model()
    preview = model["ai_handoff_preview"]

    assert "AI-guided Plant Design Handoff Preview" in model["section_labels"]
    assert preview["title"] == "AI-guided Plant Design Handoff Preview"
    assert preview["read_only"] is True
    assert preview["persistent"] is False
    assert preview["scope_category"] == "company_handoff_request"
    assert preview["preview_status"] == "supported plant mock preview"
    assert preview["status_badges"][0]["value"] == preview["preview_status"]
    assert preview["allowed_outputs"]
    assert preview["blocked_outputs"]
    assert preview["boundary_statements"]
    assert preview["parsed_intent_rows"]
    assert preview["empty_state"]["is_empty"] is False
    assert any(row["Field"] == "Original user request" for row in preview["request_scope_rows"])
    assert any(row["Readback"] == "rice" for row in preview["design_intent_rows"])
    assert any(row["Readback"] == "seed" for row in preview["plant_context_rows"])
    assert preview["missing_information_rows"]
    assert preview["component_candidate_rows"]
    assert preview["construct_slot_rows"]
    assert preview["handoff_section_rows"]


def test_r104_ai_handoff_preview_renders_without_write_controls(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)

    model = workspace.render()
    rendered = _rendered_text(fake_st)

    assert model["ai_handoff_preview"]["title"] == "AI-guided Plant Design Handoff Preview"
    assert "AI-guided Plant Design Handoff Preview" in rendered
    assert "Fixed rice albumin-like read-only mock preview - deterministic fixture - manual review required" in rendered
    assert "Original user request" in rendered
    assert "Safety / scope decision" in rendered
    assert "Allowed outputs" in rendered
    assert "Blocked outputs" in rendered
    assert "User-input Plant Design Mock Preview" in rendered
    assert "Parsed design intent" in rendered
    assert "Plant design context" in rendered
    assert "Construct draft slot scaffold" in rendered
    assert "Company handoff draft sections" in rendered
    assert "Manual review status" in rendered
    assert "albumin-like protein" in rendered
    assert "rice" in rendered
    assert "seed" in rendered
    assert "documentation-only, non-operational" in rendered
    assert "draft slots only" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.text_input_calls == []
    assert len(fake_st.text_area_calls) == 1
    assert "deterministic preview only; not saved" in fake_st.text_area_calls[0]["label"]
    assert fake_st.file_uploader_calls == []
    assert fake_st.dataframes == []
    assert fake_st.tables == []


def test_r104_workspace_source_does_not_add_persistence_export_or_ai_paths() -> None:
    source = inspect.getsource(workspace).casefold()

    forbidden_markers = [
        "download_button",
        "form_submit_button",
        "st.button",
        "text_input",
        "file_uploader",
        "session_state",
        "sqlite",
        "project_import",
        "project_export",
        "package_export_service",
        "export_package",
        "save_",
        "write_",
        "insert",
        "update",
        "delete",
        "openai",
        "requests",
        "httpx",
        "fasta",
        "genbank",
        "codon",
        "sequence_output",
    ]

    assert [marker for marker in forbidden_markers if marker in source] == []
