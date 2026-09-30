"""
components/test_modules/tab_linear_map.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Linear Map tab — zoomable SVG feature map.
"""
import streamlit as st
from components.test_modules.seq_utils import smart_annotate_sequence

FEATURE_COLORS = {
    'Promoter':'#3b82f6','RBS':'#8b5cf6','CDS':'#22c55e','Tag':'#06b6d4',
    'Terminator':'#f59e0b','Operator':'#ec4899','Resistance':'#ef4444',
    'Origin':'#f97316','Border':'#6b7280',
}


def _linear_svg(seq_len: int, features: list, zoom: float = 1.0) -> str:
    W = int(800 * zoom)
    H = 120
    scale = W / max(seq_len, 1)
    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}'>",
        f"<rect x='0' y='54' width='{W}' height='12' rx='4' fill='#e2e8f0'/>",
    ]
    for i in range(0, seq_len, max(1, seq_len//10)):
        x = int(i * scale)
        parts.append(f"<line x1='{x}' y1='54' x2='{x}' y2='68' stroke='#94a3b8' stroke-width='1'/>")
        parts.append(f"<text x='{x}' y='82' font-size='9' fill='#64748b' text-anchor='middle'>{i}</text>")

    for feat in features:
        x1 = int((feat['Start'] - 1) * scale)
        x2 = int(feat['End'] * scale)
        w  = max(x2 - x1, 3)
        col = FEATURE_COLORS.get(feat['Type'], '#94a3b8')
        parts.append(
            f"<rect x='{x1}' y='44' width='{w}' height='32' rx='3' "
            f"fill='{col}' opacity='0.85'>"
            f"<title>{feat['Name']} ({feat['Type']}) {feat['Start']}-{feat['End']}</title></rect>"
        )
        if w > 30:
            parts.append(
                f"<text x='{x1 + w//2}' y='63' font-size='8' fill='white' "
                f"text-anchor='middle' font-weight='bold'>{feat['Name'][:12]}</text>"
            )
    parts.append("</svg>")
    return ''.join(parts)


def render(seq: str) -> None:
    st.markdown("#### 线性序列图谱")
    features = smart_annotate_sequence(seq)

    st.markdown("**全局概览**")
    st.markdown(
        f"<div style='border:1px solid #e0e0e0;background:#fafafa;"
        f"padding:10px;border-radius:8px'>{_linear_svg(len(seq), features, 1.0)}</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown("**缩放视图**")
    zoom = st.slider("缩放倍数", 1.0, 12.0, 2.5, 0.5, key="test_zoom")
    st.markdown(
        f"<div style='overflow-x:auto;border:1px solid #4A90E2;border-radius:8px;"
        f"background:#fff;padding:16px'>"
        f"<div style='min-width:{int(800*zoom)}px'>"
        f"{_linear_svg(len(seq), features, zoom)}</div></div>",
        unsafe_allow_html=True,
    )
    if features:
        with st.expander("特征列表"):
            import pandas as pd
            df = pd.DataFrame(features)
            if "Type" in df:
                df["Type"] = df["Type"].replace({
                    "Promoter": "启动子",
                    "RBS": "RBS",
                    "CDS": "CDS",
                    "Tag": "标签",
                    "Terminator": "终止子",
                    "Operator": "操纵子",
                    "Resistance": "抗性",
                    "Origin": "复制起点",
                    "Border": "边界序列",
                })
            df["长度"] = df["End"] - df["Start"] + 1
            display_df = df.rename(columns={"Name": "名称", "Type": "类型", "Start": "起始", "End": "终止"})
            st.dataframe(display_df[["名称","类型","起始","终止","长度"]],
                          use_container_width=True, hide_index=True)
