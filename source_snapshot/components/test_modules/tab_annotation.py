"""
components/test_modules/tab_annotation.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Feature Annotation tab.
"""
import pandas as pd
import streamlit as st
from components.test_modules.seq_utils import smart_annotate_sequence

FEATURE_COLORS = {
    'Promoter':   '#3b82f6',
    'RBS':        '#8b5cf6',
    'CDS':        '#22c55e',
    'Tag':        '#06b6d4',
    'Terminator': '#f59e0b',
    'Operator':   '#ec4899',
    'Resistance': '#ef4444',
    'Origin':     '#f97316',
    'Border':     '#6b7280',
}

TYPE_LABELS = {
    'Promoter': '启动子',
    'RBS': 'RBS',
    'CDS': 'CDS',
    'Tag': '标签',
    'Terminator': '终止子',
    'Operator': '操纵子',
    'Resistance': '抗性',
    'Origin': '复制起点',
    'Border': '边界序列',
}


def render(seq: str) -> None:
    st.markdown("#### 特征注释")
    features = smart_annotate_sequence(seq)

    if not features:
        st.info("当前序列中未检测到已知生物特征。")
        return

    st.success(f"检测到 {len(features)} 个生物特征")

    # Type counts
    type_counts: dict = {}
    for f in features:
        ftype = f['Type']
        type_counts[ftype] = type_counts.get(ftype, 0) + 1
    cols = st.columns(min(len(type_counts), 5))
    for i, (ftype, cnt) in enumerate(type_counts.items()):
        cols[i % len(cols)].metric(TYPE_LABELS.get(ftype, ftype), cnt)

    # Legend
    legend_html = " ".join(
        f"<span style='background:{c};color:#fff;padding:2px 8px;"
        f"border-radius:4px;font-size:.72rem;font-weight:600'>{TYPE_LABELS.get(t, t)}</span>"
        for t, c in FEATURE_COLORS.items() if t in type_counts
    )
    st.markdown(legend_html, unsafe_allow_html=True)

    df = pd.DataFrame(features)
    df["Type"] = df["Type"].map(lambda x: TYPE_LABELS.get(x, x))
    df["长度 (bp)"] = df["End"] - df["Start"] + 1
    st.dataframe(
        df[["Name","Type","Start","End","长度 (bp)"]],
        use_container_width=True, hide_index=True,
        column_config={
            "Name":       st.column_config.TextColumn("特征",      width=200),
            "Type":       st.column_config.TextColumn("类型",      width=110),
            "Start":      st.column_config.NumberColumn("起始",    width=90),
            "End":        st.column_config.NumberColumn("终止",      width=90),
            "长度 (bp)": st.column_config.NumberColumn("长度",  width=90),
        },
    )
