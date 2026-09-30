"""
components/data_modules/tab_primers.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Primer Library tab — search, filter by species/status, view, add, delete.
"""
import streamlit as st
import pandas as pd
from core.unified_database import get_all_primers, add_primer, delete_component
from core.activity_log import log_data_activity

try:
    from core.primer_utils import calc_tm, calc_gc, check_primer_issues
    _P3_OK = True
except ImportError:
    _P3_OK = False


def render() -> None:
    st.subheader("Primer Library")
    st.caption("Design, store and manage PCR primers")

    df_all = get_all_primers()

    # ── Search & Filter ──
    fc1, fc2, fc3 = st.columns([2, 1, 1])
    search  = fc1.text_input("Search name / sequence", key="primer_search",
                              placeholder="e.g. M13, T7, GFP...")
    sp_opts = ["All"] + sorted(df_all['species'].dropna().unique().tolist()) if not df_all.empty else ["All"]
    st_opts = ["All"] + sorted(df_all['status'].dropna().unique().tolist())  if not df_all.empty else ["All"]
    sp_f = fc2.selectbox("Species", sp_opts, key="primer_sp_f")
    st_f = fc3.selectbox("Status",  st_opts, key="primer_st_f")

    df = df_all.copy() if not df_all.empty else pd.DataFrame()
    if not df.empty:
        if search.strip():
            mask = (df['name'].str.contains(search, case=False, na=False) |
                    df['sequence'].str.contains(search, case=False, na=False))
            df = df[mask]
        if sp_f != "All":
            df = df[df['species'] == sp_f]
        if st_f != "All":
            df = df[df['status'] == st_f]

    st.caption(f"{len(df)} record(s) shown")

    if not df.empty:
        show_cols = [c for c in ['id','name','sequence','tm','gc_content',
                                  'species','status','design_date'] if c in df.columns]
        st.dataframe(
            df[show_cols], use_container_width=True, hide_index=True,
            column_config={
                'name':        st.column_config.TextColumn('Name', width=160),
                'sequence':    st.column_config.TextColumn('Sequence', width=240),
                'tm':          st.column_config.NumberColumn('Tm (°C)', format="%.1f", width=80),
                'gc_content':  st.column_config.NumberColumn('GC%',    format="%.1f", width=70),
                'species':     st.column_config.TextColumn('Species', width=100),
                'status':      st.column_config.TextColumn('Status',  width=90),
            },
        )
        with st.expander("Check primer quality"):
            sel = st.selectbox("Select primer", df['name'].tolist(), key="primer_qc_sel")
            row = df[df['name'] == sel].iloc[0]
            seq = str(row.get('sequence', ''))
            if seq and _P3_OK:
                tm_val = calc_tm(seq)
                gc_val = calc_gc(seq)
                issues = check_primer_issues(seq)
                c1, c2, c3 = st.columns(3)
                c1.metric("Tm (primer3-py)", f"{tm_val} °C")
                c2.metric("GC%",             f"{gc_val:.1f}%")
                c3.metric("Length",          f"{len(seq)} bp")
                if issues:
                    for iss in issues:
                        st.warning(iss)
                else:
                    st.success("No issues detected")
            elif seq:
                st.code(seq)
        with st.expander("Delete primer", expanded=False):
            pid = st.selectbox("Select to delete",
                               options=df['id'].tolist(),
                               format_func=lambda x: f"{df[df['id']==x]['name'].iloc[0]} ({x})",
                               key="del_primer")
            if st.button("Confirm Delete", key="btn_del_primer", type="primary"):
                ok, msg = delete_component('primers', pid)
                st.success(msg) if ok else st.error(msg)
                if ok:
                    log_data_activity(f"Deleted primer {pid}", "")
                    st.rerun()
    else:
        st.info("No primers match the current filter.")

    # ── Add new with auto Tm/GC ──
    with st.expander("Add Primer"):
        with st.form("add_primer_form"):
            c1, c2 = st.columns(2)
            p_name = c1.text_input("Primer name",    key="pr_name")
            p_seq  = c2.text_input("Sequence (5'→3')", key="pr_seq")
            c3, c4, c5 = st.columns(3)
            p_sp   = c3.selectbox("Species", ["Universal","Plant","E. coli",
                                               "Bacteria","Yeast","Mammalian"], key="pr_sp")
            p_st   = c4.selectbox("Status",  ["Designed","Ordered","Validated",
                                               "Failed"], key="pr_st")
            p_note = c5.text_input("Notes", key="pr_note")
            if st.form_submit_button("Add Primer", type="primary"):
                if p_name and p_seq:
                    clean = ''.join(c for c in p_seq.upper() if c in 'ATCGN')
                    tm_v  = calc_tm(clean)  if _P3_OK else 0.0
                    gc_v  = calc_gc(clean)  if _P3_OK else 0.0
                    ok, msg = add_primer(p_name, clean, tm_v, gc_v, p_sp, p_st)
                    st.success(f"{msg} — Tm: {tm_v}°C, GC: {gc_v:.1f}%") if ok else st.error(msg)
                    if ok:
                        log_data_activity(f"Added primer: {p_name}",
                                          f"{len(clean)} bp · Tm {tm_v}°C")
                        st.rerun()
                else:
                    st.warning("Name and sequence are required.")
