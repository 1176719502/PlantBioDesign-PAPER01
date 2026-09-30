from __future__ import annotations

import inspect
from pathlib import Path

from tests.helpers.fake_streamlit import FakeStreamlit
import views.PlantDesignWorkspace as workspace
import views.tool_typography as tool_typography


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_PRODUCT_CLAIMS = (
    _term("recom", "mended"),
    _term("optimized"),
    _term("be", "st"),
    _term("ready to build"),
    _term("experiment", "-ready"),
    _term("guaranteed expression"),
    _term("high", "-yield"),
    _term("successful production"),
    _term("wet", "-lab ready"),
    _term("feasible"),
)


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    dataframe_text = "\n".join(
        frame.to_string(index=False) if hasattr(frame, "to_string") else str(frame)
        for frame in fake_st.dataframes
    )
    code_text = "\n".join(call["body"] for call in fake_st.code_calls)
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
        + dataframe_text.splitlines()
        + code_text.splitlines()
    )


def test_workspace_model_contains_required_shell_labels_and_boundary_copy() -> None:
    model = workspace.build_plant_design_workspace_shell_model()

    assert model["page_title"] == "Plant Design Workspace"
    assert "Documentation-only plant design review workspace" in model["subtitle"]
    assert "manual review" in model["subtitle"]
    assert "experimental validation" in model["subtitle"]
    assert model["read_only"] is True
    assert model["section_labels"] == list(workspace.SECTION_LABELS)
    assert "Plant route review chain overview" in model["section_labels"]
    assert "User-input Plant Design Mock Preview" in model["section_labels"]
    assert "Framework coverage summary" in model["section_labels"]
    assert "Route template registry readback" in model["section_labels"]
    assert "Module card registry readback" in model["section_labels"]
    assert "Example walkthrough readback" in model["section_labels"]
    assert "Route draft summary" in model["section_labels"]
    assert "Construct slot plan readback" in model["section_labels"]
    assert "Dedicated slot plan presenter readback" in model["section_labels"]
    assert "Evidence package flow readback" in model["section_labels"]
    assert "Component candidate readback" in model["section_labels"]
    assert "Gap / manual review queue" in model["section_labels"]
    assert "Package snapshot summary" in model["section_labels"]
    assert "Markdown readback preview" in model["section_labels"]
    assert "Boundary notice" in model["section_labels"]
    assert "Empty state" in model["section_labels"]
    assert "documentation-only" in model["boundary_notice"].casefold()
    assert "not experiment evidence" in model["boundary_notice"].casefold()


def test_workspace_uses_only_allowed_fixture_chain_outputs() -> None:
    model = workspace.build_plant_design_workspace_shell_model()

    assert model["fixture_ids"] == [
        "rice_albumin_expression_review",
        "n_benthamiana_expression_context_review",
        "generic_plant_expression_missing_fields",
    ]
    assert model["active_fixture_id"] == "rice_albumin_expression_review"
    assert model["overview"]["Fixture"].tolist() == list(model["fixture_ids"])
    assert not model["framework_summary_rows"].empty
    assert model["framework_summary"]["coverage_summary"]["workspace_mount_count"] >= 3
    assert "Evidence / Gap / Package Flow" in model["framework_summary_rows"]["Layer"].tolist()
    assert not model["route_template_registry"].empty
    assert "rice_seed_protein_expression" in model["route_template_registry"]["Route"].tolist()
    assert not model["module_card_registry"].empty
    assert "plant_target_intake" in model["module_card_registry"]["Module"].tolist()
    assert "rice_seed_protein_expression" in model["route_summary"]["Readback"].tolist()
    assert not model["overview"].empty
    assert not model["dedicated_slot_plan_presenter"].empty
    assert "promoter_slot" in model["dedicated_slot_plan_presenter"]["Slot"].tolist()
    assert not model["evidence_package_flow"].empty
    assert "Evidence records" in model["evidence_package_flow"]["Flow row"].tolist()
    assert not model["component_candidate_readback"].empty
    assert not model["package_snapshot_summary"].empty
    assert "# Plant Walkthrough Review Snapshot" in model["markdown_readback_preview"]
    assert model["markdown_readback_preview_limit"] == workspace.MARKDOWN_PREVIEW_CHAR_LIMIT
    assert model["markdown_readback_full_length"] > model["markdown_readback_preview_limit"]
    assert len(model["markdown_readback_preview"]) < model["markdown_readback_full_length"]
    assert "Preview shortened for readability" in model["markdown_readback_preview"]


def test_workspace_empty_state_is_safe_when_chain_output_is_empty() -> None:
    model = workspace.build_plant_design_workspace_shell_model([])

    assert model["empty_state"]["is_empty"] is True
    assert model["empty_state"]["manual_review_required"] is True
    assert "No plant walkthrough fixture output is available" in model["empty_state"]["message"]
    assert model["overview"].empty
    route_rows = dict(zip(model["route_summary"]["Field"], model["route_summary"]["Readback"]))
    assert model["active_fixture_id"] == "no_fixture_output"
    assert route_rows["Fixture"] == "not recorded"
    assert "documentation review snapshot" in model["markdown_readback_preview"].casefold()


def test_rendered_workspace_contains_required_sections_without_write_controls(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)

    model = workspace.render()
    rendered = _rendered_text(fake_st)

    assert model["page_title"] == "Plant Design Workspace"
    assert "Plant Design Workspace" in rendered
    assert "Documentation-only plant design review workspace" in rendered
    assert "Plant route review chain overview" in rendered
    assert "AI-guided Plant Design Handoff Preview" in rendered
    assert "User-input Plant Design Mock Preview" in rendered
    assert "Input scope route" in rendered
    assert "Allowed mock outputs" in rendered
    assert "Blocked mock outputs" in rendered
    assert "Framework coverage summary" in rendered
    assert "Route template registry readback" in rendered
    assert "Module card registry readback" in rendered
    assert "Example walkthrough readback" in rendered
    assert "Route draft summary" in rendered
    assert "Construct slot plan readback" in rendered
    assert "Dedicated slot plan presenter readback" in rendered
    assert "Evidence package flow readback" in rendered
    assert "Component candidate readback" in rendered
    assert "Gap / manual review queue" in rendered
    assert "Package snapshot summary" in rendered
    assert "Markdown readback preview" in rendered
    assert "Show bounded Markdown preview" in rendered
    assert "Boundary notice" in rendered
    assert "Empty state" in rendered
    assert "candidate match" in rendered.casefold()
    assert "source/evidence readback" in rendered.casefold()
    assert "manual review required" in rendered.casefold()
    assert "documentation-only" in rendered.casefold()
    assert "not experiment evidence" in rendered.casefold()
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.text_input_calls == []
    assert len(fake_st.text_area_calls) == 1
    assert fake_st.text_area_calls[0]["label"] == "Plant design request mock input (deterministic preview only; not saved)"
    assert fake_st.file_uploader_calls == []
    assert fake_st.dataframes == []
    assert fake_st.tables == []
    assert fake_st.code_calls == []
    assert fake_st.expander_calls == [{"label": "Show bounded Markdown preview", "expanded": False}]


def test_workspace_static_readback_preserves_required_labels_without_native_table_toolbar(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)

    workspace.render()
    rendered = _rendered_text(fake_st)

    assert "rice_albumin_expression_review" in rendered
    assert "Chain status" in rendered
    assert "Candidate match" in rendered
    assert "Source/evidence readback" in rendered
    assert "Evidence status" in rendered
    assert "Gap review items" in rendered
    assert "Handoff summary" in rendered
    assert "Workspace mounts" in rendered
    assert "Required modules" in rendered
    assert "Required slots" in rendered
    assert "Package status" in rendered
    assert "Documentation-only bounded preview for manual review context" in rendered
    assert "deterministic and unsaved" in rendered
    assert fake_st.dataframes == []
    assert fake_st.tables == []
    assert fake_st.download_button_calls == []


def test_workspace_copy_avoids_unsafe_product_claims_outside_boundary_requirements() -> None:
    source = (Path(__file__).resolve().parents[1] / "views" / "PlantDesignWorkspace.py").read_text(encoding="utf-8")
    model = workspace.build_plant_design_workspace_shell_model()
    text = f"{source}\n{model}".casefold()

    assert [phrase for phrase in FORBIDDEN_PRODUCT_CLAIMS if phrase in text] == []


def test_workspace_source_does_not_add_database_import_export_package_export_or_sequence_paths() -> None:
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
        "agent",
        "cloud",
        "fasta",
        "genbank",
        "codon",
        "sequence_output",
    ]

    assert [marker for marker in forbidden_markers if marker in source] == []


def test_legacy_workspace_module_is_retained_but_not_formally_mounted() -> None:
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    registry = (root / "core" / "module_registry.py").read_text(encoding="utf-8")

    assert (root / "views" / "PlantDesignWorkspace.py").is_file()
    assert '"id": "plant_design_workspace"' in registry
    assert '"route_key": "Plant Design Workspace"' in registry
    assert "Read-only plant route review shell" in registry
    assert '"Plant Design Workspace"' not in app
    assert "PlantDesignWorkspace" not in app
    assert "PAGE_PROJECT_HOME = \"Project Home\"" in app
    assert "PAGE_DESIGN_WORKSPACE = \"Six-Step Design Workspace\"" in app
    assert "PAGE_RESULTS_EXPORT = \"Results and Export\"" in app
    assert "PAGE_PLANT_LIBRARY = \"Plant Component Library\"" in app
