"""
components/data_modules/tab_promoters.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Promoter Library tab — search, filter, view, add, delete.
"""
import streamlit as st
import pandas as pd
from core.unified_database import (
    get_all_components, search_components,
    add_component, delete_component,
)
from core.activity_log import log_data_activity


def render() -> None:
    st.subheader("Promoter Library")
    st.caption(f"Constitutive & inducible promoters for plant and bacterial expression")

    df_all = get_all_components('promoters')

    # ── Search & Filter row ──
    fc1, fc2, fc3 = st.columns([2, 1, 1])
    search = fc1.text_input("Search name / description / ID", key="prom_search",
                             placeholder="e.g. CaMV, T7, inducible...")
    strength_opts = ["All"] + sorted(df_all['strength'].dropna().unique().tolist()) if not df_all.empty else ["All"]
    chassis_opts  = ["All"] + sorted(set(
        c.strip() for row in df_all['chassis_compatibility'].dropna()
        for c in row.split(',') if c.strip()
    )) if not df_all.empty else ["All"]
    strength_f = fc2.selectbox("Strength",           strength_opts, key="prom_str_f")
    chassis_f  = fc3.selectbox("Chassis",            chassis_opts,  key="prom_cha_f")

    # Apply filters
    if search.strip():
        df = search_components('promoters', search.strip())
    else:
        df = df_all.copy()

    if not df.empty:
        if strength_f != "All":
            df = df[df['strength'] == strength_f]
        if chassis_f != "All":
            df = df[df['chassis_compatibility'].str.contains(chassis_f, na=False)]

    st.caption(f"{len(df)} record(s) shown")

    if not df.empty:
        show_cols = [c for c in ['id','name','strength','chassis_compatibility',
                                  'inducible','source_id','evidence_level'] if c in df.columns]
        st.dataframe(
            df[show_cols], use_container_width=True, hide_index=True,
            column_config={
                'name':                   st.column_config.TextColumn('Name', width=200),
                'strength':               st.column_config.TextColumn('Strength', width=120),
                'chassis_compatibility':  st.column_config.TextColumn('Chassis', width=200),
                'inducible':              st.column_config.TextColumn('Inducible', width=120),
            },
        )
        # Detail expander
        with st.expander("View full details"):
            sel = st.selectbox("Select promoter",
                               df['name'].tolist(), key="prom_detail_sel")
            row = df[df['name'] == sel].iloc[0]
            st.markdown(f"""
| Field | Value |
|---|---|
| **ID** | `{row.get('id','')}` |
| **Name** | {row.get('name','')} |
| **Strength** | {row.get('strength','')} |
| **Chassis** | {row.get('chassis_compatibility','')} |
| **Inducible** | {row.get('inducible','')} |
| **Source** | {row.get('source_id','')} |
| **Evidence** | {row.get('evidence_level','')} |
| **Description** | {str(row.get('description',''))[:300]} |
            """)
            seq = str(row.get('sequence',''))
            if seq and len(seq) > 3:
                st.code(seq[:200] + ('...' if len(seq)>200 else ''), language='text')
        # Delete
        with st.expander("Delete promoter", expanded=False):
            pid = st.selectbox("Select to delete",
                               options=df['id'].tolist(),
                               format_func=lambda x: f"{df[df['id']==x]['name'].iloc[0]} ({x})",
                               key="del_prom")
            if st.button("Confirm Delete", key="btn_del_prom", type="primary"):
                ok, msg = delete_component('promoters', pid)
                st.success(msg) if ok else st.error(msg)
                if ok:
                    log_data_activity(f"Deleted promoter {pid}", "")
                    st.rerun()
    else:
        st.info("No promoters match the current filter.")

    # ── Add new ──
    with st.expander("Add Promoter"):
        with st.form("add_promoter_form"):
            c1, c2 = st.columns(2)
            comp_id  = c1.text_input("ID (unique)",  key="p_id")
            name     = c2.text_input("Name",         key="p_name")
            c3, c4, c5 = st.columns(3)
            strength = c3.selectbox("Strength", ["Strong","Medium","Weak",
                                                  "Very Strong","Inducible"], key="p_str")
            inducible = c4.text_input("Inducible by", key="p_ind")
            source   = c5.text_input("Source ID",   key="p_src")
            chassis  = st.text_input("Chassis (comma-separated)", key="p_cha")
            desc     = st.text_area("Description",  height=80, key="p_desc")
            seq      = st.text_area("Sequence (optional)", height=60, key="p_seq")
            if st.form_submit_button("Add Promoter", type="primary"):
                if comp_id and name:
                    ok, msg = add_component('promoters', {
                        'id': comp_id, 'name': name, 'type': 'Promoter',
                        'strength': strength, 'inducible': inducible,
                        'chassis_compatibility': chassis, 'description': desc,
                        'source_id': source, 'sequence': seq,
                        'evidence_level': 'User-added',
                    })
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        log_data_activity(f"Added promoter: {name}", chassis)
                        st.rerun()
                else:
                    st.warning("ID and Name are required.")
