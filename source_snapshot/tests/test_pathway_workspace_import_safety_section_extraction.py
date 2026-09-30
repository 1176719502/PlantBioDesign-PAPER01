from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_DIR = ROOT / "views" / "pathway_workspace_sections"
IMPORT_SAFETY_SECTION = SECTIONS_DIR / "import_safety_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_import_safety_section_exists() -> None:
    assert IMPORT_SAFETY_SECTION.exists()


def test_pathway_workspace_imports_import_safety_renderer() -> None:
    source = _read(PATHWAY_WORKSPACE)
    assert "from views.pathway_workspace_sections.import_safety_section import render_import_safety_section" in source


def test_import_preview_calls_import_safety_renderer() -> None:
    preview_source = _read(SECTIONS_DIR / "import_preview_section.py")
    assert "from views.pathway_workspace_sections.import_safety_section import render_import_safety_section" in preview_source
    assert "render_import_safety_section(safety_report)" in preview_source


def test_import_package_safety_check_report_copy_preserved() -> None:
    source = _read(IMPORT_SAFETY_SECTION)
    required = [
        "Import Package Safety Check Report",
        "read-only safety check",
        "Blocking issues",
        "Warnings",
        "STATUS_NOT_EVALUATED",
        "No database writes are performed.",
        "This report does not import or modify any project.",
        "Blocked / NO-GO safety states stop the separate gated create-as-new action.",
        "This report never creates a project.",
    ]
    for text in required:
        assert text in source


def test_import_safety_has_no_real_import_execution_entry_points() -> None:
    source = "\n".join([_read(PATHWAY_WORKSPACE), _read(IMPORT_SAFETY_SECTION), _read(Path(__file__))])
    forbidden = [
        "enable_database_write" + "=True",
        "execute_project_import" + "_as_new_project",
        "Import" + " Project",
        "Execute" + " Import",
        "Confirm" + " Import",
        "Import" + " now",
        "Ready" + " to import",
        "Ready" + " for execution",
        "successful" + " import",
        "import" + " succeeded",
        "project" + " imported",
    ]
    for text in forbidden:
        assert text not in source
