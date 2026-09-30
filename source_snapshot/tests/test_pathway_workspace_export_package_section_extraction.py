from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_DIR = ROOT / "views" / "pathway_workspace_sections"
SECTION = SECTIONS_DIR / "export_package_section.py"
PROJECT_OUTPUTS_SECTION = SECTIONS_DIR / "project_outputs_section.py"
SERVICE = ROOT / "services" / "project_export_package_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section_sources() -> str:
    return _read(SECTION) + "\n" + _read(SERVICE)


def test_section_module_exists() -> None:
    assert SECTION.exists()


def test_pathway_workspace_imports_and_calls_export_package_section() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    project_outputs_source = _read(PROJECT_OUTPUTS_SECTION)
    assert "from views.pathway_workspace_sections.export_package_section import render_export_package_section" in workspace_source
    assert "render_export_package_section=render_export_package_section" in workspace_source
    assert "render_export_package_section(" in project_outputs_source
    assert "def _render_project_export_package_download" not in workspace_source


def test_project_export_package_copy_preserved() -> None:
    source = _section_sources()
    required = [
        "Project Export Package",
        "Documentation-only package summary",
        "Download Project Export Package",
        "Package contents preview",
        "Package contents",
        "Post-download next steps",
        "Project Import Package Preview",
    ]
    for text in required:
        assert text in source


def test_documentation_only_export_boundary_preserved() -> None:
    source = _section_sources()
    required = [
        "Documentation-only package summary",
        "Import Preview for read-only structure and field checks",
        "this export does not certify experimental readiness, predict yield, optimize pathways, or provide wet-lab instructions.",
        "Boundary summary: documentation-only package for review and traceability; no readiness, yield, optimization, or protocol claims.",
        "does not provide wet-lab protocols",
        "Import Preview stays read-only.",
        "Blocked / NO-GO states apply only to the gated create-as-new action",
    ]
    for text in required:
        assert text in source


def test_no_forbidden_import_execution_strings() -> None:
    source = _read(PATHWAY_WORKSPACE) + "\n" + _read(SECTION)
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
        "yield" + " prediction available",
        "yield" + " prediction result",
        "fabrication" + "-ready",
        "execution" + "-ready",
    ]
    for text in forbidden:
        assert text not in source


def test_no_export_schema_change_hints() -> None:
    source = _read(SECTION)
    forbidden = [
        "schema_version =",
        "package_version =",
        "EXPORT_PACKAGE_SCHEMA",
        "manifest_schema",
        "payload_schema",
        "migration",
        "ALTER TABLE",
        "CREATE TABLE",
        "enable_database_write" + "=True",
    ]
    for text in forbidden:
        assert text not in source
