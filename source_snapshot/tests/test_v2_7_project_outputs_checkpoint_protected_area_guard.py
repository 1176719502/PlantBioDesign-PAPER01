from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_OUTPUTS_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py"
PROJECT_REPORT_DOWNLOAD_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_report_download_section.py"
OUTPUTS_VIEW_MODEL = ROOT / "services" / "pathway_outputs_workflow_view_model.py"
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_extracted_project_outputs_checkpoint_files_stay_out_of_protected_runtime_areas() -> None:
    checked_sources = {
        PROJECT_OUTPUTS_SECTION: _read(PROJECT_OUTPUTS_SECTION),
        PROJECT_REPORT_DOWNLOAD_SECTION: _read(PROJECT_REPORT_DOWNLOAD_SECTION),
        OUTPUTS_VIEW_MODEL: _read(OUTPUTS_VIEW_MODEL),
    }
    protected_terms = [
        "from services.project_import_service",
        "from services.project_export_package_service",
        "execute_project_import_as_new_project",
        "validate_project_import_package",
        "ALTER TABLE",
        "CREATE TABLE",
        "sqlite3",
        "get_connection",
        "primer3",
        ".venv",
        "DBTL",
        "experiment execution",
        "yield" + " prediction",
        "pathway" + " optimization",
        "production" + "-ready",
    ]

    hits = [
        f"{path.relative_to(ROOT)} contains {term!r}"
        for path, source in checked_sources.items()
        for term in protected_terms
        if term in source
    ]

    assert hits == []


def test_project_outputs_section_uses_callbacks_for_sensitive_output_surfaces() -> None:
    section_source = _read(PROJECT_OUTPUTS_SECTION)
    workspace_source = _read(PATHWAY_WORKSPACE)

    for callback_name in [
        "render_documentation_report_download",
        "render_export_package_section",
        "render_import_package_preview",
    ]:
        assert f"{callback_name}: Renderer" in section_source
        assert f"{callback_name}=" in workspace_source

    assert "render_documentation_report_download(" in section_source
    assert "render_export_package_section(" in section_source
    assert "render_import_package_preview()" in section_source
    assert "render_import_preview_section()" not in section_source
    assert "generate_pathway_markdown_report(" not in section_source


def test_project_report_download_section_keeps_report_generation_injected() -> None:
    report_source = _read(PROJECT_REPORT_DOWNLOAD_SECTION)

    assert "generate_markdown_report: MarkdownReportGenerator" in report_source
    assert "build_report_filename: ReportFilenameBuilder" in report_source
    assert "generate_markdown_report(" in report_source
    assert "build_report_filename(project)" in report_source
    assert "generate_pathway_markdown_report" not in report_source
    assert "_safe_report_filename" not in report_source
