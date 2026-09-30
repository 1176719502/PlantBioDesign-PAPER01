from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_FILE = ROOT / "views" / "PathwayWorkspace.py"
TRACEABILITY_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "traceability_section.py"
PROJECT_OUTPUTS_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py"
REVIEW_SIGNALS_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "review_signals_section.py"
OVERVIEW_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "overview_summary_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_overview_remains_first_workspace_tab_and_keeps_read_only_summary_entry_points() -> None:
    source = _read(WORKSPACE_FILE)
    overview_source = _read(OVERVIEW_SECTION_FILE)

    assert '["Overview", "Plant Review", "Pathway Steps", "Linked Designs", "Linked Catalog Assets", "Traceability", "Review Signals", "Review Notes"]' in source
    assert "with overview_tab:" in source
    assert source.index("with overview_tab:") < source.index("with plant_review_tab:")
    assert source.index("with overview_tab:") < source.index("with steps_tab:")
    assert "render_overview_summary_section(" in source
    assert "def _render_overview_tab(" not in source

    for required in [
        '_render_demo_guide()',
        '_render_catalog_reference_overview_panel(',
        '_render_project_status_summary(project, steps, expression_links, test_records, completeness_summary, [], snapshots)',
        '_render_step_evidence_matrix(',
        'render_review_signals_summary(',
        'with st.expander("Step-level documentation details", expanded=False):',
        'st.subheader("Test / Review / Snapshot status")',
        'with st.expander("Documentation gaps summary", expanded=False):',
        'render_documentation_gaps(review_signals, steps)',
    ]:
        assert required in overview_source


def test_overview_copy_and_summary_surfaces_stay_documentation_only() -> None:
    source = _read(WORKSPACE_FILE)
    overview_source = _read(OVERVIEW_SECTION_FILE)

    required_phrases = [
        "Overview summarizes the current project as the main local project workspace.",
        "Expression Wizard is a design record subflow for gene-level records",
        'st.subheader("Project Status Summary")',
        "They summarize coverage, ",
        "linked records, traceability context, and missing documentation; they are not biological readiness, ",
        "experimental conclusions, approvals, or scores for execution.",
        'st.subheader("Step Documentation Coverage Matrix")',
        "it does not forecast production, optimize pathways, or certify readiness.",
        'st.subheader("Catalog Reference Overview")',
        "It is not recommendation, validation, readiness, or prediction.",
        'with st.expander("Documentation gaps summary", expanded=False):',
    ]
    for phrase in required_phrases:
        assert phrase in overview_source

    forbidden_positive_terms = [
        "safe-for-lab-use",
        "safe for lab use",
        "ready for execution",
        "production-ready",
        "experiment-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
    ]
    normalized_overview = overview_source.lower()
    for phrase in forbidden_positive_terms:
        assert phrase not in normalized_overview


def test_empty_and_missing_project_path_stays_separate_from_overview_rendering() -> None:
    source = _read(WORKSPACE_FILE)

    assert 'CURRENT_PROJECT_KEY = "pathway_current_project_id"' in source
    assert "project_id = st.session_state.get(CURRENT_PROJECT_KEY)" in source
    assert "project = get_pathway_project(project_id)" in source
    assert "if not project:" in source
    assert "render_no_active_project_empty_state(change_page)" in source
    assert source.index("if not project:") < source.index("steps = list_pathway_steps(resolved_project_id)")
    assert "No active pathway project selected" in source


def test_r132_and_r134_extracted_sections_remain_the_only_traceability_and_review_signal_owners() -> None:
    workspace_source = _read(WORKSPACE_FILE)
    traceability_source = _read(TRACEABILITY_SECTION_FILE)
    project_outputs_source = _read(PROJECT_OUTPUTS_SECTION_FILE)
    review_signals_source = _read(REVIEW_SIGNALS_SECTION_FILE)
    overview_source = _read(OVERVIEW_SECTION_FILE)

    assert "render_traceability_graph_lite_section(" in workspace_source
    assert "render_project_outputs_traceability_summary=render_project_outputs_traceability_summary" in workspace_source
    assert "render_project_outputs_traceability_summary(" in project_outputs_source
    assert "render_review_signals_summary(" in overview_source
    assert "render_documentation_gaps(review_signals, steps)" in overview_source
    assert "render_review_signals_tab(suggestions, steps)" in workspace_source

    assert "def _render_traceability_graph_lite_section(" not in workspace_source
    assert "def _render_project_outputs_traceability_summary(" not in workspace_source
    assert "def _render_suggestions_tab(" not in workspace_source
    assert "def _render_review_signals_summary(" not in workspace_source
    assert "def _render_documentation_gaps(" not in workspace_source

    assert "def render_traceability_graph_lite_section(" in traceability_source
    assert "def render_project_outputs_traceability_summary(" in traceability_source
    assert "def render_review_signals_summary(" in review_signals_source
    assert "def render_documentation_gaps(" in review_signals_source
