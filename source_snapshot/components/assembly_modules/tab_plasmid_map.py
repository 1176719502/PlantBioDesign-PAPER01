"""
components/assembly_modules/tab_plasmid_map.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Sequence Visualization tab — linear sequence map using dna_features_viewer.

Data sources (in priority order):
  1. st.session_state['assembly_result']  — assembled product string from the
     Cloning Simulation tab (plain DNA string).
  2. st.session_state['build_seq']        — manually entered / FASTA-parsed
     sequence from the current Build session.

Feature annotations are taken from st.session_state['build_features'] when
available, and supplemented with automatic ORF / regulatory-motif detection.

All rendering is delegated to components.plasmid_map.render_plasmid_map,
which uses dna_features_viewer (DFV) with a graceful matplotlib fallback.
"""
from __future__ import annotations

import io
import re
from typing import List, Dict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import streamlit as st

from components.assembly_modules.assembly_utils import (
    clean_dna, validate_sequence, sequence_stats, quality_warnings,
)
from core.activity_log import log_build_activity
from core.i18n import t as _t
from core.session_keys import SK

try:
    from components.plasmid_map import render_plasmid_map
    _PMAP_OK = True
except Exception:
    _PMAP_OK = False

try:
    from Bio import SeqIO as _SeqIO
    _BIO_OK = True
except ImportError:
    _BIO_OK = False


# ---------------------------------------------------------------------------
# Scientific color palette — feature type -> hex
# ---------------------------------------------------------------------------

_TYPE_COLORS: Dict[str, str] = {
    'promoter':   '#3B82F6',   # blue
    'rbs':        '#F59E0B',   # amber
    'cds':        '#10B981',   # emerald green
    'terminator': '#EF4444',   # red
    'reporter':   '#8B5CF6',   # violet
    'operator':   '#06B6D4',   # cyan
    'regulatory': '#A78BFA',   # light violet
    'vector':     '#6B7280',   # grey
    'origin':     '#14B8A6',   # teal
    'resistance': '#F97316',   # orange
    'marker':     '#EC4899',   # pink
    'misc':       '#9CA3AF',   # muted grey
}

_PART_LABEL: Dict[str, str] = {
    'promoter':   'Promoter',
    'rbs':        'RBS',
    'cds':        'CDS',
    'terminator': 'Terminator',
    'reporter':   'Reporter',
    'operator':   'Operator',
    'regulatory': 'Regulatory',
    'vector':     'Vector backbone',
    'origin':     'Origin of replication',
    'resistance': 'Antibiotic resistance',
    'marker':     'Selection marker',
    'misc':       'Misc. feature',
}


def _color_for_type(part_type: str) -> str:
    """Return hex color for a given part type string."""
    return _TYPE_COLORS.get(part_type.lower(), _TYPE_COLORS['misc'])


def _first_recorded_value(feature: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = feature.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _feature_direction_label(feature: dict) -> str:
    return "reverse" if int(feature.get('strand', 1) or 1) < 0 else "forward"


def _feature_source_status(feature: dict) -> str:
    return _first_recorded_value(
        feature,
        (
            'source_status',
            'source_provenance_status',
            'provenance_status',
            'source_record_label',
            'source_label',
            'source',
        ),
    ) or "Source/provenance status not recorded"


def _feature_review_status(feature: dict) -> str:
    return _first_recorded_value(
        feature,
        ('review_status', 'documentation_status', 'manual_follow_up_status'),
    ) or "Manual documentation follow-up"


def _feature_missing_documentation_cue(feature: dict) -> str:
    missing: list[str] = []
    if _feature_source_status(feature) == "Source/provenance status not recorded":
        missing.append("source/provenance")
    if _feature_review_status(feature) == "Manual documentation follow-up":
        missing.append("manual review")
    if missing:
        return "Missing documentation cue: " + ", ".join(missing)
    return "Documentation cue recorded"


def _build_feature_readback_rows(features: List[dict]) -> List[dict[str, str]]:
    rows: List[dict[str, str]] = []
    for feature in features:
        part_type = str(feature.get('type') or 'misc').lower()
        rows.append({
            'Feature name': str(feature.get('label') or feature.get('name') or 'Feature'),
            'Feature type': _PART_LABEL.get(part_type, part_type.capitalize()),
            'Source/provenance status': _feature_source_status(feature),
            'Direction/orientation': _feature_direction_label(feature),
            'Missing documentation cue': _feature_missing_documentation_cue(feature),
            'Manual follow-up status': _feature_review_status(feature),
        })
    return rows


# ---------------------------------------------------------------------------
# Feature normalisation
# ---------------------------------------------------------------------------

def _normalise_features(raw_features: List[dict], seq_len: int) -> List[dict]:
    """
    Accept features in either of the two internal formats used by the project:

      Format A (assembly_modules):  keys Name, Start, End, Type, Color
      Format B (construct_builder): keys name, start, end, type

    Returns a list of dicts suitable for render_plasmid_map::

        { 'label': str, 'start': int, 'end': int,
          'type': str, 'color': str, 'strand': int }
    """
    normalised: List[dict] = []
    for feat in raw_features:
        try:
            # Resolve name
            label = (
                feat.get('label')
                or feat.get('Name')
                or feat.get('name')
                or 'Feature'
            )
            # Resolve type
            part_type = (
                str(feat.get('type') or feat.get('Type') or 'misc').lower()
            )
            # Resolve coordinates — both formats may be 0-based or 1-based;
            # render_plasmid_map uses 0-based half-open [start, end).
            raw_start = feat.get('start', feat.get('Start', 0))
            raw_end   = feat.get('end',   feat.get('End',   raw_start + 10))
            start = max(0, int(raw_start))
            end   = min(seq_len, int(raw_end))
            if end <= start:
                end = min(seq_len, start + 1)
            # Resolve color
            color = (
                feat.get('color')
                or feat.get('Color')
                or _color_for_type(part_type)
            )
            normalised.append({
                'label':  str(label),
                'start':  start,
                'end':    end,
                'type':   part_type,
                'color':  color,
                'strand': int(feat.get('strand', 1)),
                'source_status': _first_recorded_value(
                    feat,
                    (
                        'source_status',
                        'source_provenance_status',
                        'provenance_status',
                        'source_record_label',
                        'source_label',
                        'source',
                    ),
                ),
                'review_status': _first_recorded_value(
                    feat,
                    ('review_status', 'documentation_status', 'manual_follow_up_status'),
                ),
            })
        except Exception:
            continue
    return normalised


# ---------------------------------------------------------------------------
# Auto-detection of ORFs and regulatory motifs
# ---------------------------------------------------------------------------

def _auto_detect_features(seq: str) -> List[dict]:
    """
    Detect ORFs (>= 100 bp) and a curated set of regulatory motifs.
    Returns a list in the normalised feature format.
    """
    feats: List[dict] = []
    s = seq.upper()

    # Open reading frames (forward strand only, minimum 100 bp)
    for m in re.finditer(r'ATG(?:[ATCG]{3})*?(?:TAA|TAG|TGA)', s):
        if len(m.group()) >= 100:
            feats.append({
                'label':  f'ORF_{m.start() + 1}',
                'start':  m.start(),
                'end':    m.end(),
                'type':   'cds',
                'color':  _TYPE_COLORS['cds'],
                'strand': 1,
            })

    # Regulatory motifs
    _MOTIFS: List[tuple] = [
        ('TATAAA', 'TATA box',  'regulatory'),
        ('CCAAT',  'CAAT box',  'regulatory'),
        ('TTGACA', '-35 box',   'promoter'),
        ('TATAAT', '-10 box',   'promoter'),
        ('AAAGAGGAG', 'Shine-Dalgarno', 'rbs'),
    ]
    for pattern, name, ptype in _MOTIFS:
        for m in re.finditer(pattern, s):
            feats.append({
                'label':  name,
                'start':  m.start(),
                'end':    m.end(),
                'type':   ptype,
                'color':  _color_for_type(ptype),
                'strand': 1,
            })

    return feats[:30]   # cap to avoid rendering overload


# ---------------------------------------------------------------------------
# Sequence statistics panel
# ---------------------------------------------------------------------------

def _render_stats_panel(seq: str) -> None:
    """Render a four-column metrics bar for the given DNA sequence."""
    stats = sequence_stats(seq)
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric('Sequence Length',   f"{stats['length']:} bp")
    col_b.metric('GC Content',     f"{stats['gc_content']:.1f} %")
    col_c.metric('AT Content',     f"{stats['at_content']:.1f} %")
    col_d.metric('Estimated Tm',     f"{stats['tm']:.1f} \u00b0C")
    for warning in quality_warnings(seq):
        st.warning(warning)


# ---------------------------------------------------------------------------
# Feature legend
# ---------------------------------------------------------------------------

def _render_feature_legend(features: List[dict]) -> None:
    """Display a compact inline colour legend for the feature set."""
    seen: set = set()
    badges: List[str] = []
    for feat in features:
        ptype = feat.get('type', 'misc').lower()
        label = _PART_LABEL.get(ptype, ptype.capitalize())
        color = feat.get('color', _color_for_type(ptype))
        key   = (label, color)
        if key in seen:
            continue
        seen.add(key)
        badges.append(
            f'<span style="'
            f'display:inline-flex;align-items:center;gap:5px;'
            f'background:{color}1a;border:1px solid {color}66;'
            f'border-radius:20px;padding:2px 12px;'
            f'font-size:.73rem;font-weight:600;color:{color};margin:2px">'
            f'<span style="width:8px;height:8px;border-radius:50%;'
            f'background:{color};display:inline-block"></span>'
            f'{label}</span>'
        )
    if badges:
        st.markdown(
            '<div style="display:flex;flex-wrap:wrap;gap:2px;margin:6px 0 10px">'
            + ''.join(badges) + '</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Main render entry point
# ---------------------------------------------------------------------------

def render() -> None:
    """
    Render the Sequence Visualization tab.

    Sequence resolution order
    -------------------------
    1. st.session_state['ctx_seq']          (original active handoff sequence)
    2. st.session_state['assembly_result']  (legacy fallback)
    3. User input via text area on this page
    """
    st.markdown("#### Sequence documentation preview")
    st.caption(
        "Sequence documentation preview for construct feature-order review. Map annotations and topology views are "
        "workspace references only: not sequence verification, not cloning feasibility verification, "
        "not experimental readiness approval, and not a replacement for expert/company review."
    )

    # ── 1. Resolve sequence from session state ────────────────────────────
    assembly_result = st.session_state.get(SK.ASSEMBLY_RESULT, '')
    active_seq      = st.session_state.get(SK.ACTIVE_SEQ, '')

    # assembly_result may be a plain string (product of tab_cloning) or a dict
    if isinstance(assembly_result, dict):
        seq_from_state = assembly_result.get('final_sequence', '')
    else:
        seq_from_state = str(assembly_result) if assembly_result else ''

    seq_from_state = active_seq or seq_from_state
    seq_from_state, _ = clean_dna(seq_from_state) if seq_from_state else ('', [])

    # ── 2. Sequence source controls ──────────────────────────────────────
    st.markdown("**Sequence documentation input**")
    col_src, col_name = st.columns([3, 1])

    with col_src:
        seq_input = st.text_area(
            "DNA sequence (plain or FASTA format)",
            value=seq_from_state,
            height=110,
            placeholder=">construct\nATGCATGCATGC...",
            key="vizmap_seq_input",
            label_visibility="collapsed",
        )

    with col_name:
        construct_name = st.text_input(
            "Construct label",
            value=st.session_state.get(SK.PROJECT_NAME, 'Construct'),
            key="vizmap_cname",
        )
        map_type = st.radio(
            "Map topology",
            ["Linear", "Circular"],
            horizontal=True,
            key="vizmap_topology",
        )

    # ── 3. Parse input sequence ───────────────────────────────────────────
    seq_clean = ''
    if seq_input.strip():
        raw = seq_input.strip()
        if raw.startswith('>') and _BIO_OK:
            try:
                rec = next(_SeqIO.parse(io.StringIO(raw), 'fasta'))
                seq_clean = str(rec.seq).upper()
                if rec.id and rec.id != '<unknown id>':
                    construct_name = rec.id
            except Exception:
                seq_clean, _ = clean_dna(raw)
        else:
            seq_clean, parse_warns = clean_dna(raw)
            for w in parse_warns:
                st.warning(w)

    # ── 4. Guard: empty state ─────────────────────────────────────────────
    if not seq_clean or len(seq_clean) < 20:
        st.info(
            "No sequence documentation is available yet. Add or paste sequence data above for manual "
            "documentation follow-up; missing sequence data is not treated as an experimental outcome signal."
        )
        return

    # ── 5. Validate sequence ──────────────────────────────────────────────
    is_valid, val_msg = validate_sequence(seq_clean)
    if not is_valid:
        st.error(f"Sequence documentation check could not parse this input: {val_msg}")
        return

    seq_len = len(seq_clean)

    # ── 6. Sequence statistics panel ─────────────────────────────────────
    st.divider()
    st.markdown("**Sequence Statistics**")
    _render_stats_panel(seq_clean)

    # ── 7. Feature annotation ─────────────────────────────────────────────
    st.divider()
    st.markdown("**Construct feature order preview**")

    col_feat_a, col_feat_b = st.columns([2, 1])
    auto_detect = col_feat_a.checkbox(
        "Detect features automatically (ORFs and regulatory elements)",
        value=True,
        key="vizmap_auto_feat",
    )

    # Pull features from session state (set by Design / Cloning tabs)
    session_features: List[dict] = st.session_state.get(SK.FEATURES, [])

    raw_features: List[dict] = list(session_features)  # copy to avoid mutation
    if auto_detect:
        detected = _auto_detect_features(seq_clean)
        raw_features = raw_features + detected

    features = _normalise_features(raw_features, seq_len)

    # Deduplicate by (label, start, end)
    seen_coords: set = set()
    unique_features: List[dict] = []
    for f in features:
        key = (f['label'], f['start'], f['end'])
        if key not in seen_coords:
            seen_coords.add(key)
            unique_features.append(f)
    features = unique_features

    feat_count = len(features)
    col_feat_b.metric("Documented features", feat_count)

    if feat_count == 0:
        st.info(
            "No documented features were found for this sequence. Add feature annotations or keep this item "
            "as manual documentation follow-up before using a map preview for handoff review."
        )
    else:
        _render_feature_legend(features)

    # Optional: feature summary table
    with st.expander(f"Assembly documentation readback ({feat_count} feature records)", expanded=False):
        if features:
            import pandas as pd
            df_feat = pd.DataFrame([
                {
                    **row,
                    'Start':  f['start'],
                    'End':    f['end'],
                    'Length': f['end'] - f['start'],
                }
                for f, row in zip(features, _build_feature_readback_rows(features))
            ])
            st.dataframe(
                df_feat,
                use_container_width=True,
                hide_index=True,
                column_config={
                    'Start':  st.column_config.NumberColumn('Start (bp)', format='%d'),
                    'End':    st.column_config.NumberColumn('End (bp)',   format='%d'),
                    'Length': st.column_config.NumberColumn('Length (bp)',format='%d'),
                },
            )
        else:
            st.caption(
                "No feature documentation is available to display. Manual documentation follow-up is required "
                "before this surface can show a construct feature-order preview."
            )

    # ── 8. Enzyme site selection ──────────────────────────────────────────
    st.divider()
    with st.expander("Restriction site overlay (optional)", expanded=False):
        _COMMON_ENZYMES = [
            'EcoRI', 'BamHI', 'HindIII', 'NotI', 'XhoI',
            'NdeI',  'NcoI',  'XbaI',    'SalI', 'KpnI',
            'BsaI',  'BsmBI', 'SmaI',    'EcoRV','NheI',
        ]
        selected_enzymes: List[str] = st.multiselect(
            "Restriction enzymes to overlay on the map",
            options=_COMMON_ENZYMES,
            default=[],
            key="vizmap_enzymes",
        )

    # ── 9. Render map ─────────────────────────────────────────────────────
    st.divider()
    if feat_count == 0:
        st.caption(
            "Map rendering is paused because required feature documentation is missing. This is a documentation "
            "follow-up state, not an outcome or wet-lab readiness judgment."
        )
        return

    st.markdown("**Sequence documentation map**")
    st.caption(
        f"Construct: **{construct_name}** \u00b7 "
        f"Length: **{seq_len:,} bp** \u00b7 "
        f"Topology: **{map_type}** \u00b7 "
        f"Feature records: **{feat_count}** \u00b7 "
        "documentation-only preview"
    )

    if not _PMAP_OK:
        st.error(
            "The sequence documentation map component could not be loaded. "
            "Confirm that `components/plasmid_map.py` exists and that "
            "`dna_features_viewer` is installed (`pip install dna_features_viewer`)."
        )
        return

    try:
        render_plasmid_map(
            sequence=seq_clean,
            features=features,
            enzymes=selected_enzymes,
            map_type=map_type,
        )
    except Exception as render_exc:
        st.error(f"Sequence documentation map rendering failed: {render_exc}")
        st.code(
            seq_clean[:300] + ('...' if seq_len > 300 else ''),
            language='text',
        )
        return

    # ── 10. Activity log + session state persistence ──────────────────────
    st.session_state[SK.ACTIVE_SEQ]      = seq_clean
    st.session_state[SK.ACTIVE_FEATURES] = features
    st.session_state[SK.PROJECT_NAME]    = construct_name

    st.caption(
        "Some map actions may update the local active sequence context and record local workspace activity for traceability. "
        "This remains documentation-only and does not verify cloning feasibility or experimental readiness."
    )

    log_build_activity(
        f"Sequence map: {construct_name}",
        f"{seq_len:,} bp \u00b7 {map_type} \u00b7 {feat_count} features",
    )
