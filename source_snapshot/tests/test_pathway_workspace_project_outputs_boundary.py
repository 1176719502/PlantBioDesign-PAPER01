from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
PROJECT_OUTPUTS_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py"
WORKFLOW_SERVICE = ROOT / "services" / "pathway_outputs_workflow_view_model.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_project_outputs_detail_table_state_is_service_owned() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    section_source = _read(PROJECT_OUTPUTS_SECTION)
    service_source = _read(WORKFLOW_SERVICE)

    assert "build_project_outputs_workflow_table_rows" in workspace_source
    assert "build_project_outputs_risk_table_rows" in workspace_source
    assert "pd.DataFrame(build_project_outputs_workflow_table_rows(workflow_rows))" in section_source
    assert "pd.DataFrame(build_project_outputs_risk_table_rows(risk_rows))" in section_source

    assert "def build_project_outputs_workflow_table_rows(" in service_source
    assert "def build_project_outputs_risk_table_rows(" in service_source


def test_project_outputs_detail_tables_use_stretch_width() -> None:
    section_source = _read(PROJECT_OUTPUTS_SECTION)

    workflow_call = 'pd.DataFrame(build_project_outputs_workflow_table_rows(workflow_rows)),\n            width="stretch"'
    risk_call = 'pd.DataFrame(build_project_outputs_risk_table_rows(risk_rows)),\n            width="stretch"'
    assert workflow_call in section_source
    assert risk_call in section_source


def test_project_outputs_detail_table_row_shaping_does_not_return_to_page_layer() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)

    forbidden_inline_row_shaping = [
        '"Output": row.get("label", "")',
        '"Next review step": row.get("next_review_step", "")',
        '"Area": row.get("label", "")',
        '"Related count": row.get("related_count", 0)',
        '"Source area": row.get("source_area", "")',
    ]
    for text in forbidden_inline_row_shaping:
        assert text not in workspace_source
