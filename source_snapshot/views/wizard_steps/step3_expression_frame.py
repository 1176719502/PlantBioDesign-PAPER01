# -*- coding: utf-8 -*-
"""
views/wizard_steps/step3_expression_frame.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Step 3 -- Codon Usage Preview & Assembly.

User-facing identity: codon usage preview for the selected host and
expression-frame preview (promoter + RBS + CDS + terminator). The
assembled frame and review metrics are the primary outputs of this step.
"""
from __future__ import annotations

import streamlit as st

from core.codon_candidate_draft import (
    CODON_CANDIDATE_DRAFT_STATUS,
    build_codon_candidate_draft,
)
from core.expression_frame_builder import build_step3_fidelity_summary
from core.session_keys import SK
from views.wizard_steps._shared import (
    _cassette,
    _gc,
    _section_label,
    _status_panel,
    _step_header,
    render_flow_strip,
)


# ---------------------------------------------------------------------------
# Host preview helpers
# ---------------------------------------------------------------------------


def _optimizer_host(host: str) -> str:
    """Resolve wizard host to codon preview host key."""
    try:
        from core.expression_frame_builder import get_host_rules

        rules = get_host_rules(host)
        return rules.get("codon_table_key") or "E.coli"
    except Exception:
        return "E.coli"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seq_summary_row(
    label: str,
    seq: str,
    col,
    highlight: bool = False,
) -> None:
    """Render a compact sequence summary card into a Streamlit column."""
    length = len(seq)
    gc = _gc(seq)
    border = "#2563eb" if highlight else "#e5e7eb"
    bg = "#eff6ff" if highlight else "#f8f9fb"
    col.markdown(
        f"""
        <div style='
            background:{bg};
            border:1px solid {border};
            border-radius:8px;
            padding:12px 16px;
            margin-bottom:4px;
        '>
            <div style='font-size:.70rem;font-weight:700;color:#6b7280;
                        text-transform:uppercase;letter-spacing:.6px;
                        margin-bottom:6px'>{label}</div>
            <div style='display:flex;gap:24px;align-items:baseline'>
                <span style='font-size:1.15rem;font-weight:700;
                             font-family:IBM Plex Mono,monospace;
                             color:#111827'>{length:,} bp</span>
                <span style='font-size:.82rem;color:#374151;
                             font-family:IBM Plex Mono,monospace'>
                    GC {gc:.1f}%
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _delta_badge(orig_len: int, opt_len: int) -> None:
    """Show a small inline delta between original and preview CDS lengths."""
    if not orig_len:
        return
    delta = opt_len - orig_len
    pct = delta / orig_len * 100
    sign = "+" if delta >= 0 else ""
    color = "#16a34a" if delta == 0 else "#d97706"
    st.markdown(
        f"<span style='font-size:.78rem;color:{color};font-weight:600;'>"
        f"Length delta: {sign}{delta} bp ({sign}{pct:.1f}%)"
        f"</span>",
        unsafe_allow_html=True,
    )


# Part-type annotation strings shown below the cassette diagram
_PART_ANNOTATIONS: dict[str, str] = {
    "promoter": "Promoter: recruits RNA polymerase to initiate transcription and largely sets the upper bound for mRNA output.",
    "RBS": "Ribosome binding site (RBS / Shine-Dalgarno): helps the ribosome recognize the start codon and tune translation-initiation efficiency.",
    "Kozak": "Kozak sequence: provides the eukaryotic sequence context required for start-codon recognition during ribosome scanning.",
    "CDS": "Coding sequence (CDS): the current target gene sequence that encodes the full amino-acid sequence of the protein of interest.",
    "tag": "Purification tag: a fusion tag appended to the protein terminus for affinity purification or detection workflows.",
    "terminator": "Terminator: stops transcription, stabilizes the mRNA 3' end, and reduces read-through into downstream regions.",
}


CODON_STATUS_READBACK_COPY = (
    "Codon status is recorded for documentation review only. "
    "This step shows codon usage preview context, metrics/readiness check status, "
    "original/preview CDS readback, host context, and review cues; the original CDS is preserved. "
    "The preview CDS is not a generated optimized sequence, and this step does not create a synonymous "
    "recoding candidate automatically. It does not automatically optimize expression, choose a best sequence, "
    "predict yield, guarantee expression, or replace expert/company review."
)

CODON_CANDIDATE_DRAFT_BOUNDARY_COPY = (
    "This candidate is a computational synonymous recoding draft for documentation review only. "
    "It is not a biological recommendation, not experimentally validated, not optimization proof, "
    "and not build-ready."
)


def _clear_step3_candidate_state_all() -> None:
    st.session_state.pop(SK.CODON_STEP3_CANDIDATE_BRIDGE, None)
    st.session_state.pop(SK.CODON_STEP3_SELECTED_CANDIDATE, None)


def _clear_step3_candidate_draft_preview_state() -> None:
    st.session_state.pop(SK.CODON_STEP3_CANDIDATE_DRAFT_PREVIEW, None)


def _codon_status_readback_rows(ds, host_context: str) -> list[tuple[str, str]]:
    codon_report = ds.codon_report if isinstance(ds.codon_report, dict) else {}
    has_preview = bool(ds.optimized_seq)
    changed = bool(codon_report.get("changed"))
    preview_provider = "Standalone Codon Usage Preview candidate" if codon_report.get("step3_candidate_applied") else "Step 3 local Codon Usage Preview"
    return [
        ("Original CDS source", "Step 1 confirmed CDS"),
        ("Original CDS preservation", "Preserved; Step 3 records preview/readback separately"),
        ("Preview CDS status", "External review draft applied; optimization not claimed" if changed else "Original CDS readback only; no generated optimized sequence"),
        ("Preview sequence provider", preview_provider if has_preview else "Not generated yet"),
        ("Synonymous recoding draft status", "Separate page-session draft preview only after explicit user action"),
        ("Target expression system / host context for review", host_context or "Not recorded"),
        ("Sequence verification status", "Documentation checks only; not experimental validation"),
        ("Manual/company review cue", "Required before downstream biological decisions"),
    ]


def _format_candidate_gc(value) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}%"
    return "Not available"


def _render_metric(target, label: str, value: str) -> None:
    metric = getattr(target, "metric", None)
    if callable(metric):
        metric(label, value)
    else:
        st.metric(label, value)


def _render_codon_candidate_draft_preview(candidate_draft: dict, show_dismiss: bool = True) -> None:
    """Render an explicit page-session codon candidate draft preview."""
    metrics = candidate_draft.get("metrics") if isinstance(candidate_draft.get("metrics"), dict) else {}
    validation = candidate_draft.get("validation") if isinstance(candidate_draft.get("validation"), dict) else {}
    errors = [str(error) for error in (candidate_draft.get("errors") or []) if str(error)]
    warnings = [str(warning) for warning in (candidate_draft.get("warnings") or []) if str(warning)]
    review_flags = [str(flag) for flag in (validation.get("review_flags") or []) if str(flag)]
    candidate_sequence = str(candidate_draft.get("candidate_sequence") or "")
    has_candidate = candidate_draft.get("status") == CODON_CANDIDATE_DRAFT_STATUS and bool(candidate_sequence)

    st.markdown("### Codon candidate draft review")
    st.caption(CODON_CANDIDATE_DRAFT_BOUNDARY_COPY)
    st.info("Codon candidate draft available for page-session review." if has_candidate else "Codon candidate draft was not created.")

    first_row = st.columns(4)
    _render_metric(first_row[0], "Original length", f"{metrics.get('original_length', 0):,} bp")
    _render_metric(first_row[1], "Candidate length", f"{metrics.get('candidate_length', 0):,} bp")
    _render_metric(first_row[2], "Original GC%", _format_candidate_gc(metrics.get("original_gc_percent")))
    _render_metric(first_row[3], "Candidate GC%", _format_candidate_gc(metrics.get("candidate_gc_percent")))

    second_row = st.columns(4)
    _render_metric(second_row[0], "Original rare codon count", str(metrics.get("original_rare_codon_count", 0)))
    _render_metric(second_row[1], "Candidate rare codon count", str(metrics.get("candidate_rare_codon_count", 0)))
    _render_metric(second_row[2], "Original rare codon clusters", str(metrics.get("original_rare_codon_clusters", 0)))
    _render_metric(second_row[3], "Candidate rare codon clusters", str(metrics.get("candidate_rare_codon_clusters", 0)))

    status_row = st.columns(2)
    _render_metric(
        status_row[0],
        "Translation preserved status",
        "Preserved" if metrics.get("translation_preserved") else "Needs review",
    )
    _render_metric(
        status_row[1],
        "Validation/review flags",
        ", ".join(review_flags) if review_flags else "No review flags recorded",
    )

    if errors:
        st.warning("Review flags/messages: " + "; ".join(errors))
    if warnings:
        st.caption("Candidate draft notes: " + "; ".join(warnings))

    if has_candidate:
        with st.expander("Review codon candidate draft sequence", expanded=False):
            st.code(candidate_sequence, language="text")

    if show_dismiss and st.button("Dismiss codon candidate draft", key="wf_p3_dismiss_candidate_draft"):
        _clear_step3_candidate_draft_preview_state()
        st.rerun()


def _render_codon_status_readback(ds, host_context: str) -> None:
    st.markdown("### Codon status readback")
    st.caption(CODON_STATUS_READBACK_COPY)
    for label, value in _codon_status_readback_rows(ds, host_context):
        c1, c2 = st.columns([1, 2])
        c1.markdown(
            f"<div style='font-size:.82rem;color:#6b7280;padding:4px 0'>{label}</div>",
            unsafe_allow_html=True,
        )
        c2.markdown(
            f"<div style='font-size:.82rem;font-weight:500;color:#111827;padding:4px 0'>{value}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='border-top:1px solid #f3f4f6;margin:0'></div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def page(ctrl) -> None:
    """Render Step 3 -- Codon Usage Preview & Assembly."""
    ds = ctrl.get()
    stale_state = ds.invalidate_stale_workflow_outputs()
    if any(stale_state.values()):
        ctrl.save(ds)

    _step_header(
        3,
        "Codon Usage Preview & Expression Frame",
        "Preview read-only sequence/codon metrics and the expression frame from the confirmed plant or host context. Step 3 is metrics/readback only, not automatic optimization.",
        [
            "Review the input CDS and current host context.",
            "Plant MVP context: read-only sequence and codon metrics; no sequence optimization output.",
            "Primary action: preview codon metrics and the expression frame.",
            "The original CDS is preserved; the preview CDS is not a generated optimized sequence.",
            "The result includes frame length, GC content, cassette structure, the full assembled sequence, codon status readback, and documentation-only review cues.",
            "Computational synonymous recoding candidates will be handled separately as review drafts when enabled.",
        ],
    )

    orig = ds.original_seq
    opt = ds.optimized_seq
    codon_report = ds.codon_report if isinstance(ds.codon_report, dict) else {}
    has_host = bool(ds.host)
    has_frame = isinstance(ds.frame, dict) and ds.frame.get("success")

    _section_label("Input overview")
    render_flow_strip(
        [
            ("Input", "Confirmed CDS plus host, tag, and regulatory context"),
            ("Output", "Assembled expression frame for primer and export review"),
        ]
    )
    col_orig, col_opt = st.columns(2)

    if orig:
        _seq_summary_row("Original CDS (from Step 1)", orig, col_orig)
    else:
        col_orig.info("No sequence is available yet. Return to Step 1 first.")

    if opt and opt != orig:
        _seq_summary_row("Preview CDS", opt, col_opt, highlight=True)
        _delta_badge(len(orig), len(opt))
    elif opt and opt == orig:
        _status_panel(
            "Original CDS preserved in preview",
            "The preview CDS currently matches the input sequence. Step 3 has not generated a synonymous recoding candidate.",
            tone="info",
        )
    else:
        _status_panel(
            "Waiting for build output",
            "After you run the metrics preview, the CDS readback appears here. It is not a generated optimized sequence.",
            tone="info",
        )

    # Phase 2A-2: transient codon preview candidate panel.
    # Selection is explicit and does not write formal Step 3 fields.
    codon_candidate = st.session_state.get(SK.CODON_STEP3_CANDIDATE_BRIDGE)
    candidate_selected = st.session_state.get(SK.CODON_STEP3_SELECTED_CANDIDATE)
    if not isinstance(codon_candidate, dict):
        if isinstance(candidate_selected, dict) and candidate_selected.get("candidate_seq"):
            selected_candidate_host = str(candidate_selected.get("optimizer_host") or "")
            expected_optimizer_host = _optimizer_host(ds.host) if getattr(ds, "host", "") else ""
            if selected_candidate_host and expected_optimizer_host and selected_candidate_host != expected_optimizer_host:
                st.session_state.pop(SK.CODON_STEP3_SELECTED_CANDIDATE, None)
                st.error("Selected external draft host no longer matches the current Step 3 host context.")
                return
        st.session_state.pop(SK.CODON_STEP3_SELECTED_CANDIDATE, None)
        candidate_selected = None

    if isinstance(codon_candidate, dict) and codon_candidate.get("candidate_seq"):
        candidate_host = str(codon_candidate.get("optimizer_host") or "")
        expected_optimizer_host = _optimizer_host(ds.host) if getattr(ds, "host", "") else ""
        host_compatible = bool(
            candidate_host
            and expected_optimizer_host
            and candidate_host == expected_optimizer_host
        )

        if host_compatible:
            st.info("External review draft available")
            st.caption(
                "Draft source: Codon Usage Preview. This external draft has not been applied yet. "
                "Step 3 itself does not generate synonymous recoding candidates in this batch. "
                "Select it only if you want to use it for the next manual Step 3 expression-frame preview."
            )
        else:
            st.warning("External draft host mismatch")
            st.caption(
                "This external draft cannot be used for the current Step 2 host context."
            )

        col_candidate_host, col_expected_host, col_length, col_gc = st.columns(4)
        col_candidate_host.metric("Draft host", candidate_host or "Unknown")
        col_expected_host.metric("Expected Step 3 host", expected_optimizer_host or "Unknown")
        col_length.metric(
            "Draft length",
            codon_candidate.get("sequence_length") or len(codon_candidate.get("candidate_seq", "")),
        )

        gc_percent = codon_candidate.get("gc_percent")
        col_gc.metric(
            "Draft GC",
            f"{gc_percent:.1f}%" if isinstance(gc_percent, (int, float)) else "Not available",
        )

        cai_before = codon_candidate.get("cai_before")
        cai_after = codon_candidate.get("cai_after")
        if cai_before is not None or cai_after is not None:
            st.caption(
                f"Preview metric before: {cai_before if cai_before is not None else 'Not available'} | "
                f"Preview metric after: {cai_after if cai_after is not None else 'Not available'}"
            )

        warnings = codon_candidate.get("warnings") or []
        if warnings:
            st.caption("External draft warnings: " + "; ".join(str(w) for w in warnings))

        if host_compatible:
            if st.button(
                "Use external draft for expression-frame preview",
                key="wf_p3_use_candidate_for_build",
            ):
                current_expected_host = _optimizer_host(ds.host) if getattr(ds, "host", "") else ""
                current_candidate_host = str(codon_candidate.get("optimizer_host") or "")
                if current_candidate_host and current_candidate_host == current_expected_host:
                    st.session_state[SK.CODON_STEP3_SELECTED_CANDIDATE] = dict(codon_candidate)
                    st.success("External draft selected for next Step 3 expression-frame preview")
                else:
                    st.session_state.pop(SK.CODON_STEP3_SELECTED_CANDIDATE, None)
                    st.warning("External draft host no longer matches the current Step 3 host context.")

        selected_candidate = candidate_selected
        if isinstance(selected_candidate, dict) and selected_candidate.get("candidate_seq"):
            st.success(
                "External draft selected for the next Step 3 expression-frame preview. "
                "Click Preview codon metrics and expression frame to update the frame readback."
            )

        if st.button("Dismiss external draft", key="wf_p3_dismiss_candidate_mismatch"):
            _clear_step3_candidate_state_all()
            st.rerun()

    st.divider()
    _section_label("Primary action")
    if has_host:
        _status_panel(
            "Build context recorded for review",
            f"Target host: {ds.host}" + (f" | Tag: {ds.tag}" if ds.tag else ""),
            tone="ready",
        )
    else:
        _status_panel(
            "Host information is missing",
            "Complete host and regulatory-element selection in Step 2 first.",
            tone="warn",
        )

    st.caption(
        "Primary action: preview codon metrics and expression frame. Original CDS is preserved; "
        "no synonymous recoding candidate is generated unless you explicitly preview the separate draft below."
    )

    candidate_draft_generated_now = False
    if st.button(
        "Preview computational codon candidate draft",
        key="wf_p3_generate_candidate_draft",
        help=(
            "Creates a page-session documentation review draft only. "
            "It does not replace the original CDS, change saved records, or route to Step 4."
        ),
        use_container_width=True,
    ):
        with st.spinner("Generating codon candidate draft for documentation review..."):
            st.session_state[SK.CODON_STEP3_CANDIDATE_DRAFT_PREVIEW] = build_codon_candidate_draft(
                raw_cds=ds.original_seq,
                table_key=_optimizer_host(ds.host) if has_host else "E.coli",
            )
            candidate_draft_generated_now = True

    candidate_draft_preview = st.session_state.get(SK.CODON_STEP3_CANDIDATE_DRAFT_PREVIEW)
    if isinstance(candidate_draft_preview, dict):
        _render_codon_candidate_draft_preview(
            candidate_draft_preview,
            show_dismiss=not candidate_draft_generated_now,
        )

    if st.button(
        "Preview codon metrics and expression frame",
        type="primary",
        key="wf_p3_build",
        use_container_width=True,
        disabled=not bool(orig and has_host),
    ):
        try:
            from core.codon_optimizer import optimize_cds_sequence
            from core.expression_frame_builder import build_expression_frame

            optimizer_host = _optimizer_host(ds.host)
            selected_candidate = st.session_state.get(SK.CODON_STEP3_SELECTED_CANDIDATE)
            use_selected_candidate = False
            selected_codon_report: dict = {}

            if selected_candidate is not None:
                selected_candidate_seq = ""
                selected_candidate_host = ""
                if isinstance(selected_candidate, dict):
                    selected_candidate_seq = str(selected_candidate.get("candidate_seq") or "").strip()
                    selected_candidate_host = str(selected_candidate.get("optimizer_host") or "")

                if not isinstance(selected_candidate, dict) or not selected_candidate_seq:
                    _clear_step3_candidate_state_all()
                    st.warning("Selected external draft is no longer valid. Please select a matching Step 3 draft again.")
                    return

                if selected_candidate_host != optimizer_host:
                    _clear_step3_candidate_state_all()
                    st.warning("Selected external draft host no longer matches the current Step 3 host context.")
                    return

                use_selected_candidate = True
                optimized_cds = selected_candidate_seq
                candidate_report = selected_candidate.get("codon_report")
                selected_codon_report = dict(candidate_report) if isinstance(candidate_report, dict) else {}
                selected_codon_report["source"] = "codon_optimizer_candidate"
                selected_codon_report["step3_candidate_applied"] = True
                selected_codon_report["origin_page"] = selected_candidate.get("origin_page")
                selected_codon_report.setdefault("success", True)
                selected_codon_report.setdefault("warnings", selected_candidate.get("warnings") or [])

            with st.spinner("Running codon metrics/readback preview and expression-frame assembly..."):
                if not use_selected_candidate:
                    optimization_result = optimize_cds_sequence(
                        sequence=ds.original_seq,
                        host=optimizer_host,
                    )

                    if not optimization_result.get("success"):
                        ds.codon_report = optimization_result
                        ds.frame = {}
                        ds.frame_context_signature = ""
                        ctrl.save(ds)
                        st.error(f"Codon metrics preview failed: {'; '.join(optimization_result.get('errors') or ['Unknown error'])}")
                        return

                    optimized_cds = optimization_result.get("optimized_sequence") or ds.original_seq
                    ds.codon_report = optimization_result
                    ds.optimized_seq = optimized_cds

                result = build_expression_frame(
                    gene_seq=optimized_cds,
                    host=ds.host,
                    tag=ds.tag,
                    custom_elements={
                        "promoter_name": ds.elements.get("promoter_name", ""),
                        "promoter_seq": ds.elements.get("promoter_seq", ""),
                        "rbs_name": ds.elements.get("rbs_name", ""),
                        "rbs_seq": ds.elements.get("rbs_seq", ""),
                        "terminator_name": ds.elements.get("terminator_name", ""),
                        "terminator_seq": ds.elements.get("terminator_seq", ""),
                    },
                )

            if use_selected_candidate:
                if result.get("success"):
                    ds.optimized_seq = optimized_cds
                    ds.codon_report = selected_codon_report
                    ds.frame = result
                    ds.frame_context_signature = ds.current_frame_context_signature()
                    resolved_seq = result.get("final_sequence", "") or ds.optimized_seq or ds.original_seq
                    if resolved_seq:
                        st.session_state[SK.ACTIVE_SEQ] = resolved_seq
                    _clear_step3_candidate_state_all()
            else:
                ds.frame = result
                ds.frame_context_signature = ds.current_frame_context_signature() if result.get("success") else ""
                if result.get("success"):
                    resolved_seq = result.get("final_sequence", "") or ds.optimized_seq or ds.original_seq
                    if resolved_seq:
                        st.session_state[SK.ACTIVE_SEQ] = resolved_seq
            ctrl.save(ds)
            if result.get("success"):
                st.success(
                    f"Metrics preview complete. Expression frame readback has a total length of {result.get('total_length', 0):,} bp"
                )
                st.rerun()
            else:
                st.error(f"Assembly failed: {result.get('error', 'Unknown error')}")
        except Exception as exc:
            ds.frame = {}
            ds.frame_context_signature = ""
            ctrl.save(ds)
            st.error(f"Build error: {exc}")

    if codon_report.get("success"):
        before = codon_report.get("before") or {}
        after = codon_report.get("after") or {}
        warning_count = len(codon_report.get("warnings") or [])
        st.markdown("<div style='margin-top:.35rem'></div>", unsafe_allow_html=True)
        s1, s2, s3, s4 = st.columns(4)
        s1.metric(
            "CAI",
            f"{after.get('cai', 0.0):.4f}",
            delta=f"{(after.get('cai', 0.0) - before.get('cai', 0.0)):+.4f}",
        )
        s2.metric(
            "GC",
            f"{after.get('gc_percent', 0.0):.1f}%",
            delta=f"{(after.get('gc_percent', 0.0) - before.get('gc_percent', 0.0)):+.1f}%",
        )
        s3.metric("Codon changes", str(len(codon_report.get('history') or [])))
        s4.metric("Remaining warnings", str(warning_count))
        st.caption(
            "These are codon-usage preview metrics for documentation review and manual review context, "
            "not expression prediction, biological scoring, host compatibility proof, or wet-lab readiness judgment."
        )
        _render_codon_status_readback(ds, _optimizer_host(ds.host) if has_host else "")

    st.divider()
    _section_label("Result")
    if has_frame:
        frame = ds.frame
        _status_panel(
            "Expression-frame preview available for review",
            "You can now review frame metrics and cassette structure, then continue to Cassette / Boundary Review.",
            tone="ready",
        )

        m1, m2, m3 = st.columns(3)
        m1.metric("Frame length", f"{frame.get('total_length', 0):,} bp")
        m2.metric("GC content", f"{frame.get('gc_content', 0):.1f}%")
        cds_len = len(ds.optimized_seq) if ds.optimized_seq else 0
        m3.metric("Preview CDS", f"{cds_len:,} bp")

        fidelity = build_step3_fidelity_summary(
            original_seq=ds.original_seq,
            optimized_seq=ds.optimized_seq,
            frame=frame,
            tag=ds.tag,
        )

        st.markdown("### Translation and integrity checks")
        f1, f2, f3 = st.columns(3)
        f1.metric(
            "Translation consistency",
            "Matched" if fidelity.get("translations_match") else "Mismatch",
        )
        f2.metric(
            "Preview CDS stop codon",
            "Retained" if fidelity.get("optimized_has_stop") else "Missing",
        )
        f3.metric(
            "Framed CDS stop codon",
            "Retained" if fidelity.get("framed_cds_has_stop") else "Missing",
        )
        st.markdown(
            f"- **Original CDS:** {fidelity.get('original_cds_length', 0):,} bp\n"
            f"- **Preview CDS:** {fidelity.get('optimized_cds_length', 0):,} bp "
            f"({fidelity.get('optimization_delta_bp', 0):+d} bp from codon metrics/readback preview)\n"
            f"- **Framed CDS:** {fidelity.get('framed_cds_length', 0):,} bp "
            f"({fidelity.get('cds_assembly_delta_bp', 0):+d} bp from expression-frame assembly)\n"
            f"- **Full expression frame:** {fidelity.get('full_frame_length', 0):,} bp "
            f"({fidelity.get('frame_context_delta_bp', 0):+d} bp from promoter/RBS/Kozak/terminator context)"
        )
        st.caption(fidelity.get("length_change_reason_summary", ""))
        if fidelity.get("tag_applied") and fidelity.get("tag_applied") != "No tag":
            st.info(
                f"Selected tag: {fidelity.get('tag_applied')}. "
                "Any CDS length increase during assembly comes from tag/linker fusion rather than the codon usage preview."
            )

        # --- Compact construct summary strip ---
        _aa_count = cds_len // 3 if cds_len else 0
        _vector = frame.get("vector_suggestion") or "—"
        _tag_used = ds.tag or "No tag"
        _kingdom = str(frame.get("host_context", {}).get("kingdom") or ds.host or "")
        _kingdom_label = {
            "prokaryote": "Prokaryotic system",
            "plant_delivery": "Plant delivery",
            "plant_monocot": "Monocot plant",
            "plant_dicot": "Dicot plant",
            "yeast": "Yeast",
            "mammalian": "Mammalian",
        }.get(_kingdom, _kingdom or "—")
        st.markdown(
            f"""
            <div style='display:flex;flex-wrap:wrap;gap:10px;margin:10px 0 6px 0'>
                <div style='background:#f8f9fb;border:1px solid #e2e6ef;border-radius:8px;
                            padding:8px 14px;min-width:90px'>
                    <div style='font-size:.62rem;font-weight:700;color:#64748b;
                                text-transform:uppercase;letter-spacing:.5px'>Protein length (aa)</div>
                    <div style='font-size:.95rem;font-weight:700;color:#2563eb;
                                font-family:IBM Plex Mono,monospace;margin-top:2px'>{_aa_count:,} aa</div>
                </div>
                <div style='background:#f8f9fb;border:1px solid #e2e6ef;border-radius:8px;
                            padding:8px 14px;min-width:90px'>
                    <div style='font-size:.62rem;font-weight:700;color:#64748b;
                                text-transform:uppercase;letter-spacing:.5px'>Vector suggestion</div>
                    <div style='font-size:.90rem;font-weight:700;color:#2563eb;
                                font-family:IBM Plex Mono,monospace;margin-top:2px'>{_vector}</div>
                </div>
                <div style='background:#f8f9fb;border:1px solid #e2e6ef;border-radius:8px;
                            padding:8px 14px;min-width:90px'>
                    <div style='font-size:.62rem;font-weight:700;color:#64748b;
                                text-transform:uppercase;letter-spacing:.5px'>Purification tag</div>
                    <div style='font-size:.90rem;font-weight:700;color:#2563eb;
                                font-family:IBM Plex Mono,monospace;margin-top:2px'>{_tag_used}</div>
                </div>
                <div style='background:#f8f9fb;border:1px solid #e2e6ef;border-radius:8px;
                            padding:8px 14px;min-width:90px'>
                    <div style='font-size:.62rem;font-weight:700;color:#64748b;
                                text-transform:uppercase;letter-spacing:.5px'>Expression system</div>
                    <div style='font-size:.90rem;font-weight:700;color:#2563eb;
                                font-family:IBM Plex Mono,monospace;margin-top:2px'>{_kingdom_label}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        parts = frame.get("parts", [])
        if parts:
            st.caption("Expression-frame structure")
            _cassette(parts)

            # --- Per-part annotations ---
            _seen_types: set[str] = set()
            _annotation_lines: list[str] = []
            for _p in parts:
                _ptype = str(_p.get("type", "")).lower()
                # Normalise tag part type (frame builder uses 'tag' or part name)
                _lookup_key = _ptype
                if _ptype not in _PART_ANNOTATIONS:
                    # Fall back: check if name contains 'tag'
                    if "tag" in str(_p.get("name", "")).lower():
                        _lookup_key = "tag"
                if _lookup_key not in _seen_types and _lookup_key in _PART_ANNOTATIONS:
                    _annotation_lines.append(
                        f"**{_p.get('name', _ptype)}** — {_PART_ANNOTATIONS[_lookup_key]}"
                    )
                    _seen_types.add(_lookup_key)
            if _annotation_lines:
                with st.expander("View element-function notes", expanded=False):
                    for _line in _annotation_lines:
                        st.markdown(f"- {_line}")

        seq = frame.get("final_sequence", "")
        if seq:
            with st.expander("View full assembled sequence"):
                st.code(seq[:600] + ("..." if len(seq) > 600 else ""), language="text")
    else:
        _status_panel(
            "No expression-frame preview yet",
            "After you click the primary action button above, this area shows the complete construct structure and sequence for documentation-only review.",
            tone="info",
        )
