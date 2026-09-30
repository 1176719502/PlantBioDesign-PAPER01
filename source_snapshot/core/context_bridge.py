# core/context_bridge.py
"""
Cross-module relay: write completed work into the global project context
and optionally navigate to the target page.

Rules
-----
- No business logic here. Only session_state writes + navigation.
- Every public function is callable from any view module.
- The change_page callback is optional; pass None to skip navigation.
- No Streamlit imports at module level (safe for unit tests).
"""
from __future__ import annotations
from typing import Callable, Optional

from core.session_keys import SK

# Canonical sequence keys for cross-page relay:
# - SK.ACTIVE_SEQ: global project context sequence (ctx_seq)
# - SK.SEQ: assembly/workbench primary sequence (build_seq)
# Legacy keys are still mirrored for backward compatibility.


def send_codon_step3_candidate(
    payload: dict,
    change_page: Optional[Callable] = None,
) -> None:
    """Send a transient Codon Optimizer candidate to Wizard Step 3.

    Writes only a transient session payload used by Expression Wizard Step 3.
    This helper must not write to DesignSession Step 1/3 fields and must not
    reuse the Step 1 relay semantics of send_seq_to_wizard().

    Parameters
    ----------
    payload : dict
        Candidate payload generated from a successful standalone codon
        optimization result.
    change_page : callable, optional
        The _change_page callback from app.py. Pass None to relay data
        without navigating.
    """
    import streamlit as st

    if not isinstance(payload, dict) or not str(payload.get("candidate_seq") or "").strip():
        return

    st.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = payload
    st.session_state.pop(SK.CODON_STEP3_SELECTED_CANDIDATE, None)

    if change_page is not None:
        change_page("Expression Wizard")


def send_parts_step2_candidate(
    payload: dict,
    change_page: Optional[Callable] = None,
) -> None:
    """Send a transient Parts Registry candidate to Wizard Step 2.

    Writes only the transient bridge payload consumed by Expression Wizard
    Step 2. This helper must not write Step 2 formal design fields, confirm
    the step, or advance the workflow.
    """
    import streamlit as st

    if not isinstance(payload, dict):
        return

    st.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = payload
    st.session_state.pop(SK.PARTS_STEP2_SELECTED_CANDIDATE, None)

    try:
        from core.design_session import SessionController
        ctrl = SessionController()
        ds = ctrl.get()
        if getattr(ds, "step", None) != 2:
            ds.step = 2
            ctrl.save(ds)
    except Exception:
        pass

    page_callback = change_page or st.session_state.get("_change_page_cb")
    if callable(page_callback):
        page_callback("Expression Wizard")


def send_seq_to_wizard(
    seq: str,
    gene_name: str = "",
    change_page: Optional[Callable] = None,
) -> None:
    """Send a finished sequence into Expression Wizard Step 1.

    Writes the sequence into:
      1. The four global context keys (SK.ACTIVE_*)
      2. The active DesignSession (so Step 1 shows it pre-filled)

    Then navigates to the Expression Wizard page if change_page is provided.

    Parameters
    ----------
    seq : str
        Clean DNA sequence to relay (uppercase, no whitespace).
    gene_name : str
        Optional label; keeps existing name if empty string.
    change_page : callable, optional
        The _change_page callback from app.py. Pass None to relay data
        without navigating (useful for testing).
    """
    import streamlit as st

    if not seq:
        return

    # 1. Write to global context keys
    st.session_state[SK.ACTIVE_SEQ]  = seq
    if gene_name:
        st.session_state[SK.ACTIVE_NAME] = gene_name

    # 2. Pre-fill wizard DesignSession so Step 1 shows the sequence immediately
    try:
        from core.design_session import SessionController
        ctrl = SessionController()
        ds = ctrl.get()
        ds.original_seq = seq
        if gene_name:
            ds.gene_name = gene_name
        # Land on Step 1 so the user sees the pre-filled data
        ds.step = 1
        ctrl.save(ds)
        # SK.ACTIVE_SEQ is the single cross-page sequence slot.
        # All consumers now read SK.ACTIVE_SEQ; legacy aliases removed.
    except Exception:
        # Never block navigation due to session errors
        pass

    # 3. Navigate
    if change_page is not None:
        change_page("Expression Wizard")


def send_wizard_to_assembly(
    change_page: Optional[Callable] = None,
) -> None:
    """Send the wizard's completed design to Assembly & Cloning.

    Extracts final_sequence and features from the active DesignSession,
    writes them into global context keys and the assembly session keys,
    then navigates to the Assembly & Cloning page.

    Safe to call at any wizard step; silently skips if no sequence is
    available.

    Parameters
    ----------
    change_page : callable, optional
        The _change_page callback from app.py.
    """
    import streamlit as st

    try:
        from core.design_session import SessionController
        ctrl = SessionController()
        # sync_to_global_state writes build_seq / seq / final_sequence / build_features
        ctrl.sync_to_global_state()
        ds  = ctrl.get()
        seq = ds.final_sequence or ds.optimized_seq or ds.original_seq
        features = ds.frame.get("features", []) if isinstance(ds.frame, dict) else []
    except Exception:
        seq = ""
        features = []

    if not seq:
        return

    # Write to global context keys
    st.session_state[SK.ACTIVE_SEQ]      = seq
    st.session_state[SK.ACTIVE_FEATURES] = features

    # Seed the assembly workbench input from the same canonical key.
    st.session_state[SK.ASSEMBLY_RESULT] = seq

    # Navigate
    if change_page is not None:
        change_page("Assembly & Cloning")
