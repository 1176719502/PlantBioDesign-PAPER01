"""AI Literature Research page — local deterministic V2.6-R2 stub."""
from __future__ import annotations

import streamlit as st

from services.ai_literature_research_service import (
    BOUNDARY_NOTE,
    empty_input_state,
    generate_literature_research_brief,
    unavailable_state,
)
from views.tool_typography import inject_tool_typography_css, render_help_text

PAGE_TITLE = "AI Literature Research"
PAGE_SUBTITLE = (
    "Local documentation assistant for literature context, provenance notes, and human review."
)


def _render_sections(brief_markdown: str) -> None:
    st.markdown(brief_markdown)


def render(change_page=None) -> None:  # pragma: no cover - Streamlit entry point
    inject_tool_typography_css()
    st.title(PAGE_TITLE)
    render_help_text(PAGE_SUBTITLE)

    st.info("Local deterministic stub for draft research briefs. No external AI services, web search, or database writes.")

    target = st.text_input(
        "Research target / topic",
        value="",
        placeholder="albumin / 白蛋白 / human serum albumin",
        key="ai_literature_research_target",
    )

    if not target.strip():
        empty_state = empty_input_state()
        st.warning(empty_state["title"])
        st.write(empty_state["body"])
        with st.expander("Boundary note", expanded=False):
            st.markdown(BOUNDARY_NOTE)
        return

    try:
        brief = generate_literature_research_brief(target)
    except ValueError:
        state = unavailable_state("Research target is required.")
        st.error(state["title"])
        st.write(state["body"])
        st.info(state["boundary"])
        return
    except Exception as exc:  # pragma: no cover - bounded failure state
        state = unavailable_state(str(exc))
        st.error(state["title"])
        st.write(state["body"])
        st.info(state["boundary"])
        return

    st.success("Draft research brief generated for human review.")
    st.caption("Source review needed before using this text as report draft documentation.")
    _render_sections(brief.as_markdown())

    with st.expander("Source review and provenance notes"):
        st.markdown(
            "- No external source lookup was performed in this stub.\n"
            "- Add citations, accession notes, and usage notes during human review.\n"
            "- Keep source-backed facts separate from draft interpretation."
        )

    st.info(BOUNDARY_NOTE)
