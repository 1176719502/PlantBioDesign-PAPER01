from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_INIT = ROOT / "views" / "pathway_workspace_sections" / "__init__.py"
SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_report_download_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _report_wrapper_source() -> str:
    source = _read(PATHWAY_WORKSPACE)
    start = source.index("def _render_documentation_report_download")
    end = source.index("_IMPORT_SECTION_EXTRACTED_COPY_ANCHOR", start)
    return source[start:end]


def test_project_report_download_section_module_exists_and_is_exported() -> None:
    assert SECTION.exists()
    init_source = _read(SECTIONS_INIT)

    assert (
        "from views.pathway_workspace_sections.project_report_download_section "
        "import render_documentation_report_download_section"
    ) in init_source
    assert '"render_documentation_report_download_section"' in init_source


def test_pathway_workspace_keeps_report_download_wrapper_as_thin_delegate() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    wrapper_source = _report_wrapper_source()

    assert "project_report_download_section," in workspace_source
    assert "project_report_download_section.st = st" in wrapper_source
    assert "project_report_download_section.render_documentation_report_download_section(" in wrapper_source
    assert "generate_markdown_report=generate_pathway_markdown_report" in wrapper_source
    assert "build_report_filename=_safe_report_filename" in wrapper_source
    assert "PathwayReportConfig(" not in wrapper_source
    assert "st.download_button(" not in wrapper_source


def test_report_download_section_owns_report_ui_but_not_report_generation_service() -> None:
    section_source = _read(SECTION)

    assert "def render_documentation_report_download_section(" in section_source
    assert 'st.subheader("Documentation Report")' in section_source
    assert '"Download Documentation Report"' in section_source
    assert "PathwayReportConfig(" in section_source
    assert "generate_markdown_report(" in section_source
    assert "generate_pathway_markdown_report" not in section_source
    assert "build_report_filename(project)" in section_source


def test_report_download_section_copy_stays_documentation_only() -> None:
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
