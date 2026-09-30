"""
bio_utils.py  --  Sequence-calculation utilities + matplotlib helpers.
No session_state access. All functions are pure or render to st directly.

Exports (UI helpers):
    _light()                   -- apply matplotlib light theme
    _fig_to_st(fig)            -- save fig to PNG buffer and st.image()
    ui_metric_card(...)        -- render a styled HTML metric card

Exports (pure sequence functions):
    gc_content(seq)            -- float %
    mol_weight_dna(seq)        -- float Da (0.33 kDa/nt approximation)
    get_tm(seq)                -- float degC (nearest-neighbour method)
    find_orfs(seq, min_len)    -- DataFrame
    reverse_complement(seq)    -- str
    translate_seq(seq)         -- str (amino-acid sequence)
    six_frame_translation(seq) -- dict {'+1'..'-3': aa_str}
    check_frameshift_at_junction(seq1, seq2, name) -- dict

Exports (rendering):
    render_six_frame_translation(seq, highlight_stops)
    annotate_sequence(seq)     -- List[Dict]  (uses FEATURE_LIBRARY)
    render_sequence_map(seq, features, title)
    render_heatmap(seq)
    render_venn(seq, cmp_seq, cmp_name, k)
"""
from __future__ import annotations

import io
import logging
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# ── Chinese font support ──────────────────────────────────────────
def _setup_chinese_font() -> None:
    """Try to configure a CJK-capable font so Chinese labels render correctly."""
    import matplotlib.font_manager as fm
    candidates = ["SimHei", "Microsoft YaHei", "Arial Unicode MS",
                  "WenQuanYi Micro Hei", "Noto Sans CJK SC"]
    available = {f.name for f in fm.fontManager.ttflist}
    chosen = next((f for f in candidates if f in available), None)
    if chosen:
        matplotlib.rcParams["font.family"] = chosen
    # Always fix the minus-sign rendering issue
    matplotlib.rcParams["axes.unicode_minus"] = False

_setup_chinese_font()
import numpy as np
import pandas as pd
import streamlit as st
from Bio.Seq import Seq
from Bio.SeqUtils import MeltingTemp as mt

from .static_data import FEATURE_LIBRARY

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
#  MATPLOTLIB HELPERS
# ══════════════════════════════════════════════════════════════════
def _light() -> None:
    """Apply the BioDesign Studio light theme to matplotlib."""
    import matplotlib.font_manager as fm
    _candidates = ["SimHei", "Microsoft YaHei", "Arial Unicode MS",
                   "WenQuanYi Micro Hei", "Noto Sans CJK SC"]
    _available = {f.name for f in fm.fontManager.ttflist}
    _font = next((f for f in _candidates if f in _available), "DejaVu Sans")
    plt.rcParams.update({
        "figure.facecolor": "#ffffff",
        "axes.facecolor": "#ffffff",
        "axes.edgecolor": "#e5e7eb",
        "axes.labelcolor": "#374151",
        "xtick.color": "#6b7280",
        "ytick.color": "#6b7280",
        "text.color": "#111827",
        "grid.color": "#e5e7eb",
        "grid.linestyle": "--",
        "grid.alpha": 0.8,
        "font.family": _font,
        "font.size": 9,
        "axes.titlesize": 9.5,
        "axes.labelsize": 8.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.unicode_minus": False,
    })


def _fig_to_st(fig, dpi: int = 150) -> None:
    """Render a matplotlib figure to a Streamlit image widget."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=dpi)
    buf.seek(0)
    st.image(buf.read(), use_container_width=True)
    plt.close(fig)


def ui_metric_card(
    label: str,
    value,
    unit: str = "",
    delta=None,
    delta_color: str = "green",
    progress=None,
) -> None:
    """Render a styled HTML metric card via st.markdown."""
    delta_html = ""
    if delta:
        color = "#059669" if delta_color == "green" else "#D97706"
        icon = "u25b2" if delta_color == "green" else "u26a0"
        delta_html = (
            f"<span style='color:{color};background:{color}15;padding:2px 8px;"
            f"border-radius:12px;font-size:12px'>{icon} {delta}</span>"
        )
    prog_html = ""
    if progress is not None:
        bc = "#2563eb" if progress < 80 else "#059669"
        prog_html = (
            f'<div style="width:100%;background:#F3F4F6;height:5px;border-radius:3px;margin-top:10px">'
            f'<div style="width:{progress}%;background:{bc};height:5px;border-radius:3px"></div></div>'
        )
    st.markdown(
        f"""<div style="background:white;border-radius:10px;padding:18px 20px;
        box-shadow:0 2px 6px rgba(0,0,0,.05);border:1px solid #E5E7EB">
        <div style="font-size:12px;font-weight:600;color:#6B7280;text-transform:uppercase;letter-spacing:.4px">{label}</div>
        <div style="font-size:26px;font-weight:700;color:#1F2937;margin:4px 0">{value}<span style="font-size:14px;color:#9CA3AF;margin-left:4px">{unit}</span></div>
        <div>{delta_html}</div>{prog_html}</div>""",
        unsafe_allow_html=True,
    )
# ══════════════════════════════════════════════════════════════════
#  PURE SEQUENCE UTILITIES
# ══════════════════════════════════════════════════════════════════
def gc_content(seq: str) -> float:
    return (seq.count("G") + seq.count("C")) / len(seq) * 100 if seq else 0.0


def mol_weight_dna(seq: str) -> float:
    """Approximate DNA molecular weight (0.33 kDa per nucleotide)."""
    return len(seq) * 0.33


def get_tm(seq: str) -> float:
    """Nearest-neighbour Tm (degC). Returns 0.0 on failure."""
    try:
        return float(mt.Tm_NN(Seq(seq)))
    except Exception:
        return 0.0


def find_orfs(seq: str, min_len: int = 30) -> pd.DataFrame:
    """Find ORFs in all 3 forward frames. Returns DataFrame."""
    orfs = []
    for frame in range(3):
        for i in range(frame, len(seq), 3):
            if seq[i:i + 3] == "ATG":
                for j in range(i + 3, len(seq), 3):
                    if seq[j:j + 3] in ("TAA", "TAG", "TGA"):
                        if (j + 3) - i >= min_len:
                            orfs.append({
                                "Frame": frame + 1,
                                "Start": i + 1,
                                "End": j + 3,
                                "Length (bp)": (j + 3) - i,
                            })
                        break
    return (
        pd.DataFrame(orfs)
        if orfs
        else pd.DataFrame(columns=["Frame", "Start", "End", "Length (bp)"])
    )


def reverse_complement(seq: str) -> str:
    comp = str.maketrans("ATCGatcg", "TAGCtagc")
    return seq.translate(comp)[::-1]


def translate_seq(seq: str) -> str:
    try:
        s = Seq(seq)
        s = s[: len(s) - len(s) % 3]
        return str(s.translate())
    except Exception as e:
        return f"Translation error: {e}"


def six_frame_translation(seq: str) -> Dict[str, str]:
    """
    Translate all six reading frames.
    Returns dict with keys '+1', '+2', '+3', '-1', '-2', '-3'.
    """
    results: Dict[str, str] = {}
    seq_upper = seq.upper()
    for frame in range(3):
        subseq = seq_upper[frame:]
        subseq = subseq[: len(subseq) - len(subseq) % 3]
        try:
            results[f"+{frame + 1}"] = str(Seq(subseq).translate()) if subseq else ""
        except Exception:
            results[f"+{frame + 1}"] = ""
    seq_rc = reverse_complement(seq_upper)
    for frame in range(3):
        subseq = seq_rc[frame:]
        subseq = subseq[: len(subseq) - len(subseq) % 3]
        try:
            results[f"-{frame + 1}"] = str(Seq(subseq).translate()) if subseq else ""
        except Exception:
            results[f"-{frame + 1}"] = ""
    return results


def check_frameshift_at_junction(
    seq1: str, seq2: str, junction_name: str = "Junction"
) -> Dict:
    """Detect frameshift risk at the junction of two sequences."""
    len1 = len(seq1)
    len2 = len(seq2)
    is_frameshift = (len1 % 3 != 0)
    result = {
        "is_frameshift": is_frameshift,
        "upstream_len": len1,
        "downstream_len": len2,
        "junction_name": junction_name,
        "frame_offset": len1 % 3,
    }
    if is_frameshift:
        result["warning"] = (
            f"⚠ Frameshift risk! Upstream sequence at {junction_name} is {len1} bp "
            f"(not a multiple of 3) — downstream protein will undergo frameshift mutation!"
        )
        result["suggestion"] = (
            f"Recommendation: add/delete {3 - (len1 % 3)} base(s) at {junction_name} "
            "to make the upstream length a multiple of 3."
        )
    else:
        result["warning"] = None
        result["suggestion"] = (
            f"✅ {junction_name} reading frame OK (upstream length {len1} bp = {len1 // 3} × 3)"
        )
    junction_region = (
        seq1[-30:] + seq2[:30] if len1 >= 30 and len2 >= 30 else seq1 + seq2
    )
    junction_region = junction_region[: len(junction_region) - len(junction_region) % 3]
    try:
        junction_aa = str(Seq(junction_region).translate())
        stop_count = junction_aa.count("*")
        result["junction_translation"] = junction_aa
        result["stop_codons_in_junction"] = stop_count
        if stop_count > 1:
            result["warning"] = (
                (result.get("warning") or "") +
                f"\n⚠ Junction region contains {stop_count} stop codon(s), which may cause protein truncation!"
            )
    except Exception:
        result["junction_translation"] = "Translation failed"
        result["stop_codons_in_junction"] = 0
    return result
# ══════════════════════════════════════════════════════════════════
#  RENDERING FUNCTIONS
# ══════════════════════════════════════════════════════════════════
def render_six_frame_translation(seq: str, highlight_stops: bool = True) -> None:
    """Six-frame translation — compact genome-browser style tracks."""
    _light()
    translations = six_frame_translation(seq)
    # Compact height: ~0.45 in per track + small title margin
    fig, axes = plt.subplots(6, 1, figsize=(16, 4.2), sharex=True)
    fig.subplots_adjust(hspace=0.06, top=0.91, bottom=0.10, left=0.06, right=0.99)
    fig.suptitle("Six-Frame Translation", fontsize=10, fontweight="600",
                 color="#374151", y=0.97)
    frames = ["+1", "+2", "+3", "-1", "-2", "-3"]
    colors = ["#3B82F6", "#2563EB", "#1D4ED8", "#10B981", "#059669", "#047857"]
    # Thin separator line between fwd (+) and rev (-) groups
    legend_added = False
    for idx, (frame, color) in enumerate(zip(frames, colors)):
        ax = axes[idx]
        aa_seq = translations[frame]
        # Draw a subtle genome-track baseline
        ax.axhline(0.5, color=color, linewidth=0.6, alpha=0.25, zorder=1)
        if not aa_seq:
            ax.text(0.5, 0.5, "No translation", ha="center", va="center",
                    fontsize=7, color="#9CA3AF", transform=ax.transAxes)
            ax.set_ylabel(frame, fontsize=7, fontweight="600", color=color,
                          rotation=0, ha="right", va="center", labelpad=4)
            ax.set_yticks([])
            ax.set_ylim(0.1, 0.9)
            for sp in ("top", "right", "left", "bottom"):
                ax.spines[sp].set_visible(False)
            continue
        x = list(range(len(aa_seq)))
        y = [0.5] * len(aa_seq)
        stops  = [i for i, a in enumerate(aa_seq) if a == "*"]
        starts = [i for i, a in enumerate(aa_seq) if a == "M"]
        normals= [i for i, a in enumerate(aa_seq) if a not in ("*", "M")]
        if normals:
            ax.scatter([x[i] for i in normals], [y[i] for i in normals],
                       c=color, s=5, alpha=0.55, marker="|", zorder=2)
        if starts:
            ax.vlines([x[i] for i in starts], 0.25, 0.75,
                      colors="#16A34A", linewidth=0.9, alpha=0.9, zorder=5,
                      label="Start (M)" if not legend_added else None)
        if stops and highlight_stops:
            ax.scatter([x[i] for i in stops], [y[i] for i in stops],
                       c="#EF4444", s=22, alpha=0.95, marker="X",
                       edgecolors="#DC2626", linewidths=0.8, zorder=10,
                       label="Stop (*)" if not legend_added else None)
        if not legend_added and (starts or stops):
            ax.legend(loc="upper right", fontsize=6, framealpha=0.85,
                      edgecolor="#E5E7EB", ncol=2,
                      handlelength=1.2, handletextpad=0.4,
                      borderpad=0.4, labelspacing=0.3)
            legend_added = True
        info = f"{len(aa_seq)} aa"
        if starts: info += f"  {len(starts)}M"
        if stops:  info += f"  {len(stops)}*"
        ax.text(0.015, 0.72, info, transform=ax.transAxes, fontsize=5.5,
                color="#6B7280", va="center",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                          edgecolor="#E5E7EB", alpha=0.75, linewidth=0.5))
        ax.set_ylabel(frame, fontsize=7, fontweight="700", color=color,
                      rotation=0, ha="right", va="center", labelpad=4)
        ax.set_ylim(0.1, 0.9)
        ax.set_yticks([])
        for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_visible(idx == 5)  # only last track shows x-axis line
        ax.grid(axis="x", alpha=0.18, linewidth=0.5)
        # Draw a thin divider between fwd/rev groups
        if idx == 2:
            ax.plot([0, 1], [0.05, 0.05], color="#CBD5E1", linewidth=0.8,
                    transform=ax.transAxes, clip_on=False)
    axes[-1].set_xlabel("Amino acid position (codon index)",
                        fontsize=7.5, color="#6B7280")
    _fig_to_st(fig)


def annotate_sequence(seq: str) -> List[Dict]:
    """Scan seq for known elements from FEATURE_LIBRARY (fwd + rev strand)."""
    features: List[Dict] = []
    seq_upper = seq.upper()
    for category, motifs in FEATURE_LIBRARY.items():
        for name, motif_seq in motifs.items():
            motif_upper = motif_seq.upper()
            motif_len = len(motif_upper)
            start = 0
            while True:
                pos = seq_upper.find(motif_upper, start)
                if pos == -1: break
                features.append({"type": category.rstrip("s"), "name": name,
                                  "start": pos, "end": pos + motif_len,
                                  "strand": "+", "length": motif_len})
                start = pos + 1
            motif_rc = reverse_complement(motif_upper)
            start = 0
            while True:
                pos = seq_upper.find(motif_rc, start)
                if pos == -1: break
                features.append({"type": category.rstrip("s"),
                                  "name": f"{name} (Reverse)",
                                  "start": pos, "end": pos + motif_len,
                                  "strand": "-", "length": motif_len})
                start = pos + 1
    features.sort(key=lambda x: x["start"])
    return features
def render_sequence_map(seq: str, features: List[Dict], title: str = "Linear Map") -> None:
    """Collision-aware linear sequence map with greedy lane assignment."""
    _light()
    seq_len = len(seq)
    if not features or seq_len == 0:
        st.info("No features to display.")
        return

    LANE_HEIGHT = 0.55   # vertical spacing between lanes (data units)
    TRACK_H     = 0.30   # height of each feature bar
    BASE_Y      = 0.0
    PADDING     = max(1, int(seq_len * 0.005))
    DENSE_THRESHOLD = 8

    COLOR_MAP = {
        "Promoter":         "#3B82F6",
        "Terminator":       "#EF4444",
        "RBS":              "#10B981",
        "RBS/Kozak":        "#10B981",
        "Tag":              "#F59E0B",
        "Restriction Site": "#8B5CF6",
        "CDS":              "#06B6D4",
        "Ori":              "#F97316",
        "Border":           "#84CC16",
        "MCS":              "#6B7280",
    }

    def _get(f, *keys, default=0):
        for k in keys:
            if k in f:
                return f[k]
        return default

    def assign_lanes(feats, padding):
        sfeats = sorted(feats, key=lambda f: _get(f, "start", "Start"))
        lane_ends = []
        result = []
        for feat in sfeats:
            s = _get(feat, "start", "Start")
            e = _get(feat, "end",   "End", default=s + 1)
            placed = False
            for li, le in enumerate(lane_ends):
                if s >= le + padding:
                    lane_ends[li] = e
                    result.append((feat, li))
                    placed = True
                    break
            if not placed:
                result.append((feat, len(lane_ends)))
                lane_ends.append(e)
        return result, len(lane_ends)

    assignments, n_lanes = assign_lanes(features, PADDING)
    use_legend = len(features) >= DENSE_THRESHOLD

    # Figure height scales with number of lanes, minimum 4 inches
    fig_h = max(4.0, min(n_lanes * LANE_HEIGHT * 1.6 + 2.5, 18))
    fig_w = 20 if use_legend else 18

    if use_legend:
        fig, (ax, ax_leg) = plt.subplots(
            1, 2, figsize=(fig_w, fig_h),
            gridspec_kw={"width_ratios": [5, 1.4]})
    else:
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        ax_leg = None

    # Backbone
    ax.plot([0, seq_len], [BASE_Y, BASE_Y],
            color="#374151", linewidth=2.5, zorder=1, solid_capstyle="round")

    legend_handles = []
    seen_types: set = set()

    for feat, lane in assignments:
        s      = _get(feat, "start",  "Start")
        e      = _get(feat, "end",    "End",    default=s + 1)
        name   = str(_get(feat, "name",   "Name",   default=""))
        ftype  = str(_get(feat, "type",   "Type",   default="other"))
        strand = str(_get(feat, "strand", "Strand", default="+"))
        color  = COLOR_MAP.get(ftype, "#6B7280")
        y_c    = BASE_Y + (lane + 1) * LANE_HEIGHT
        w      = max(e - s, seq_len * 0.004)

        rect = patches.FancyBboxPatch(
            (s, y_c - TRACK_H / 2), w, TRACK_H,
            boxstyle="round,pad=0.003",
            linewidth=1.5,
            edgecolor=color,
            facecolor=color,
            alpha=0.82,
            zorder=2,
        )
        ax.add_patch(rect)

        # Strand arrow
        mid = s + (e - s) / 2
        dx  = max((e - s) * 0.28, seq_len * 0.004)
        if strand not in ("+", "1"):
            dx = -dx
        ax.annotate(
            "", xy=(mid + dx, y_c), xytext=(mid - dx, y_c),
            arrowprops=dict(arrowstyle="-|>", color="white", lw=1.5,
                            mutation_scale=10),
            zorder=3,
        )

        # Label — always shown
        ax.text(
            mid, y_c + TRACK_H / 2 + 0.035, name,
            ha="center", va="bottom",
            fontsize=8, color=color, fontweight="700",
            bbox=dict(boxstyle="round,pad=0.28", facecolor="white",
                      edgecolor=color, alpha=0.92, linewidth=0.9),
            zorder=4, clip_on=True,
        )

        if ftype not in seen_types:
            seen_types.add(ftype)
            legend_handles.append(
                patches.Patch(facecolor=color, edgecolor=color,
                              label=ftype, alpha=0.85))

    # x-axis
    tick_iv = max(50, seq_len // 10)
    ticks   = list(range(0, seq_len + 1, tick_iv))
    ax.set_xticks(ticks)
    ax.set_xticklabels(["{:,}".format(t) for t in ticks], fontsize=9)
    ax.set_xlim(-seq_len * 0.01, seq_len * 1.01)
    ax.set_ylim(
        BASE_Y - LANE_HEIGHT * 0.5,
        BASE_Y + (n_lanes + 1) * LANE_HEIGHT + LANE_HEIGHT * 0.8,
    )
    ax.set_yticks([])
    for sp in ["left", "right", "top"]:
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_linewidth(1.2)
    ax.tick_params(axis="x", length=4, width=1)

    ax.set_title(title, loc="left", fontsize=13, fontweight="700",
                 color="#1F2937", pad=10)
    ax.set_xlabel(
        "Position (bp)  ·  total {:,} bp".format(seq_len),
        fontsize=9.5, color="#6b7280", labelpad=8,
    )

    # Legend panel
    if use_legend and ax_leg is not None:
        ax_leg.axis("off")
        srt    = sorted(assignments, key=lambda x: _get(x[0], "start", "Start"))
        n_items = len(srt)
        ystep  = min(0.055, 0.92 / max(n_items, 1))
        ax_leg.text(0.02, 0.99, "Features", fontsize=9.5, fontweight="700",
                    color="#1F2937", transform=ax_leg.transAxes, va="top")
        for fi, (feat, _lane) in enumerate(srt):
            fname = str(_get(feat, "name",  "Name",  default=""))
            ftype = str(_get(feat, "type",  "Type",  default=""))
            s     = _get(feat, "start", "Start")
            e     = _get(feat, "end",   "End",   default=s)
            color = COLOR_MAP.get(ftype, "#6B7280")
            yp    = 0.95 - (fi + 1) * ystep
            ax_leg.add_patch(patches.Rectangle(
                (0.01, yp - 0.010), 0.09, 0.020,
                facecolor=color, edgecolor=color, alpha=0.85,
                transform=ax_leg.transAxes, clip_on=False))
            ax_leg.text(
                0.14, yp,
                "{} ({:,}-{:,})".format(fname[:18], s, e),
                fontsize=6.5, color="#374151", va="center",
                transform=ax_leg.transAxes, clip_on=False,
            )
    else:
        ax.legend(handles=legend_handles, loc="upper right",
                  fontsize=8.5, framealpha=0.92, ncol=2,
                  edgecolor="#E5E7EB")

    fig.tight_layout(pad=1.2)
    _fig_to_st(fig, dpi=180)
def render_heatmap(seq: str) -> None:
    """GC content line chart -- compact, single-panel, publication quality."""
    import numpy as _np

    window_size = 50
    step = max(1, len(seq) // 200) if len(seq) > 500 else 10

    if len(seq) < window_size:
        st.warning(
            f"Sequence length ({len(seq)} bp) is smaller than window size "
            f"({window_size} bp); cannot generate GC profile."
        )
        return

    # Compute per-window GC values
    positions = []
    gc_values = []
    for i in range(0, len(seq) - window_size + 1, step):
        w = seq[i: i + window_size]
        positions.append(i + window_size // 2)
        gc_values.append((w.count("G") + w.count("C")) / window_size * 100)

    positions_arr = _np.array(positions, dtype=float)
    gc_arr        = _np.array(gc_values, dtype=float)
    mean_gc = float(gc_arr.mean())
    std_gc  = float(gc_arr.std())

    # Single-panel GC line chart
    _light()
    fig, ax = plt.subplots(figsize=(12, 4), dpi=150)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f8fafc")

    ax.axhline(50, color="#94a3b8", linewidth=1.0, linestyle="--",
               alpha=0.8, zorder=1, label="50% baseline")
    ax.fill_between(positions_arr, gc_arr, 50,
                    where=(gc_arr >= 50), interpolate=True,
                    color="#16a34a", alpha=0.20, zorder=2, label="High GC (>=50%)")
    ax.fill_between(positions_arr, gc_arr, 50,
                    where=(gc_arr < 50), interpolate=True,
                    color="#2563eb", alpha=0.18, zorder=2, label="Low GC (<50%)")
    ax.plot(positions_arr, gc_arr,
            color="#1e3a8a", linewidth=1.6, alpha=0.95, zorder=3)
    ax.axhline(mean_gc, color="#f97316", linewidth=1.0, linestyle=":"
               , alpha=0.9, zorder=4, label=f"Mean {mean_gc:.1f}%")

    ax.set_xlim(positions_arr[0], positions_arr[-1])
    ax.set_ylim(0, 100)
    ax.set_xlabel(
        f"Sequence position (bp)  ·  window {window_size} bp, step {step} bp",
        fontsize=8.5, color="#6b7280",
    )
    ax.set_ylabel("GC Content (%)", fontsize=8.5, color="#6b7280")
    ax.set_title(
        f"GC Content Profile  ({len(seq):,} bp)",
        loc="left", fontsize=10, fontweight="600", color="#1f2937", pad=8,
    )
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=8, framealpha=0.85, edgecolor="#e5e7eb",
              loc="upper right", handlelength=1.5)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#e5e7eb")
    ax.spines["bottom"].set_color("#e5e7eb")

    fig.tight_layout(pad=0.6)
    _fig_to_st(fig, dpi=150)
    st.caption(
        f"Mean GC: **{mean_gc:.1f}%** ± {std_gc:.1f}%"
        f"  |  Min: {gc_arr.min():.1f}%"
        f"  |  Max: {gc_arr.max():.1f}%"
        f"  |  Windows: {len(gc_values)}"
    )


def render_venn(seq: str, cmp_seq: str, cmp_name: str, k: int = 5, max_width: int = 320) -> None:
    """k-mer Venn diagram with matplotlib_venn (soft palette, no text overlap).

    Uses matplotlib_venn when available; graceful fallback to manual circles.
    Improvements over the original:
    - Softer, desaturated colour palette (colorblind-friendlier)
    - Larger, bold subset-count labels
    - Set-name labels positioned outside circles to avoid overlap
    - Subtitle line with Jaccard index baked into the figure title
    - Stats rendered as Streamlit metrics below the chart (unchanged)
    """
    import io as _io

    def kmers(s):
        return set(s[i: i + k] for i in range(len(s) - k + 1)) if len(s) >= k else set()

    sa, sb  = kmers(seq), kmers(cmp_seq)
    only_a  = len(sa - sb)
    only_b  = len(sb - sa)
    shared  = len(sa & sb)
    total   = only_a + only_b + shared
    jaccard = shared / total if total > 0 else 0.0
    min_sz  = min(len(sa), len(sb))
    overlap = shared / min_sz * 100 if min_sz > 0 else 0.0

    label_a = "Current Seq"
    label_b = cmp_name[:18]

    # Soft, desaturated palette
    COL_A      = "#6baed6"   # muted blue
    COL_B      = "#74c476"   # muted green
    COL_EDGE_A = "#2171b5"
    COL_EDGE_B = "#238b45"
    COL_SHARED = "#9e9ac8"   # soft lavender for the intersection

    try:
        from matplotlib_venn import venn2, venn2_circles

        fig, ax = plt.subplots(figsize=(5.2, 4.6), dpi=130)
        fig.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#ffffff")

        v = venn2(
            subsets=(only_a, only_b, shared),
            set_labels=("", ""),   # suppress built-in labels; we draw our own
            ax=ax,
            alpha=0.0,             # we set colours manually below
        )

        # Colour patches
        _patch_cfg = [
            ("10", COL_A,      0.52),
            ("01", COL_B,      0.52),
            ("11", COL_SHARED, 0.70),
        ]
        for pid, col, alph in _patch_cfg:
            p = v.get_patch_by_id(pid)
            if p:
                p.set_facecolor(col)
                p.set_alpha(alph)
                p.set_edgecolor("none")

        # Edge circles — thin, dark
        c = venn2_circles(subsets=(only_a, only_b, shared), ax=ax, linewidth=1.6)
        if c[0]: c[0].set_edgecolor(COL_EDGE_A); c[0].set_linewidth(1.6)
        if c[1]: c[1].set_edgecolor(COL_EDGE_B); c[1].set_linewidth(1.6)

        # Subset count labels — larger, bold
        for pid, col in (("10", COL_EDGE_A), ("01", COL_EDGE_B), ("11", "#3f007d")):
            lbl = v.get_label_by_id(pid)
            if lbl:
                lbl.set_fontsize(14)
                lbl.set_fontweight("bold")
                lbl.set_color(col)

        # Draw set-name labels manually outside the circles to avoid overlap
        # Get circle centres from venn2 internals
        try:
            centres = [v.get_circle_center(i) for i in range(2)]
            radii   = [v.get_circle_radius(i)  for i in range(2)]
            offset  = 0.06
            ax.text(centres[0].x, centres[0].y + radii[0] + offset,
                    label_a, ha="center", va="bottom",
                    fontsize=9, fontweight="700", color=COL_EDGE_A)
            ax.text(centres[1].x, centres[1].y + radii[1] + offset,
                    label_b, ha="center", va="bottom",
                    fontsize=9, fontweight="700", color=COL_EDGE_B)
        except Exception:
            # Fallback: use fixed positions
            ax.text(0.28, 0.88, label_a, transform=ax.transAxes,
                    ha="center", va="bottom",
                    fontsize=9, fontweight="700", color=COL_EDGE_A)
            ax.text(0.72, 0.88, label_b, transform=ax.transAxes,
                    ha="center", va="bottom",
                    fontsize=9, fontweight="700", color=COL_EDGE_B)

        ax.set_title(
            f"{k}-mer Similarity  |  Jaccard = {jaccard:.3f}",
            fontsize=10, fontweight="600", color="#374151",
            loc="center", pad=10,
        )
        fig.tight_layout(pad=1.2)

    except ImportError:
        # ── Manual fallback circles ───────────────────────────────────────
        fig, ax = plt.subplots(figsize=(5.2, 4.6), dpi=130)
        fig.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#ffffff")

        total_a = only_a + shared
        total_b = only_b + shared
        max_sz  = max(total_a, total_b, 1)
        r_a = 0.26 * np.sqrt(total_a / max_sz) if total_a > 0 else 0.16
        r_b = 0.26 * np.sqrt(total_b / max_sz) if total_b > 0 else 0.16
        distance = (r_a + r_b) * (0.85 - jaccard * 0.35)
        cx, cy = 0.5, 0.5
        ca = (cx - distance / 2, cy)
        cb = (cx + distance / 2, cy)
        margin = 0.14
        ax.set_xlim(ca[0] - r_a - margin, cb[0] + r_b + margin)
        ax.set_ylim(cy - max(r_a, r_b) - margin,
                    cy + max(r_a, r_b) + margin + 0.14)
        ax.set_aspect("equal")

        ax.add_patch(patches.Circle(ca, r_a, facecolor=COL_A, alpha=0.50,
                                    edgecolor=COL_EDGE_A, lw=1.8))
        ax.add_patch(patches.Circle(cb, r_b, facecolor=COL_B, alpha=0.50,
                                    edgecolor=COL_EDGE_B, lw=1.8))

        ax.text(ca[0] - r_a * 0.45, cy, str(only_a),
                ha="center", va="center",
                fontsize=13, fontweight="bold", color="#1e40af")
        ax.text(cb[0] + r_b * 0.45, cy, str(only_b),
                ha="center", va="center",
                fontsize=13, fontweight="bold", color="#065f46")
        ax.text((ca[0] + cb[0]) / 2, cy, str(shared),
                ha="center", va="center",
                fontsize=13, fontweight="bold", color="#4c1d95")

        ax.text(ca[0], cy + r_a + 0.06, label_a,
                ha="center", va="bottom",
                fontsize=9, fontweight="700", color=COL_EDGE_A)
        ax.text(cb[0], cy + r_b + 0.06, label_b,
                ha="center", va="bottom",
                fontsize=9, fontweight="700", color=COL_EDGE_B)

        ax.axis("off")
        ax.set_title(
            f"{k}-mer Similarity  |  Jaccard = {jaccard:.3f}",
            fontsize=10, fontweight="600", color="#374151",
            loc="center", pad=10,
        )
        fig.tight_layout(pad=1.2)
        st.caption("`pip install matplotlib-venn` for a more precise Venn diagram.")

    buf = _io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                pad_inches=0.18, dpi=130, facecolor="white")
    buf.seek(0)
    st.image(buf.read(), use_container_width=True)
    plt.close(fig)

    if total > 0:
        c1, c2, c3 = st.columns(3)
        c1.metric("Jaccard Index", f"{jaccard:.3f}")
        c2.metric("Overlap", f"{overlap:.1f}%")
        c3.metric(f"Shared {k}-mers", f"{shared} / {total}")
