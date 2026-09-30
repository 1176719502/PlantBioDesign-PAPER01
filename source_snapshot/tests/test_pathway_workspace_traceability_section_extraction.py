from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_FILE = ROOT / "views" / "PathwayWorkspace.py"
SECTION_INIT_FILE = ROOT / "views" / "pathway_workspace_sections" / "__init__.py"
SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "traceability_section.py"
PROJECT_OUTPUTS_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py"


def test_traceability_section_extraction_moves_render_logic_into_section_helper() -> None:
    workspace_source = WORKSPACE_FILE.read_text(encoding="utf-8")
    section_init_source = SECTION_INIT_FILE.read_text(encoding="utf-8")
    section_source = SECTION_FILE.read_text(encoding="utf-8")

    assert "from views.pathway_workspace_sections.traceability_section import (" in workspace_source
    assert "render_traceability_graph_lite_section" in workspace_source
    assert "render_project_outputs_traceability_summary" in workspace_source

    assert "def _render_traceability_graph_lite_section(" not in workspace_source
    assert "def _render_project_outputs_traceability_summary(" not in workspace_source
    assert "def _traceability_summary_counts(" not in workspace_source
    assert "traceability_summary_counts" not in section_init_source
    assert "def traceability_summary_counts(" not in section_source

    assert "def render_traceability_graph_lite_section(" in section_source
    assert "def render_project_outputs_traceability_summary(" in section_source
    assert "traceability_summary_counts" not in section_source
    assert "build_traceability_graph_lite_display_state(" in section_source
    assert "build_traceability_graph_lite_summary_state" not in section_source
    assert "build_traceability_graph_lite_table_state" not in section_source
    assert "build_project_outputs_traceability_summary_state(" in section_source
    assert "build_traceability_graph_lite(" in section_source


def test_traceability_tab_and_project_outputs_tab_order_remain_unchanged() -> None:
    workspace_source = WORKSPACE_FILE.read_text(encoding="utf-8")
    project_outputs_source = PROJECT_OUTPUTS_SECTION_FILE.read_text(encoding="utf-8")

    assert '["Overview", "Plant Review", "Pathway Steps", "Linked Designs", "Linked Catalog Assets", "Traceability", "Review Signals", "Review Notes"]' in workspace_source
    assert '["Documentation Snapshots", "Reports", "Quality Review", "Handoff Review", "Export Package", "Import Preview"]' in project_outputs_source
