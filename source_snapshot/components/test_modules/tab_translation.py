"""
components/test_modules/tab_translation.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Translation tab — 6-frame translation.
"""
import streamlit as st
from components.test_modules.seq_utils import translate_dna


def render(seq: str) -> None:
    st.markdown("#### 六框翻译")
    c1, c2 = st.columns([1, 2])
    frame = c1.selectbox(
        "阅读框",
        [1, 2, 3, -1, -2, -3],
        format_func=lambda x: f"+{x} 框（正链）" if x > 0 else f"{x} 框（反链）",
        key="translate_frame",
    )
    protein = translate_dna(seq, frame=frame)
    c2.metric("蛋白质长度", f"{len(protein)} aa")

    stop_count = protein.count('*')
    met_count  = protein.count('M')
    c3, c4 = st.columns(2)
    c3.metric("终止密码子数",    stop_count)
    c4.metric("Met（甲硫氨酸）残基数",   met_count)

    st.markdown("**翻译结果：**")
    with st.container(border=True):
        display = protein if len(protein) <= 1000 else (
            protein[:1000] + f"\n...（已截断，全长：{len(protein)} aa）"
        )
        st.text(display)
    st.caption("标准遗传密码；* = 终止密码子")
