"""Shared typography helpers for standalone tool surfaces.

Presentation-only helpers: no algorithms, persistence, schemas, or safety boundaries.
"""
from __future__ import annotations

import html
from collections.abc import Iterable
from contextlib import contextmanager
from typing import Any, Iterator

import streamlit as st

TOOL_TYPOGRAPHY_CSS = """
<style>
.tool-title{font-size:1.78rem;font-weight:800;line-height:1.18;color:#0f172a;margin:0 0 .25rem 0}
.tool-subtitle{font-size:1rem;line-height:1.5;color:#475569;margin:0 0 .95rem 0;max-width:78ch}
.tool-intro-card{margin:0 0 1.05rem 0;padding:1rem 1.1rem;border-radius:10px;border:1px solid #bfdbfe;background:linear-gradient(135deg,#eff6ff 0%,#f8fbff 100%)}
.tool-intro-kicker{font-size:.76rem;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:#1d4ed8;margin-bottom:.4rem}
.tool-intro-body{font-size:.96rem;color:#1f2937;line-height:1.62;max-width:90ch}
.tool-boundary-note{font-size:.94rem;line-height:1.62;color:#1e3a5f;background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:.85rem 1rem;margin:.45rem 0 .95rem 0;max-width:96ch}
.tool-help-text{font-size:.92rem;line-height:1.62;color:#475569;margin:.25rem 0 .8rem 0;max-width:92ch}
.tool-section-heading{font-size:1.12rem;font-weight:750;line-height:1.28;color:#0f172a;margin:1.15rem 0 .38rem 0}
.tool-subsection-heading{font-size:1rem;font-weight:750;line-height:1.32;color:#1e293b;margin:.9rem 0 .3rem 0}
.tool-summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.7rem;margin:.65rem 0 1rem 0}
.tool-summary-card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:.82rem .9rem;min-height:68px}
.tool-summary-label{font-size:.72rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#64748b;margin-bottom:.3rem;line-height:1.25}
.tool-summary-value{font-size:1.05rem;font-weight:760;line-height:1.24;color:#0f172a;overflow-wrap:anywhere}
.tool-summary-delta{font-size:.82rem;line-height:1.42;color:#64748b;margin-top:.22rem}
@media (max-width: 760px){
  .tool-title{font-size:1.48rem}
  .tool-subtitle,.tool-intro-body,.tool-boundary-note,.tool-help-text{font-size:.95rem}
  .tool-summary-grid{grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:.55rem}
  .tool-summary-card{padding:.72rem .75rem}
}
</style>
"""


@contextmanager
def temporary_streamlit_binding(streamlit_api: Any) -> Iterator[None]:
    """Bind a caller's Streamlit adapter for one render without leaking it."""
    global st
    previous_st = st
    st = streamlit_api
    try:
        yield
    finally:
        st = previous_st


def inject_tool_typography_css() -> None:
    st.markdown(TOOL_TYPOGRAPHY_CSS, unsafe_allow_html=True)


def render_tool_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"<div class='tool-title'>{html.escape(title)}</div>"
        f"<div class='tool-subtitle'>{html.escape(subtitle)}</div>",
        unsafe_allow_html=True,
    )


def render_tool_intro(kicker: str, body: str) -> None:
    st.markdown(
        "<div class='tool-intro-card'>"
        f"<div class='tool-intro-kicker'>{html.escape(kicker)}</div>"
        f"<div class='tool-intro-body'>{html.escape(body)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_boundary_note(copy: str) -> None:
    st.markdown(f"<div class='tool-boundary-note'>{html.escape(copy)}</div>", unsafe_allow_html=True)


def render_help_text(copy: str) -> None:
    st.markdown(f"<div class='tool-help-text'>{html.escape(copy)}</div>", unsafe_allow_html=True)


def render_section_heading(text: str) -> None:
    st.markdown(f"<div class='tool-section-heading'>{html.escape(text)}</div>", unsafe_allow_html=True)


def render_subsection_heading(text: str) -> None:
    st.markdown(f"<div class='tool-subsection-heading'>{html.escape(text)}</div>", unsafe_allow_html=True)


def render_compact_summary_cards(items: Iterable[tuple[str, str, str | None]]) -> None:
    cards = []
    for label, value, delta in items:
        delta_html = f"<div class='tool-summary-delta'>{html.escape(delta)}</div>" if delta else ""
        cards.append(
            "<div class='tool-summary-card'>"
            f"<div class='tool-summary-label'>{html.escape(label)}</div>"
            f"<div class='tool-summary-value'>{html.escape(value)}</div>"
            f"{delta_html}"
            "</div>"
        )
    st.markdown("<div class='tool-summary-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)
