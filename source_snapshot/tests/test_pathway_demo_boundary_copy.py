from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_SOURCE = ROOT / "views" / "PathwayProjects.py"
WORKSPACE_SOURCE = ROOT / "views" / "PathwayWorkspace.py"
OVERVIEW_SECTION_SOURCE = ROOT / "views" / "pathway_workspace_sections" / "overview_summary_section.py"
REVIEW_SIGNALS_SECTION_SOURCE = ROOT / "views" / "pathway_workspace_sections" / "review_signals_section.py"

PROJECTS_CAPTIONS = [
    "Use Pathway Projects when expression vector design records need optional project grouping, review notes, or documentation traceability.",
    "Selecting a pathway project makes it the active project for Pathway Workspace.",
]

WORKSPACE_BOUNDARY_CAPTION = (
    "This Pathway workflow is documentation-only. It organizes pathway steps, test records, linked designs, "
    "and review signals without predicting yield, optimizing production, or certifying experimental readiness."
)

OVERVIEW_COPY = (
    "Completeness score and Documentation status are documentation quality context only. They summarize coverage, "
    "linked records, traceability context, and missing documentation; they are not biological readiness, "
    "experimental conclusions, approvals, or scores for execution."
)

STEPS_COPY = (
    "Linked Expression Wizard designs are traceability links only and remain governed by Wizard validation, "
    "Step 6 export rules, and primer-risk semantics."
)

TEST_RECORDS_COPY = (
    "Test Records capture user-entered observations and notes only. They do not provide experimental validation, "
    "automated analysis, predictive results, readiness certification, or changes to completeness score semantics."
)

REVIEW_SIGNALS_COPY = (
    "Review Signals are documentation-only prompts for unresolved questions, source review, documentation gaps, "
    "manual follow-up notes, record consistency checks, and evidence-chain review."
)

REVIEW_SIGNALS_INLINE_COPY = (
    "They are not experimental judgments, predictions, optimization instructions, readiness approval, "
    "recommendation engine output, experimental guidance, action instructions, or protocol generation."
)

REVIEW_SIGNALS_EMPTY_COPY = (
    "No documentation-only review signals were generated from the currently recorded data."
)

WIZARD_LINK_COPY = (
    "Returning a Wizard design link records traceability only; it does not change pathway scoring semantics or "
    "certify experimental readiness."
)

DESCRIPTION_PLACEHOLDER = "Briefly describe the pathway documentation goal and review context."

PROHIBITED_MISLEADING_PHRASES = [
    "Ready for Experimental Use",
    "Experimental Ready",
    "Bottleneck identified",
    "Predicted yield",
    "Predicted production",
    "Recommended optimization",
    "Automatically optimized pathway",
    "Yield will improve",
    "This is the bottleneck",
]


def _pathway_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECTS_SOURCE,
            WORKSPACE_SOURCE,
            OVERVIEW_SECTION_SOURCE,
            REVIEW_SIGNALS_SECTION_SOURCE,
        )
    )


def _pathway_string_literals() -> str:
    values: list[str] = []
    for source_path in (
        PROJECTS_SOURCE,
        WORKSPACE_SOURCE,
        OVERVIEW_SECTION_SOURCE,
        REVIEW_SIGNALS_SECTION_SOURCE,
    ):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                values.append(node.value)
    return "\n".join(values)


def test_pathway_demo_boundary_copy_is_current():
    source = _pathway_string_literals()

    for caption in PROJECTS_CAPTIONS:
        assert caption in source
    assert WORKSPACE_BOUNDARY_CAPTION in source
    assert OVERVIEW_COPY in source
    assert STEPS_COPY in source
    assert TEST_RECORDS_COPY in source
    assert "Documentation-only review signals" in source
    assert REVIEW_SIGNALS_COPY in source
    assert REVIEW_SIGNALS_INLINE_COPY in source
    assert REVIEW_SIGNALS_EMPTY_COPY in source
    assert WIZARD_LINK_COPY in source
    assert DESCRIPTION_PLACEHOLDER in source
    assert "or Expression Wizard integration" not in source


def test_pathway_pages_do_not_use_misleading_readiness_or_phase4_terms():
    source = _pathway_string_literals()

    for phrase in PROHIBITED_MISLEADING_PHRASES:
        assert phrase not in source

    assert "documentation-only" in source
    assert "documentation coverage" in source
    assert "documentation quality context only" in source
    assert "not biological readiness" in source
    assert "experimental conclusions" in source
    assert "approval" in source
    assert "scores for execution" in source
    assert "Test Records are user-entered observations only" in source
    assert "Review Signals are documentation-only prompts" in source
    assert "documentation gaps" in source
    assert "record consistency checks" in source
    assert "predictions" in source
    assert "experimental judgments" in source
    assert "not experimental validation" in source
    assert "optimization instructions" in source
    assert "readiness approval" in source
    assert "recommendation engine output" in source
    assert "protocol generation" in source
    assert "experimental guidance" in source
    assert "action instructions" in source
    assert "action instructions" in source
    assert "This workflow does not validate experiments" in source
    assert "It does not predict yield" in source
    assert "It does not optimize pathways" in source
    assert "It does not provide wet-lab instructions" in source
    assert "Wizard validation, Step 6 export rules, and primer-risk semantics" in source
    assert "Expression Wizard is the primary expression vector design preparation path" in source


def test_nicotiana_demo_case_copy_is_visible_in_pathway_sources():
    source = _pathway_string_literals()

    assert "Nicotiana benthamiana artemisinin precursor documentation case" in source
    assert "source context, provenance context" in source
    assert "traceability records, review prompts, and documentation package value" in source
    assert "Use this case to point at recorded context, not biological conclusions" in source
    assert "Linked Catalog Assets" in source
    assert "Traceability" in source
    assert "not a biological recommendation, not an experimental validation, and not a wet-lab readiness judgment" in source
    assert "It does not recommend promoters or confirm host compatibility." in source
    assert "Demo data uses bundled documentation-only seed records." in source
