# core/session_keys.py
"""
Centralised registry of ALL st.session_state keys used across BioDesign Studio.

Problem solved
--------------
Previously the same logical data (e.g. the active DNA sequence) was stored
under different key names in different files:

    views/Test.py       -> 'build_seq', 'current_seq', 'seq', 'assembled_seq'
    views/Dashboard.py  -> 'seq', 'build_seq'
    wizard_flow.py      -> 'original_seq', 'wiz_p1_seq'
    app.py              -> 'selected_page'

This caused silent bugs where one module wrote a key that another module
never read because it used a different spelling.

Usage
-----
    from core.session_keys import SK

    st.session_state[SK.SEQ] = my_sequence
    seq = st.session_state.get(SK.SEQ, "")

Helpers
-------
    SK.get(key, default)  -- safe read with default
    SK.set(key, value)    -- write (requires Streamlit context)
    SK.clear(*keys)       -- delete one or more keys
    SK.get_seq()          -- priority-order read across all sequence keys
"""
from __future__ import annotations
from typing import Any


class SK:
    """
    Namespace for session state key constants.

    Convention
    ----------
    All constants are plain strings.  Group related keys with a shared
    prefix so they sort together and are easy to find.
    """

    # ── Navigation ────────────────────────────────────────────────────────
    SELECTED_PAGE   = "selected_page"

    # ── Primary sequence slot (all modules should read/write this) ────────
    SEQ             = "build_seq"       # canonical active DNA sequence
    FEATURES        = "build_features"  # list[dict] feature annotations
    PROJECT_NAME    = "build_pname"     # human-readable project name

    # ── Legacy / cross-page aliases (read-only by new code) ──────────────
    # These exist because older modules wrote to them.  New code should
    # always write to SK.SEQ; only read these as fallbacks.
    SEQ_DESIGN      = "seq"             # Design / Wizard generic slot
    SEQ_CURRENT     = "current_seq"     # in-page editor override (Test.py)
    SEQ_ASSEMBLED   = "assembled_seq"   # Wizard pipeline output
    SEQ_ORIGINAL    = "original_seq"    # Wizard Step 1 raw input
    SEQ_FINAL       = "final_sequence"  # built expression frame

    # ── Assembly & Cloning ────────────────────────────────────────────────
    ASSEMBLY_METHOD = "assembly_method"
    ASSEMBLY_RESULT = "assembly_result"

    # ── Wizard (wizard_flow.py / ExpressionWizard.py) ─────────────────────
    DESIGN_SESSION  = "design_session"  # DesignSession dataclass instance
    WIZARD_STEP     = "wizard_step"     # current step integer (1-6)

    # ── Protein / downstream ──────────────────────────────────────────────
    PROTEIN_SEQ         = "protein_sequence"
    TRANSLATED_PROTEIN  = "translated_protein"
    PDB_ID              = "pdb_id"

    # ── Analysis ──────────────────────────────────────────────────────────
    FBA_RESULT      = "fba_result"
    AI9_RESULT      = "ai9_result"

    # ── Project / Dashboard ───────────────────────────────────────────────
    DASHBOARD_PROJECT   = "dashboard_selected_project"
    CHASSIS             = "chassis"
    RESEARCHER_NAME     = "researcher_name"

    # ── AI / Chat ─────────────────────────────────────────────────────────
    CHAT_HISTORY    = "chat_history"

    # ── UI / internationalization ─────────────────────────────────────────
    UI_LANGUAGE     = "ui_language"

    # ── Active Project Context ───────────────────────────────────────────────
    # These keys define the "current project" visible to every page.
    # Initialised once by SK.init_project_context() called from app.py.
    ACTIVE_HOST     = "ctx_host"      # str  — e.g. "Rice", "E.coli", "Arabidopsis"
    ACTIVE_SEQ      = "ctx_seq"       # str  — canonical working DNA sequence
    ACTIVE_NAME     = "ctx_name"      # str  — human label, e.g. "OsGI_construct_v2"
    ACTIVE_FEATURES = "ctx_features"  # list[dict] — feature annotations (may be [])
    ACTIVE_TYPE     = "ctx_type"      # str  — current design/workflow type
    ACTIVE_RESET_TOKEN = "ctx_reset_token"  # str — bump to invalidate stale UI state

    # ── Transient Step 3 bridge payloads ─────────────────────────────────────
    CODON_STEP3_CANDIDATE_BRIDGE = "codon_step3_candidate_bridge"
    CODON_STEP3_SELECTED_CANDIDATE = "codon_step3_selected_candidate"
    CODON_STEP3_CANDIDATE_DRAFT_PREVIEW = "codon_step3_candidate_draft_preview"

    # ── Transient Step 2 parts-registry bridge payloads ──────────────────────
    PARTS_STEP2_CANDIDATE_BRIDGE = "parts_step2_candidate_bridge"
    PARTS_STEP2_SELECTED_CANDIDATE = "parts_step2_selected_candidate"

    # ── Expression Wizard async task context guards ─────────────────────────
    PRIMER_TASK_CONTEXT_SIGNATURE = "primer_task_context_signature"
    VALIDATION_TASK_CONTEXT_SIGNATURE = "validation_task_context_signature"

    # ======================================================================
    # Helpers  (require Streamlit runtime context)
    # ======================================================================

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Safe read from session_state with a default."""
        import streamlit as st
        return st.session_state.get(key, default)

    @staticmethod
    def set(key: str, value: Any) -> None:
        """Write a value to session_state."""
        import streamlit as st
        st.session_state[key] = value

    @staticmethod
    def clear(*keys: str) -> None:
        """Delete one or more keys from session_state (silently ignores missing keys)."""
        import streamlit as st
        for k in keys:
            st.session_state.pop(k, None)

    @classmethod
    def get_seq(cls) -> str:
        """
        Return the best available active DNA sequence.

        Priority order
        (matches the logic that was hand-coded in Test.py _get_seq())
        1. SK.SEQ        (build_seq)
        2. SK.SEQ_CURRENT (current_seq)
        3. SK.SEQ_DESIGN  (seq)
        4. SK.SEQ_ASSEMBLED (assembled_seq)
        Returns empty string when nothing found.
        """
        import streamlit as st
        import re
        for key in (
            cls.SEQ,
            cls.SEQ_CURRENT,
            cls.SEQ_DESIGN,
            cls.SEQ_ASSEMBLED,
        ):
            val = st.session_state.get(key, "")
            if val:
                return re.sub(r"\[.*?\]", "", str(val)).upper()
        return ""

    @classmethod
    def clear_wizard(cls) -> None:
        """Clear all wizard-related keys to start a fresh session."""
        cls.clear(
            cls.DESIGN_SESSION,
            cls.SEQ_ORIGINAL,
            cls.SEQ_ASSEMBLED,
            cls.SEQ_FINAL,
            cls.WIZARD_STEP,
        )
        # Also clear ewiz_ / wiz_ legacy prefixes
        import streamlit as st
        for k in list(st.session_state.keys()):
            if k.startswith(("ewiz_", "wiz_", "wf_")):
                st.session_state.pop(k, None)

    @classmethod
    def init_project_context(cls) -> None:
        """Initialise the four global project-context keys in session_state.

        Must be called once from app.py before the page router runs.
        Uses setdefault-style logic so it never overwrites data that a
        previous rerun already populated.
        """
        import streamlit as st
        defaults = {
            cls.ACTIVE_HOST:     "",
            cls.ACTIVE_SEQ:      "",
            cls.ACTIVE_NAME:     "Untitled Project",
            cls.ACTIVE_FEATURES: [],
            cls.ACTIVE_TYPE:     "",
            cls.ACTIVE_RESET_TOKEN: "0",
            cls.UI_LANGUAGE:     "en",
        }
        for key, val in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = val

    @classmethod
    def clear_project_context(cls) -> None:
        """Clear the canonical active-project context without touching UI prefs."""
        cls.clear(cls.ACTIVE_HOST, cls.ACTIVE_SEQ, cls.ACTIVE_NAME, cls.ACTIVE_FEATURES, cls.ACTIVE_TYPE)

    @classmethod
    def reset_workspace(cls) -> None:
        """Reset the active project state and wizard state together."""
        cls.clear_project_context()
        cls.clear_wizard()
        cls.set(cls.ACTIVE_RESET_TOKEN, str(int(cls.get(cls.ACTIVE_RESET_TOKEN, "0")) + 1))
