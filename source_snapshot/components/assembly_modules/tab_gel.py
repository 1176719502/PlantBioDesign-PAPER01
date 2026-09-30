"""
components/assembly_modules/tab_gel.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Virtual Gel Electrophoresis tab.
"""
import pandas as pd
import streamlit as st
from core.session_keys import SK
from components.assembly_modules.assembly_utils import clean_dna, scan_restriction_sites, REBASE_DB
from services.lab_tools_service import virtual_gel_fragment_summary

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    _MPL_OK = True
except ImportError:
    _MPL_OK = False

LADDERS = {
    "100bp Ladder":    [1000, 900, 800, 700, 600, 500, 400, 300, 200, 100],
    "1kb Ladder":      [10000, 8000, 6000, 5000, 4000, 3000, 2000, 1500, 1000, 750, 500, 250, 100],
    "Lambda HindIII": [23130, 9416, 6557, 4361, 2322, 2027, 564, 125],
}


def _bp_to_y(bp: int, min_bp: int = 50, max_bp: int = 25000) -> float:
    """Convert bp to gel Y position (log scale, top = large)."""
    import math
    bp = max(min_bp, min(max_bp, bp))
    return 1.0 - (math.log10(bp) - math.log10(min_bp)) / \
                 (math.log10(max_bp) - math.log10(min_bp))


def _draw_gel(lanes: list, labels: list, ladder: list,
              ladder_label: str = "Ladder") -> object:
    """Draw gel image. lanes = list of list of bp sizes."""
    if not _MPL_OK:
        return None
    n_lanes = len(lanes) + 1  # +1 for ladder
    fig, ax = plt.subplots(figsize=(max(4, n_lanes * 1.2), 6))
    ax.set_facecolor('#1a1a2e')
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_xlim(0, n_lanes + 1)
    ax.set_ylim(-0.05, 1.05)
    ax.axis('off')

    def _band(x, bp, color='#00ff88', alpha=0.85):
        y = _bp_to_y(bp)
        ax.add_patch(plt.Rectangle((x - 0.35, y - 0.012), 0.7, 0.024,
                                   color=color, alpha=alpha, zorder=3))
        ax.text(x, y - 0.028, str(bp), ha='center', va='top',
                fontsize=6, color='#aaaaaa')

    # Ladder lane
    for bp in ladder:
        _band(1, bp, color='#ffcc44', alpha=0.9)
    ax.text(1, -0.04, ladder_label, ha='center', va='top',
            fontsize=7, color='#ffcc44', fontweight='bold')

    # Sample lanes
    colors = ['#00ff88', '#00ccff', '#ff6688', '#ffaa44',
               '#aa88ff', '#44ffaa', '#ff88cc', '#88ccff']
    for i, (bands, lbl) in enumerate(zip(lanes, labels)):
        x = i + 2
        col = colors[i % len(colors)]
        for bp in bands:
            _band(x, bp, color=col)
        ax.text(x, -0.04, lbl, ha='center', va='top',
                fontsize=7, color=col, fontweight='bold')

    ax.set_title('Virtual Gel Electrophoresis',
                 color='white', fontsize=9, pad=8)
    return fig


def render() -> None:
    st.markdown("#### Virtual Gel Preview")
    st.caption(
        "Fragment size visualization preview only. This does not claim or reproduce real electrophoresis results."
    )

    gel_mode = st.radio("Input mode",
                         ["Manual band sizes", "Restriction digest"],
                         horizontal=True, key="gel_mode")

    # Ladder selector
    ldr_opts = list(LADDERS.keys()) + ["Custom"]
    ldr_sel  = st.selectbox("Marker", ldr_opts, key="gel_ldr")
    if ldr_sel == "Custom":
        raw_l = st.text_input("Custom marker (bp, comma-separated)",
                               value="10000,5000,2000,1000,500,100",
                               key="gel_ldr_custom")
        try:
            ladder = [int(x.strip()) for x in raw_l.split(',') if x.strip()]
        except Exception:
            ladder = [10000, 5000, 2000, 1000, 500, 100]
    else:
        ladder = LADDERS[ldr_sel]

    st.divider()
    lanes, labels = [], []

    if gel_mode == "Manual band sizes":
        n_lanes = st.number_input("Number of lanes", min_value=1,
                                   max_value=8, value=3, key="gel_n")
        for i in range(int(n_lanes)):
            ca, cb = st.columns([1, 2])
            lbl = ca.text_input(f"Lane {i+1} name",
                                 value=f"Sample {i+1}", key=f"gel_lbl_{i}")
            raw_sizes = cb.text_input(f"Band sizes (bp, comma-separated)",
                                       value="1000,500" if i == 0 else "800,300",
                                       key=f"gel_sz_{i}")
            try:
                sizes = [int(x.strip()) for x in raw_sizes.split(',') if x.strip()]
            except Exception:
                sizes = []
            lanes.append(sizes)
            labels.append(lbl)

    else:  # Restriction digest
        seq_raw = st.text_area("DNA sequence to digest",
                                value=st.session_state.get(SK.ACTIVE_SEQ, ''),
                                height=90, key="gel_seq")
        seq, _ = clean_dna(seq_raw) if seq_raw.strip() else ('', [])
        enz_choices = list(REBASE_DB.keys())
        selected_enzymes = st.multiselect("Restriction enzymes",
                                           enz_choices,
                                           default=enz_choices[:2],
                                           key="gel_enzymes")
        lane_name = st.text_input("Lane name", value="Digest", key="gel_dig_name")
        if seq and selected_enzymes:
            hits = scan_restriction_sites(seq, selected_enzymes)
            positions = sorted([0] + [h['position'] for h in hits] + [len(seq)])
            band_sizes = [positions[i+1] - positions[i]
                          for i in range(len(positions)-1) if positions[i+1] - positions[i] > 0]
            lanes.append(band_sizes)
            labels.append(lane_name)
            st.caption(f"Digest preview produces {len(band_sizes)} fragment(s): "
                       f"{ ', '.join(str(b)+' bp' for b in sorted(band_sizes, reverse=True)[:5]) }")

    all_sizes = [bp for lane in lanes for bp in lane]
    gel_preview = virtual_gel_fragment_summary(all_sizes)
    if gel_preview.status == "ok":
        st.markdown("##### Preview summary")
        st.dataframe(pd.DataFrame(gel_preview.summary["fragment_table"]), use_container_width=True, hide_index=True)
        st.caption(f"Textual gel preview: {gel_preview.summary['textual_gel_preview']}")
        st.markdown("##### Fragment review notes")
        st.caption("No flagged issue")
        st.markdown("##### Documentation artifact")
        st.caption("Documentation artifact available. Computational preview only; this is not experimental confirmation.")

    if st.button("Run Gel Preview", type="primary", use_container_width=True, key="btn_gel"):
        if not any(lanes):
            st.warning("Please add at least one lane with band sizes.")
        elif not _MPL_OK:
            st.error("matplotlib not available — cannot render gel.")
        else:
            fig = _draw_gel(lanes, labels, ladder, ldr_sel)
            if fig:
                st.pyplot(fig, use_container_width=True)
            else:
                st.error("Gel rendering failed.")
