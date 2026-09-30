# -*- coding: utf-8 -*-
"""
views/AssemblyCloning.py — Assembly and Cloning workbench.
Left panel: Construct Overview. Right: Tabbed tools incl. Virtual Gel.
"""
from __future__ import annotations

import streamlit as st

from core.i18n import t as _t
from core.session_keys import SK

_DEFAULTS: dict = {
    SK.PROJECT_NAME: "pBioDesign",
    SK.ASSEMBLY_RESULT: "",
    SK.ASSEMBLY_METHOD: "",
    "pcr_product_len": 0,
}


def _init_state() -> None:
    for key, default in _DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default
    ctx_seq = st.session_state.get(SK.ACTIVE_SEQ, "")
    if ctx_seq and not st.session_state.get(SK.ASSEMBLY_RESULT):
        st.session_state[SK.ASSEMBLY_RESULT] = ctx_seq


def _gc(seq: str) -> float:
    s = seq.upper()
    return round((s.count("G") + s.count("C")) / len(s) * 100, 1) if s else 0.0


def _build_handoff_context() -> dict:
    active_sequence = st.session_state.get(SK.ACTIVE_SEQ, "") or st.session_state.get(SK.ASSEMBLY_RESULT, "")
    active_sequence_name = st.session_state.get(SK.ACTIVE_NAME, "")
    if not active_sequence_name or active_sequence_name == "Untitled Project":
        active_sequence_name = st.session_state.get(SK.PROJECT_NAME, "pBioDesign")
    active_sequence_source = "Expression Wizard" if st.session_state.get(SK.ACTIVE_SEQ) else "Assembly workspace"
    return {
        "active_sequence": active_sequence,
        "active_sequence_name": active_sequence_name,
        "active_sequence_source": active_sequence_source,
        "active_sequence_length": len(active_sequence) if active_sequence else 0,
        "active_sequence_gc": _gc(active_sequence),
        "is_from_expression_wizard": bool(st.session_state.get(SK.ACTIVE_SEQ)),
    }


def _render_construct_overview(seq: str, features: list, pname: str) -> None:
    st.markdown(
        f"<div style='font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:#6b7280;margin-bottom:8px'>{_t('assembly.construct_overview')}</div>",
        unsafe_allow_html=True,
    )
    if not seq:
        st.markdown(
            f"<div style='color:#9ca3af;font-size:.82rem;font-style:italic;padding:8px 0'>{_t('assembly.no_sequence')}</div>",
            unsafe_allow_html=True,
        )
        return

    gc = _gc(seq)
    n = len(seq)
    st.markdown(
        f"<div style='display:flex;flex-direction:column;gap:6px;margin-bottom:10px'>"
        f"<div style='background:#f0f9ff;border:1px solid #bae6fd;border-radius:7px;padding:8px 12px'>"
        f"<div style='font-size:.6rem;color:#0369a1;font-weight:700;text-transform:uppercase;letter-spacing:.5px'>{_t('assembly.total_length')}</div>"
        f"<div style='font-size:1.15rem;font-weight:800;color:#0c4a6e;font-family:monospace'>{n} bp</div></div>"
        f"<div style='background:#f0fdf4;border:1px solid #bbf7d0;border-radius:7px;padding:8px 12px'>"
        f"<div style='font-size:.6rem;color:#166534;font-weight:700;text-transform:uppercase;letter-spacing:.5px'>{_t('assembly.gc_content')}</div>"
        f"<div style='font-size:1.15rem;font-weight:800;color:#14532d;font-family:monospace'>{gc} %</div></div>"
        f"<div style='background:#fdf4ff;border:1px solid #e9d5ff;border-radius:7px;padding:8px 12px'>"
        f"<div style='font-size:.6rem;color:#7e22ce;font-weight:700;text-transform:uppercase;letter-spacing:.5px'>{_t('assembly.construct_name')}</div>"
        f"<div style='font-size:.9rem;font-weight:700;color:#581c87;font-family:monospace;word-break:break-all'>{pname or _t('assembly.unnamed')}</div></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if features:
        st.markdown(
            f"<div style='font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#6b7280;margin-bottom:5px'>{_t('assembly.features')}</div>",
            unsafe_allow_html=True,
        )
        type_colors = {
            "promoter": "#1d4ed8",
            "CDS": "#15803d",
            "cds": "#15803d",
            "terminator": "#b91c1c",
            "RBS": "#b45309",
            "Kozak": "#b45309",
            "tag": "#7c3aed",
            "misc": "#6b7280",
        }
        for feature in features[:14]:
            feature_type = feature.get("type", "misc")
            feature_name = feature.get("label") or feature.get("name") or feature_type
            feature_len = abs(feature.get("end", 0) - feature.get("start", 0))
            color = type_colors.get(feature_type, "#6b7280")
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid #f3f4f6'>"
                f"<span style='font-size:.75rem;color:{color};font-weight:600'>{feature_name}</span>"
                f"<span style='font-size:.68rem;color:#9ca3af'>{feature_len} bp</span></div>",
                unsafe_allow_html=True,
            )
        if len(features) > 14:
            st.caption(_t("assembly.more_features", count=len(features) - 14))
    else:
        st.caption(_t("assembly.no_features"))


def _render_virtual_gel(wizard_seq_len: int) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        st.error(_t("assembly.need_matplotlib"))
        return

    ladders = {
        "100 bp Ladder": [1000, 900, 800, 700, 600, 500, 400, 300, 200, 100],
        "1 kb Ladder": [10000, 8000, 6000, 5000, 4000, 3000, 2000, 1500, 1000, 750, 500, 250, 100],
        "Lambda HindIII": [23130, 9416, 6557, 4361, 2322, 2027, 564, 125],
    }

    ladder_col, custom_col = st.columns([1, 2])
    ladder_name = ladder_col.selectbox(_t("assembly.dna_marker"), list(ladders.keys()) + ["Custom"], key="vg_ladder")
    if ladder_name == "Custom":
        custom_text = custom_col.text_input(_t("assembly.custom_marker"), value="10000,5000,2000,1000,500,100", key="vg_ldr_custom")
        try:
            ladder = [int(x.strip()) for x in custom_text.split(",") if x.strip()]
        except Exception:
            ladder = [10000, 5000, 2000, 1000, 500, 100]
    else:
        ladder = ladders[ladder_name]

    st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:.72rem;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px'>{_t('assembly.lane_setup')}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "Virtual gel is a computational preview only. The default backbone lane is user-specified/default "
        "and is not inferred from the Expression Wizard handoff unless you explicitly edit or provide it."
    )

    lane_count = st.number_input(_t("assembly.lane_count"), min_value=1, max_value=6, value=2, key="vg_n_lanes")
    lane_rows: list[tuple[str, list[int]]] = []
    for i in range(int(lane_count)):
        c1, c2, c3 = st.columns([1, 2, 1])
        if i == 0 and wizard_seq_len > 0:
            default_label, default_bp = _t("assembly.wizard_frame"), str(wizard_seq_len)
        elif i == 1:
            default_label, default_bp = _t("assembly.default_backbone_lane"), "4700"
        else:
            default_label, default_bp = _t("assembly.sample", index=i + 1), "1000,500"

        label = c1.text_input(_t("assembly.lane_label", index=i + 1), value=default_label, key=f"vg_lbl_{i}")
        raw_bp = c2.text_input(_t("assembly.lane_bands"), value=default_bp, key=f"vg_bp_{i}")
        try:
            sizes = [int(x.strip()) for x in raw_bp.split(",") if x.strip()]
        except Exception:
            sizes = []
        c3.markdown(
            f"<div style='padding-top:28px;font-size:.75rem;color:#6b7280'>{_t('assembly.band_count', count=len(sizes))}</div>",
            unsafe_allow_html=True,
        )
        lane_rows.append((label, sizes))

    if not st.button(_t("assembly.run_virtual_gel"), type="primary", use_container_width=True, key="btn_vg_run"):
        return
    if not any(s for _, s in lane_rows):
        st.warning(_t("assembly.need_band"))
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.set_title(_t("assembly.virtual_gel_title"))
    ax.axis("off")
    summary = [f"{_t('assembly.dna_marker')}: {ladder_name}"]
    for label, bands in lane_rows:
        summary.append(f"{label}: {', '.join(str(bp) for bp in bands) if bands else '—'}")
    ax.text(0.02, 0.98, "\n".join(summary), va="top", ha="left", transform=ax.transAxes, family="monospace")

    gcl, gcc, gcr = st.columns([1, 4, 1])
    with gcc:
        st.pyplot(fig, use_container_width=True)
    plt.close(fig)


def render(change_page=None) -> None:
    _init_state()

    context = _build_handoff_context()
    seq = context["active_sequence"]
    features = st.session_state.get(SK.ACTIVE_FEATURES, [])
    pname = context["active_sequence_name"]

    st.markdown(
        f"<h1 style='margin-bottom:0'>{_t('assembly.title')}</h1>"
        f"<p style='color:#6b7280;font-size:.875rem;margin-top:4px;margin-bottom:.75rem'>{_t('assembly.subtitle')}</p>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div style='margin:0 0 1rem 0;padding:.85rem 1rem;border-radius:10px;border:1px solid #c7d2fe;background:linear-gradient(135deg,#eef2ff 0%,#f8faff 100%);'>"
        f"<div style='font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#4338ca;margin-bottom:.35rem'>{_t('assembly.optional_title')}</div>"
        f"<div style='font-size:.92rem;color:#1f2937;line-height:1.55'>{_t('assembly.optional_body')}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if seq and context["is_from_expression_wizard"]:
        st.success(_t("assembly.received_from_wizard", length=context["active_sequence_length"], name=pname), icon=None)

    col_info, col_main = st.columns([1, 3], gap="large")
    with col_info:
        _render_construct_overview(seq, features, pname)

    with col_main:
        tab_gel, tab_clone, tab_pcr, tab_map, tab_export = st.tabs([
            _t("assembly.tab.gel"),
            _t("assembly.tab.cloning"),
            _t("assembly.tab.pcr"),
            _t("assembly.tab.map"),
            _t("assembly.tab.export"),
        ])

        with tab_gel:
            _render_virtual_gel(len(seq) if seq else 0)
        with tab_clone:
            from components.assembly_modules import tab_cloning
            tab_cloning.render()
        with tab_pcr:
            from components.assembly_modules import tab_pcr
            tab_pcr.render()
        with tab_map:
            from components.assembly_modules import tab_plasmid_map
            tab_plasmid_map.render()
        with tab_export:
            from components.assembly_modules import tab_export
            tab_export.render()
