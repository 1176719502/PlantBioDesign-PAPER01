from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_FILE = ROOT / "views" / "PathwayWorkspace.py"
SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "review_signals_section.py"
OVERVIEW_SECTION_FILE = ROOT / "views" / "pathway_workspace_sections" / "overview_summary_section.py"


def test_review_signals_section_extraction_moves_render_logic_into_section_helper() -> None:
    workspace_source = WORKSPACE_FILE.read_text(encoding="utf-8")
    section_source = SECTION_FILE.read_text(encoding="utf-8")
    overview_source = OVERVIEW_SECTION_FILE.read_text(encoding="utf-8")

    assert "from views.pathway_workspace_sections.review_signals_section import render_review_signals_tab" in workspace_source
    assert "render_review_signals_tab" in workspace_source
    assert "from views.pathway_workspace_sections.review_signals_section import (" in overview_source
    assert "render_review_signals_summary" in overview_source
    assert "render_documentation_gaps" in overview_source

    assert "def _render_suggestions_tab(" not in workspace_source
    assert "def _render_review_signals_summary(" not in workspace_source
    assert "def _render_documentation_gaps(" not in workspace_source
    assert "def _render_suggestion_card(" not in workspace_source

    assert "def render_review_signals_tab(" in section_source
    assert "def render_review_signals_summary(" in section_source
    assert "def render_documentation_gaps(" in section_source


def test_review_signals_copy_and_wiring_remain_documentation_only() -> None:
    workspace_source = WORKSPACE_FILE.read_text(encoding="utf-8")
    section_source = SECTION_FILE.read_text(encoding="utf-8")
    overview_source = OVERVIEW_SECTION_FILE.read_text(encoding="utf-8")

    assert '["Overview", "Plant Review", "Pathway Steps", "Linked Designs", "Linked Catalog Assets", "Traceability", "Review Signals", "Review Notes"]' in workspace_source
    assert "render_review_signals_tab(suggestions, steps)" in workspace_source
    assert "render_review_signals_summary(" in overview_source
    assert "render_documentation_gaps(review_signals, steps)" in overview_source

    assert "Review Signals are documentation-only prompts for unresolved questions, source review, documentation gaps," in section_source
    assert "They are not experimental judgments, predictions, optimization instructions, readiness approval," in section_source
    assert "Review Signals do not identify established results or forecast production." in section_source
    assert "No documentation-only review signals were generated from the currently recorded data." in section_source
    assert "No high-review or medium-review documentation gaps recorded." in section_source
