from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
PROJECT_OUTPUTS_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py"
PROJECT_REPORT_DOWNLOAD_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_report_download_section.py"
REPORT_UI_TEST = ROOT / "tests" / "test_pathway_report_ui.py"
IMPORT_SAFETY_TEST = ROOT / "tests" / "test_import_safety_regression.py"
IMPORT_PREVIEW_E2E_TEST = ROOT / "tests" / "test_import_package_preview_e2e.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _import_preview_wrapper_source() -> str:
    source = _read(PATHWAY_WORKSPACE)
    start = source.index("def _render_import_package_preview")
    end = source.index("def _safe_int", start)
    return source[start:end]


def test_import_preview_remains_page_local_compatibility_wrapper() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    wrapper_source = _import_preview_wrapper_source()

    assert "def _render_import_package_preview() -> None:" in workspace_source
    assert "_sync_import_section_dependencies()" in wrapper_source
    assert "render_import_preview_section()" in wrapper_source
    assert "validate_project_import_package" in wrapper_source
    assert "render_import_package_preview=_render_import_package_preview" in workspace_source
    assert "render_import_preview_section()" not in _read(PROJECT_OUTPUTS_SECTION)


def test_project_outputs_section_uses_injected_import_preview_callback_only() -> None:
    section_source = _read(PROJECT_OUTPUTS_SECTION)

    assert "render_import_package_preview: Renderer" in section_source
    assert "render_import_package_preview()" in section_source
    forbidden = [
        "validate_project_import_package",
        "_sync_import_section_dependencies",
        "render_import_preview_section()",
        "execute_project_import_as_new_project",
        "enable_database_write=True",
    ]
    assert [text for text in forbidden if text in section_source] == []


def test_report_download_section_stays_out_of_import_preview_boundary() -> None:
    report_section_source = _read(PROJECT_REPORT_DOWNLOAD_SECTION)

    forbidden = [
        "Import Preview",
        "validate_project_import_package",
        "render_import_preview_section",
        "execute_project_import_as_new_project",
        "Create New Documentation Project",
    ]
    assert [text for text in forbidden if text in report_section_source] == []


def test_existing_tests_still_call_import_preview_wrapper_directly() -> None:
    direct_call_count = sum(
        _read(path).count("pathway_workspace._render_import_package_preview()")
        for path in [REPORT_UI_TEST, IMPORT_SAFETY_TEST, IMPORT_PREVIEW_E2E_TEST]
    )

    assert direct_call_count >= 5
