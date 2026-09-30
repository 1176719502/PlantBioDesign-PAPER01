# [DORMANT — V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
# (Restore: add 'Lab Tools' back to _TOOL_PAGES in app.py)
"""
views/LabTools.py
~~~~~~~~~~~~~~~~~
Lab Tools — Assembly and Cloning + Review Checks combined.

Tabs (top level)
----------------
  Assembly and Cloning  — Plasmid Map, Cloning Sim, PCR, Gel, Export
  Review Checks   — Construct Validation, Seq Viewer, Annotation,
                        Restriction Sites, Translation, Linear Map
"""
from __future__ import annotations
import re
from typing import List, Dict

import pandas as pd
import streamlit as st
from core.activity_log import log_build_activity

# Assembly modules
import components.assembly_modules.tab_cloning     as _tab_cloning
import components.assembly_modules.tab_pcr         as _tab_pcr
import components.assembly_modules.tab_gel         as _tab_gel
import components.assembly_modules.tab_export      as _tab_export

# Test modules
import components.test_modules.tab_seq_view    as _tab_seq
import components.test_modules.tab_annotation  as _tab_ann
import components.test_modules.tab_restriction as _tab_rest
import components.test_modules.tab_translation as _tab_trans
import components.test_modules.tab_linear_map  as _tab_linear
from components.test_modules.seq_utils import (
    build_demo_seq,
    smart_annotate_sequence,
    translate_dna,
)
from core.expression_evaluator import ExpressionEvaluator
from services.lab_tools_service import (
    BOUNDARY_COPY,
    cloning_preview_summary,
    lab_preview_artifact_payload,
    pcr_preview_summary,
    sequence_export_preview,
    virtual_gel_fragment_summary,
)
from services.pathway_repository import list_pathway_projects
from services.tool_artifact_library_presenter import artifact_save_success_message
from services.tool_artifact_service import (
    create_tool_artifact,
    delete_tool_artifact,
    list_tool_artifacts,
    raw_payload_preview,
    readable_payload_summary,
)
from views.tool_typography import (
    inject_tool_typography_css,
    render_boundary_note,
    render_compact_summary_cards,
    render_help_text,
    render_section_heading,
    render_subsection_heading,
    render_tool_header,
    render_tool_intro,
)


# Global CSS is now injected once in app.py — no per-page overrides needed.
STYLE = ""  # kept for compatibility; app.py handles all global styling

_WARN_STYLE = (
    "background:#fff7ed;border-left:4px solid #f97316;"
    "border-radius:0 6px 6px 0;padding:8px 14px;"
    "margin:4px 0;font-size:.82rem;color:#431407;"
)
_PASS_STYLE = (
    "background:#f0fdf4;border-left:4px solid #22c55e;"
    "border-radius:0 6px 6px 0;padding:8px 14px;"
    "margin:4px 0;font-size:.82rem;color:#14532d;"
)
_INFO_STYLE = (
    "background:#eff6ff;border-left:4px solid #3b82f6;"
    "border-radius:0 6px 6px 0;padding:8px 14px;"
    "margin:4px 0;font-size:.82rem;color:#1e3a5f;"
)

_TYPE_LABEL: Dict[str, str] = {
    'promoter':   'Promoter',
    'rbs':        'RBS',
    'cds':        'CDS',
    'terminator': 'Terminator',
    'reporter':   'Reporter Gene',
    'operator':   'Operator Element',
    'regulatory': 'Regulatory Element',
    'vector':     'Vector Backbone',
    'origin':     'Origin of Replication',
    'resistance': 'Resistance Gene',
    'marker':     'Selection Marker',
    'misc':       'Other Feature',
}

ARTIFACT_EMPTY_STATE = "No saved documentation artifacts yet."
LAB_TOOLS_DORMANT_BOUNDARY_COPY = (
    "Lab Tools is a dormant / V1 frozen / documentation artifact preview surface. "
    "It is retained for reviewing legacy-style computational preview records only. "
    "It is not the current mainline tool path and not a wet-lab execution workflow."
)
ARTIFACT_BOUNDARY_COPY = (
    "Saved documentation records are documentation-only review records. "
    "Artifact saved as a documentation artifact. "
    "They are saved as documentation artifacts for linked project context review when a project is selected. "
    "They can be visible from Pathway Workspace linked documentation artifacts. "
    "They are not validation, not prediction, not recommendation, not readiness approval, and not wet-lab protocol. "
    "They are not experimental conclusions, not claims of experimental readiness, not a production readiness claim, "
    "not yield prediction, not pathway optimization, and not wet-lab protocols."
)
ARTIFACT_PROJECT_LINK_COPY = (
    "Linking a documentation record to a pathway project is for traceability only. "
    "It can be reviewed in linked project context and visible from Pathway Workspace linked documentation artifacts. "
    "It does not change project readiness, completeness score, or experimental status. "
    "It is not validation, not prediction, not recommendation, not readiness approval, and not wet-lab protocol."
)
CLONING_RECORD_WORKSPACE_TITLE = "Cloning documentation preview workspace"
CLONING_RECORD_PRIMARY_BUTTON = "Save current cloning preview record"
CLONING_RECORD_PRIMARY_BUTTON_ZH = "保存当前克隆预览记录"
RECENT_RECORD_LIMIT = 5

_ARTIFACT_TYPE_LABELS: Dict[str, str] = {
    'lab_tools_cloning_preview': 'Cloning preview record',
    'lab_tools_pcr_preview': 'PCR preview record',
    'lab_tools_virtual_gel_preview': 'Virtual gel preview record',
    'lab_tools_sequence_export_preview': 'Sequence export preview record',
}
_FRIENDLY_RECORD_COLUMNS: Dict[str, str] = {
    'created_at': 'Created time',
    'artifact_type': 'Record type',
    'title': 'Title',
    'source_module': 'Source module',
    'summary': 'Summary',
    'boundary_label': 'Boundary note',
}


def _render_artifact_details(artifact: dict) -> None:
    st.caption(ARTIFACT_BOUNDARY_COPY)
    for label, key in (
        ("Created time", "created_at"),
        ("Record type", "artifact_type"),
        ("Title", "title"),
        ("Source module", "source_module"),
        ("Summary", "summary"),
        ("Boundary note", "boundary_label"),
        ("Notes", "notes"),
        ("Project ID", "project_id"),
    ):
        value = artifact.get(key)
        if value not in (None, ""):
            if key == "artifact_type":
                value = _friendly_artifact_type(str(value))
            if key == "source_module":
                value = _friendly_source_module(str(value))
            st.write(f"{label}: {value}")

    st.markdown("##### Readable payload summary")
    for label, value in readable_payload_summary(artifact.get("payload_json", {})):
        st.write(f"{label}: {value}")

    with st.expander("Advanced raw payload preview", expanded=False):
        preview, truncated = raw_payload_preview(artifact.get("payload_json", {}), max_chars=2000)
        st.code(preview, language="json")
        if truncated:
            st.caption("Payload summary truncated for readability.")


# ===========================================================================
# Sequence helpers (from Test.py)
# ===========================================================================

def _get_seq() -> str:
    for key in ('build_seq', 'current_seq', 'seq', 'assembled_seq'):
        val = st.session_state.get(key, '')
        if val:
            return re.sub(r'\[.*?\]', '', str(val)).upper()
    return build_demo_seq()


def _seq_origin_label() -> str:
    if st.session_state.get('build_seq'):
        return 'Assembly and Cloning product'
    if st.session_state.get('current_seq'):
        return 'current editor'
    if st.session_state.get('seq'):
        return 'Design / Build'
    if st.session_state.get('assembled_seq'):
        return 'Wizard result'
    return 'demo sequence'


def _build_construct_result(seq: str) -> dict:
    seq_upper = seq.upper()
    seq_len   = len(seq_upper)
    raw_session: List[dict] = list(st.session_state.get('build_features', []))
    if not raw_session:
        raw_session = smart_annotate_sequence(seq_upper)
    features: List[dict] = []
    for feat in raw_session:
        try:
            name  = feat.get('name') or feat.get('Name') or feat.get('label') or 'Feature'
            ftype = str(feat.get('type') or feat.get('Type') or 'misc').strip()
            start = int(feat.get('start') or feat.get('Start') or 1)
            end   = int(feat.get('end')   or feat.get('End')   or start)
            start = max(1, min(start, seq_len))
            end   = max(start, min(end, seq_len))
            features.append({'name': str(name), 'type': ftype, 'start': start, 'end': end})
        except (TypeError, ValueError):
            continue
    return {'final_sequence': seq_upper, 'total_length': seq_len, 'features': features}


# ===========================================================================
# Validation tab renderer (from Test.py)
# ===========================================================================

def _get_warning_explanation(warning_text: str) -> tuple:
    w = warning_text.lower()
    if 'gc content' in w and ('below' in w or '< 30' in w or 'low' in w):
        return (
            'Low GC content reduces DNA duplex stability (Tm) and can impair transcription efficiency.',
            'Review codon usage targeting 40-65% GC.'
        )
    if 'gc content' in w and ('exceed' in w or '> 70' in w or 'high' in w):
        return (
            'High GC content (>70%) promotes secondary structures that block polymerase elongation.',
            'Review codon usage options to reduce GC while preserving amino acid sequence.'
        )
    if 'promoter' in w and ('absent' in w or 'no promoter' in w or 'not annotated' in w):
        return (
            'Without a promoter, RNA polymerase has no binding site and transcription cannot initiate.',
            'Add a host-compatible promoter upstream of the RBS/CDS.'
        )
    if 'rbs' in w or 'ribosome binding' in w or 'shine' in w:
        return (
            'Without an RBS, translation efficiency drops >100-fold.',
            'For E. coli: add Shine-Dalgarno (AGGAGG) 6-8 bp upstream of ATG.'
        )
    if 'terminator' in w:
        return (
            'Without a terminator, RNA polymerase reads into downstream sequences.',
            'Add a Rho-independent terminator downstream of the stop codon.'
        )
    if 'stop codon' in w and ('no stop' in w or 'not detected' in w or 'absent' in w):
        return (
            'Without a stop codon the ribosome will not release from the mRNA.',
            'Ensure the CDS ends with TAA, TAG, or TGA.'
        )
    if 'premature stop' in w or 'internal stop' in w:
        return (
            'A stop codon within the CDS terminates translation early, producing a truncated protein.',
            'Check reading frame from ATG — a premature stop usually indicates a frameshift.'
        )
    if 'atg' in w or 'start codon' in w or 'methionine' in w:
        return (
            'Without ATG, ribosomes cannot assemble the initiation complex.',
            'Ensure the CDS begins with ATG and is in-frame with any upstream tags.'
        )
    return (
        'This warning indicates a potential issue with the biological design.',
        'Review the construct design before proceeding to the cloning step.'
    )


def _render_validation(seq: str) -> None:
    render_section_heading("Construct review summary")
    render_help_text(
        "Rule-based documentation review powered by ExpressionEvaluator, "
        "including global sequence metrics, CDS translation results, and review notes."
    )
    render_subsection_heading("Rule-based documentation review")
    if not seq or len(seq) < 10:
        st.info("No construct sequence is currently available. Please complete the 'Assembly and Cloning' step first.")
        return

    construct_result = _build_construct_result(seq)
    evaluator        = ExpressionEvaluator()
    try:
        report = evaluator.evaluate_construct(construct_result)
    except Exception as exc:
        st.error(f"ExpressionEvaluator runtime error: {exc}")
        return

    gc_pct   = report.get('global_gc_content', 0.0)
    cds_map  = report.get('cds_translations', {})
    warnings = report.get('warnings', [])
    seq_len  = len(seq)
    features = construct_result.get('features', [])
    cds_feats = [f for f in features if f['type'].strip().lower() == 'cds']

    # 1. Global metrics
    render_subsection_heading("1. Global Sequence Metrics")
    render_compact_summary_cards([
        ("Sequence Length", f"{seq_len:} bp", None),
        ("Global GC Content", f"{gc_pct:.2f} %", None),
        ("Annotated Features", str(len(features)), None),
        ("CDS Regions", str(len(cds_feats)), None),
    ])

    if gc_pct < 30:
        st.markdown(f"<div style='{_WARN_STYLE}'>GC content ({gc_pct:.2f}%) is below 30%, which may reduce stability.</div>", unsafe_allow_html=True)
    elif gc_pct > 70:
        st.markdown(f"<div style='{_WARN_STYLE}'>GC content ({gc_pct:.2f}%) is above 70%, which may promote secondary structure formation.</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='{_PASS_STYLE}'>Rule check passed: GC content ({gc_pct:.2f}%) is within the review range (30-70%).</div>", unsafe_allow_html=True)

    st.divider()

    # 2. CDS translations
    render_subsection_heading("2. CDS Translation Results")
    if not cds_map:
        st.markdown(f"<div style='{_INFO_STYLE}'>No CDS features were detected. Please confirm that CDS annotations were added correctly.</div>", unsafe_allow_html=True)
    else:
        for cds_name, protein_seq in cds_map.items():
            with st.expander(f"CDS: {cds_name} ({len(protein_seq)} residues)", expanded=True):
                has_start = protein_seq.startswith('M')
                has_stop  = protein_seq.endswith('*')
                internal_stops = protein_seq[:-1].count('*') if len(protein_seq) > 1 else 0
                aa_len = len(protein_seq.rstrip('*'))
                render_compact_summary_cards([
                    ("Protein Length", f"{aa_len} aa", None),
                    ("Start Codon (ATG)", "Present" if has_start else "Missing", None),
                    ("Stop Codon", "Present" if has_stop else "Missing", None),
                ])
                if not has_start:
                    st.markdown(f"<div style='{_WARN_STYLE}'>Start methionine (ATG) was not detected.</div>", unsafe_allow_html=True)
                if not has_stop:
                    st.markdown(f"<div style='{_WARN_STYLE}'>No stop codon was detected; the CDS may be truncated.</div>", unsafe_allow_html=True)
                if internal_stops > 0:
                    st.markdown(f"<div style='{_WARN_STYLE}'>{internal_stops} premature stop codon(s) detected.</div>", unsafe_allow_html=True)
                if has_start and has_stop and internal_stops == 0:
                    st.markdown(f"<div style='{_PASS_STYLE}'>Review check passed: {cds_name} CDS structure is complete and consistent in this rule check.</div>", unsafe_allow_html=True)
                display_seq = protein_seq if len(protein_seq) <= 800 else protein_seq[:800] + "..."
                with st.container(border=True):
                    st.code(display_seq, language='text')

    st.divider()

    # 3. Biological logic warnings
    render_subsection_heading("Review notes")
    extra_warnings: list = []
    feat_types = [f['type'].strip().lower() for f in features]
    has_promoter   = any(t in ('promoter', 'regulatory') for t in feat_types)
    has_rbs        = 'rbs' in feat_types
    has_cds_feat   = 'cds' in feat_types
    has_terminator = 'terminator' in feat_types
    if has_cds_feat and not has_promoter:
        extra_warnings.append("No promoter element is annotated upstream of the CDS.")
    if has_cds_feat and not has_rbs:
        extra_warnings.append("No ribosome binding site (RBS) is annotated; translation efficiency may be substantially reduced.")
    if has_cds_feat and not has_terminator:
        extra_warnings.append("No transcription terminator is annotated; transcriptional readthrough may occur.")
    if seq_len < 50:
        extra_warnings.append(f"Construct length ({seq_len} bp) is below 50 bp.")
    all_warnings = list(warnings) + extra_warnings
    if not all_warnings:
        st.markdown(f"<div style='{_PASS_STYLE}'>No flagged issue: no biological logic review notes were returned by automated checks.</div>", unsafe_allow_html=True)
    else:
        st.caption(f"{len(all_warnings)} review note(s) total — please review them before continuing.")
        for i, w in enumerate(all_warnings, start=1):
            why, fix = _get_warning_explanation(w)
            st.markdown(
                f"<div style='{_WARN_STYLE}'>"
                f"<b>Review note {i:02d}.</b> {w}<br>"
                f"<span style='color:#92400e'><b>Context:</b> {why}</span><br>"
                f"<span style='color:#1d4ed8'><b>Suggested review:</b> {fix}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    # 4. Feature inventory
    render_subsection_heading("4. Feature Inventory")
    if features:
        df_feats = pd.DataFrame([
            {
                'Feature Name': f['name'],
                'Type':         _TYPE_LABEL.get(f['type'], f['type'].capitalize()),
                'Start (bp)':   f['start'],
                'End (bp)':     f['end'],
                'Length (bp)':  f['end'] - f['start'] + 1,
            }
            for f in features
        ])
        st.dataframe(
            df_feats, use_container_width=True, hide_index=True,
            column_config={
                'Start (bp)':  st.column_config.NumberColumn(format='%d'),
                'End (bp)':    st.column_config.NumberColumn(format='%d'),
                'Length (bp)': st.column_config.NumberColumn(format='%d'),
            },
        )
    else:
        st.caption("No annotated features are currently available.")

    render_subsection_heading("Boundary note")
    render_help_text(BOUNDARY_COPY)


# ===========================================================================
# Documentation artifact helpers
# ===========================================================================

def _artifact_summary_text(summary: dict) -> str:
    if not isinstance(summary, dict):
        return "Lab Tools computational preview."
    if summary.get('input_summary'):
        return str(summary['input_summary'])
    if summary.get('expected_amplicon_summary'):
        return str(summary['expected_amplicon_summary'])
    if summary.get('textual_gel_preview'):
        return str(summary['textual_gel_preview'])
    if summary.get('sequence_name'):
        return f"{summary.get('sequence_name')} · {summary.get('sequence_length_bp', 0)} bp · {summary.get('format', '')}"
    return str(summary.get('message') or 'Lab Tools computational preview.')


def _friendly_artifact_type(artifact_type: str) -> str:
    return _ARTIFACT_TYPE_LABELS.get(artifact_type, artifact_type.replace('_', ' ').title())


def _friendly_source_module(source_module: str | None) -> str:
    if source_module == 'Lab Tools':
        return 'Cloning Tools'
    return str(source_module or 'Unknown source')


def _lab_artifact_type_options() -> dict[str, str]:
    return {'All record types': 'All', **{label: key for key, label in _ARTIFACT_TYPE_LABELS.items()}}


def _render_current_cloning_preview_summary(preview, seq: str) -> None:
    render_subsection_heading("Current cloning preview summary")
    summary = preview.summary if isinstance(preview.summary, dict) else {}
    render_compact_summary_cards([
        ("Preview status", "Ready to save" if preview.status == 'ok' else "Needs usable input", None),
        ("Insert length", f"{summary.get('insert_length_bp', 0)} bp", None),
        ("Vector", str(summary.get('vector', 'Vector/backbone not specified')), None),
        ("Assembly method", str(summary.get('assembly_method', 'Assembly method not specified')), None),
    ])
    st.caption(f"Working sequence source: {_seq_origin_label()} · {len(seq):,} bp")


def _render_recent_artifact_cards(lab_rows: list[dict]) -> None:
    render_subsection_heading("Recent records")
    for artifact in lab_rows[:RECENT_RECORD_LIMIT]:
        created = artifact.get('created_at', 'Unknown time')
        title = artifact.get('title') or 'Untitled record'
        with st.expander(f"{created} · {title}", expanded=False):
            st.write(f"Created time: {created}")
            st.write(f"Title: {title}")
            st.write(f"Source module: {_friendly_source_module(artifact.get('source_module'))}")
            st.write(f"Record type: {_friendly_artifact_type(str(artifact.get('artifact_type', '')))}")
            if artifact.get('summary'):
                st.write(f"Summary: {artifact.get('summary')}")
            st.caption(ARTIFACT_BOUNDARY_COPY)
            with st.expander("Record details", expanded=False):
                _render_artifact_details(artifact)
                st.warning('This removes the saved documentation record only.')
                if st.button('Delete record', key=f"delete_lab_artifact_{artifact.get('artifact_id')}"):
                    deleted, delete_message = delete_tool_artifact(artifact.get('artifact_id'))
                    if deleted:
                        st.success(delete_message)
                        st.rerun()
                    else:
                        st.error(delete_message)


def _render_raw_artifact_table(lab_rows: list[dict]) -> None:
    with st.expander("Advanced: view raw documentation record table", expanded=False):
        st.dataframe(pd.DataFrame([{
            'created_at': a.get('created_at', ''),
            'artifact_type': _friendly_artifact_type(str(a.get('artifact_type', ''))),
            'title': a.get('title', ''),
            'source_module': _friendly_source_module(a.get('source_module')),
            'summary': a.get('summary', ''),
            'boundary_label': a.get('boundary_label', ''),
        } for a in lab_rows]).rename(columns=_FRIENDLY_RECORD_COLUMNS), use_container_width=True, hide_index=True)


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


def _save_preview_artifact(preview_kind: str, preview, inputs: dict, project_id: int | None = None) -> None:
    payload = lab_preview_artifact_payload(preview, preview_kind=preview_kind, inputs=inputs)
    ok, message, artifact_id = create_tool_artifact(
        artifact_type=str(payload.get('artifact_type') or ''),
        title=str(payload.get('title') or preview.title),
        source_module='Lab Tools',
        summary=_artifact_summary_text(payload.get('summary', {})),
        payload_json=payload,
        boundary_label=str(payload.get('boundary_label') or ''),
        project_id=project_id,
    )
    if ok:
        st.info(artifact_save_success_message(artifact_id, project_id))
    else:
        st.error(message)


def _render_lab_artifact_save_panel() -> None:
    st.markdown('### Cloning preview records')
    st.caption(LAB_TOOLS_DORMANT_BOUNDARY_COPY)
    st.caption(
        'Documentation record / cloning preview record. Save the current cloning preview as a documentation-only '
        'review record. This page is not an experiment execution system and not a wet-lab execution workflow.'
    )
    st.caption(f"Chinese label: {CLONING_RECORD_PRIMARY_BUTTON_ZH}")

    project_id = _selected_artifact_project_id('lab_artifact_project_link')
    seq = _get_seq()
    cloning = cloning_preview_summary(
        insert_sequence=seq,
        vector_name=st.session_state.get('build_pname', 'pBioDesign'),
        assembly_method=st.session_state.get('assembly_method', 'Assembly method not specified'),
        insert_name='Current working sequence',
    )

    _render_current_cloning_preview_summary(cloning, seq)
    if st.button(
        CLONING_RECORD_PRIMARY_BUTTON,
        disabled=cloning.status != 'ok',
        key='save_current_cloning_preview_record',
        type='primary',
        help='Requires a current cloning preview with usable input.' if cloning.status != 'ok' else 'Save the current cloning preview as a documentation-only review record.',
    ):
        _save_preview_artifact('cloning', cloning, {'sequence_source': _seq_origin_label(), 'sequence_length_bp': len(seq)}, project_id)

    st.caption("Generate or review a cloning preview, then use Save current cloning preview record if you need a traceability record.")
    st.info(ARTIFACT_BOUNDARY_COPY)

    artifacts = list_tool_artifacts(source_module='Lab Tools')
    lab_rows = [a for a in artifacts if str(a.get('artifact_type', '')).startswith('lab_tools_')]

    render_subsection_heading("Filters")
    type_options = _lab_artifact_type_options()
    filter_col1, filter_col2 = st.columns(2)
    selected_type_label = filter_col1.selectbox('Record type', list(type_options.keys()), key='lab_artifact_type_filter')
    selected_source_label = filter_col2.selectbox('Source module', ['Cloning Tools'], key='lab_artifact_source_filter')
    selected_type = type_options[selected_type_label]
    selected_source = 'Lab Tools' if selected_source_label == 'Cloning Tools' else selected_source_label
    if selected_type != 'All':
        lab_rows = [a for a in lab_rows if a.get('artifact_type') == selected_type]
    lab_rows = [a for a in lab_rows if a.get('source_module') == selected_source]

    if not lab_rows:
        st.info(f"{ARTIFACT_EMPTY_STATE} Generate or review a cloning preview, then use Save current cloning preview record if you need a traceability record.")
        return

    _render_recent_artifact_cards(lab_rows)
    _render_raw_artifact_table(lab_rows)

# ===========================================================================
# ASSEMBLY & CLONING tab
# ===========================================================================

def _render_assembly_tab() -> None:
    st.markdown("### Assembly and Cloning")
    st.caption("Cloning preview · PCR preview · virtual gel preview · sequence export preview")
    st.caption("Each preview uses a consistent structure: Preview summary · Review notes · Documentation artifact.")
    st.divider()

    # Initialise session state
    for k, v in [
        ('build_seq', ''), ('build_features', []),
        ('build_pname', 'pBioDesign'), ('assembly_result', ''),
        ('assembly_method', ''), ('pcr_product_len', 0),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v

    # Auto-pull sequence from Design page
    seq_from_design = st.session_state.get('seq', '')
    if seq_from_design and not st.session_state['build_seq']:
        st.session_state['build_seq'] = seq_from_design

    t1, t2, t3, t4 = st.tabs([
        "Cloning Preview",
        "PCR Preview",
        "Virtual Gel Preview",
        "Sequence Export Preview",
    ])
    with t1: _tab_cloning.render()
    with t2: _tab_pcr.render()
    with t3: _tab_gel.render()
    with t4: _tab_export.render()

    st.divider()
    _render_lab_artifact_save_panel()


# ===========================================================================
# Review Checks tab
# ===========================================================================

def _render_test_tab() -> None:
    st.markdown("### Review Checks")
    st.caption("Construct review checks · sequence viewer · annotation · restriction sites · translation · linear map")
    st.divider()

    seq    = _get_seq()
    origin = _seq_origin_label()
    st.info(
        f"Current working sequence: **{len(seq):,} bp** (source: {origin})  "
        "— To paste or edit a different sequence, switch to the 'Sequence Viewer'."
    )

    t0, t1, t2, t3, t4, t5 = st.tabs([
        "Construct Review Summary",
        "Sequence Viewer",
        "Feature Annotation",
        "Restriction Sites",
        "Translation",
        "Linear Map",
    ])

    with t0:
        _render_validation(seq)
    with t1:
        _tab_seq.render(seq)
        seq = _get_seq()
    with t2:
        _tab_ann.render(seq)
    with t3:
        _tab_rest.render(seq)
    with t4:
        _tab_trans.render(seq)
        st.session_state['translated_protein'] = translate_dna(seq, frame=1)
    with t5:
        _tab_linear.render(seq)


# ===========================================================================
# MAIN ENTRY POINT
# ===========================================================================

def render(goto=None) -> None:
    """Entry point called by app.py router."""
    st.markdown(STYLE, unsafe_allow_html=True)
    inject_tool_typography_css()

    render_tool_header("Cloning Tools", CLONING_RECORD_WORKSPACE_TITLE)
    render_boundary_note(BOUNDARY_COPY)
    st.info(LAB_TOOLS_DORMANT_BOUNDARY_COPY)
    render_tool_intro(
        CLONING_RECORD_WORKSPACE_TITLE,
        "Input: current or pasted DNA sequence plus preview settings for cloning, PCR, virtual gel, export, and review checks. "
        "Output: computational previews, documentation-only review notes, and optional documentation records. "
        "Boundary: this is a dormant V1 frozen preview surface, not the current mainline tool path, not validation, "
        "not prediction, not recommendation, not readiness approval, and not wet-lab protocol. "
        "Next step: open Assembly and Cloning for preview modules, or Review Checks to inspect the current working sequence.",
    )

    tab_build, tab_test = st.tabs(["Assembly and Cloning", "Review Checks"])

    with tab_build:
        _render_assembly_tab()

    with tab_test:
        _render_test_tab()

