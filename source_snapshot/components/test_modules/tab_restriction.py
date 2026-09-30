"""
components/test_modules/tab_restriction.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Restriction Analysis tab.
"""
import pandas as pd
import streamlit as st
from components.test_modules.seq_utils import find_enzymes


def render(seq: str) -> None:
    st.markdown("#### 限制性位点分析")
    cut_filter = st.radio("末端类型", ["全部", "粘性末端", "平末端"],
                           horizontal=True, key="cut_filter")

    results = find_enzymes(seq)
    df = pd.DataFrame(results) if results else pd.DataFrame()

    if not df.empty:
        if cut_filter == "粘性末端":
            df = df[df["Type"] == "Sticky"]
        elif cut_filter == "平末端":
            df = df[df["Type"] == "Blunt"]

    if df.empty:
        st.info("当前筛选条件下未检测到限制性位点。")
        return

    display_df = df.copy()
    if "Type" in display_df:
        display_df["Type"] = display_df["Type"].replace({"Sticky": "粘性末端", "Blunt": "平末端"})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("位点总数",   len(df))
    c2.metric("粘性末端",   len(df[df["Type"]=="Sticky"]) if "Type" in df else 0)
    c3.metric("平末端",    len(df[df["Type"]=="Blunt"])  if "Type" in df else 0)
    c4.metric("特异性酶种数",df["Enzyme"].nunique()         if "Enzyme" in df else 0)

    st.dataframe(
        display_df, use_container_width=True, hide_index=True,
        column_config={
            "Enzyme":   st.column_config.TextColumn("酶",    width=130),
            "Site":     st.column_config.TextColumn("识别位点",      width=130),
            "Type":     st.column_config.TextColumn("末端类型",  width=100),
            "Position": st.column_config.NumberColumn("位置 (bp)", width=120),
        },
    )
