"""
components/assembly_modules/tab_pcr.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
PCR Amplification Simulation tab.
"""
import re
import streamlit as st
from components.assembly_modules.assembly_utils import rc, gc, tm, clean_dna
from core.activity_log import log_build_activity
from core.session_keys import SK


def _simulate_pcr(template: str, fwd: str, rev: str,
                  cycles: int = 35, err_rate: float = 1e-4) -> dict:
    """Simulate PCR and return result dict."""
    t = template.upper()
    f = fwd.upper()
    r = rev.upper()

    # Find primer binding — try full primer first, then 3' 12bp seed
    def _find_pos(primer, seq):
        pos = seq.find(primer)
        if pos >= 0:
            return pos
        seed = primer[-12:]
        return seq.find(seed)

    fwd_pos = _find_pos(f, t)
    rev_pos = _find_pos(rc(r), t)

    fwd_match = fwd_pos >= 0
    rev_match  = rev_pos >= 0

    if not fwd_match or not rev_match or fwd_pos >= rev_pos:
        return {
            'success': False,
            'message': 'Primers do not match template or orientation is incorrect',
            'product_sequence': '',
            'fwd_match': fwd_match,
            'rev_match': rev_match,
            'amplicon_length': 0,
            'tm_f': 0.0, 'tm_r': 0.0,
            'efficiency': 0.0,
            'off_targets': [],
            'has_off_target': False,
        }

    amplicon_len = rev_pos - fwd_pos + len(r)
    amplicon_sequence = t[fwd_pos:rev_pos + len(r)]
    tm_f = tm(f)
    tm_r = tm(r)
    tm_diff = abs(tm_f - tm_r)

    # Simple efficiency model
    efficiency = 95.0
    if tm_diff > 5:  efficiency -= tm_diff * 2
    if amplicon_len > 5000: efficiency -= 10
    efficiency = max(0.0, min(100.0, efficiency))

    # Off-target scan (simple)
    off_targets = []
    for m in re.finditer(f[-8:], t):
        if m.start() != fwd_pos:
            off_targets.append({'position': m.start(), 'primer': 'forward'})

    return {
        'success': True,
        'message': f'PCR product: {amplicon_len} bp',
        'product_sequence': amplicon_sequence,
        'fwd_match': True, 'rev_match': True,
        'amplicon_length': amplicon_len,
        'tm_f': round(tm_f, 1),
        'tm_r': round(tm_r, 1),
        'efficiency': round(efficiency, 1),
        'off_targets': off_targets[:5],
        'has_off_target': len(off_targets) > 0,
    }


def render() -> None:
    st.markdown("#### PCR Amplification Simulation")
    st.caption(
        "Computational PCR preview only. This simulation does not certify primer specificity, "
        "experimental success, or Wizard readiness. Some actions may record local workspace activity for traceability."
    )

    # Prefer the original Expression Wizard handoff sequence when present.
    tmpl_def = st.session_state.get(SK.ACTIVE_SEQ,
               st.session_state.get(SK.ASSEMBLY_RESULT, ''))
    tmpl = st.text_area("Template Sequence", value=tmpl_def, height=110,
                         placeholder="Paste DNA template sequence...", key="pcr_tmpl")

    c1, c2 = st.columns(2)
    fwd_name = c1.text_input("Forward Primer Name", value="Forward primer", key="pcr_fwd_name")
    rev_name = c2.text_input("Reverse Primer Name", value="Reverse primer", key="pcr_rev_name")
    fwd = c1.text_input("Forward Primer (5'→3')", placeholder="ATGCATGC...", key="pcr_fwd")
    rev = c2.text_input("Reverse Primer (5'→3')", placeholder="ATGCATGC...", key="pcr_rev")

    c3, c4 = st.columns(2)
    cyc = c3.number_input("PCR Cycles", min_value=1, max_value=50, value=35, key="pcr_cyc")
    err = c4.number_input("Polymerase Error Rate (per bp / per cycle)", min_value=0.0,
                           max_value=0.01, value=0.0001, format="%f", key="pcr_err")

    if st.button("Run PCR Simulation", type="primary",
                 use_container_width=True, key="btn_pcr"):
        if not tmpl.strip():
            st.error("Please enter a template sequence.")
        elif not fwd.strip() or not rev.strip():
            st.error("Please enter both forward and reverse primers.")
        else:
            with st.spinner("Simulating..."):
                tmpl_c, _ = clean_dna(tmpl)
                res = _simulate_pcr(tmpl_c, fwd.strip().upper(),
                                    rev.strip().upper(),
                                    cycles=int(cyc), err_rate=float(err))
            if res['success']:
                st.markdown("##### Preview summary")
                st.markdown(
                    f"<div style='background:#f0fdf4;border:1px solid #86efac;"
                    f"border-radius:8px;padding:12px 16px;margin:8px 0'>"
                    f"<b>Preview generated — {res['message']}</b></div>",
                    unsafe_allow_html=True,
                )
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Expected Amplicon",      f"{res['amplicon_length']} bp")
                m2.metric("Forward Primer", fwd_name)
                m3.metric("Reverse Primer", rev_name)
                m4.metric("Target Length", f"{len(tmpl_c)} bp")
                st.markdown("##### Primer review notes")
                st.caption("Primer-target preview only; this does not guarantee amplification and does not replace primer review.")
                if res['has_off_target']:
                    st.warning(
                        f"{len(res['off_targets'])} potential additional primer-target "
                        f"match(es) detected in this computational preview."
                    )
                if not res['has_off_target']:
                    st.caption("No flagged issue")
                st.markdown("##### Documentation artifact")
                st.caption("Documentation artifact available for this computational preview only.")
                if res['amplicon_length'] > 0:
                    st.session_state['pcr_preview_product'] = res['product_sequence']
                log_build_activity("PCR Simulation",
                    f"{res['amplicon_length']} bp · Fwd Tm {res['tm_f']}°C")
            else:
                st.error(res['message'])
                st.info("Tip: check that primer sequences match the template and orientation is correct.")
                    