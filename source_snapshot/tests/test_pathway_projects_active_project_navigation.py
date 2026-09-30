from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_PROJECTS = ROOT / "views" / "PathwayProjects.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_pathway_projects_active_project_selector_has_nearby_open_action() -> None:
    source = _read(PATHWAY_PROJECTS)

    assert 'CURRENT_PROJECT_KEY = "pathway_current_project_id"' in source
    assert '"Continue a Project"' in source
    assert '"Search existing projects"' in source
    assert "Search filters existing records only. It does not edit, rename, or delete projects." in source
    assert '"Select project to preview"' in source
    assert "Typing filters the list only. Use Set as Active Project to change the active project." in source
    assert "This only changes the active project. It does not edit, rename, or delete records." in source
    assert '"Set a project as active first."' in source
    assert '"Set as Active Project"' in source
    assert '"Open Active Project in Pathway Workspace"' in source
    assert "disabled=not has_active_project" in source
    assert '_set_current_project(selected_id)' in source
    assert 'change_page("Pathway Workspace")' in source
    assert '_render_project_selector(projects, change_page)' in source


def test_pathway_projects_table_remains_overview_only_without_row_selection() -> None:
    source = _read(PATHWAY_PROJECTS)

    assert "st.dataframe(" in source
    assert "st.selectbox(" in source
    assert "unsafe_allow_html" not in source
    assert "on_select" not in source
    assert "selection_mode" not in source
    assert "st.data_editor" not in source
    assert "LinkColumn" not in source
    assert "<div class=\"pathway-project-row" not in source
    assert "pathway-project-overview" not in source
    assert "pathway-project-detail" not in source
    assert '"Ref": f"Ref #{project_id}"' in source
    assert "def _render_project_result_row" not in source
    assert '"Use this project"' not in source
    assert "st.radio(" not in source
    assert "_render_selected_project_summary(selected_project, is_active=selected_is_active)" in source
