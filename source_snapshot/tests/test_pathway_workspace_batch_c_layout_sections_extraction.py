from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_DIR = ROOT / "views" / "pathway_workspace_sections"
PROJECT_OUTPUTS_SECTION = SECTIONS_DIR / "project_outputs_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _review_report_call_index(source: str) -> int:
    review_index = source.index("render_project_review_report_section(")
    call_block = source[review_index : source.index(")", review_index)]
    assert "project," in call_block
    assert "steps," in call_block
    assert "expression_links=expression_links" in call_block
    assert "test_records=test_records" in call_block
    assert "snapshots=snapshots" in call_block
    assert "review_signals=review_signals" in call_block
    assert "completeness_result=completeness_result" in call_block
    assert "project_catalog_links = persisted_project_links(project.get(\"id\"))" in source
    assert "linked_catalog_assets=project_catalog_links" in call_block
    return review_index


def test_batch_c_added_only_allowed_layout_traceability_sections() -> None:
    allowed_new_modules = {
        "linked_artifacts_section.py",
        "project_header.py",
        "empty_state.py",
    }
    for module_name in allowed_new_modules:
        assert (SECTIONS_DIR / module_name).exists()

    assert not (SECTIONS_DIR / "pathway_steps_section.py").exists()
    assert not (SECTIONS_DIR / "delete_confirmation_section.py").exists()


def test_previously_extracted_sections_still_exist_and_delegate() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    section_source = _read(PROJECT_OUTPUTS_SECTION)
    for module_name in [
        "project_quality_dashboard_section.py",
        "project_review_report_section.py",
        "export_package_section.py",
        "import_preview_section.py",
        "import_safety_section.py",
    ]:
        assert (SECTIONS_DIR / module_name).exists()

    assert "render_project_quality_dashboard_section=render_project_quality_dashboard_section" in workspace_source
    assert "render_project_quality_dashboard_section(" in section_source
    assert "expression_links=expression_links" in section_source
    assert "snapshots=snapshots" in section_source
    assert "review_signals=review_signals" in section_source
    _review_report_call_index(section_source)
    assert "render_export_package_section(" in section_source
    assert "render_import_preview_section()" in workspace_source
    assert "render_import_safety_section" in workspace_source


def test_pathway_workspace_batch_c_delegates_new_sections() -> None:
    source = _read(PATHWAY_WORKSPACE)
    overview_source = _read(SECTIONS_DIR / "overview_summary_section.py")
    assert "render_linked_artifacts_section(project.get(\"id\"))" in source
    assert "render_project_header(project, change_page)" in source
    assert "render_no_active_project_empty_state(change_page)" in source
    assert "render_overview_summary_section(" in source
    assert "_render_catalog_reference_overview_panel(" in overview_source
    assert "build_project_catalog_reference_overview(project, linked_catalog_assets=project_catalog_links)" in overview_source


def test_no_large_multi_section_extraction_beyond_batch_c_scope() -> None:
    forbidden_modules = [
        "pathway_steps_section.py",
        "delete_confirmation_section.py",
        "steps_section.py",
        "tests_section.py",
    ]
    for module_name in forbidden_modules:
        assert not (SECTIONS_DIR / module_name).exists()

    workspace_source = _read(PATHWAY_WORKSPACE)
    section_source = _read(PROJECT_OUTPUTS_SECTION)
    assert "def _render_steps_tab" in workspace_source
    assert "render_documentation_snapshots_section(" in section_source
    assert "Confirm delete step" in workspace_source
