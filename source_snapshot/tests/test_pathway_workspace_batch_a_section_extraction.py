from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_DIR = ROOT / "views" / "pathway_workspace_sections"
DASHBOARD_SECTION = SECTIONS_DIR / "project_quality_dashboard_section.py"
REVIEW_SECTION = SECTIONS_DIR / "project_review_report_section.py"
EXPORT_SECTION = SECTIONS_DIR / "export_package_section.py"
PROJECT_OUTPUTS_SECTION = SECTIONS_DIR / "project_outputs_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _dashboard_call_index(source: str) -> int:
    return source.index("render_project_quality_dashboard_section(")


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


def test_batch_a_sections_still_exist_after_later_extractions() -> None:
    assert REVIEW_SECTION.exists()
    assert EXPORT_SECTION.exists()
    assert (SECTIONS_DIR / "import_preview_section.py").exists()
    assert (SECTIONS_DIR / "linked_artifacts_section.py").exists()
    assert (SECTIONS_DIR / "project_header.py").exists()


def test_project_quality_dashboard_section_still_exists_and_is_called() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    project_outputs_source = _read(PROJECT_OUTPUTS_SECTION)
    assert DASHBOARD_SECTION.exists()
    assert "from views.pathway_workspace_sections.project_quality_dashboard_section import (" in workspace_source
    assert "render_project_handoff_review_workspace_section," in workspace_source
    assert "render_project_quality_dashboard_section," in workspace_source
    assert "render_project_quality_dashboard_section=render_project_quality_dashboard_section" in workspace_source
    assert "render_project_quality_dashboard_section(" in project_outputs_source
    assert "expression_links=expression_links" in project_outputs_source
    assert "snapshots=snapshots" in project_outputs_source
    assert "review_signals=review_signals" in project_outputs_source


def test_pathway_workspace_delegates_batch_a_sections_in_expected_order() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    section_source = _read(PROJECT_OUTPUTS_SECTION)
    dashboard_index = _dashboard_call_index(section_source)
    review_index = _review_report_call_index(section_source)
    export_index = section_source.rindex("render_export_package_section(")
    import_preview_index = section_source.rindex("render_import_package_preview()")

    assert "render_import_package_preview=_render_import_package_preview" in workspace_source

    assert dashboard_index < review_index < export_index < import_preview_index


def test_no_large_multi_section_extraction_beyond_allowed_scope() -> None:
    forbidden_modules = [
        "steps_section.py",
        "tests_section.py",
    ]
    for module_name in forbidden_modules:
        assert not (SECTIONS_DIR / module_name).exists()

    source = _read(PATHWAY_WORKSPACE)
    assert "render_import_preview_section()" in source
    assert "render_import_safety_section" in source
    assert "render_project_header(project, change_page)" in source
    assert "render_linked_artifacts_section(project.get(\"id\"))" in source


def test_batch_a_safety_scan() -> None:
    source = "\n".join(
        [
            _read(PATHWAY_WORKSPACE),
            _read(REVIEW_SECTION),
            _read(EXPORT_SECTION),
            _read(Path(__file__)),
        ]
    )
    forbidden = [
        "enable_database_write" + "=True",
        "execute_project_import" + "_as_new_project",
        "Import" + " Project",
        "Execute" + " Import",
        "Confirm" + " Import",
        "Import" + " now",
        "Ready" + " to import",
        "Ready" + " for execution",
        "Quality" + " Score",
        "Evidence" + " Score",
        "Readiness" + " Score",
        "Validation" + " Score",
        "Experiment" + " Ready",
        "Production" + " Ready",
        "validated" + " construct",
        "successful" + " cloning",
        "successful" + " PCR",
        "successful" + " expression",
        "optimized" + " pathway",
        "yield" + " prediction",
    ]
    for text in forbidden:
        assert text not in source
