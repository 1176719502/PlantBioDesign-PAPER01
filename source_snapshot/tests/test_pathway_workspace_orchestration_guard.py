from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_FILE = ROOT / "views" / "PathwayWorkspace.py"
TRACEABILITY_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "traceability_section.py"
PROJECT_OUTPUTS_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py"
REVIEW_SIGNALS_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "review_signals_section.py"
OVERVIEW_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "overview_summary_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_workspace_tab_order_and_core_workspace_surfaces_remain_wired() -> None:
    source = _read(WORKSPACE_FILE)
    overview_source = _read(OVERVIEW_SECTION_FILE)

    assert '["Overview", "Plant Review", "Pathway Steps", "Linked Designs", "Linked Catalog Assets", "Traceability", "Review Signals", "Review Notes"]' in source
    assert "overview_tab, plant_review_tab, steps_tab, linked_designs_tab, linked_catalog_assets_tab, traceability_tab, review_signals_tab, review_notes_tab = st.tabs(" in source
    assert source.index('"Overview", "Plant Review", "Pathway Steps", "Linked Designs", "Linked Catalog Assets", "Traceability", "Review Signals", "Review Notes"') < source.index("with overview_tab:")
    assert "render_overview_summary_section(" in source
    assert "render_plant_review_workflow_section(" in source
    assert "_render_steps_tab(project, project_id, steps, change_page, expression_links)" in source
    assert "_render_tests_tab(project_id, steps, test_records)" in source
    assert "_render_linked_designs_tab(project, steps, expression_links)" in source
    assert "render_linked_catalog_assets_section(project)" in source
    assert "render_review_signals_tab(suggestions, steps)" in source
    assert "_render_documentation_review_tab(project, project_id)" in source
    assert 'st.subheader("Project Status Summary")' in overview_source
    assert 'st.subheader("Catalog Reference Overview")' in overview_source
    assert 'st.subheader("Step Documentation Coverage Matrix")' in overview_source


def test_project_outputs_tab_order_and_entry_point_wiring_remain_unchanged() -> None:
    workspace_source = _read(WORKSPACE_FILE)
    section_source = _read(PROJECT_OUTPUTS_SECTION_FILE)

    assert "project_outputs_section.render_project_outputs_section(" in workspace_source
    assert "render_documentation_report_download=_render_documentation_report_download" in workspace_source
    assert "render_import_package_preview=_render_import_package_preview" in workspace_source
    assert '["Documentation Snapshots", "Reports", "Quality Review", "Handoff Review", "Export Package", "Import Preview"]' in section_source
    assert "snapshots_tab, reports_tab, quality_tab, handoff_tab, export_tab, import_tab = st.tabs(" in section_source
    assert "render_project_outputs_traceability_summary(" in section_source
    assert "render_documentation_snapshots_section(" in section_source
    assert "render_documentation_report_download(" in section_source
    assert "render_project_quality_dashboard_section(" in section_source
    assert "render_project_review_report_section(" in section_source
    assert "render_export_package_section(" in section_source
    assert "render_import_package_preview()" in section_source
    assert 'st.subheader("Import Preview")' in section_source
    assert '"Quality Review: review documentation completeness, linked records, traceability context, and missing documentation."' in section_source


def test_r132_traceability_extraction_seam_stays_connected_to_main_workspace() -> None:
    workspace_source = _read(WORKSPACE_FILE)
    section_source = _read(TRACEABILITY_SECTION_FILE)
    project_outputs_source = _read(PROJECT_OUTPUTS_SECTION_FILE)

    assert "from views.pathway_workspace_sections.traceability_section import (" in workspace_source
    assert "render_traceability_graph_lite_section(" in workspace_source
    assert "render_project_outputs_traceability_summary=render_project_outputs_traceability_summary" in workspace_source
    assert "render_project_outputs_traceability_summary(" in project_outputs_source
    assert "lineage_copy=TRACEABILITY_LINEAGE_COPY" in workspace_source
    assert "boundary_copy=TRACEABILITY_BOUNDARY_COPY" in workspace_source
    assert "status_helper_copy=TRACEABILITY_STATUS_HELPER_COPY" in workspace_source
    assert "empty_state_copy=TRACEABILITY_EMPTY_STATE_COPY" in workspace_source

    assert "def _render_traceability_graph_lite_section(" not in workspace_source
    assert "def _render_project_outputs_traceability_summary(" not in workspace_source

    assert "def render_traceability_graph_lite_section(" in section_source
    assert "def render_project_outputs_traceability_summary(" in section_source
    assert "build_traceability_graph_lite(" in section_source


def test_r134_review_signals_extraction_seam_stays_connected_to_main_workspace() -> None:
    workspace_source = _read(WORKSPACE_FILE)
    review_signals_section_source = _read(REVIEW_SIGNALS_SECTION_FILE)
    overview_section_source = _read(OVERVIEW_SECTION_FILE)

    assert "from views.pathway_workspace_sections.review_signals_section import render_review_signals_tab" in workspace_source
    assert "render_review_signals_tab(suggestions, steps)" in workspace_source
    assert "render_review_signals_summary(" in overview_section_source
    assert "render_documentation_gaps(review_signals, steps)" in overview_section_source

    assert "def _render_suggestions_tab(" not in workspace_source
    assert "def _render_review_signals_summary(" not in workspace_source
    assert "def _render_documentation_gaps(" not in workspace_source
    assert "def _render_suggestion_card(" not in workspace_source

    assert "def render_review_signals_tab(" in review_signals_section_source
    assert "def render_review_signals_summary(" in review_signals_section_source
    assert "def render_documentation_gaps(" in review_signals_section_source
    assert "Review Signals are documentation-only prompts for unresolved questions, source review, documentation gaps," in review_signals_section_source
    assert "No high-review or medium-review documentation gaps recorded." in review_signals_section_source


def test_import_export_wiring_guard_stays_at_entry_point_level_only() -> None:
    workspace_source = _read(WORKSPACE_FILE)
    section_source = _read(PROJECT_OUTPUTS_SECTION_FILE)

    assert "render_export_package_section" in workspace_source
    assert "render_import_package_preview=_render_import_package_preview" in workspace_source
    assert "render_export_package_section(" in section_source
    assert "render_import_package_preview()" in section_source
    assert "_sync_import_section_dependencies()" in workspace_source
    assert "render_import_preview_section()" in workspace_source
    assert "render_import_safety_section(report)" in workspace_source

    forbidden = [
        "schema_version =",
        "ALTER TABLE",
        "CREATE TABLE",
        "execute_project_import_as_new_project(",
        "enable_database_write=True",
    ]
    for text in forbidden:
        assert text not in workspace_source
        assert text not in section_source
