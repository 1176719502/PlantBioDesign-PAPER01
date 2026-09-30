"""
components/test_modules/tab_seq_view.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Sequence View tab — edit, search, highlight.
"""
import re
import streamlit as st

from core.session_keys import SK
from utils.sequence_utils import clean_dna


def _seq_html(seq: str, highlight: str = '') -> str:
    COLORS = {'A':'#ef4444','T':'#3b82f6','C':'#22c55e','G':'#f59e0b','N':'#9ca3af'}
    out = []
    for i, b in enumerate(seq.upper()):
        if i % 60 == 0:
            out.append(f"<span style='color:#9ca3af;font-size:.62rem;font-family:monospace;user-select:none'>{i+1:6d} </span>")
        out.append(f"<span style='color:{COLORS.get(b,'#374151')};font-family:monospace;font-size:.72rem'>{b}</span>")
        if (i + 1) % 60 == 0:
            out.append('<br>')
    html = ''.join(out)
    if highlight:
        try:
            html = re.sub(f'({re.escape(highlight.upper())})',
                          r"<mark style='background:#fef08a'>\1</mark>", html)
        except re.error:
            pass
    return (
        "<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;"
        "padding:12px 16px;overflow-x:auto;line-height:2'>" + html + "</div>"
    )



def render(seq: str) -> None:
    col_edit, col_search = st.columns([3, 1])
    edit_mode = col_edit.toggle("编辑模式", value=False, key="test_edit_mode")
    search_term = col_search.text_input("搜索", placeholder="ATG...",
                                        key="search_query", label_visibility="collapsed")
    if edit_mode:
        new_val = st.text_area("序列（仅 ATCGN）：", seq, height=500,
                               label_visibility="collapsed", key="test_seq_area")
        cleaned, _warnings = clean_dna(new_val)
        if cleaned != seq:
            st.session_state[SK.ACTIVE_SEQ] = cleaned
            st.session_state['current_seq'] = cleaned
            st.rerun()
    else:
        st.markdown(_seq_html(seq[:3000], search_term), unsafe_allow_html=True)
        if len(seq) > 3000:
            st.info(f"显示前 3,000 bp，共 {len(seq):,} bp。")
        if search_term:
            try:
                hits = len(re.findall(re.escape(search_term.upper()), seq.upper()))
                st.caption(f"“{search_term}”共匹配 {hits} 次")
            except re.error:
                pass
