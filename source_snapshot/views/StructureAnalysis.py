# -*- coding: utf-8 -*-
"""
views/StructureAnalysis.py
Structure & Metabolic Analysis workbench.
Layout: st.columns([1, 3]) — left: protein props, right: 3D viewer.
"""
from __future__ import annotations
import logging
import streamlit as st
import streamlit.components.v1 as components
from core.session_keys import SK
from services.tool_artifact_library_presenter import artifact_save_success_message
from services.protein_structure_analysis_service import (
    BOUNDARY_COPY,
    calculate_documentation_properties,
    pdb_id_source_state,
    structure_analysis_artifact_payload,
    uploaded_pdb_source_state,
)
from services.pathway_repository import list_pathway_projects
from services.tool_artifact_service import (
    create_tool_artifact,
    delete_tool_artifact,
    list_tool_artifacts,
    raw_payload_preview,
    readable_payload_summary,
)
from views.tool_typography import inject_tool_typography_css, render_boundary_note, render_tool_intro

logger = logging.getLogger(__name__)

_CSS = """
<style>
.prop-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 14px;margin-bottom:8px}
.prop-label{font-size:.66rem;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.6px;display:block;margin-bottom:2px}
.prop-value{font-size:1.02rem;font-weight:700;color:#2563eb;display:block;font-family:'IBM Plex Mono',monospace}
.prop-ok{color:#16a34a!important}.prop-warn{color:#ea580c!important}
.panel-sep{font-size:.66rem;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.8px;margin:14px 0 6px 0;padding-bottom:4px;border-bottom:1px solid #e5e7eb}
</style>
"""

_CODON_TABLE = {
    'TTT':'F','TTC':'F','TTA':'L','TTG':'L','CTT':'L','CTC':'L','CTA':'L','CTG':'L',
    'ATT':'I','ATC':'I','ATA':'I','ATG':'M','GTT':'V','GTC':'V','GTA':'V','GTG':'V',
    'TCT':'S','TCC':'S','TCA':'S','TCG':'S','CCT':'P','CCC':'P','CCA':'P','CCG':'P',
    'ACT':'T','ACC':'T','ACA':'T','ACG':'T','GCT':'A','GCC':'A','GCA':'A','GCG':'A',
    'TAT':'Y','TAC':'Y','TAA':'*','TAG':'*','CAT':'H','CAC':'H','CAA':'Q','CAG':'Q',
    'AAT':'N','AAC':'N','AAA':'K','AAG':'K','GAT':'D','GAC':'D','GAA':'E','GAG':'E',
    'TGT':'C','TGC':'C','TGA':'*','TGG':'W','CGT':'R','CGC':'R','CGA':'R','CGG':'R',
    'AGT':'S','AGC':'S','AGA':'R','AGG':'R','GGT':'G','GGC':'G','GGA':'G','GGG':'G',
}

ARTIFACT_EMPTY_STATE = "No saved documentation artifacts yet."
ARTIFACT_BOUNDARY_COPY = (
    "Saved artifacts are documentation records only for inspection and structure review context. "
    "PDB and uploaded structure results are local documentation review context. "
    "They are not validation, not prediction, not recommendation, not readiness approval, and not wet-lab protocol."
)
ARTIFACT_PROJECT_LINK_COPY = (
    "Linking an artifact to a pathway project is for traceability only. "
    "Linked records can be reviewed in the linked project context and are visible from Pathway Workspace linked documentation artifacts. "
    "It does not change project readiness, completeness score, or experimental status."
)
PROTEIN_INPUT_EMPTY_COPY = (
    "Enter a protein sequence or receive a CDS handoff from Expression Wizard to view sequence-derived property estimates. "
    "Property estimates are documentation-only review context."
)
STRUCTURE_SOURCE_SUMMARY_COPY = (
    "Structure source review shows either a 4-character RCSB PDB ID or a locally uploaded PDB file. "
    "Viewer failures do not change saved documentation records."
)


def _render_artifact_details(artifact: dict) -> None:
    st.caption(ARTIFACT_BOUNDARY_COPY)
    st.caption(
        "Review location: saved documentation artifacts and, when linked to a Pathway Project, "
        "Pathway Workspace linked documentation artifacts."
    )
    for label, key in (
        ("Created at", "created_at"),
        ("Record type", "artifact_type"),
        ("Title", "title"),
        ("Created from", "source_module"),
        ("Summary", "summary"),
        ("Boundary note", "boundary_label"),
        ("Notes", "notes"),
        ("Project ID", "project_id"),
    ):
        value = artifact.get(key)
        if value not in (None, ""):
            st.write(f"{label}: {value}")

    st.markdown("##### Readable payload summary")
    for label, value in readable_payload_summary(artifact.get("payload_json", {})):
        st.write(f"{label}: {value}")

    with st.expander("Advanced record details", expanded=False):
        preview, truncated = raw_payload_preview(artifact.get("payload_json", {}), max_chars=2000)
        st.code(preview, language="json")
        if truncated:
            st.caption("Payload summary truncated for readability.")


def _translate_dna(dna: str) -> str:
    dna = dna.upper().replace(' ', '').replace('\n', '')
    prot = []
    for i in range(0, len(dna) - 2, 3):
        aa = _CODON_TABLE.get(dna[i:i+3], 'X')
        if aa == '*':
            break
        prot.append(aa)
    return ''.join(prot)


@st.cache_data(ttl=3600, show_spinner=False)
def _calc_props(seq: str) -> dict:
    return calculate_documentation_properties(seq)


def _prop_card(label: str, value: str, css_class: str = '') -> str:
    return (f'<div class="prop-card">'
            f'<span class="prop-label">{label}</span>'
            f'<span class="prop-value {css_class}">{value}</span>'
            f'</div>')


_STYLE_MAP = {
    'Cartoon': "v.setStyle({},{cartoon:{color:'spectrum'}});",
    'Stick':   "v.setStyle({},{stick:{colorscheme:'Jmol',radius:0.12}});",
    'Sphere':  "v.setStyle({},{sphere:{colorscheme:'Jmol',scale:0.28}});",
    'Surface': ("v.setStyle({},{cartoon:{color:'spectrum',opacity:0.25}});"
                "v.addSurface($3Dmol.SurfaceType.VDW,{opacity:0.70,colorscheme:'spectrum'});"),
    'Line':    "v.setStyle({},{line:{colorscheme:'Jmol'}});",
}

_VIEWER_BASE_CSS = (
    "html,body{margin:0;padding:0;background:#f8f9fb;overflow:hidden}"
    "#vc{width:100%;height:HEIGHTpx;background:#f8f9fb;position:relative;"
    "border:1px solid #e5e7eb;border-radius:8px;overflow:hidden}"
    "#v{width:100%;height:100%}"
    "#bdg{position:absolute;bottom:10px;right:12px;"
    "background:rgba(248,249,251,.92);border:1px solid #e5e7eb;"
    "border-radius:6px;padding:3px 9px;"
    "font:11px monospace;color:#9ca3af;z-index:10}"
)

def _viewer_pdb_id(pid: str, style: str, spin: bool, height: int) -> str:
    js_style = _STYLE_MAP.get(style, _STYLE_MAP['Cartoon'])
    spin_js  = 'v.spin(true);' if spin else ''
    css = _VIEWER_BASE_CSS.replace('HEIGHT', str(height))
    msg_css = ("#msg{position:absolute;top:50%;left:50%;"
               "transform:translate(-50%,-50%);"
               "color:#2563eb;font:13px sans-serif;"
               "text-align:center;pointer-events:none;z-index:10}")
    return f"""<!DOCTYPE html><html><head>
<script src="https://3dmol.org/build/3Dmol-min.js"></script>
<style>{css}{msg_css}</style></head><body>
<div id="vc"><div id="v"></div>
<div id="msg">Loading {pid}...</div>
<div id="bdg">3Dmol.js / RCSB PDB</div></div>
<script>
(function(){{
var v=$3Dmol.createViewer(document.getElementById('v'),{{backgroundColor:'#f8f9fb',antialias:true}});
fetch('https://files.rcsb.org/download/{pid}.pdb')
.then(function(r){{if(!r.ok)throw new Error('PDB {pid} not found (HTTP '+r.status+')');return r.text();}})
.then(function(d){{
document.getElementById('msg').style.display='none';
v.addModel(d,'pdb');
{js_style}
v.zoomTo();v.render();{spin_js}
}}).catch(function(e){{
document.getElementById('msg').innerHTML='<div style="background:#2d1f1f;border:1px solid #7f3f3f;border-radius:8px;padding:14px;color:#fbbf24;font-size:12px"><b>Load failed:</b><br>'+e.message+'<br><small>Please verify the PDB ID on <a href="https://www.rcsb.org" target="_blank" style="color:#60a5fa">rcsb.org</a></small></div>';
}});
}})();
</script></body></html>"""


def _viewer_upload(pdb_text: str, style: str, spin: bool, height: int) -> str:
    js_style = _STYLE_MAP.get(style, _STYLE_MAP['Cartoon'])
    spin_js  = 'v.spin(true);' if spin else ''
    css = _VIEWER_BASE_CSS.replace('HEIGHT', str(height))
    safe = pdb_text.replace('\\', '\\\\').replace('`', '\\`')
    return f"""<!DOCTYPE html><html><head>
<script src="https://3dmol.org/build/3Dmol-min.js"></script>
<style>{css}</style></head><body>
<div id="vc"><div id="v"></div>
<div id="bdg">3Dmol.js &bull; Uploaded PDB</div></div>
<script>
(function(){{
var v=$3Dmol.createViewer(document.getElementById('v'),{{backgroundColor:'#f8f9fb',antialias:true}});
v.addModel(`{safe}`,'pdb');
{js_style}
v.zoomTo();v.render();{spin_js}
}})();
</script></body></html>"""

def _render_left_panel() -> str:
    """Render left column widgets and return current protein sequence."""
    st.markdown('<div class="panel-sep">Protein Physicochemical Properties</div>', unsafe_allow_html=True)

    # Auto-filled from wizard via session state
    auto_prot = st.session_state.get(SK.TRANSLATED_PROTEIN, '')
    auto_dna  = st.session_state.get(SK.ACTIVE_SEQ, '')

    # If we have a DNA CDS but no protein yet, translate it
    if auto_dna and not auto_prot:
        auto_prot = _translate_dna(auto_dna)
        if auto_prot:
            st.session_state[SK.TRANSLATED_PROTEIN] = auto_prot

    protein_seq = st.text_area(
        'Protein sequence (amino acids)',
        value=auto_prot,
        height=100,
        key='sa_prot_input',
        placeholder='MKTAYIAKQRQISFVKSHFSRQ...\n(or paste FASTA format)',
    )

    if not protein_seq.strip():
        st.info(PROTEIN_INPUT_EMPTY_COPY)
    else:
        props = _calc_props(protein_seq)
        clean = props.get('sequence', '')
        length = props.get('length', len(clean))
        mw = props.get('molecular_weight', '--')
        pi_val = props.get('isoelectric_point', '--')
        ii = props.get('instability_index', '--')
        gravy = props.get('gravy', '--')
        arom = props.get('aromaticity', '--')

        ii_class = ''
        if isinstance(ii, (int, float)):
            ii_class = 'prop-ok' if float(ii) < 40 else 'prop-warn'

        cards = [
            _prop_card('Sequence length', f'{length} aa', ''),
            _prop_card('Molecular weight estimate', f'{mw} Da', ''),
        ]
        if pi_val != '--':
            cards.append(_prop_card('Isoelectric point', str(pi_val), ''))
        if ii != '--':
            cards.append(_prop_card('Instability index', str(ii), ii_class))
        if gravy != '--':
            cards.append(_prop_card('GRAVY', str(gravy), ''))
        if arom != '--':
            cards.append(_prop_card('Aromaticity', str(arom), ''))
        st.markdown(''.join(cards), unsafe_allow_html=True)

        if not props.get('ok'):
            st.warning(props.get('error', 'Unable to calculate protein properties.'))
            invalid = props.get('invalid_residues') or []
            if invalid:
                st.caption(f'Unsupported symbols: {", ".join(invalid)}')
        else:
            st.caption('Properties are derived from the cleaned amino acid sequence only; no folding, function, expression, or readiness conclusion is generated.')

        aa_counts = props.get('aa_counts') or {}
        if aa_counts:
            with st.expander('Amino acid counts'):
                for aa_name, count in sorted(aa_counts.items()):
                    st.write(f'{aa_name}: {count}')

        if props.get('ok') and props.get('aa_percent'):
            with st.expander('Amino acid composition percentages'):
                aa = props['aa_percent']
                top = sorted(aa.items(), key=lambda x: -x[1])[:10]
                for aa_name, pct in top:
                    st.progress(min(pct / 15.0, 1.0), text=f'{aa_name}  {pct:.1f}%')

    # PDB ID is entered in the RCSB tab on the right panel (sa_rcsb_pid_main).
    # Sync sa_current_pdb from that key so left-panel prop cards remain compatible.
    _rcsb_pid = st.session_state.get('sa_rcsb_pid_main', '')
    if not _rcsb_pid:
        # Pre-populate from SK.PDB_ID hint or wizard-handoff default on first load
        _pdb_hint = st.session_state.get(SK.PDB_ID, '')
        _rcsb_pid = _pdb_hint if _pdb_hint else ('' if st.session_state.get('_wizard_handoff') else '1EMA')
        st.session_state['sa_rcsb_pid_main'] = _rcsb_pid
    st.session_state['sa_current_pdb'] = _rcsb_pid.strip().upper()

    st.divider()
    st.markdown('<div class="panel-sep">Upload PDB File</div>', unsafe_allow_html=True)
    pdb_file = st.file_uploader('Upload .pdb file', type=['pdb', 'ent'],
                                key='sa_pdb_upload')
    if pdb_file is not None:
        uploaded_text = pdb_file.read().decode('utf-8', errors='replace')
        upload_state = uploaded_pdb_source_state(uploaded_text)
        if upload_state.get('ok') == 'true':
            st.session_state['sa_uploaded_pdb'] = uploaded_text
            st.caption(f'Loaded: {pdb_file.name} · structure source = uploaded PDB file')
        else:
            st.session_state['sa_uploaded_pdb'] = ''
            st.warning(upload_state.get('message', 'Uploaded file is not supported.'))

    return protein_seq.strip() if protein_seq else ''

def _render_right_panel(protein_seq: str) -> None:
    """Render right column: viewer controls + 3Dmol iframe."""
    st.markdown(
        "<span style='font-size:.72rem;font-weight:700;color:#374151;"
        "text-transform:uppercase;letter-spacing:.6px'>Protein Structure Viewer — 3Dmol.js</span>",
        unsafe_allow_html=True,
    )

    st.caption(STRUCTURE_SOURCE_SUMMARY_COPY)

    height_map = {'Standard (530px)': 530, 'Tall (700px)': 700, 'Compact (380px)': 380}
    tab_rcsb, tab_upload = st.tabs(['RCSB PDB Online Search', 'Upload PDB File'])

    with tab_rcsb:
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        pdb_id = c1.text_input(
            'PDB ID', value=st.session_state.get('sa_current_pdb', '') or '',
            key='sa_rcsb_pid_main',
            help='RCSB accession ID, for example 1EMA, 6LU7, or 4HHB',
        )
        render_style = c2.selectbox(
            'Render style', ['Cartoon', 'Stick', 'Sphere', 'Surface', 'Line'],
            key='sa_style_rcsb',
        )
        height_opt = c3.selectbox(
            'Viewer height', ['Standard (530px)', 'Tall (700px)', 'Compact (380px)'],
            key='sa_height_rcsb',
        )
        spin = c4.checkbox('Auto-rotate', value=False, key='sa_spin_rcsb')

        viewer_h = height_map.get(height_opt, 530)

        source_state = pdb_id_source_state(pdb_id)
        pid = source_state.get('pdb_id', '')
        if source_state.get('ok') != 'true':
            st.info(
                f"{source_state.get('message')} Enter a PDB ID such as 6LU7 or 4HHB, or switch to the Upload PDB File tab "
                'to inspect a selected/uploaded PDB structure.'
            )
        else:
            st.caption('Structure source = RCSB PDB')
            html_src = _viewer_pdb_id(pid, render_style, spin, viewer_h)
            components.html(html_src, height=viewer_h + 8, scrolling=False)
            st.caption(
                f'Structure: **{pid}** · Style: {render_style} · '
                f'Source: [RCSB PDB](https://www.rcsb.org/structure/{pid}) · '
                'If loading fails, verify the PDB ID; the rest of this page remains usable.'
            )

        if protein_seq:
            with st.expander('Translated protein sequence', expanded=False):
                st.code(protein_seq, language=None)
                st.caption(
                    'You can submit this sequence to [RCSB BLAST]'
                    '(https://www.rcsb.org/search?request=%7B%22query%22%3A%7B%22type%22%3A%22terminal%22%2C%22service%22%3A%22sequence%22%7D%7D) '
                    'to search for matching PDB structures.'
                )

    with tab_upload:
        uploaded = st.session_state.get('sa_uploaded_pdb', '')
        upload_state = uploaded_pdb_source_state(uploaded)
        if upload_state.get('ok') != 'true':
            st.info('Upload a non-empty .pdb file in the left panel to display the structure here. Files are rendered locally in the browser and are not uploaded to external services.')
        else:
            st.caption('Structure source = uploaded PDB file')
            c1u, c2u, c3u, c4u = st.columns([2, 2, 2, 1])
            render_style_u = c1u.selectbox(
                'Render style', ['Cartoon', 'Stick', 'Sphere', 'Surface', 'Line'],
                key='sa_style_upload',
            )
            height_opt_u = c2u.selectbox(
                'Viewer height', ['Standard (530px)', 'Tall (700px)', 'Compact (380px)'],
                key='sa_height_upload',
            )
            spin_u = c3u.checkbox('Auto-rotate', value=False, key='sa_spin_upload')
            height_u = height_map.get(height_opt_u, 530)

            html_u = _viewer_upload(uploaded, render_style_u, spin_u, height_u)
            components.html(html_u, height=height_u + 8, scrolling=False)
            st.caption('Viewing uploaded PDB file · Rendered with 3Dmol.js · No external upload is performed.')


def _selected_artifact_project_id(widget_key: str) -> int | None:
    projects = list_pathway_projects()
    options = ["Global artifact (no project link)"] + [
        f"{project.get('id')} · {project.get('name', 'Untitled project')}" for project in projects
    ]
    selected = st.selectbox("Optional Pathway Project link", options, key=widget_key)
    st.caption(ARTIFACT_PROJECT_LINK_COPY)
    if selected.startswith("Global artifact"):
        return None
    try:
        return int(selected.split(" · ", 1)[0])
    except (TypeError, ValueError):
        return None


def _render_structure_artifact_panel(protein_seq: str) -> None:
    st.divider()
    st.markdown('### Documentation Artifacts')
    st.caption(
        'Save the current property/source preview as a documentation artifact for inspection and structure review context only. '
        'This does not validate folding, function, expression, or experimental readiness.'
    )
    project_id = _selected_artifact_project_id('sa_artifact_project_link')
    source_state = {}
    uploaded = st.session_state.get('sa_uploaded_pdb', '')
    if uploaded_pdb_source_state(uploaded).get('ok') == 'true':
        source_state = uploaded_pdb_source_state(uploaded)
    else:
        source_state = pdb_id_source_state(st.session_state.get('sa_rcsb_pid_main', ''))
    payload = structure_analysis_artifact_payload(protein_sequence=protein_seq, structure_source=source_state)
    can_save = bool(payload)
    if st.button(
        'Save Documentation Artifact',
        disabled=not can_save,
        help='Enter a protein sequence or select a valid PDB source before saving a documentation-only artifact.' if not can_save else 'Save the current preview as a documentation-only artifact.',
    ):
        ok, message, artifact_id = create_tool_artifact(
            artifact_type='protein_structure_analysis',
            title=str(payload.get('title') or 'Protein Structure Analysis Review Record'),
            source_module='Structure Analysis',
            summary=str(payload.get('summary') or 'Protein structure analysis documentation review record.'),
            payload_json=payload,
            boundary_label=str(payload.get('boundary_label') or ''),
            project_id=project_id,
        )
        if ok:
            st.info(artifact_save_success_message(artifact_id, project_id))
        else:
            st.error(message)

    st.info(ARTIFACT_BOUNDARY_COPY)
    filter_col1, filter_col2 = st.columns(2)
    selected_type = filter_col1.selectbox('Filter by record type', ['All', 'protein_structure_analysis'], key='sa_artifact_type_filter')
    selected_source = filter_col2.selectbox('Filter by source page', ['Structure Analysis'], key='sa_artifact_source_filter')
    artifacts = list_tool_artifacts(
        artifact_type=None if selected_type == 'All' else selected_type,
        source_module=selected_source,
    )
    if not artifacts:
        st.info(
            f"{ARTIFACT_EMPTY_STATE} Save a Documentation Artifact after entering a protein sequence or selecting a PDB source "
            "if you need a local documentation review record. Linked records are visible from Pathway Workspace linked documentation artifacts."
        )
        return

    import pandas as pd
    st.dataframe(pd.DataFrame([{
        'created_at': a.get('created_at', ''),
        'record type': a.get('artifact_type', ''),
        'title': a.get('title', ''),
        'created from': a.get('source_module', ''),
        'summary': a.get('summary', ''),
        'boundary note': a.get('boundary_label', ''),
    } for a in artifacts]), use_container_width=True, hide_index=True)
    for artifact in artifacts:
        label = f"{artifact.get('created_at', '')} · {artifact.get('artifact_type', '')} · {artifact.get('title', '')}"
        with st.expander(label):
            _render_artifact_details(artifact)
            st.warning('This removes the saved documentation artifact only.')
            if st.button('Delete artifact', key=f"delete_sa_artifact_{artifact.get('artifact_id')}"):
                deleted, delete_message = delete_tool_artifact(artifact.get('artifact_id'))
                if deleted:
                    st.success(delete_message)
                    st.rerun()
                else:
                    st.error(delete_message)


def render(_change_page=None) -> None:
    """Main entry point called by app.py router."""
    st.markdown(_CSS, unsafe_allow_html=True)
    inject_tool_typography_css()

    st.markdown(
        "<div class='tool-title'>Protein Structure Analysis</div>"
        "<div class='tool-subtitle'>Protein physicochemical analysis and 3D structure viewing</div>",
        unsafe_allow_html=True,
    )
    render_boundary_note(BOUNDARY_COPY)
    render_tool_intro(
        "Documentation-only inspection and structure review helper",
        "Input: protein sequence plus either an RCSB PDB ID or an uploaded PDB file. "
        "Output: documentation-only protein property estimates, local/browser structure view, and optional documentation artifacts for local review context. "
        "Next step: enter a protein sequence, choose a PDB source, then save a Documentation Artifact only if you need a traceability record.",
    )

    # Incoming sequence from wizard (context_bridge relay)
    incoming_dna = st.session_state.get('struct_cds_seq', '')
    if incoming_dna:
        st.session_state[SK.ACTIVE_SEQ] = incoming_dna
        del st.session_state['struct_cds_seq']
        # Clear protein widget so Streamlit respects new value= on rerun.
        st.session_state.pop('sa_prot_input', None)
        # Force re-translation from new CDS.
        st.session_state.pop(SK.TRANSLATED_PROTEIN, None)
        # Clear stale PDB viewer state so 1EMA is not shown for an unrelated protein.
        st.session_state.pop('sa_pdb_id', None)
        st.session_state.pop('sa_rcsb_pid_main', None)
        st.session_state['sa_current_pdb'] = ''
        st.session_state['_wizard_handoff'] = True
        st.info(
            'Received CDS sequence from the Expression Wizard. The protein sequence has been translated automatically and is shown below.\n\n'
            'Enter a PDB ID in the "RCSB PDB Online Search" tab on the right (for example 6LU7 or 4HHB), '
            'or switch to the "Upload PDB File" tab to inspect a selected or uploaded PDB structure.'
        )

    col_left, col_right = st.columns([1, 3])

    with col_left:
        protein_seq = _render_left_panel()

    with col_right:
        _render_right_panel(protein_seq)
        _render_structure_artifact_panel(protein_seq)
