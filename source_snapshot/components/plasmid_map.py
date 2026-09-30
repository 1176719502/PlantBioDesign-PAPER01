# [ACTIVE - ASSEMBLY SEQUENCE MAP RENDERER]
# Used by components/assembly_modules/tab_plasmid_map.py for the active
# Assembly and Cloning Sequence Map surface.
# Not used by the Expression Wizard Step 4/Step 6 PNG/export map path.
"""
components/plasmid_map.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Assembly Sequence Map renderer for BioDesign Studio.

This module owns the Streamlit-rendered Assembly and Cloning sequence
documentation preview. Wizard construct/cassette PNG previews are rendered by
utils.plasmid_visualizer.PlasmidVisualizer instead.

Fixes
-----
* import re added (NameError in _fig_to_svg_str)
* DFV except block calls _render_fallback instead of silently returning
* _build_graphic_features clamps coords to [0, seq_len], skips bad entries
"""
from __future__ import annotations
import html, io, re, json
from typing import Dict, List
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import streamlit as st
import streamlit.components.v1 as st_components

_DFV_OK = False
GraphicFeature = CircularGraphicRecord = GraphicRecord = None
try:
    from dna_features_viewer import (
        GraphicFeature as _GF,
        CircularGraphicRecord as _CGR,
        GraphicRecord as _GR,
    )
    GraphicFeature, CircularGraphicRecord, GraphicRecord = _GF, _CGR, _GR
    _DFV_OK = True
except ImportError:
    pass

_BIO_OK = False
try:
    from Bio.Seq import Seq as _BioSeq
    from Bio import Restriction as _Restriction
    _BIO_OK = True
except ImportError:
    pass

_TYPE_COLORS: Dict[str, str] = {
    'promoter':'#7EB8F7','cds':'#82D9A0','terminator':'#F4A896',
    'resistance':'#FFD580','misc':'#C3A8F0','origin':'#80D8D0',
    'marker':'#F7C59F','regulatory':'#A8D8F0',
}
_ENZYME_COLOR = '#F08080'
_STRAND_MAP: Dict = {'+':1,'-':-1,1:1,-1:-1,0:1}
_RECOG_SEQS: Dict[str,str] = {
    'EcoRI':'GAATTC','BamHI':'GGATCC','HindIII':'AAGCTT','XhoI':'CTCGAG',
    'NdeI':'CATATG','NotI':'GCGGCCGC','XbaI':'TCTAGA','SalI':'GTCGAC',
    'KpnI':'GGTACC','SacI':'GAGCTC','PstI':'CTGCAG','NcoI':'CCATGG',
    'SmaI':'CCCGGG','EcoRV':'GATATC','BglII':'AGATCT','ClaI':'ATCGAT',
    'NheI':'GCTAGC','SpeI':'ACTAGT','BsaI':'GGTCTC','BsmBI':'CGTCTC',
}


def _resolve_color(f: dict) -> str:
    if f.get('color'): return f['color']
    t = str(f.get('type','misc')).lower()
    if t == 'antibiotic': t = 'resistance'
    return _TYPE_COLORS.get(t, _TYPE_COLORS['misc'])


def _resolve_strand(f: dict) -> int:
    return _STRAND_MAP.get(f.get('strand',1), 1)


def _find_enzyme_sites(sequence:str, enzyme_names:List[str], unique_only:bool=False) -> List[Dict]:
    seq_u = sequence.upper()
    sites: List[Dict] = []
    if _BIO_OK and enzyme_names:
        try:
            bio_seq = _BioSeq(seq_u)
            valid = [getattr(_Restriction,e) for e in enzyme_names if hasattr(_Restriction,e)]
            if valid:
                rb = _Restriction.RestrictionBatch(valid)
                ana = _Restriction.Analysis(rb, bio_seq, linear=True)
                for enz, positions in ana.full().items():
                    for p in positions:
                        sites.append({'name':str(enz),'position':p-1})
                return sites
        except Exception:
            pass
    for name in enzyme_names:
        recog = _RECOG_SEQS.get(name)
        if not recog: continue
        idx = 0
        while True:
            pos = seq_u.find(recog, idx)
            if pos == -1: break
            sites.append({'name':name,'position':pos})
            idx = pos+1
    if unique_only:
        from collections import Counter
        counts = Counter(s['name'] for s in sites)
        sites = [s for s in sites if counts[s['name']]==1]
    return sites


def _fig_to_svg_str(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format='svg', bbox_inches='tight', pad_inches=0.25,
                facecolor=fig.get_facecolor())
    buf.seek(0)
    svg = buf.read().decode('utf-8')
    svg = re.sub(r'(<svg\b[^>]*?)\s+width="[^"]*"', r'\1', svg, count=1)
    svg = re.sub(r'(<svg\b[^>]*?)\s+height="[^"]*"', r'\1', svg, count=1)
    return svg.replace('<svg ','<svg style="width:100%;height:auto;display:block;" ',1)


def _render_legend(features:List[dict], enzyme_sites:List[Dict]) -> None:
    parts: List[str] = []
    seen: set = set()
    for feat in features:
        lbl = html.escape(str(feat.get('label', feat.get('type',''))))
        col = _resolve_color(feat)
        k = (lbl, col)
        if k in seen: continue
        seen.add(k)
        parts.append(f'<span style="display:inline-flex;align-items:center;gap:5px;background:{col}18;border:1px solid {col}55;border-radius:20px;padding:2px 10px;font-size:.73rem;font-weight:600;color:{col};margin:2px"><span style="width:8px;height:8px;border-radius:50%;background:{col};display:inline-block"></span>{lbl}</span>')
    seen_e: set = set()
    for site in enzyme_sites:
        n = html.escape(site['name'])
        if n in seen_e: continue
        seen_e.add(n)
        parts.append(f'<span style="display:inline-flex;align-items:center;gap:5px;background:{_ENZYME_COLOR}18;border:1px solid {_ENZYME_COLOR}55;border-radius:20px;padding:2px 10px;font-size:.73rem;font-weight:600;color:{_ENZYME_COLOR};margin:2px"><span style="width:8px;height:8px;border-radius:2px;background:{_ENZYME_COLOR};display:inline-block"></span>{n}</span>')
    if parts:
        st.markdown('<div style="display:flex;flex-wrap:wrap;gap:2px;margin:6px 0 10px">'+''.join(parts)+'</div>',unsafe_allow_html=True)


def _render_fallback(sequence:str, features:List[dict], enzyme_sites:List[Dict], map_type:str) -> None:
    from matplotlib.patches import FancyArrow
    seq_len = max(len(sequence), 1)
    fig, ax = plt.subplots(figsize=(10, 2.4))
    ax.set_facecolor('#F8FAFD'); fig.patch.set_facecolor('#F8FAFD')
    ax.set_xlim(-2, seq_len+2); ax.set_ylim(0, 10); ax.axis('off')
    ax.plot([0, seq_len],[5, 5], color='#d1d5db', lw=3, solid_capstyle='round', zorder=1)
    hl = max(seq_len * 0.02, 1)
    for feat in features:
        try:
            s = max(0, int(feat.get('start',0)))
            e = min(seq_len, int(feat.get('end', s+10))); e = max(e, s+1)
            w = e-s; c = _resolve_color(feat); lbl = str(feat.get('label',''))
            fwd = _resolve_strand(feat) >= 0
            h2 = min(hl, w*0.4); dx = (w-h2) if fwd else -(w-h2); x0 = s if fwd else e
            ax.add_patch(FancyArrow(x0,5,dx,0,width=3.2,head_width=4.0,head_length=h2,
                facecolor=c,edgecolor='white',lw=0.8,length_includes_head=True,zorder=2))
            ax.text(s+w/2,5,lbl,ha='center',va='center',fontsize=7,color='white',fontweight='bold',zorder=3)
        except Exception: continue
    for site in enzyme_sites:
        try:
            pos = int(site['position'])
            ax.axvline(pos,color=_ENZYME_COLOR,lw=1.5,linestyle='--',alpha=0.8,zorder=4)
            ax.text(pos,8.6,site['name'],ha='center',va='bottom',fontsize=6.5,color=_ENZYME_COLOR,rotation=45)
        except Exception: continue
    ax.set_title(f'Sequence documentation preview ({map_type}) - {seq_len} bp',
                 fontsize=9,color='#374151',loc='left',fontweight='600')
    plt.tight_layout(pad=0.4)
    st.markdown(f'<div style="width:100%;overflow:hidden;">{_fig_to_svg_str(fig)}</div>',unsafe_allow_html=True)
    plt.close(fig)


def _build_graphic_features(features, enzyme_sites, seq_len=1):
    gfeatures = []
    for feat in features:
        try:
            s = max(0, int(feat.get('start', 0)))
            e = int(feat.get('end', s+10))
            s = min(s, seq_len-1); e = min(e, seq_len); e = max(e, s+1)
            gfeatures.append(GraphicFeature(
                start=s, end=e, strand=_resolve_strand(feat),
                color=_resolve_color(feat),
                label=str(feat.get('label', feat.get('type', ''))),
                linecolor='white',
            ))
        except Exception:
            continue
    for site in enzyme_sites:
        try:
            pos = int(site['position'])
            s = max(0, pos-2); e = min(seq_len, pos+4); e = max(e, s+1)
            gfeatures.append(GraphicFeature(
                start=s, end=e, strand=+1,
                color=_ENZYME_COLOR, label=site['name'], linecolor='#8B0000',
            ))
        except Exception:
            continue
    return gfeatures


def _render_circular(gfeatures, seq_len, label,
                     sequence='', features_raw=None, enzyme_sites=None,
                     figsize=(6, 6)):
    if enzyme_sites is None: enzyme_sites = []
    if features_raw is None: features_raw = []
    record = CircularGraphicRecord(
        sequence_length=seq_len, features=gfeatures,
        top_position=max(1, seq_len//8),
    )
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    fig.patch.set_facecolor('white'); ax.set_facecolor('white')
    try:
        record.plot(ax=ax, with_ruler=False, strand_in_label_threshold=7,
                    annotate_inline=True)
    except Exception as err:
        plt.close(fig)
        st.warning(f'DFV rendering failed ({err}), switching to fallback.')
        _render_fallback(sequence, features_raw, enzyme_sites, 'Circular')
        return
    ax.set_title(label, fontsize=10, color='#1a1a2e', fontweight='700', pad=4)
    fig.tight_layout(pad=0.3)
    svg = _fig_to_svg_str(fig)
    plt.close(fig)
    st.markdown(f'<div style="width:100%;overflow:hidden;">{svg}</div>', unsafe_allow_html=True)


def _render_linear(gfeatures, seq_len, label,
                   sequence='', features_raw=None, enzyme_sites=None,
                   figsize=(12, 3.5)):
    if enzyme_sites is None: enzyme_sites = []
    if features_raw is None: features_raw = []
    record = GraphicRecord(sequence_length=seq_len, features=gfeatures)
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    fig.patch.set_facecolor('white'); ax.set_facecolor('white')
    try:
        record.plot(ax=ax, with_ruler=True, strand_in_label_threshold=7,
                    annotate_inline=False, elevate_outline_annotations=True,
                    level_offset=0.5)
    except Exception as err:
        plt.close(fig)
        st.warning(f'DFV rendering failed ({err}), switching to fallback.')
        _render_fallback(sequence, features_raw, enzyme_sites, 'Linear')
        return
    ax.set_title(label, fontsize=10, color='#1a1a2e', fontweight='700', pad=8)
    fig.tight_layout(pad=0.4)
    svg = _fig_to_svg_str(fig)
    plt.close(fig)
    st.markdown(f'<div style="width:100%;overflow:hidden;">{svg}</div>', unsafe_allow_html=True)


def _render_enzyme_table(enzyme_sites, seq_len):
    import pandas as pd
    rows = [
        {'Enzyme': s['name'], 'Position': s['position'],
         'Rel. pos.': f"{s['position']/max(seq_len,1)*100:.1f}%"}
        for s in enzyme_sites
    ]
    if not rows:
        return
    with st.expander(f'Restriction Sites Detected ({len(rows)})', expanded=False):
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                     column_config={'Position': st.column_config.NumberColumn(format='%d bp')})


def _render_seqviz(sequence:str, features:List[dict], map_type:str) -> bool:
    """Render interactive map with SeqViz via Streamlit HTML component.

    Returns True if render path was attempted and should be considered handled.
    Returns False only when essential inputs are missing.
    """
    seq = (sequence or '').upper().strip()
    if not seq:
        return False

    normalized_features = []
    for feat in features:
        try:
            start = max(0, int(feat.get('start', 0)))
            end = min(len(seq), int(feat.get('end', start + 1)))
            if end <= start:
                end = min(len(seq), start + 1)
            normalized_features.append({
                'name': str(feat.get('label', feat.get('type', 'Feature'))),
                'start': start,
                'end': end,
                'direction': 1 if _resolve_strand(feat) >= 0 else -1,
                'color': _resolve_color(feat),
                'type': str(feat.get('type', 'misc')).lower(),
            })
        except Exception:
            continue

    is_circular = str(map_type).strip().lower() in ('circular',)
    payload = {
        'name': 'Construct',
        'seq': seq,
        'annotations': normalized_features,
        'style': {'height': '620px', 'width': '100%'},
        'viewer': 'circular' if is_circular else 'linear',
        'enzymes': [],
    }

    payload_json = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
    html_doc = f"""
<div id=\"seqviz_root\" style=\"width:100%;min-height:620px;background:#0f1115;border:1px solid #222938;border-radius:12px;padding:6px;\"></div>
<script crossorigin src=\"https://unpkg.com/seqviz@3.7.13\"></script>
<script>
(function() {{
  const mount = document.getElementById('seqviz_root');
  if (!mount) return;
  const props = {payload_json};

  function renderWithViewer() {{
    if (!window.seqviz || !window.seqviz.Viewer) {{
      mount.innerHTML = '<div style="padding:16px;color:#fca5a5;font-family:ui-monospace,Consolas">SeqViz failed to load. Please check network and refresh.</div>';
      return;
    }}
    mount.innerHTML = '';
    try {{
      window.seqviz.Viewer('seqviz_root', props).render();
    }} catch (err) {{
      mount.innerHTML = '<div style="padding:16px;color:#fca5a5;font-family:ui-monospace,Consolas">SeqViz render error: ' + String(err) + '</div>';
    }}
  }}

  if (window.seqviz && window.seqviz.Viewer) {{
    renderWithViewer();
    return;
  }}

  const fallback = document.createElement('script');
  fallback.src = 'https://cdn.jsdelivr.net/npm/seqviz@3.7.13';
  fallback.crossOrigin = 'anonymous';
  fallback.onload = renderWithViewer;
  fallback.onerror = function() {{
    mount.innerHTML = '<div style="padding:16px;color:#fca5a5;font-family:ui-monospace,Consolas">Unable to load SeqViz CDN script.</div>';
  }};
  document.head.appendChild(fallback);
}})();
</script>
"""
    st_components.html(html_doc, height=660, scrolling=False)
    return True


def render_plasmid_map(sequence, features, enzymes, map_type='Circular'):
    seq_clean = sequence.upper().strip()
    seq_len   = max(len(seq_clean), 1)
    if not map_type:
        map_type = st.radio('Map Type', ['Circular', 'Linear'],
                            horizontal=True, key='plasmid_map_type')
    else:
        map_type = map_type.strip().capitalize()
        if map_type in ('Circular',):
            map_type = 'Circular'
        elif map_type in ('Linear',):
            map_type = 'Linear'
        else:
            map_type = 'Circular'
    enzyme_sites = []
    if enzymes:
        enz_filter = st.radio(
            'Restriction Sites',
            ['All Selected', 'Unique Cutters Only', 'Hide All'],
            horizontal=True, index=1, key='plasmid_enz_filter',
        )
        if enz_filter != 'Hide All':
            enzyme_sites = _find_enzyme_sites(
                seq_clean, enzymes,
                unique_only=(enz_filter == 'Unique Cutters Only'),
            )
    _render_legend(features, enzyme_sites)
    map_label = f'Sequence documentation preview - {seq_len:,} bp'

    # SeqViz is temporarily bypassed because its embedded JS mount can show
    # only the dark container while swallowing the visible map render.
    if not _DFV_OK:
        st.warning('`dna_features_viewer` not installed - showing simplified fallback. '
                   'Run `pip install dna_features_viewer` for full rendering.')
        _render_fallback(seq_clean, features, enzyme_sites, map_type)
        return

    gfeatures = _build_graphic_features(features, enzyme_sites, seq_len=seq_len)

    feature_spans = [
        max(1, int(feat.end) - int(feat.start))
        for feat in gfeatures
        if hasattr(feat, 'start') and hasattr(feat, 'end')
    ]
    smallest_feature_span = min(feature_spans) if feature_spans else None
    force_linear_for_visibility = (
        map_type == 'Circular'
        and smallest_feature_span is not None
        and seq_len <= 500
        and smallest_feature_span <= 20
    )

    if force_linear_for_visibility:
        _render_linear(gfeatures, seq_len, map_label,
                       sequence=seq_clean, features_raw=features,
                       enzyme_sites=enzyme_sites)
    elif map_type == 'Circular':
        _render_circular(gfeatures, seq_len, map_label,
                         sequence=seq_clean, features_raw=features,
                         enzyme_sites=enzyme_sites)
    else:
        _render_linear(gfeatures, seq_len, map_label,
                       sequence=seq_clean, features_raw=features,
                       enzyme_sites=enzyme_sites)

    if enzyme_sites:
        _render_enzyme_table(enzyme_sites, seq_len)
