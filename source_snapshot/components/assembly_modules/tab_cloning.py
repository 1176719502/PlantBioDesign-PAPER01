"""
components/assembly_modules/tab_cloning.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Cloning Simulation tab — Restriction Cloning, Golden Gate, Gibson Assembly.
"""
import hashlib

import streamlit as st
import pandas as pd
from Bio.Seq import Seq
from components.assembly_modules.assembly_utils import (
    REBASE_DB, rc, gc, tm, clean_dna, validate_sequence,
    scan_restriction_sites, select_orthogonal_overhangs, sequence_stats,
)
from core.activity_log import log_build_activity
from core.session_keys import SK


_DEFAULT_RC_INSERT_PLACEHOLDER = "ATGAAACCC..."
_DEFAULT_RC_INSERT_EXAMPLE = "ATGAAACCC"


# ── Assembly logic ────────────────────────────────────────────────

def _clean_product_sequence(product: str) -> str:
    cleaned, _ = clean_dna(product) if product else ('', [])
    return cleaned


def _restriction_clone(insert: str, e1: str, e2: str) -> dict:
    info1 = REBASE_DB.get(e1, {})
    info2 = REBASE_DB.get(e2, {})
    site1 = info1.get('site', '')
    site2 = info2.get('site', '')
    ovhg1 = info1.get('ovhg', 4)
    ovhg2 = info2.get('ovhg', 4)
    prefix = site1 + ('AA' if ovhg1 > 0 else '')
    suffix = ('TT' if ovhg2 > 0 else '') + site2
    product = _clean_product_sequence(prefix + insert + suffix)
    ends = f"5'-{site1[:ovhg1] if ovhg1 > 0 else 'blunt'} / {site2[-abs(ovhg2):] if ovhg2 < 0 else 'blunt'}-3'"
    return {
        'enzyme1': e1, 'enzyme2': e2,
        'insert_len': len(insert),
        'length': len(product),
        'product': product,
        'ligation_ends': ends,
    }


def _gg_assemble(seqs: list, names: list, overhangs: list) -> dict:
    product = _clean_product_sequence(''.join(s[:] for s in seqs))
    return {'length': len(product), 'product': product,
            'n_fragments': len(seqs), 'overhangs': overhangs}


def _gibson_assemble(seqs: list, names: list, overlap: int = 20) -> dict:
    if not seqs:
        return {'length': 0, 'product': ''}
    product = seqs[0]
    for s in seqs[1:]:
        product = product + s[overlap:] if len(s) > overlap else product + s
    return {'length': len(product), 'product': _clean_product_sequence(product), 'overlap': overlap}


def _design_primers_gg(seqs: list, names: list, overhangs: list, bind_len: int = 20) -> pd.DataFrame:
    rows = []
    for i, (seq, name) in enumerate(zip(seqs, names)):
        oh_l = overhangs[i]   if i < len(overhangs) else 'AAAC'
        oh_r = overhangs[i+1] if i+1 < len(overhangs) else 'AATG'
        fwd_seq = oh_l + seq[:bind_len]
        rev_seq = oh_r + rc(seq[-bind_len:])
        rows.append({
            'Fragment': name,
            'Forward Primer': fwd_seq,
            'Fwd Tm (°C)': tm(seq[:bind_len]),
            'Reverse Primer': rev_seq,
            'Rev Tm (°C)': tm(rc(seq[-bind_len:])),
            '5\' Overhang (Fwd)': oh_l,
            '5\' Overhang (Rev)': oh_r,
        })
    return pd.DataFrame(rows)


def _design_primers_gibson(seqs: list, names: list, homology: int = 20) -> pd.DataFrame:
    rows = []
    for i, (seq, name) in enumerate(zip(seqs, names)):
        prev_seq = seqs[i-1] if i > 0 else seqs[-1]
        next_seq = seqs[(i+1) % len(seqs)]
        arm_fwd = prev_seq[-homology:] if len(prev_seq) >= homology else prev_seq
        arm_rev = rc(next_seq[:homology]) if len(next_seq) >= homology else rc(next_seq)
        fwd_bind = seq[:20]
        rev_bind = rc(seq[-20:])
        rows.append({
            'Fragment': name,
            'Forward Primer': arm_fwd + fwd_bind,
            'Fwd Binding Tm (°C)': tm(fwd_bind),
            'Reverse Primer': arm_rev + rev_bind,
            'Rev Binding Tm (°C)': tm(rev_bind),
            'Homology Arm (bp)': homology,
        })
    return pd.DataFrame(rows)


def _enrich_planner_primers(primers: list, overlap_len: int) -> pd.DataFrame:
    """
    Convert AssemblyPlanner primer dicts to a display DataFrame.

    Prefers the pre-calculated Tm fields emitted by the updated AssemblyPlanner
    (``Fwd Anneal Tm (°C)`` / ``Rev Anneal Tm (°C)``).  Falls back to
    re-deriving Tm from the arm-offset position for backward compatibility
    with any older planner output that lacks those fields.
    """
    from core.primer_utils import calc_tm as _tm, calc_gc as _gc
    rows = []
    for p in primers:
        fwd = p["Forward Primer (5'->3')"]
        rev = p["Reverse Primer (5'->3')"]
        fwd_arm_len = p.get("Fwd Arm (bp)", overlap_len)
        rev_arm_len = p.get("Rev Arm (bp)", overlap_len)
        # Annealing Tm: use planner-provided value when available
        fwd_tm = p.get("Fwd Anneal Tm (\u00b0C)") or (
            _tm(fwd[fwd_arm_len:]) if len(fwd) > fwd_arm_len else _tm(fwd)
        )
        rev_tm = p.get("Rev Anneal Tm (\u00b0C)") or (
            _tm(rev[rev_arm_len:]) if len(rev) > rev_arm_len else _tm(rev)
        )
        rows.append({
            'Fragment':                 p['Fragment Name'],
            "Forward Primer (5'\u21923')": fwd,
            'Fwd Length (bp)':          len(fwd),
            'Fwd Binding Tm (\u00b0C)': round(float(fwd_tm), 1),
            'Fwd GC (%)':               round(_gc(fwd), 1),
            "Reverse Primer (5'\u21923')": rev,
            'Rev Length (bp)':          len(rev),
            'Rev Binding Tm (\u00b0C)': round(float(rev_tm), 1),
            'Rev GC (%)':               round(_gc(rev), 1),
            'Homology Arm (bp)':        overlap_len,
        })
    return pd.DataFrame(rows)


def _validate_assembly(seqs: list) -> tuple:
    warnings = []
    for i, s in enumerate(seqs):
        if len(s) < 20:
            warnings.append(f"Fragment {i+1} is too short ({len(s)} bp)")
        if gc(s) < 20 or gc(s) > 80:
            warnings.append(f"Fragment {i+1} has extreme GC content ({gc(s):.1f}%)")
    return len(warnings) == 0, warnings


def _format_fragment_summary(names: list, seqs: list) -> dict:
    filled = [(name, seq) for name, seq in zip(names, seqs) if seq]
    lengths = [len(seq) for _, seq in filled]
    return {
        'filled_count': len(filled),
        'empty_count': max(len(seqs) - len(filled), 0),
        'total_bp': sum(lengths),
        'order_text': " → ".join(name for name, _ in filled) if filled else "No fragments entered",
        'length_text': ", ".join(f"{name}: {len(seq)} bp" for name, seq in filled[:6]) if filled else "No valid fragment lengths",
    }



def _find_internal_site_warnings(seqs: list, names: list, enzymes: list[str]) -> list[str]:
    warnings = []
    for idx, (name, seq) in enumerate(zip(names, seqs), start=1):
        if not seq:
            continue
        hits = scan_restriction_sites(seq, enzymes)
        if not hits:
            continue
        enzyme_counts = {}
        for hit in hits:
            enzyme_counts[hit['enzyme']] = enzyme_counts.get(hit['enzyme'], 0) + 1
        enzyme_text = ", ".join(f"{enzyme}×{count}" for enzyme, count in sorted(enzyme_counts.items()))
        warnings.append(f"Fragment {idx} ({name}) contains internal site(s): {enzyme_text}")
    return warnings



def _build_fragment_validation_table(
    names: list[str],
    seqs: list[str],
    enzymes: list[str],
) -> pd.DataFrame:
    rows = []
    for idx, (name, seq) in enumerate(zip(names, seqs), start=1):
        label = name or f"Fragment {idx}"
        if not seq:
            rows.append({
                'Fragment': label,
                'Length (bp)': 0,
                'GC (%)': 0.0,
                'Internal Site Count': 0,
                'Status': 'Empty',
            })
            continue

        internal_site_count = len(scan_restriction_sites(seq, enzymes))
        row_warnings = []
        if len(seq) < 20:
            row_warnings.append('short')
        seq_gc = gc(seq)
        if seq_gc < 20 or seq_gc > 80:
            row_warnings.append('gc')
        if internal_site_count:
            row_warnings.append('site')

        rows.append({
            'Fragment': label,
            'Length (bp)': len(seq),
            'GC (%)': round(seq_gc, 1),
            'Internal Site Count': internal_site_count,
            'Status': 'Warn' if row_warnings else 'Pass',
        })

    return pd.DataFrame(rows)



def _render_fragment_validation_table(
    title: str,
    names: list[str],
    seqs: list[str],
    enzymes: list[str],
) -> None:
    table = _build_fragment_validation_table(names, seqs, enzymes)
    if table.empty:
        return

    st.markdown(f"###### {title}")
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        height=min(320, 74 + 35 * len(table)),
        column_config={
            'Fragment': st.column_config.TextColumn('Fragment', width='medium'),
            'Length (bp)': st.column_config.NumberColumn('Length (bp)', format='%d', width='small'),
            'GC (%)': st.column_config.NumberColumn('GC (%)', format='%.1f', width='small'),
            'Internal Site Count': st.column_config.NumberColumn('Internal Site Count', format='%d', width='small'),
            'Status': st.column_config.TextColumn('Status', width='small'),
        },
    )



def _find_duplicate_overhang_warnings(overhangs: list) -> list[str]:
    warnings = []
    positions = {}
    reverse_map = {}
    for idx, overhang in enumerate(overhangs, start=1):
        positions.setdefault(overhang, []).append(idx)
        reverse_map.setdefault(str(Seq(overhang).reverse_complement()), []).append((idx, overhang))

    for overhang, idxs in positions.items():
        if len(idxs) > 1:
            warnings.append(
                f"Overhang {overhang} is reused at junctions {', '.join(map(str, idxs))}."
            )

    seen_pairs = set()
    for overhang, idxs in positions.items():
        rev = str(Seq(overhang).reverse_complement())
        if overhang == rev or rev not in positions:
            continue
        pair_key = tuple(sorted((overhang, rev)))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        warnings.append(
            f"Overhang pair {overhang}/{rev} are reverse complements and may cross-ligate."
        )
    return warnings



def _render_validation_summary(title: str, lines: list[str], tone: str = 'info') -> None:
    if not lines:
        return
    if tone == 'warning':
        st.warning(f"{title}\n- " + "\n- ".join(lines))
    elif tone == 'error':
        st.error(f"{title}\n- " + "\n- ".join(lines))
    else:
        st.info(f"{title}\n- " + "\n- ".join(lines))


def _build_gibson_fragment_boundary_table(
    names: list[str],
    seqs: list[str],
    overlap: int,
) -> pd.DataFrame:
    rows = []
    cursor = 1
    for idx, (name, seq) in enumerate(zip(names, seqs), start=1):
        if not seq:
            continue
        start = cursor
        end = cursor + len(seq) - 1
        boundary_span = min(overlap, len(seq), 12)
        rows.append({
            'Fragment': name or f'Fragment {idx}',
            'Length (bp)': len(seq),
            'Start': start,
            'End': end,
            "5' Boundary": seq[:boundary_span],
            "3' Boundary": seq[-boundary_span:],
        })
        cursor = end + 1
    return pd.DataFrame(rows)



def _build_gibson_primer_review_table(plan: dict, overlap: int) -> pd.DataFrame:
    rows = []
    for primer in plan.get('primers', []):
        warnings = primer.get('Warnings') or []
        rows.append({
            'Fragment': primer['Fragment Name'],
            'Fwd Arm (bp)': primer.get('Fwd Arm (bp)', overlap),
            'Rev Arm (bp)': primer.get('Rev Arm (bp)', overlap),
            'Fwd Anneal Tm (°C)': primer.get('Fwd Anneal Tm (°C)'),
            'Rev Anneal Tm (°C)': primer.get('Rev Anneal Tm (°C)'),
            'Warnings': ' | '.join(warnings) if warnings else 'None',
        })
    return pd.DataFrame(rows)



def _render_gibson_fragment_review(
    names: list[str],
    seqs: list[str],
    overlap: int,
    plan: dict | None = None,
) -> None:
    boundary_table = _build_gibson_fragment_boundary_table(names, seqs, overlap)
    if not boundary_table.empty:
        st.markdown('###### Fragment boundaries')
        st.dataframe(
            boundary_table,
            use_container_width=True,
            hide_index=True,
            height=min(320, 74 + 35 * len(boundary_table)),
            column_config={
                'Fragment': st.column_config.TextColumn('Fragment', width='medium'),
                'Length (bp)': st.column_config.NumberColumn('Length (bp)', format='%d', width='small'),
                'Start': st.column_config.NumberColumn('Start', format='%d', width='small'),
                'End': st.column_config.NumberColumn('End', format='%d', width='small'),
                "5' Boundary": st.column_config.TextColumn("5' Boundary", width='medium'),
                "3' Boundary": st.column_config.TextColumn("3' Boundary", width='medium'),
            },
        )

    primer_map = {
        primer['Fragment Name']: primer
        for primer in (plan or {}).get('primers', [])
    }

    st.markdown('###### Per-fragment review')
    for idx, (name, seq) in enumerate(zip(names, seqs), start=1):
        if not seq:
            continue

        fragment_label = name or f'Fragment {idx}'
        upstream_seq = seqs[idx - 2] if idx > 1 else ''
        downstream_seq = seqs[idx] if idx < len(seqs) else ''
        left_overlap = upstream_seq[-overlap:] if upstream_seq else 'None (first fragment)'
        right_overlap = downstream_seq[:overlap] if downstream_seq else 'None (last fragment)'
        primer_info = primer_map.get(fragment_label, {})
        primer_warnings = primer_info.get('Warnings') or []

        with st.expander(f"{fragment_label} · {len(seq)} bp", expanded=False):
            start = sum(len(s) for s in seqs[:idx - 1]) + 1
            end = start + len(seq) - 1
            st.markdown(
                f"**Coordinate span:** {start}-{end}  \n"
                f"**5' boundary:** `{seq[:min(overlap, len(seq))]}`  \n"
                f"**3' boundary:** `{seq[-min(overlap, len(seq)):]}`"
            )
            st.markdown(
                f"**Upstream overlap source:** `{left_overlap}`  \n"
                f"**Downstream overlap target:** `{right_overlap}`"
            )
            if primer_info:
                st.markdown(
                    f"**Forward homology arm:** {primer_info.get('Fwd Arm (bp)', 0)} bp  \\n"
                    f"**Reverse homology arm:** {primer_info.get('Rev Arm (bp)', 0)} bp  \\n"
                    f"**Forward anneal Tm:** {primer_info.get('Fwd Anneal Tm (°C)', 'n/a')} °C  \\n"
                    f"**Reverse anneal Tm:** {primer_info.get('Rev Anneal Tm (°C)', 'n/a')} °C"
                )
            if primer_warnings:
                st.warning('Fragment-specific planner warnings\n- ' + '\n- '.join(primer_warnings))

    primer_review = _build_gibson_primer_review_table(plan or {}, overlap)
    if not primer_review.empty:
        st.markdown('###### Primer and overlap summary')
        st.dataframe(
            primer_review,
            use_container_width=True,
            hide_index=True,
            height=min(320, 74 + 35 * len(primer_review)),
            column_config={
                'Fragment': st.column_config.TextColumn('Fragment', width='medium'),
                'Fwd Arm (bp)': st.column_config.NumberColumn('Fwd Arm (bp)', format='%d', width='small'),
                'Rev Arm (bp)': st.column_config.NumberColumn('Rev Arm (bp)', format='%d', width='small'),
                'Fwd Anneal Tm (°C)': st.column_config.NumberColumn('Fwd Anneal Tm (°C)', format='%.1f', width='small'),
                'Rev Anneal Tm (°C)': st.column_config.NumberColumn('Rev Anneal Tm (°C)', format='%.1f', width='small'),
                'Warnings': st.column_config.TextColumn('Warnings', width='large'),
            },
        )


def _maybe_prefill_restriction_insert() -> None:
    handoff_seq = st.session_state.get(SK.ACTIVE_SEQ, '')
    handoff_seq, _ = clean_dna(handoff_seq) if handoff_seq else ('', [])
    if not handoff_seq:
        return

    handoff_name = st.session_state.get(SK.ACTIVE_NAME, '') or st.session_state.get(SK.PROJECT_NAME, '')
    handoff_id = f"{handoff_name}:{len(handoff_seq)}:{hashlib.sha256(handoff_seq.encode('utf-8')).hexdigest()}"
    current_insert = st.session_state.get('rc_insert', '')
    current_text = str(current_insert or '').strip().upper()
    current_clean, _ = clean_dna(current_text) if current_text else ('', [])
    placeholder_clean, _ = clean_dna(_DEFAULT_RC_INSERT_PLACEHOLDER)
    can_prefill = (
        not current_text
        or current_text == _DEFAULT_RC_INSERT_PLACEHOLDER
        or current_clean in {_DEFAULT_RC_INSERT_EXAMPLE, placeholder_clean}
    )

    if st.session_state.get('rc_insert_last_handoff_id') != handoff_id and can_prefill:
        st.session_state['rc_insert'] = handoff_seq
        st.session_state['rc_insert_last_handoff_id'] = handoff_id


# ── UI renders ────────────────────────────────────────────────────

def _render_restriction_cloning():
    st.markdown("##### Restriction Enzyme Cloning")
    st.caption(
        "Exploratory cloning preview only. Review any output in the Expression Wizard "
        "Step 5/Step 6 readiness flow before treating it as final."
    )
    c1, c2 = st.columns(2)
    _maybe_prefill_restriction_insert()
    raw = c1.text_area("Insert Sequence", height=120,
                       placeholder=_DEFAULT_RC_INSERT_PLACEHOLDER, key="rc_insert").upper().strip()
    insert, _ = clean_dna(raw) if raw else ('', [])
    enzyme_list = list(REBASE_DB.keys())
    e1 = c1.selectbox("5' Restriction Enzyme (Upstream)",   enzyme_list, index=0, key="rc_e1")
    e2 = c2.selectbox("3' Restriction Enzyme (Downstream)", enzyme_list, index=1, key="rc_e2")
    same = c2.checkbox("Use the same enzyme at both ends", value=False, key="rc_same")
    if same:
        e2 = e1

    fragment_summary = _format_fragment_summary(["Insert"], [insert])
    if raw and not insert:
        _render_validation_summary(
            "Sequence summary",
            ["Input was provided but no valid DNA bases remained after cleaning."],
            tone='warning',
        )
    elif insert:
        summary_lines = [
            f"Filled fragments: {fragment_summary['filled_count']} of 1",
            f"Insert length: {len(insert)} bp",
            f"Planned cloning: {e1} → insert → {e2}",
        ]
        _render_validation_summary("Cloning summary", summary_lines)
        _render_fragment_validation_table(
            "Fragment validation",
            ["Insert"],
            [insert],
            [e1, e2],
        )

        internal_warnings = _find_internal_site_warnings([insert], ["Insert"], [e1, e2])
        if internal_warnings:
            _render_validation_summary(
                "Restriction site warning",
                internal_warnings,
                tone='warning',
            )

    if st.button("Run Restriction Cloning Preview", type="primary",
                 use_container_width=True, key="btn_rc"):
        if not insert:
            st.error("Please enter an insert sequence.")
        else:
            result = _restriction_clone(insert, e1, e2)
            log_build_activity(f"Restriction enzyme cloning: {e1}/{e2}", f"{result['length']} bp")
            st.markdown("##### Preview summary")
            st.markdown(
                f"<div style='background:#f0fdf4;border:1px solid #86efac;"
                f"border-radius:8px;padding:12px 16px;margin:8px 0'>"
                f"Preview generated — <b>{result['length']} bp</b><br>"
                f"Upstream: <b>{e1}</b> ({REBASE_DB[e1]['site']}) · "
                f"Downstream: <b>{e2}</b> ({REBASE_DB[e2]['site']})<br>"
                f"Ligation ends: {result['ligation_ends']}<br>"
                f"Product structure: {e1} site + insert + {e2} site"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown("##### Review notes")
            st.caption("No flagged issue" if not internal_warnings else "Flagged for review: review restriction site notes above.")
            st.markdown("##### Documentation artifact")
            st.caption("Documentation artifact available. Computational preview only; this does not certify cloning, PCR, gel, or expression success.")
            st.session_state['cloning_preview_product'] = result['product']
            st.session_state['cloning_preview_method'] = 'Restriction Enzyme Cloning'
            with st.expander("View product sequence"):
                st.code(result['product'], language='text')


def _render_golden_gate():
    st.markdown("##### Golden Gate Assembly (BsaI / BsmBI)")
    st.caption(
        "Computational assembly and primer-table preview only. This does not replace "
        "Wizard validation or Step 6 readiness review."
    )
    n = st.number_input("Fragment count", min_value=2, max_value=8, value=3, step=1, key="gg_n")
    bind_len = st.slider("Binding region length (bp)", 15, 30, 20, key="gg_bind")
    parts_seqs, parts_names = [], []
    for i in range(int(n)):
        ca, cb = st.columns([1, 3])
        nm = ca.text_input(f"Fragment {i+1} name", value=f"Fragment_{i+1}", key=f"gg_nm_{i}")
        raw = cb.text_area(f"Fragment {i+1} sequence", height=68,
                           placeholder="ATGCATGC...", key=f"gg_sq_{i}").upper().strip()
        sq, _ = clean_dna(raw) if raw else ('', [])
        parts_seqs.append(sq)
        parts_names.append(nm)

    fragment_summary = _format_fragment_summary(parts_names, parts_seqs)
    _render_validation_summary(
        "Assembly summary",
        [
            f"Filled fragments: {fragment_summary['filled_count']} of {int(n)}",
            f"Empty inputs: {fragment_summary['empty_count']}",
            f"Current order: {fragment_summary['order_text']}",
            f"Entered DNA total: {fragment_summary['total_bp']} bp",
        ],
    )
    _render_fragment_validation_table(
        "Fragment validation",
        parts_names,
        parts_seqs,
        ['BsaI', 'BsmBI'],
    )

    internal_warnings = _find_internal_site_warnings(parts_seqs, parts_names, ['BsaI', 'BsmBI'])
    if internal_warnings:
        _render_validation_summary(
            "Golden Gate site warning",
            internal_warnings,
            tone='warning',
        )

    planned_overhangs = select_orthogonal_overhangs(int(n))
    overhang_warnings = _find_duplicate_overhang_warnings(planned_overhangs)
    if overhang_warnings:
        _render_validation_summary(
            "Overhang compatibility warning",
            overhang_warnings,
            tone='warning',
        )

    if st.button("Run Golden Gate Primer and Assembly Preview",
                 type="primary", use_container_width=True, key="btn_gg"):
        valid = [s for s in parts_seqs if s and len(s) >= 20]
        if len(valid) < 2:
            st.error("Please enter at least 2 valid fragments, each at least 20 bp.")
        else:
            ok, warns = _validate_assembly(parts_seqs)
            for w in warns:
                st.warning(w)
            overhangs = planned_overhangs
            result = _gg_assemble(parts_seqs, parts_names, overhangs)
            df_p = _design_primers_gg(parts_seqs, parts_names, overhangs, bind_len)
            log_build_activity(f"Golden Gate Assembly: {int(n)} fragments", f"{result['length']} bp")
            st.markdown("##### Preview summary")
            st.markdown(
                (
                    "<div style='background:#f0fdf4;border:1px solid #86efac;"
                    "border-radius:8px;padding:12px 16px;margin:8px 0'>"
                    f"Preview generated — <b>{result['length']} bp</b> · "
                    f"{len(valid)} valid fragments / {int(n)} input fragments<br>"
                    f"Fragment order: {fragment_summary['order_text']}<br>"
                    f"Junction overhangs: " + " → ".join(overhangs[:len(valid) + 1]) + "</div>"
                ),
                unsafe_allow_html=True,
            )
            st.markdown("##### Review notes")
            st.caption(f"Fragment length overview: {fragment_summary['length_text']}")
            st.caption("No flagged issue" if not (warns or internal_warnings or overhang_warnings) else "Flagged for review: review fragment, site, or overhang notes above.")
            st.markdown("##### Documentation artifact")
            st.caption("Documentation artifact available. Computational preview only; this does not certify cloning, PCR, gel, or expression success.")
            st.dataframe(df_p, use_container_width=True, hide_index=True)
            csv = df_p.to_csv(index=False).encode('utf-8-sig')
            st.download_button("Download primer table", csv, "gg_primers.csv", "text/csv")
            st.session_state['cloning_preview_product'] = result['product']
            st.session_state['cloning_preview_method'] = 'Golden Gate Assembly'
            with st.expander("View assembled product"):
                st.code(result['product'], language='text')


def _render_gibson():
    """Gibson Assembly primer designer powered by core.assembly_planner.AssemblyPlanner."""
    from core.assembly_planner import AssemblyPlanner
    from core.construct_builder import ConstructBuilder
    from core.part_library import BioPart

    st.markdown("##### Gibson Assembly — Primer Design")
    st.caption(
        "Primers are generated by the existing **AssemblyPlanner** using homology-arm overlaps. "
        "This standalone preview does not replace Expression Wizard Step 4 full-cassette "
        "primer design, Step 5 validation, or Step 6 readiness review."
    )

    # ── 1. Sequence source ────────────────────────────────────────
    session_seq = st.session_state.get(SK.ACTIVE_SEQ, '')
    session_seq, _ = clean_dna(session_seq) if session_seq else ('', [])

    source_mode = st.radio(
        "Sequence source",
        ["Use active design sequence", "Manual fragment entry"],
        horizontal=True,
        key="gib_src_mode",
    )

    # ── 2. Parameters ─────────────────────────────────────────────
    col_ov, col_n = st.columns(2)
    overlap = col_ov.slider("Homology arm length (bp)", 15, 40, 20, key="gib_ov")
    n_frags = int(col_n.number_input(
        "Fragment count", min_value=2, max_value=8, value=3, step=1, key="gib_n"
    ))

    # ── 3. Fragment input ─────────────────────────────────────────
    parts_seqs: list[str] = []
    parts_names: list[str] = []

    if source_mode == "Use active design sequence":
        if not session_seq or len(session_seq) < 40:
            st.warning(
                "No usable active construct sequence was found. "
                "Design or load a sequence first, or switch to manual fragment entry."
            )
            return

        st.info(
            f"Active construct detected: **{len(session_seq)} bp**. "
            f"It will be partitioned into **{n_frags}** linear fragments for Gibson review."
        )

        frag_len = len(session_seq) // n_frags
        for i in range(n_frags):
            start = i * frag_len
            end = start + frag_len if i < n_frags - 1 else len(session_seq)
            parts_seqs.append(session_seq[start:end])
            parts_names.append(f"Fragment_{i + 1}")

        st.markdown("**Fragment labels** (optional)")
        rename_cols = st.columns(min(n_frags, 4))
        for i in range(n_frags):
            col = rename_cols[i % 4]
            parts_names[i] = col.text_input(
                f"Fragment {i + 1}", value=parts_names[i], key=f"gib_pname_{i}"
            )

    else:
        for i in range(n_frags):
            ca, cb = st.columns([1, 3])
            nm = ca.text_input(
                f"Fragment {i + 1} name", value=f"Fragment_{i + 1}", key=f"gib_nm_{i}"
            )
            raw = cb.text_area(
                f"Fragment {i + 1} sequence", height=68,
                placeholder="ATGCATGC...", key=f"gib_sq_{i}"
            ).upper().strip()
            sq, _ = clean_dna(raw) if raw else ('', [])
            parts_seqs.append(sq)
            parts_names.append(nm)

    fragment_summary = _format_fragment_summary(parts_names, parts_seqs)
    _render_validation_summary(
        "Gibson input summary",
        [
            f"Filled fragments: {fragment_summary['filled_count']} of {n_frags}",
            f"Empty inputs: {fragment_summary['empty_count']}",
            f"Current order: {fragment_summary['order_text']}",
            f"Entered DNA total: {fragment_summary['total_bp']} bp",
            f"Requested overlap per junction: {overlap} bp",
        ],
    )
    _render_fragment_validation_table(
        "Fragment validation",
        parts_names,
        parts_seqs,
        [],
    )
    _render_gibson_fragment_review(parts_names, parts_seqs, overlap)

    # ── 4. Run primer design ──────────────────────────────────────
    st.divider()
    if st.button(
        "Design Gibson assembly primers",
        type="primary",
        use_container_width=True,
        key="btn_gib",
    ):
        valid_seqs = [s for s in parts_seqs if s and len(s) >= 20]
        if len(valid_seqs) < 2:
            st.error(
                "At least 2 fragments with length ≥ 20 bp are required. "
                "Please review the fragment inputs."
            )
            return

        ok, warns = _validate_assembly(parts_seqs)
        if warns:
            _render_validation_summary(
                "Input review warning",
                warns,
                tone='warning',
            )

        try:
            builder = ConstructBuilder()
            bio_parts = [
                BioPart(name=nm, part_type="CDS", sequence=sq)
                for nm, sq in zip(parts_names, parts_seqs)
                if sq and len(sq) >= 20
            ]
            construct_result = builder.build_linear_construct(bio_parts)
        except Exception as exc:
            st.error(f"Failed to build Gibson construct: {exc}")
            return

        planner = AssemblyPlanner()
        plan = planner.plan_gibson_assembly(construct_result, overlap_len=overlap)

        if not plan.get("primers"):
            reason = plan.get('reason') or 'AssemblyPlanner did not return primer rows.'
            st.error(reason)
            return

        df_primers = _enrich_planner_primers(plan["primers"], overlap)
        total_len = construct_result["total_length"]
        planner_warnings = plan.get('warnings') or []

        log_build_activity(
            f"Gibson Assembly: {len(bio_parts)} fragments",
            f"{overlap} bp overlap · {total_len} bp construct",
        )

        st.markdown("##### Preview summary")
        st.markdown(
            f"<div style='"
            f"background:#f0fdf4;border:1px solid #86efac;"
            f"border-radius:8px;padding:14px 18px;margin:10px 0;"
            f"font-family:inherit'>"
            f"<b>Preview generated.</b><br>"
            f"Method: {plan['method']} &nbsp;·&nbsp; "
            f"Fragments: <b>{len(bio_parts)}</b> &nbsp;·&nbsp; "
            f"Homology arm: <b>{overlap} bp</b> &nbsp;·&nbsp; "
            f"Construct length: <b>{total_len} bp</b>"
            f"</div>",
            unsafe_allow_html=True,
        )

        st.markdown("##### Review notes")
        st.caption("No flagged issue" if not planner_warnings else "Flagged for review: review planner notes below.")
        st.markdown("##### Documentation artifact")
        st.caption("Documentation artifact available. Computational preview only; this does not certify cloning, PCR, gel, or expression success.")

        if planner_warnings:
            _render_validation_summary(
                "Planner warnings",
                planner_warnings,
                tone='warning',
            )

        _render_gibson_fragment_review(
            [part.name for part in bio_parts],
            [part.sequence for part in bio_parts],
            overlap,
            plan,
        )

        st.markdown("###### Primer table")
        st.dataframe(
            df_primers,
            use_container_width=True,
            hide_index=True,
            column_config={
                'Fragment': st.column_config.TextColumn('Fragment', width='medium'),
                "Forward Primer (5'→3')": st.column_config.TextColumn("Forward Primer (5'→3')", width='large'),
                'Fwd Length (bp)': st.column_config.NumberColumn('Fwd Length (bp)', format='%d'),
                'Fwd Binding Tm (°C)': st.column_config.NumberColumn('Fwd Binding Tm (°C)', format='%.1f'),
                'Fwd GC (%)': st.column_config.NumberColumn('Fwd GC (%)', format='%.1f'),
                "Reverse Primer (5'→3')": st.column_config.TextColumn("Reverse Primer (5'→3')", width='large'),
                'Rev Length (bp)': st.column_config.NumberColumn('Rev Length (bp)', format='%d'),
                'Rev Binding Tm (°C)': st.column_config.NumberColumn('Rev Binding Tm (°C)', format='%.1f'),
                'Rev GC (%)': st.column_config.NumberColumn('Rev GC (%)', format='%.1f'),
                'Homology Arm (bp)': st.column_config.NumberColumn('Homology Arm (bp)', format='%d'),
            },
        )

        csv_bytes = df_primers.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="Download primer table as CSV",
            data=csv_bytes,
            file_name="gibson_assembly_primers.csv",
            mime="text/csv",
            use_container_width=True,
            key="gib_csv_dl",
        )

        st.caption(
            "Primer-table preview only; use Wizard Step 4, Step 5, and Step 6 for the MVP readiness path."
        )

        assembled_product = _clean_product_sequence(construct_result.get("final_sequence") or "".join(parts_seqs))
        st.session_state['cloning_preview_product'] = assembled_product
        st.session_state['cloning_preview_method'] = 'Gibson Assembly'

        with st.expander("View assembled construct sequence"):
            st.code(assembled_product, language='text')


def render() -> None:
    st.markdown("#### Cloning Preview")
    st.caption(
        "Restriction cloning · Golden Gate Assembly · Gibson Assembly. "
        "These tools create computational previews and documentation artifacts only. "
        "They do not provide wet-lab protocols or certify experimental readiness."
    )
    method = st.selectbox(
        "Cloning strategy",
        ["Restriction Enzyme Cloning", "Golden Gate Assembly", "Gibson Assembly"],
        key="build_clone_method",
    )
    st.divider()
    if method == "Restriction Enzyme Cloning":
        _render_restriction_cloning()
    elif method == "Golden Gate Assembly":
        _render_golden_gate()
    else:
        _render_gibson()
