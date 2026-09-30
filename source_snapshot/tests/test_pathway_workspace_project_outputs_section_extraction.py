from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_INIT = ROOT / "views" / "pathway_workspace_sections" / "__init__.py"
SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_project_outputs_section_module_exists_and_is_exported() -> None:
    assert SECTION.exists()
    init_source = _read(SECTIONS_INIT)

    assert "from views.pathway_workspace_sections.project_outputs_section import render_project_outputs_section" in init_source
    assert '"render_project_outputs_section"' in init_source


def test_pathway_workspace_delegates_project_outputs_section_through_wrapper() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    section_source = _read(SECTION)

    assert "project_outputs_section," in workspace_source
    assert "def _render_project_outputs_tabs(" in workspace_source
    assert "project_outputs_section.render_project_outputs_section(" in workspace_source
    assert "project_outputs_boundary_copy=PROJECT_OUTPUTS_BOUNDARY_COPY" in workspace_source
    assert "traceability_status_helper_copy=TRACEABILITY_STATUS_HELPER_COPY" in workspace_source
    assert "render_documentation_report_download=_render_documentation_report_download" in workspace_source
    assert "render_import_package_preview=_render_import_package_preview" in workspace_source
    assert "persisted_project_links=linked_catalog_assets_section._persisted_project_links" in workspace_source

    assert "def render_project_outputs_section(" in section_source
    assert "def _render_project_outputs_tabs(" not in section_source


def test_project_outputs_tab_order_and_copy_are_section_owned() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    section_source = _read(SECTION)

    assert '["Documentation Snapshots", "Reports", "Quality Review", "Handoff Review", "Export Package", "Import Preview"]' in section_source
    assert "snapshots_tab, reports_tab, quality_tab, handoff_tab, export_tab, import_tab = st.tabs(" in section_source
    assert "Project Outputs is the review and traceability area" in section_source
    assert "Documentation Risk Summary: documentation gaps" in section_source
    assert "Review import package preview: inspect package structure" in section_source

    assert '["Documentation Snapshots", "Reports", "Quality Review", "Handoff Review", "Export Package", "Import Preview"]' not in workspace_source
    assert "snapshots_tab, reports_tab, quality_tab, handoff_tab, export_tab, import_tab = st.tabs(" not in workspace_source


def test_project_outputs_section_keeps_import_export_internals_out_of_section_shell() -> None:
    section_source = _read(SECTION)

    forbidden = [
        "validate_project_import_package",
        "execute_project_import_as_new_project",
        "enable_database_write=True",
        "PathwayReportConfig(",
        "generate_pathway_markdown_report(",
        "create_pathway_documentation_snapshot(",
        "build_documentation_snapshot_payload(",
        "schema_version =",
        "ALTER TABLE",
        "CREATE TABLE",
    ]
    assert [text for text in forbidden if text in section_source] == []


def test_project_outputs_section_copy_stays_documentation_only() -> None:
    section_source = _read(SECTION).lower()
    forbidden = [
        "successful" + " import",
        "project" + " imported",
        "ready" + " for execution",
        "experiment" + "-ready",
        "production" + "-ready",
        "validated" + " construct",
        "optimized" + " pathway",
        "yield" + " prediction",
    ]
    assert [text for text in forbidden if text in section_source] == []
