from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_PATH not in sys.path:
    sys.path.insert(0, ROOT_PATH)

from tests.helpers.fake_streamlit import FakeStreamlit
import views.pathway_workspace_sections.empty_state as empty_state_section

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
PROJECT_HEADER = ROOT / "views" / "pathway_workspace_sections" / "project_header.py"
EMPTY_STATE = ROOT / "views" / "pathway_workspace_sections" / "empty_state.py"
SECTIONS_INIT = ROOT / "views" / "pathway_workspace_sections" / "__init__.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_project_header_and_empty_state_modules_exist_and_are_imported() -> None:
    source = _read(PATHWAY_WORKSPACE)
    assert PROJECT_HEADER.exists()
    assert EMPTY_STATE.exists()
    assert "from views.pathway_workspace_sections.project_header import render_project_header" in source
    assert "from views.pathway_workspace_sections.empty_state import render_no_active_project_empty_state" in source


def test_pathway_workspace_calls_project_header_and_empty_state_renderers() -> None:
    source = _read(PATHWAY_WORKSPACE)
    assert "render_project_header(project, change_page)" in source
    assert "render_no_active_project_empty_state(change_page)" in source


def test_project_header_identity_copy_preserved() -> None:
    source = _read(PROJECT_HEADER)
    assert "Active project" in source
    assert "currently selected pathway documentation workspace" in source
    assert "Pathway workflow is documentation-only" in source
    assert "documentation workspace" in source
    assert "review signals" in source
    assert "computational previews" in source
    assert "Project concepts" in source


def test_empty_state_copy_preserved() -> None:
    source = _read(EMPTY_STATE)
    assert "No active pathway project selected" in source
    assert "Select a pathway documentation workspace" in source
    assert "documentation-only" in source
    assert "Import Preview stays read-only" in source


def test_project_header_empty_state_no_database_write_or_import_execution_forbidden_strings() -> None:
    source = "\n".join([_read(PATHWAY_WORKSPACE), _read(PROJECT_HEADER), _read(EMPTY_STATE), _read(Path(__file__))])
    forbidden = [
        "enable_database_write" + "=True",
        "execute_project_import" + "_as_new_project",
        "Import" + " Project",
        "Execute" + " Import",
        "Confirm" + " Import",
        "Import" + " now",
        "Ready" + " to import",
        "Ready" + " for execution",
        "successful" + " import",
        "import" + " succeeded",
        "project" + " imported",
        "Quality" + " Score",
        "Evidence" + " Score",
        "Readiness" + " Score",
        "Validation" + " Score",
    ]
    for text in forbidden:
        assert text not in source


def test_empty_state_render_routes_to_pathway_projects_without_import_claims(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.button_values[None] = True
    page_changes: list[str] = []
    monkeypatch.setattr(empty_state_section, "st", fake_st)

    empty_state_section.render_no_active_project_empty_state(page_changes.append)

    rendered = "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.info_messages
        + fake_st.caption_messages
        + [call["label"] for call in fake_st.button_calls]
    ).lower()
    assert page_changes == ["Pathway Projects"]
    assert "pathway workspace" in rendered
    assert "no active pathway project selected" in rendered
    assert "documentation-only" in rendered
    assert "go to pathway projects" in rendered
    for text in (
        "successful" + " import",
        "project" + " imported",
        "ready" + " for execution",
        "experiment" + "-ready",
    ):
        assert text not in rendered


def test_runtime_sources_do_not_reference_archived_docs_or_plans() -> None:
    source = "\n".join([_read(PATHWAY_WORKSPACE), _read(PROJECT_HEADER), _read(EMPTY_STATE), _read(SECTIONS_INIT)])
    forbidden = [
        "docs/archive/",
        "docs\\archive\\",
        "pathway_workspace_decomposition_plan_v1_15_4.md",
        "V2_6_R21_PATHWAY_WORKSPACE_CODE_QUALITY_AUDIT.md",
    ]
    for text in forbidden:
        assert text not in source
