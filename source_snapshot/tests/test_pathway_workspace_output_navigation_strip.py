from __future__ import annotations

from pathlib import Path

from tests.helpers.fake_streamlit import FakeStreamlit
from views import PathwayWorkspace as workspace


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_FILE = ROOT / "views" / "PathwayWorkspace.py"
PROJECT_OUTPUTS_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_output_navigation_strip_items_are_present_in_review_order() -> None:
    source = _read(WORKSPACE_FILE)
    expected_labels = [
        "Plant Design Review Package",
        "Slot Coverage / Review Matrix",
        "Project Review Report",
        "Handoff Review",
        "Package / Markdown Preview",
    ]

    label_positions = [source.index(label) for label in expected_labels]

    assert label_positions == sorted(label_positions)
    assert "OUTPUT_NAVIGATION_BOUNDARY_COPY" in source
    render_body_start = source.index("render_project_header(project, change_page)")
    assert "_render_output_navigation_strip()" in source
    assert source.index("_render_output_navigation_strip()", render_body_start) < source.index(
        "_render_active_project_summary(", render_body_start
    )


def test_output_navigation_strip_renders_read_only_jump_links(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(workspace, "st", fake_st)

    workspace._render_output_navigation_strip()

    rendered = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)
    assert "Output navigation" in rendered
    assert "Output map for quick review only" in rendered
    assert "Plant Design Review Package" in rendered
    assert "Slot Coverage / Review Matrix" in rendered
    assert "Project Review Report" in rendered
    assert "Handoff Review" in rendered
    assert "Package / Markdown Preview" in rendered
    assert "href='#pathway-workspace-plant-review'" in rendered
    assert "href='#pathway-project-output-quality-review'" in rendered
    assert "href='#pathway-project-output-handoff-review'" in rendered
    assert "href='#pathway-project-outputs'" in rendered
    assert all(call.get("unsafe_allow_html") is True for call in fake_st.markdown_calls)
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_output_navigation_destinations_stay_attached_to_existing_sections() -> None:
    workspace_source = _read(WORKSPACE_FILE)
    project_outputs_source = _read(PROJECT_OUTPUTS_SECTION_FILE)

    assert "id='pathway-workspace-tabs'" in workspace_source
    assert "id='pathway-workspace-plant-review'" in workspace_source
    assert workspace_source.index("id='pathway-workspace-plant-review'") < workspace_source.index(
        "render_plant_review_workflow_section("
    )
    assert "id='pathway-project-outputs'" in workspace_source
    assert workspace_source.index("id='pathway-project-outputs'") < workspace_source.index(
        "project_outputs_section.render_project_outputs_section("
    )
    assert "id='pathway-project-output-reports'" in project_outputs_source
    assert "id='pathway-project-output-quality-review'" in project_outputs_source
    assert "id='pathway-project-output-handoff-review'" in project_outputs_source
    assert "id='pathway-project-output-export-package'" in project_outputs_source
    assert '["Documentation Snapshots", "Reports", "Quality Review", "Handoff Review", "Export Package", "Import Preview"]' in project_outputs_source
