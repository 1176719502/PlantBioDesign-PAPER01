from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_FILE = ROOT / "views" / "PathwayWorkspace.py"
OVERVIEW_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "overview_summary_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_r136_overview_summary_section_is_extracted_and_wired_from_main_workspace() -> None:
    workspace_source = _read(WORKSPACE_FILE)
    section_source = _read(OVERVIEW_SECTION_FILE)

    assert "from views.pathway_workspace_sections.overview_summary_section import render_overview_summary_section" in workspace_source
    assert "render_overview_summary_section(" in workspace_source
    assert "project_catalog_links=linked_catalog_assets_section._persisted_project_links(project.get(\"id\"))" in workspace_source
    assert "project_level_tests=project_level_tests" in workspace_source
    assert "step_associated_tests=step_associated_tests" in workspace_source
    assert "step_test_counts=step_test_counts" in workspace_source
    assert "format_step_reaction=_format_step_reaction" in workspace_source

    assert "def _render_overview_tab(" not in workspace_source
    assert "def render_overview_summary_section(" in section_source
    assert 'with st.expander("Demo Guide", expanded=False):' in section_source
    assert 'st.subheader("Catalog Reference Overview")' in section_source
    assert 'st.subheader("Project Status Summary")' in section_source
    assert 'st.subheader("Step Documentation Coverage Matrix")' in section_source
    assert "render_review_signals_summary(" in section_source
    assert 'with st.expander("Documentation gaps summary", expanded=False):' in section_source


def test_r136_overview_section_keeps_read_only_documentation_only_summary_copy() -> None:
    section_source = _read(OVERVIEW_SECTION_FILE)
    normalized = section_source.lower()

    for required in [
        "Overview summarizes the current project as the main local project workspace.",
        "Expression Wizard is a design record subflow for gene-level records",
        "They summarize coverage, ",
        "linked records, traceability context, and missing documentation; they are not biological readiness, ",
        "experimental conclusions, approvals, or scores for execution.",
        "it does not forecast production, optimize pathways, or certify readiness.",
        "It is not recommendation, validation, readiness, or prediction.",
        "This matrix is for documentation and traceability only.",
    ]:
        assert required in section_source

    for forbidden in [
        "safe-for-lab-use",
        "safe for lab use",
        "ready for execution",
        "production-ready",
        "experiment-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
    ]:
        assert forbidden not in normalized
