"""Biology-facing application scenario page for BioDesign Studio.

Read-only UI copy only: no persistence, schemas, algorithms, external APIs, or
wet-lab procedure content.
"""
from __future__ import annotations

import streamlit as st

from views.tool_typography import (
    inject_tool_typography_css,
    render_boundary_note,
    render_help_text,
    render_section_heading,
    render_tool_header,
    render_tool_intro,
)

_SCENARIO_CSS = """
<style>
.application-scenario-list{margin:.25rem 0 .75rem 0;padding-left:1.15rem}
.application-scenario-list li{font-size:.95rem;line-height:1.62;color:#1f2937;margin:.25rem 0}
.application-scenario-flow{font-size:.98rem;line-height:1.65;color:#1f2937;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:.85rem 1rem;margin:.35rem 0 .85rem 0;overflow-wrap:anywhere}
@media (max-width: 760px){
  .application-scenario-list li,.application-scenario-flow{font-size:.96rem}
}
</style>
"""


PAGE_TITLE = "Application Scenario"
PAGE_SUBTITLE = "Biological design context for pre-experiment documentation review."

SCENARIO_INTRO_COPY = (
    "A researcher is preparing an expression construct or synthetic biology design before an experiment "
    "or outsourcing request. BioDesign Studio helps organize the target intent, expression-system context, "
    "construct/component records, source and provenance notes, review gaps, and handoff material in one "
    "local project workspace."
)

BOUNDARY_COPY = (
    "Documentation/review only: this page explains the biological application context. It does not guarantee "
    "expression, does not optimize yield, does not predict experimental success, does not replace expert "
    "biological review, and does not provide wet-lab protocols."
)

TYPICAL_USERS = [
    "Synthetic biology design personnel who organize construct or pathway design records.",
    "Wet-lab students or researchers who prepare documentation before experiment planning or outsourcing.",
    "Advisors, PI, or reviewers who check source evidence, missing context, and handoff readiness as documentation.",
]

TYPICAL_INPUTS = [
    "Target protein, product, or pathway intent",
    "Host or expression system candidate",
    "Promoter",
    "CDS",
    "Tag or signal peptide",
    "Terminator",
    "Vector or backbone",
    "Marker",
    "Source and provenance notes",
]

TYPICAL_OUTPUTS = [
    "Construct summary",
    "Component evidence table",
    "Review gap and follow-up list",
    "Design Review Package",
    "Outsourcing handoff material",
]

BIOLOGICAL_WORKFLOW = [
    "Target intent",
    "Expression system candidate",
    "Construct/component records",
    "Source/provenance evidence",
    "Review gaps",
    "Design Review Package",
]

BOUNDARY_POINTS = [
    "Documentation-only local project workspace",
    "No guarantee of expression",
    "No yield optimization claim",
    "No experimental success prediction",
    "No replacement for expert biological review",
    "No wet-lab protocols or operational experimental instructions",
    "No clinical, regulatory, or product-readiness judgment",
]

SCENARIO_COPY_SECTIONS = {
    "Typical biological use case": (
        "Prepare an expression construct or synthetic biology design before experiment planning or outsourcing, "
        "with enough documentation context for human review."
    ),
    "Typical users": TYPICAL_USERS,
    "Typical inputs": TYPICAL_INPUTS,
    "Typical outputs": TYPICAL_OUTPUTS,
    "Biological workflow": BIOLOGICAL_WORKFLOW,
    "Boundaries": BOUNDARY_POINTS,
}

def _render_list(items: list[str]) -> None:
    list_items = "".join(f"<li>{item}</li>" for item in items)
    st.markdown(
        f"<ul class='application-scenario-list'>{list_items}</ul>",
        unsafe_allow_html=True,
    )


def _render_workflow_path() -> None:
    st.markdown(
        f"<div class='application-scenario-flow'>{' -> '.join(BIOLOGICAL_WORKFLOW)}</div>",
        unsafe_allow_html=True,
    )


def scenario_text() -> str:
    """Return user-visible scenario copy for focused tests."""
    parts: list[str] = [PAGE_TITLE, PAGE_SUBTITLE, SCENARIO_INTRO_COPY, BOUNDARY_COPY]
    for title, section in SCENARIO_COPY_SECTIONS.items():
        parts.append(title)
        if isinstance(section, list):
            parts.extend(section)
        else:
            parts.append(section)
    return "\n".join(parts)


def render(change_page=None) -> None:
    """Render the read-only biological application scenario page."""
    inject_tool_typography_css()
    st.markdown(_SCENARIO_CSS, unsafe_allow_html=True)
    render_tool_header(PAGE_TITLE, PAGE_SUBTITLE)
    render_boundary_note(BOUNDARY_COPY)
    render_tool_intro("Biological design context", SCENARIO_INTRO_COPY)
    render_help_text(
        "Use this page as a quick explanation of what biological problem the workspace addresses, "
        "what information users bring in, and what documentation outputs they can prepare for review."
    )

    render_section_heading("Typical Biological Use Case")
    st.markdown(SCENARIO_COPY_SECTIONS["Typical biological use case"])

    left_col, right_col = st.columns(2, gap="medium")
    with left_col:
        render_section_heading("Typical Users")
        _render_list(TYPICAL_USERS)
        render_section_heading("Typical Inputs")
        _render_list(TYPICAL_INPUTS)
    with right_col:
        render_section_heading("Typical Outputs")
        _render_list(TYPICAL_OUTPUTS)
        render_section_heading("Boundaries")
        _render_list(BOUNDARY_POINTS)

    render_section_heading("Biological Workflow")
    _render_workflow_path()

    st.info(
        "Reviewer note: BioDesign Studio records and organizes design context for human review. "
        "A biological expert still decides whether the documented design context is sufficient for the next project step."
    )

    if change_page and st.button("Open Pathway Projects", key="application_scenario_open_projects"):
        change_page("Pathway Projects")
