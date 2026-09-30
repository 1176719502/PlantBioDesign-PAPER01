from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_INIT = ROOT / "views" / "pathway_workspace_sections" / "__init__.py"
SECTION = ROOT / "views" / "pathway_workspace_sections" / "documentation_snapshots_section.py"
PROJECT_OUTPUTS_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_documentation_snapshots_section_module_exists_and_is_exported() -> None:
    assert SECTION.exists()
    init_source = _read(SECTIONS_INIT)
    assert "from views.pathway_workspace_sections.documentation_snapshots_section import render_documentation_snapshots_section" in init_source
    assert '"render_documentation_snapshots_section"' in init_source


def test_pathway_workspace_delegates_documentation_snapshots_section() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    project_outputs_source = _read(PROJECT_OUTPUTS_SECTION)
    assert "from views.pathway_workspace_sections.documentation_snapshots_section import render_documentation_snapshots_section" in workspace_source
    assert "def _render_documentation_snapshots_section" not in workspace_source
    assert "render_documentation_snapshots_section=render_documentation_snapshots_section" in workspace_source
    assert "render_documentation_snapshots_section(" in project_outputs_source
    assert "create_pathway_documentation_snapshot" not in workspace_source
    assert "build_documentation_snapshot_payload" not in workspace_source


def test_documentation_snapshots_copy_and_session_keys_preserved() -> None:
    source = _read(SECTION)
    required = [
        "Documentation Snapshots",
        "Next action: save a documentation-only snapshot of the current Pathway workspace state for local traceability.",
        "Include generated Markdown report text in this documentation snapshot",
        "Snapshot title",
        "Optional label for this documentation snapshot",
        "Snapshot note",
        "Optional note describing why this snapshot was saved.",
        "Save Documentation Snapshot",
        "Documentation snapshot saved.",
        "Saved Snapshots",
        "No documentation snapshots have been saved for this project yet.",
        "Untitled Documentation Snapshot",
        "No snapshot note recorded.",
        "Generated Markdown captured:",
        "Payload counts:",
        "pathway_documentation_snapshot_include_markdown",
        "pathway_documentation_snapshot_title",
        "pathway_documentation_snapshot_note",
        "pathway_save_documentation_snapshot",
    ]
    for text in required:
        assert text in source


def test_documentation_snapshot_safety_boundary_and_services_preserved() -> None:
    source = _read(SECTION)
    assert "DOCUMENTATION_SNAPSHOT_BOUNDARY_STATEMENT" in source
    assert "build_documentation_snapshot_payload(" in source
    assert "create_pathway_documentation_snapshot(" in source
    assert "list_pathway_documentation_snapshots(" in source
    assert "generate_pathway_markdown_report(" in source
    assert "get_default_documentation_review()" in source


def test_documentation_snapshot_extraction_does_not_touch_forbidden_surfaces() -> None:
    combined = _read(PATHWAY_WORKSPACE) + "\n" + _read(SECTION)
    forbidden = [
        "pathway_steps_section.py",
        "delete_confirmation_section.py",
        "execute_project_import" + "_as_new_project",
        "enable_database_write" + "=True",
        "Import" + " Project",
        "Execute" + " Import",
        "Confirm" + " Import",
        "Import" + " now",
        "Ready" + " to import",
        "Ready" + " for execution",
        "Experiment" + " Ready",
        "Production" + " Ready",
        "optimized" + " pathway",
        "yield" + " prediction",
    ]
    for text in forbidden:
        assert text not in combined

    workspace_source = _read(PATHWAY_WORKSPACE)
    assert "def _render_steps_tab" in workspace_source
    assert "Confirm delete step" in workspace_source
