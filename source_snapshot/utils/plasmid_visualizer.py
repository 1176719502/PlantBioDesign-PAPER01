"""
utils/plasmid_visualizer.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
PlasmidVisualizer - reusable utility for circular and linear DNA feature maps.
Uses dna_features_viewer (Edinburgh Genome Foundry) with a matplotlib fallback.

Install: pip install dna_features_viewer  (already in requirements.txt v3.1.3)

Usage::
    from utils.plasmid_visualizer import PlasmidVisualizer
    viz = PlasmidVisualizer()
    fig, png_bytes = viz.draw_circular_map(
        sequence='ATGCGT...',
        features=[{'label': 'CDS', 'start': 0, 'end': 600, 'type': 'cds'}],
        title='pMyPlasmid',
    )
    import streamlit as st
    st.pyplot(fig)
    st.download_button('Download PNG', png_bytes, 'plasmid.png', 'image/png')
"""
from __future__ import annotations

import io
import re
import math
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use('Agg')
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
_TYPE_COLORS: Dict[str, str] = {
    'promoter':   '#3B82F6',
    'rbs':        '#F59E0B',
    'cds':        '#10B981',
    'terminator': '#EF4444',
    'reporter':   '#8B5CF6',
    'operator':   '#06B6D4',
    'regulatory': '#A78BFA',
    'vector':     '#6B7280',
    'origin':     '#14B8A6',
    'resistance': '#F97316',
    'marker':     '#EC4899',
    'misc':       '#9CA3AF',
    'kozak':      '#D97706',
    'tag':        '#7C3AED',
}

# ---------------------------------------------------------------------------
# dna_features_viewer — optional, graceful fallback if not installed
# ---------------------------------------------------------------------------
_DFV_OK = False
_GraphicFeature = None
_CircularGraphicRecord = None
_GraphicRecord = None

try:
    from dna_features_viewer import (
        GraphicFeature        as _GF,
        CircularGraphicRecord as _CGR,
        GraphicRecord         as _GR,
    )
    _GraphicFeature        = _GF
    _CircularGraphicRecord = _CGR
    _GraphicRecord         = _GR
    _DFV_OK = True
except ImportError:
    pass


def _color_for_type(part_type: str) -> str:
    return _TYPE_COLORS.get(str(part_type).lower().strip(), _TYPE_COLORS['misc'])


def _resolve_strand(raw) -> int:
    return {'+': 1, '-': -1, 1: 1, -1: -1, 0: 1, '1': 1, '-1': -1}.get(raw, 1)


def _create_figure(*args, **kwargs) -> Tuple[plt.Figure, object]:
    fig = Figure(*args, **kwargs)
    FigureCanvasAgg(fig)
    return fig, fig.subplots()


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class PlasmidVisualizer:
    """Render circular and linear DNA feature maps.

    All draw_* methods return ``(matplotlib.figure.Figure, png_bytes)``.
    The bytes object is PNG-encoded and ready for Streamlit download buttons.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def draw_circular_map(
        self,
        sequence: str,
        features: List[Dict],
        title: str = 'Circular Plasmid Map',
        figsize: Tuple[float, float] = (4, 4),
    ) -> Tuple[plt.Figure, bytes]:
        """Render a circular plasmid map.

        Parameters
        ----------
        sequence : str
            Full DNA sequence (A/T/C/G). Length is used for the map scale.
        features : list of dict
            Keys: label, start (int), end (int),
                  type (str, optional), strand (int|str, optional),
                  color (str hex, optional)
        title : str
            Map title.
        figsize : tuple
            Matplotlib figure size in inches.

        Returns
        -------
        (fig, png_bytes)
        """
        seq_clean  = self._clean_seq(sequence)
        seq_len    = max(len(seq_clean), 1)
        norm_feats = self._normalise_features(features, seq_len)
        if _DFV_OK:
            fig = self._dfv_circular(norm_feats, seq_len, title, figsize)
        else:
            fig = self._fallback_circular(norm_feats, seq_len, title, figsize)
        return fig, self._fig_to_png(fig)

    def draw_linear_map(
        self,
        sequence: str,
        features: List[Dict],
        title: str = 'Linear Construct Map',
        figsize: Tuple[float, float] = (12, 3.5),
    ) -> Tuple[plt.Figure, bytes]:
        """Render a linear DNA feature map. Parameters mirror draw_circular_map."""
        seq_clean  = self._clean_seq(sequence)
        seq_len    = max(len(seq_clean), 1)
        norm_feats = self._normalise_features(features, seq_len)
        if _DFV_OK:
            fig = self._dfv_linear(norm_feats, seq_len, title, figsize)
        else:
            fig = self._fallback_linear(norm_feats, seq_len, title, figsize)
        return fig, self._fig_to_png(fig)

    def export_to_bytes(
        self, fig: plt.Figure, fmt: str = 'png', dpi: int = 150
    ) -> bytes:
        """Export a matplotlib Figure to bytes (png or svg)."""
        buf = io.BytesIO()
        fig.savefig(buf, format=fmt, dpi=dpi, bbox_inches='tight',
                    pad_inches=0.2, facecolor=fig.get_facecolor())
        buf.seek(0)
        return buf.read()

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_seq(raw: str) -> str:
        lines = [ln for ln in raw.splitlines() if not ln.strip().startswith('>')]
        return re.sub(r'[^ATCGatcg]', '', ''.join(lines)).upper()

    @staticmethod
    def _normalise_features(features: List[Dict], seq_len: int) -> List[Dict]:
        """Accept features in any internal project format; return uniform dicts."""
        out: List[Dict] = []
        for feat in features:
            try:
                label     = (feat.get('label') or feat.get('name') or
                             feat.get('Name') or 'Feature')
                part_type = str(
                    feat.get('type') or feat.get('Type') or 'misc'
                ).lower().strip()
                start = max(0, int(feat.get('start', feat.get('Start', 0))))
                end   = int(feat.get('end', feat.get('End', start + 10)))
                end   = min(seq_len, max(end, start + 1))
                color = (feat.get('color') or feat.get('Color') or
                         _color_for_type(part_type))
                strand = _resolve_strand(feat.get('strand', 1))
                out.append({
                    'label':  str(label),
                    'start':  start,
                    'end':    end,
                    'type':   part_type,
                    'color':  color,
                    'strand': strand,
                })
            except Exception:
                continue
        return out

    def _fig_to_png(self, fig: plt.Figure, dpi: int = 150) -> bytes:
        return self.export_to_bytes(fig, fmt='png', dpi=dpi)

    # ------------------------------------------------------------------
    # dna_features_viewer rendering
    # ------------------------------------------------------------------

    def _build_gfeatures(self, norm_feats: List[Dict], seq_len: int) -> list:
        gf_list = []
        for f in norm_feats:
            try:
                s = max(0, int(f['start']))
                e = min(seq_len, int(f['end']))
                e = max(e, s + 1)
                gf_list.append(_GraphicFeature(
                    start=s, end=e, strand=f['strand'],
                    color=f['color'], label=f['label'], linecolor='white',
                ))
            except Exception:
                continue
        return gf_list

    def _dfv_circular(
        self, norm_feats: List[Dict], seq_len: int,
        title: str, figsize: Tuple[float, float]
    ) -> plt.Figure:
        gfeatures = self._build_gfeatures(norm_feats, seq_len)
        record = _CircularGraphicRecord(
            sequence_length=seq_len, features=gfeatures,
            top_position=max(1, seq_len // 8),
        )
        fig, ax = _create_figure(figsize=figsize)
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')
        try:
            record.plot(
                ax=ax, with_ruler=False, strand_in_label_threshold=7,
                annotate_inline=True,
            )
        except Exception:
            plt.close(fig)
            return self._fallback_circular(norm_feats, seq_len, title, figsize)
        ax.set_title(title, fontsize=9, color='#1a1a2e', fontweight='700', pad=4)
        fig.tight_layout(pad=0.3)
        return fig

    def _dfv_linear(
        self, norm_feats: List[Dict], seq_len: int,
        title: str, figsize: Tuple[float, float]
    ) -> plt.Figure:
        gfeatures = self._build_gfeatures(norm_feats, seq_len)
        record = _GraphicRecord(sequence_length=seq_len, features=gfeatures)
        fig, ax = _create_figure(figsize=figsize)
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')
        try:
            record.plot(
                ax=ax, with_ruler=True, strand_in_label_threshold=7,
                annotate_inline=False, elevate_outline_annotations=True,
                level_offset=0.5,
            )
        except Exception:
            plt.close(fig)
            return self._fallback_linear(norm_feats, seq_len, title, figsize)
        ax.set_title(title, fontsize=11, color='#1a1a2e', fontweight='700', pad=10)
        fig.subplots_adjust(left=0.02, right=0.98, top=0.85, bottom=0.28)
        return fig

    # ------------------------------------------------------------------
    # Pure-matplotlib fallback (used when DFV is absent or raises)
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_circular(
        norm_feats: List[Dict], seq_len: int,
        title: str, figsize: Tuple[float, float]
    ) -> plt.Figure:
        """Simple circular map drawn with matplotlib arcs."""
        fig, ax = _create_figure(figsize=figsize)
        fig.patch.set_facecolor('#FAFAFA')
        ax.set_facecolor('#FAFAFA')
        ax.set_aspect('equal')
        ax.axis('off')
        R, r = 1.0, 0.18
        theta = np.linspace(0, 2 * math.pi, 360)
        ax.plot(np.cos(theta) * R, np.sin(theta) * R,
                color='#D1D5DB', lw=3, zorder=1)
        for feat in norm_feats:
            s   = feat['start'] / seq_len * 2 * math.pi
            e   = feat['end']   / seq_len * 2 * math.pi
            col = feat['color']
            lbl = feat['label']
            t   = np.linspace(s, e, max(4, int((e - s) / 0.05)))
            ro, ri = R + r, R - r
            xs = np.concatenate([np.cos(t) * ro, np.cos(t[::-1]) * ri])
            ys = np.concatenate([np.sin(t) * ro, np.sin(t[::-1]) * ri])
            ax.fill(xs, ys, color=col, alpha=0.85, zorder=2)
            mid = (s + e) / 2
            ax.text(
                math.cos(mid) * (R + r + 0.18),
                math.sin(mid) * (R + r + 0.18),
                lbl, ha='center', va='center',
                fontsize=6, fontweight='600', color='#1F2937', zorder=3,
            )
        ax.text(0, 0, f'{seq_len:,} bp', ha='center', va='center',
                fontsize=10, fontweight='700', color='#374151', zorder=4)
        ax.text(0, -0.22, title.split('(')[0].strip(),
                ha='center', va='center', fontsize=8, color='#6B7280', zorder=4)
        ax.set_xlim(-1.8, 1.8)
        ax.set_ylim(-1.8, 1.8)
        ax.set_title(title, fontsize=10, color='#1a1a2e', fontweight='700', pad=6)
        plt.tight_layout(pad=0.4)
        return fig

    @staticmethod
    def _fallback_linear(
        norm_feats: List[Dict], seq_len: int,
        title: str, figsize: Tuple[float, float]
    ) -> plt.Figure:
        """Simple linear map drawn with matplotlib arrows."""
        fig, ax = _create_figure(figsize=figsize)
        fig.patch.set_facecolor('#FAFAFA')
        ax.set_facecolor('#FAFAFA')
        ax.set_xlim(-seq_len * 0.02, seq_len * 1.02)
        ax.set_ylim(0, 10)
        ax.axis('off')
        ax.plot([0, seq_len], [5, 5], color='#D1D5DB', lw=3,
                solid_capstyle='round', zorder=1)
        hl = max(seq_len * 0.02, 1)
        for feat in norm_feats:
            try:
                s   = max(0, int(feat['start']))
                e   = min(seq_len, int(feat['end']))
                e   = max(e, s + 1)
                w   = e - s
                col = feat['color']
                lbl = feat['label']
                fwd = feat['strand'] >= 0
                h2  = min(hl, w * 0.4)
                dx  = (w - h2) if fwd else -(w - h2)
                x0  = s if fwd else e
                ax.add_patch(mpatches.FancyArrow(
                    x0, 5, dx, 0, width=3.2, head_width=4.0, head_length=h2,
                    facecolor=col, edgecolor='white', lw=0.8,
                    length_includes_head=True, zorder=2,
                ))
                ax.text(s + w / 2, 8.2, lbl, ha='center', va='bottom',
                        fontsize=7, fontweight='600', color=col, zorder=3)
            except Exception:
                continue
        ax.set_title(title, fontsize=10, color='#1a1a2e',
                     fontweight='700', loc='left')
        plt.tight_layout(pad=0.4)
        return fig
