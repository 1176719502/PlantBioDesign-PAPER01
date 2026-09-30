# [DORMANT — V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
"""components/project_manager.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Project Management utility for BioDesign Studio.

Public API
----------
save_current_design(project_name) -> tuple[bool, str]
    Extract build_seq, build_features, and assembly_result from
    st.session_state, serialise them, and persist to the
    project_history table via core.unified_database.

render_save_sidebar()
    Sidebar widget: project-name text_input + primary Save button.
    Calls save_current_design() on click and surfaces success /
    error feedback directly in the sidebar.

render_save_utility()
    Same save logic rendered with plain st.* calls for use inside
    a st.expander or any other container context.

render_project_history()
    Panel listing recent saved projects with Load buttons.

Internal helpers
----------------
_get_current_construct()  -> dict | None
_next_version(name)       -> int
_load_projects(limit)     -> list[dict]
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

import streamlit as st

from core.unified_database import DB_PATH, ensure_database_exists
from core.activity_log import log_build_activity


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_SEQ_LEN: int = 10   # minimum bp required for a valid construct
_MAX_HISTORY: int = 50   # hard cap on rows returned from project_history


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_current_construct() -> Optional[dict]:
    """
    Collect the current construct from st.session_state.

    Extraction priority
    -------------------
    1. build_seq       -- primary output of the Assembly and Cloning module.
    2. seq             -- generic sequence slot used by Design / Wizard.
    3. assembly_result -- may be a plain string or a dict with key
                         'final_sequence'.

    Returns None when no sequence of at least _MIN_SEQ_LEN bp is found.
    """
    build_seq       = st.session_state.get('build_seq', '')
    seq_fallback    = st.session_state.get('seq', '')
    assembly_result = st.session_state.get('assembly_result', '')

    if isinstance(assembly_result, dict):
        assembly_result_str = assembly_result.get('final_sequence', '')
    else:
        assembly_result_str = str(assembly_result or '').strip()

    seq = (
        str(build_seq).strip()
        or str(seq_fallback).strip()
        or assembly_result_str
    ).upper()

    if len(seq) < _MIN_SEQ_LEN:
        return None

    features = st.session_state.get('build_features', [])
    if not isinstance(features, list):
        features = []

    return {
        'sequence':            seq,
        'features':            features,
        'assembly_result_raw': st.session_state.get('assembly_result', ''),
        'method':              st.session_state.get('assembly_method', 'Unknown'),
        'seq_len':             len(seq),
        'n_features':          len(features),
    }


def _next_version(project_name: str) -> int:
    """Return the next sequential version number for project_name."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT COALESCE(MAX(version), 0) FROM project_history "
            "WHERE project_name = ?",
            (project_name,),
        )
        row = c.fetchone()
        conn.close()
        return (row[0] if row else 0) + 1
    except Exception:
        return 1


def _load_projects(limit: int = 20) -> list[dict]:
    """Retrieve the most recent *limit* rows from project_history."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            SELECT id, project_name, version, chassis,
                   created_at, creator, status, design_data
            FROM project_history
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (min(limit, _MAX_HISTORY),),
        )
        rows = c.fetchall()
        conn.close()
    except Exception:
        return []

    results = []
    for row in rows:
        pid, name, ver, chassis, created_at, creator, status, raw = row
        try:
            data = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        results.append({
            'id':           pid,
            'project_name': name,
            'version':      ver,
            'chassis':      chassis or 'Unspecified',
            'created_at':   created_at or '',
            'creator':      creator or '',
            'status':       status or '',
            'seq_len':      data.get('seq_len', 0),
            'method':       data.get('method', ''),
            'sequence':     data.get('sequence', ''),
            'features':     data.get('features', []),
        })
    return results


# ---------------------------------------------------------------------------
# PRIMARY PUBLIC FUNCTION: save_current_design()
# ---------------------------------------------------------------------------

def save_current_design(project_name: str) -> tuple[bool, str]:
    """
    Extract build_seq, build_features, and assembly_result from
    st.session_state, serialise the features list as a JSON string, and
    insert a new versioned row into the project_history table.

    Parameters
    ----------
    project_name : str
        Human-readable label for this design snapshot. Must be non-empty.

    Returns
    -------
    (True,  success_message)  on a successful database write.
    (False, error_message)    when validation fails or a database exception
                              is raised.

    Notes
    -----
    * design_data stores a JSON object containing the full construct
      sequence, features list (serialised from list[dict]), raw
      assembly_result, assembly method, sequence length, and feature count.
    * sqlite3.Error exceptions are caught and returned as error strings.
    * Each call creates a new versioned row derived from MAX(version)+1.
    """
    project_name = project_name.strip()
    if not project_name:
        return False, "Project name must not be empty."

    construct = _get_current_construct()
    if construct is None:
        return (
            False,
            f"No valid construct sequence found in the current session "
            f"(minimum {_MIN_SEQ_LEN} bp required). "
            f"Complete the Assembly or Design step before saving.",
        )

    ensure_database_exists()

    # Serialise features (list[dict]) -- default=str guards against
    # non-serialisable objects such as numpy types.
    features_json: str = json.dumps(
        construct['features'],
        ensure_ascii=False,
        default=str,
    )

    assembly_result_raw = construct['assembly_result_raw']
    if isinstance(assembly_result_raw, dict):
        assembly_result_stored: str = json.dumps(
            assembly_result_raw, ensure_ascii=False, default=str
        )
    else:
        assembly_result_stored = str(assembly_result_raw)

    design_data: str = json.dumps(
        {
            'sequence':        construct['sequence'],
            'features':        construct['features'],
            'assembly_result': assembly_result_stored,
            'method':          construct['method'],
            'seq_len':         construct['seq_len'],
            'n_features':      construct['n_features'],
            'features_json':   features_json,
        },
        ensure_ascii=False,
        default=str,
    )

    version = _next_version(project_name)
    now     = datetime.now().isoformat(sep=' ', timespec='seconds')
    chassis = st.session_state.get('chassis', 'Unspecified')
    creator = st.session_state.get('researcher_name', 'BioDesign Studio')

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO project_history
                (project_name, version, chassis, design_data,
                 created_at, creator, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (project_name, version, chassis, design_data,
             now, creator, 'Saved'),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as db_exc:
        return False, f"Database write failed: {db_exc}"
    except Exception as exc:
        return False, f"Unexpected error during save: {exc}"

    log_build_activity(
        f"Project saved: {project_name} (v{version})",
        f"{construct['seq_len']} bp "
        f"· {construct['n_features']} feature(s) "
        f"· method: {construct['method']}",
    )

    st.session_state['build_pname'] = project_name
    return True, (
        f"Project '{project_name}' saved as version {version} "
        f"({construct['seq_len']} bp, "
        f"{construct['n_features']} feature(s), "
        f"method: {construct['method'] or 'unspecified'})."
    )


# ---------------------------------------------------------------------------
# SIDEBAR UI COMPONENT: render_save_sidebar()
# ---------------------------------------------------------------------------

def render_save_sidebar() -> None:
    """
    Render the project-save widget directly inside st.sidebar.

    Layout
    ------
    * st.sidebar.text_input  -- project name entry field.
    * st.sidebar.button      -- primary "Save Project" button (type="primary").
    * st.sidebar.success / st.sidebar.error for outcome feedback.

    Behaviour
    ---------
    The Save button is disabled when no valid construct sequence is present
    or the project-name field is empty, preventing accidental empty saves.
    Database exceptions are surfaced via st.sidebar.error so the researcher
    can take corrective action without inspecting logs.
    """
    construct     = _get_current_construct()
    seq_available = construct is not None

    st.sidebar.caption(
        "Create or select a pathway documentation workspace in Pathway Projects. "
        "Selecting a pathway project makes it the active project for Pathway Workspace; "
        "this does not certify experimental readiness."
    )

    default_name = st.session_state.get('build_pname', '') or 'Untitled_Project'
    project_name: str = st.sidebar.text_input(
        "Project name",
        value=default_name,
        max_chars=120,
        placeholder="e.g. GFP_Expression_v1",
        key="pm_sidebar_project_name",
        help="Assign a descriptive label to this construct snapshot.",
    ).strip()

    if seq_available:
        st.sidebar.caption(
            f"Construct ready: {construct['seq_len']} bp"
            f" · {construct['n_features']} feature(s)"
            f" · method: {construct['method'] or 'unspecified'}."
        )
    else:
        st.sidebar.warning(
            "No construct sequence is available. "
            "Complete the Assembly or Design step before saving."
        )

    button_disabled = (not seq_available) or (not project_name)
    save_clicked = st.sidebar.button(
        "Save Project",
        key="pm_sidebar_save_btn",
        use_container_width=True,
        disabled=button_disabled,
        type="primary",
        help="Persist the current construct and session metadata to the database.",
    )

    if save_clicked:
        if not project_name:
            st.sidebar.error("Please enter a project name before saving.")
        elif not seq_available:
            st.sidebar.error(
                "Cannot save: no valid construct sequence detected "
                "in the current session."
            )
        else:
            with st.spinner("Writing to database..."):
                ok, msg = save_current_design(project_name)
            if ok:
                st.sidebar.success(msg)
            else:
                st.sidebar.error(f"Save failed — {msg}")


# ---------------------------------------------------------------------------
# EXPANDER-COMPATIBLE COMPONENT: render_save_utility()
# ---------------------------------------------------------------------------

def render_save_utility() -> None:
    """
    Render the project save panel using plain st.* calls.

    Designed to be called inside a st.expander that is itself inside
    st.sidebar. Compatible with any Streamlit container context.
    """
    construct     = _get_current_construct()
    seq_available = construct is not None

    default_name = st.session_state.get('build_pname', '') or 'Untitled_Project'
    project_name: str = st.text_input(
        "Project name",
        value=default_name,
        max_chars=120,
        placeholder="e.g. GFP_Expression_v1",
        key="pm_project_name",
        help="Assign a descriptive label to this construct snapshot.",
    ).strip()

    if seq_available:
        st.caption(
            f"Construct ready: {construct['seq_len']} bp"
            f" · {construct['n_features']} feature(s)"
            f" · method: {construct['method'] or 'unspecified'}."
        )
    else:
        st.warning(
            "No construct sequence is currently available. "
            "Complete the Assembly or Design step before saving."
        )

    button_disabled = (not seq_available) or (not project_name)
    save_clicked = st.button(
        "Save Current Project",
        key="pm_save_btn",
        use_container_width=True,
        disabled=button_disabled,
        type="primary",
        help="Save the current construct and session metadata to the database.",
    )

    if save_clicked:
        if not project_name:
            st.error("Please enter a project name before saving.")
        elif not seq_available:
            st.error(
                "Cannot save: no valid sequence detected "
                "in the current session."
            )
        else:
            with st.spinner("Writing to database..."):
                ok, msg = save_current_design(project_name)
            if ok:
                st.success(msg)
            else:
                st.error(f"Save failed — {msg}")


# ---------------------------------------------------------------------------
# PROJECT HISTORY PANEL: render_project_history()
# ---------------------------------------------------------------------------

def render_project_history() -> None:
    """
    Render a panel listing recent saved projects.

    Each entry displays name, version, date, and sequence length.
    A Load button restores the construct into st.session_state.
    """
    projects = _load_projects(limit=10)

    st.divider()
    st.markdown(
        "<div style='"
        "font-size:.72rem;font-weight:700;color:#6b7280;"
        "text-transform:uppercase;letter-spacing:.6px;"
        "margin-bottom:4px'>"
        f"Saved Projects ({len(projects)})</div>",
        unsafe_allow_html=True,
    )

    if not projects:
        st.caption("No documentation records yet.")
        return

    for proj in projects:
        col_info, col_load = st.columns([3, 1])
        with col_info:
            st.markdown(
                f"<div style='font-size:.78rem;font-weight:600;"
                f"color:#111827'>{proj['project_name']} "
                f"<span style='color:#6b7280;font-weight:400'>"
                f"v{proj['version']}</span></div>"
                f"<div style='font-size:.72rem;color:#6b7280'>"
                f"{proj['seq_len']} bp"
                f" &middot; {proj['created_at'][:10]}</div>",
                unsafe_allow_html=True,
            )
        with col_load:
            if st.button(
                "Load",
                key=f"pm_load_{proj['id']}",
                use_container_width=True,
                help=(
                    f"Restore '{proj['project_name']}'"
                    f" v{proj['version']} into the current session."
                ),
            ):
                seq   = proj.get('sequence', '')
                feats = proj.get('features', [])
                if seq:
                    st.session_state['build_seq']       = seq
                    st.session_state['seq']             = seq
                    st.session_state['build_features']  = feats
                    st.session_state['build_pname']     = proj['project_name']
                    st.session_state['assembly_method'] = proj.get('method', '')
                    log_build_activity(
                        f"Project loaded: {proj['project_name']}"
                        f" v{proj['version']}",
                        f"{len(seq)} bp restored to session.",
                    )
                    st.success(
                        f"Project '{proj['project_name']}'"
                        f" v{proj['version']} loaded into session."
                    )
                    st.rerun()
                else:
                    st.warning(
                        "The selected project record contains no sequence "
                        "data and cannot be restored."
                    )

