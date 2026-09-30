# -*- coding: utf-8 -*-
"""
views/wizard_steps/step4_cloning_primers.py
Step 4 -- Cassette / Boundary Review.

Primer candidate generation remains an optional/future capability when the
backend is available; the main page is documentation-only frame review.
"""
from __future__ import annotations

import time

import streamlit as st

from core.session_keys import SK
from services.async_status_presenter import build_async_status_presenter
from services.primer_api_client import get_primer_design_task
from services.primer_service import (
    design_primers_if_available as design_outer_primers_for_cassette,
    get_primer3_backend_status,
)
from services.async_task_service import (
    handle_task_active_poll_state,
    handle_task_exception_state,
    handle_task_non_polling_state,
    handle_task_poll_update,
    handle_task_terminal_error_state,
)
from services.assembly_plan_summary_service import build_assembly_plan_summary
from services.task_polling_service import (
    build_task_detail,
    initialize_task_state,
    reset_task_runtime_state,
    should_poll_task,
)
from services.wizard_task_context_guard import (
    build_stale_primer_task_message,
    should_apply_task_result,
)
from views.wizard_steps._shared import (
    _cassette,
    _section_label,
    _status_panel,
    _step_header,
    render_flow_strip,
    render_async_task_feedback,
    render_report_download_button,
    render_report_preview_container,
)

# ---------------------------------------------------------------------------
# Sequence utilities -- delegated to service layer
# ---------------------------------------------------------------------------
try:
    from services.sequence_service import seq_hash as _seq_hash
    from services.sequence_service import primer_gc as _primer_gc
except ImportError:
    import hashlib

    def _seq_hash(seq: str) -> str:  # type: ignore[misc]
        return hashlib.sha256(seq.encode()).hexdigest() if seq else ""

    def _primer_gc(seq: str) -> float:  # type: ignore[misc]
        if not seq:
            return 0.0
        s = seq.upper()
        gc = s.count("G") + s.count("C")
        atcg = sum(s.count(b) for b in "ATCG")
        return gc / atcg * 100 if atcg else 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _initialize_primer_task_state() -> None:
    initialize_task_state(
        "primer_task",
        defaults={
            "id": "",
            "status": "idle",
            "result": None,
            "error": "",
            "poll_enabled": False,
            "last_polled_at": 0.0,
            "poll_count": 0,
            "context_signature": "",
        },
    )


_PRIMER_TASK_PROGRESS = {
    "idle": 0,
    "queued": 15,
    "deferred": 30,
    "started": 65,
    "finished": 100,
    "failed": 100,
    "not_found": 100,
    "unknown": 5,
}


_PRIMER_TASK_DETAIL = {
    "idle": "No async primer design task is running.",
    "queued": "Primer design has been queued and will be polled automatically.",
    "deferred": "Primer design is waiting for a worker slot and will be polled automatically.",
    "started": "Primer design is running. This panel refreshes automatically until results are available for review.",
    "finished": "Primer design is complete. The page refreshes automatically and displays the latest result.",
    "failed": "Primer design failed. Review the error details below before retrying.",
    "not_found": "The async primer task could not be found. Submit a new task if needed.",
    "unknown": "Primer design task status is being checked.",
}


def _reset_primer_task_runtime_state() -> None:
    reset_task_runtime_state("primer_task")


def _clear_primer_task_state_all() -> None:
    st.session_state["primer_task_id"] = ""
    st.session_state["primer_task_status"] = "idle"
    st.session_state["primer_task_result"] = None
    st.session_state["primer_task_error"] = ""
    st.session_state["primer_task_poll_count"] = 0
    st.session_state[SK.PRIMER_TASK_CONTEXT_SIGNATURE] = ""
    _reset_primer_task_runtime_state()


def _column_aware_button(column, *args, **kwargs) -> bool:
    """Use column buttons normally, but fall back to patched global buttons in tests."""
    column_module = getattr(type(column), "__module__", "")
    global_button_module = getattr(st.button, "__module__", "")
    if str(column_module).startswith("streamlit") and not str(global_button_module).startswith("streamlit"):
        return st.button(*args, **kwargs)
    return column.button(*args, **kwargs)


def _schedule_async_refresh(delay_seconds: float = 1.5) -> None:
    time.sleep(delay_seconds)
    st.rerun()


def _is_finished_primer_result_payload(result_payload: dict | None) -> bool:
    payload = result_payload if isinstance(result_payload, dict) else {}
    results = payload.get("results")
    return isinstance(results, list)


def _primer_poll_interval_seconds(poll_count: int) -> float:
    if poll_count < 3:
        return 1.0
    if poll_count < 8:
        return 1.5
    return 2.0


def _primer_task_progress(status: str) -> int:
    return _PRIMER_TASK_PROGRESS.get(str(status or "unknown").strip().lower(), _PRIMER_TASK_PROGRESS["unknown"])


def _primer_task_detail(status: str, poll_count: int) -> str:
    return build_task_detail(status, poll_count, _PRIMER_TASK_DETAIL, {"queued", "deferred", "started"})


def _refresh_primer_task_status(ds, ctrl, upstream_host: str, upstream_seq_hash: str) -> None:
    task_id = str(st.session_state.get("primer_task_id") or "").strip()
    if not task_id:
        _reset_primer_task_runtime_state()
        return

    try:
        task_response = get_primer_design_task(task_id)
        task_status, task_result, task_error = _normalize_primer_task_payload(task_response)
        handle_task_poll_update(
            "primer_task",
            status=task_status,
            now=time.time(),
        )

        if task_status in {"queued", "started", "deferred"}:
            handle_task_active_poll_state("primer_task")
        elif task_status == "finished":
            if not _is_finished_primer_result_payload(task_result):
                handle_task_terminal_error_state(
                    "primer_task",
                    status="failed",
                    error_text="Async primer design finished, but the result payload is missing the expected 'results' list.",
                )
                return
            st.session_state["primer_task_result"] = task_result
            st.session_state["primer_task_error"] = ""
            primer_count = _apply_finished_primer_task_result(
                ds,
                ctrl,
                task_result,
                upstream_host,
                upstream_seq_hash,
            )
            if primer_count:
                st.success(f"Async primer design results are available for review with {primer_count} primer pair(s).")
            else:
                st.warning("Async primer design finished, but no reusable primer rows were produced.")
        elif task_status in {"failed", "not_found"}:
            handle_task_terminal_error_state(
                "primer_task",
                status=task_status,
                error_text=task_error or f"Async primer design task returned status: {task_status}.",
            )
        else:
            handle_task_non_polling_state("primer_task", result=task_result, error_text=task_error)
    except Exception as exc:
        handle_task_exception_state("primer_task", error=exc)


def _poll_primer_task_if_needed(ds, ctrl, upstream_host: str, upstream_seq_hash: str) -> None:
    poll_count = int(st.session_state.get("primer_task_poll_count") or 0)
    if not should_poll_task(
        "primer_task",
        active_statuses={"queued", "started", "deferred"},
        now=time.time(),
        min_interval_seconds=_primer_poll_interval_seconds(poll_count),
    ):
        return

    _refresh_primer_task_status(ds, ctrl, upstream_host, upstream_seq_hash)


def _frame_summary_card(frame: dict, optimized_seq: str) -> None:
    total = frame.get("total_length", 0)
    gc = frame.get("gc_content", 0.0)
    vector = frame.get("vector_suggestion", "")
    cds_len = len(optimized_seq) if optimized_seq else 0
    cols = st.columns(4)
    cols[0].metric("Frame length", f"{total:,} bp")
    cols[1].metric("GC content", f"{gc:.1f}%")
    cols[2].metric("CDS length", f"{cds_len:,} bp")
    cols[3].metric("Vector", vector or "\u2014")
    parts = frame.get("parts", [])
    if parts:
        st.caption("Expression frame structure")
        _cassette(parts)
    seq = frame.get("final_sequence", "")
    if seq:
        with st.expander("View assembled sequence"):
            st.code(seq[:600] + ("..." if len(seq) > 600 else ""), language="text")


def _clear_primer_state(ds, ctrl) -> None:
    ds.cloning_method = "Gibson Assembly"
    ds.clear_step4_outputs()
    ds.cloning_method = "Gibson Assembly"
    ctrl.save(ds)
    for key in (
        "wf_plasmid_png",
        "wf_plasmid_features",
        "wf_plasmid_title",
    ):
        st.session_state.pop(key, None)
    _clear_primer_task_state_all()


def _record_primer_backend_unavailable(ds, ctrl, upstream_host: str, upstream_seq_hash: str, target_tm: float) -> None:
    message = (
        "Outer-primer candidate generation is not enabled in this build. "
        "This step currently supports cassette boundary and documentation review only."
    )
    current_signature = ds.current_primer_context_signature()
    already_recorded = (
        str(getattr(ds, "primer_design_status", "") or "").strip().lower() == "unavailable"
        and getattr(ds, "primer_backend_available", None) is False
        and getattr(ds, "active_primer_pair", None) is None
        and getattr(ds, "primer_context_signature", "") == current_signature
    )
    if already_recorded:
        return

    ds.cloning_method = "Gibson Assembly"
    ds.primers = []
    ds.primer_design_status = "unavailable"
    ds.primer_backend_available = False
    ds.active_primer_pair = None
    ds.primer_context_host = upstream_host
    ds.primer_context_seq_hash = upstream_seq_hash
    ds.primer_context_signature = current_signature
    ds.step4_plan_summary = {
        "design_scope": "expression_cassette",
        "primer_design_status": "unavailable",
        "primer_backend_available": False,
        "active_primer_pair": None,
        "selected_result_index": None,
        "selected_overlap_len": None,
        "selected_target_tm": float(target_tm),
        "tried_combinations": 0,
        "best_plan_summary": message,
        "structured_results": [],
    }
    ds.clear_step5_outputs()
    ctrl.save(ds)


def _hydrate_upstream_context_from_session(ds) -> tuple:
    ctx_host = str(st.session_state.get(SK.ACTIVE_HOST, "") or "").strip()
    ctx_seq = str(st.session_state.get(SK.ACTIVE_SEQ, "") or "").strip().upper()
    if not ctx_host and ds.host:
        ctx_host = str(ds.host).strip()
        st.session_state[SK.ACTIVE_HOST] = ctx_host
    if not ctx_seq:
        frame = ds.frame if isinstance(ds.frame, dict) else {}
        session_seq = (
            frame.get("final_sequence")
            or ds.optimized_seq
            or ds.original_seq
            or ""
        )
        ctx_seq = str(session_seq).strip().upper()
        if ctx_seq:
            st.session_state[SK.ACTIVE_SEQ] = ctx_seq
    return ctx_host, ctx_seq


def _render_primer_quality_summary(primers: list[dict]) -> None:
    if not primers:
        return

    recommended = sum(1 for p in primers if p.get("Quality Grade") == "Recommended")
    risky = sum(1 for p in primers if p.get("Quality Grade") == "Usable with Risk")
    not_recommended = sum(1 for p in primers if p.get("Quality Grade") == "Not Recommended")

    cols = st.columns(3)
    cols[0].metric("Review pairs", recommended)
    cols[1].metric("Risky pairs", risky)
    cols[2].metric("Not recommended pairs", not_recommended)



def _render_primer_table(primers: list[dict]) -> None:
    if not primers:
        return

    rows = []
    for p in primers:
        fwd = p.get("Forward Primer (5'->3')", "")
        rev = p.get("Reverse Primer (5'->3')", "")
        quality_reasons = p.get("Quality Reasons", []) or []
        rows.append({
            "Fragment": p.get("Fragment Name", "-"),
            "Quality grade": p.get("Quality Grade", "—"),
            "Quality summary": " | ".join(quality_reasons) if quality_reasons else "—",
            "Forward primer": fwd,
            "Forward length": len(fwd),
            "Forward GC": f"{_primer_gc(fwd):.1f}%",
            "Forward anneal Tm": p.get("Fwd Anneal Tm (°C)", "-"),
            "Reverse primer": rev,
            "Reverse length": len(rev),
            "Reverse GC": f"{_primer_gc(rev):.1f}%",
            "Reverse anneal Tm": p.get("Rev Anneal Tm (°C)", "-"),
            "Quality warnings": " | ".join(p.get("Warnings", [])) if p.get("Warnings") else "—",
        })

    try:
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except Exception:
        for row in rows:
            st.write(row)


def _stored_step4_plan_summary(ds) -> dict:
    summary = getattr(ds, "step4_plan_summary", None)
    return summary if isinstance(summary, dict) else {}


def build_step4_assembly_plan_summary(ds) -> dict:
    """Return normalized Step 4 assembly-plan display data from DesignSession."""
    return build_assembly_plan_summary(ds)


def _primer_rows_from_structured_results(results: list[dict], selected_index: int = 0) -> list[dict]:
    if not results:
        return []

    safe_index = max(0, min(len(results) - 1, int(selected_index)))
    top_result = results[safe_index] if isinstance(results[safe_index], dict) else {}
    primers = top_result.get("primers") or []
    forward = next((item for item in primers if item.get("role") == "forward"), primers[0] if primers else {})
    reverse = next((item for item in primers if item.get("role") == "reverse"), primers[1] if len(primers) > 1 else {})

    if not isinstance(forward, dict) or not isinstance(reverse, dict):
        return []

    fragment_name = str(top_result.get("name") or "").strip() or "Expression cassette"

    return [{
        "Fragment Name": fragment_name,
        "Forward Primer (5'->3')": str(forward.get("sequence") or ""),
        "Reverse Primer (5'->3')": str(reverse.get("sequence") or ""),
        "Quality Grade": top_result.get("quality_grade") or "—",
        "Quality Reasons": top_result.get("quality_reasons") or [],
        "Fwd Anneal Tm (°C)": forward.get("tm", "-"),
        "Rev Anneal Tm (°C)": reverse.get("tm", "-"),
        "Warnings": top_result.get("pair_warnings") or [],
    }]


def _normalize_structured_results_for_expression_cassette(results: list[dict]) -> list[dict]:
    normalized_results: list[dict] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        normalized_result = dict(result)
        normalized_result["name"] = str(result.get("name") or "").strip() or "Expression cassette"
        normalized_results.append(normalized_result)
    return normalized_results


def _normalize_primer_task_payload(task_payload: dict | None) -> tuple[str, dict | None, str]:
    payload = task_payload if isinstance(task_payload, dict) else {}
    status = str(payload.get("status") or "unknown").strip().lower()
    result = payload.get("result")
    error = payload.get("error")
    if error in (None, ""):
        error = payload.get("message")
    error_text = str(error).strip() if error not in (None, "") else ""
    return status, result if isinstance(result, dict) else None, error_text


def _apply_selected_structured_design(ds, ctrl, selected_index, upstream_host: str, upstream_seq_hash: str) -> int:
    existing_plan = _stored_step4_plan_summary(ds)
    structured_results = existing_plan.get("structured_results") or []
    if not isinstance(structured_results, list) or not structured_results:
        return 0

    safe_index = max(0, min(len(structured_results) - 1, int(selected_index)))
    selected_primer_rows = _primer_rows_from_structured_results(
        structured_results,
        selected_index=safe_index,
    )
    if not selected_primer_rows:
        return 0

    ds.cloning_method = "Gibson Assembly"
    ds.primers = selected_primer_rows
    ds.primer_design_status = "generated"
    ds.primer_backend_available = True
    ds.active_primer_pair = selected_primer_rows[0] if selected_primer_rows else None
    ds.primer_context_host = upstream_host
    ds.primer_context_seq_hash = upstream_seq_hash
    ds.primer_context_signature = ds.current_primer_context_signature()
    ds.step4_plan_summary = {
        **existing_plan,
        "design_scope": existing_plan.get("design_scope") or "expression_cassette",
        "structured_results": structured_results,
        "selected_result_index": safe_index,
    }
    ctrl.save(ds)
    return len(selected_primer_rows)


def _apply_finished_primer_task_result(ds, ctrl, result_payload: dict | None, upstream_host: str, upstream_seq_hash: str) -> int:
    task_signature = st.session_state.get(SK.PRIMER_TASK_CONTEXT_SIGNATURE)
    current_signature = ds.current_primer_context_signature()
    if not should_apply_task_result(task_signature, current_signature):
        st.session_state["primer_task_result"] = None
        st.session_state["primer_task_error"] = build_stale_primer_task_message()
        st.session_state["primer_task_status"] = "idle"
        _reset_primer_task_runtime_state()
        st.warning(build_stale_primer_task_message())
        return 0

    result_payload = result_payload if isinstance(result_payload, dict) else {}
    structured_results = result_payload.get("results") or []
    existing_plan = _stored_step4_plan_summary(ds)

    ds.cloning_method = "Gibson Assembly"
    selected_result_index = result_payload.get("selected_result_index", existing_plan.get("selected_result_index", 0))
    ds.primers = _primer_rows_from_structured_results(
        structured_results if isinstance(structured_results, list) else [],
        selected_index=selected_result_index,
    )
    ds.primer_design_status = "generated" if ds.primers else ""
    ds.primer_backend_available = True
    ds.active_primer_pair = ds.primers[0] if ds.primers else None
    ds.primer_context_host = upstream_host
    ds.primer_context_seq_hash = upstream_seq_hash
    ds.primer_context_signature = current_signature

    structured_results = _normalize_structured_results_for_expression_cassette(
        structured_results if isinstance(structured_results, list) else []
    )

    ds.step4_plan_summary = {
        "design_scope": "expression_cassette",
        "selected_result_index": selected_result_index,
        "selected_overlap_len": result_payload.get("selected_overlap_len", existing_plan.get("selected_overlap_len")),
        "selected_target_tm": result_payload.get("selected_target_tm", existing_plan.get("selected_target_tm")),
        "tried_combinations": result_payload.get("tried_combinations", existing_plan.get("tried_combinations")),
        "best_plan_summary": result_payload.get("best_plan_summary", existing_plan.get("best_plan_summary")),
        "structured_results": structured_results if structured_results else existing_plan.get("structured_results") or [],
    }
    ctrl.save(ds)
    _reset_primer_task_runtime_state()
    return len(ds.primers)


def _active_primer_quality_grade(primers: list[dict]) -> str:
    if not primers:
        return "Not set"
    grade = str(primers[0].get("Quality Grade") or "Not set").strip()
    return grade or "Not set"


def _primer_completion_copy(quality_grade: str) -> tuple[str, str, str]:
    if quality_grade == "Not Recommended":
        return (
            "Primer design completed — review required",
            "Selected primers are Not Recommended. Review quality reasons before Step 5 checks or export.",
            "warn",
        )
    if quality_grade == "Usable with Risk":
        return (
            "Primer design completed - review required",
            "Selected primers are Usable with Risk. Review quality reasons before validation or export.",
            "info",
        )
    if quality_grade == "Recommended":
        return (
            "Primer option recorded for review",
            "Selected primer option is in the pass range for this review summary. Review the active option before continuing to Step 5 checks.",
            "ready",
        )
    return (
        "Primer design completed - review required",
        "Review primer quality details before validation or export.",
        "info",
    )


def _primary_quality_reason(result: dict) -> str:
    reasons = result.get("quality_reasons") or []
    if not isinstance(reasons, list):
        return "No major quality note"
    for reason in reasons:
        text = str(reason).strip()
        if text:
            return text
    return "No major quality note"


def _review_status_for_grade(quality_grade: str) -> str:
    if quality_grade == "Recommended":
        return "Available for Step 5 review"
    if quality_grade == "Usable with Risk":
        return "Manual review required"
    if quality_grade == "Not Recommended":
        return "Not recommended for experimental use"
    return "Manual review required"


def _display_quality_grade(quality_grade: str) -> str:
    if quality_grade == "Recommended":
        return "Pass-range"
    if quality_grade == "Usable with Risk":
        return "Review required"
    if quality_grade == "Not Recommended":
        return "Not Recommended"
    return quality_grade or "Not set"


def _format_option_metric(value, suffix: str = "") -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value):.1f}{suffix}"
    except (TypeError, ValueError):
        return f"{value}{suffix}"


def _primer_option_label(index: int, result: dict) -> str:
    grade = _display_quality_grade(str(result.get("quality_grade") or "Not set"))
    score = result.get("quality_score", "—")
    tm_gap = _format_option_metric(result.get("tm_gap"), "°C")
    heterodimer_risk = str(result.get("hetero_dimer_risk") or "—")
    return f"Option {index + 1} · {grade} · Review value {score} · Tm gap {tm_gap} · Heterodimer {heterodimer_risk}"


def _render_active_option_risk_panel(selected_result: dict) -> None:
    quality_grade = str(selected_result.get("quality_grade") or "Not set").strip()
    if quality_grade == "Recommended":
        _status_panel(
            "Active option: Pass-range",
            "Selected option is in the pass range. Step 5 will still run review checks for the full construct.",
            tone="ready",
        )
    elif quality_grade == "Usable with Risk":
        _status_panel(
            "Active option: Review required",
            "Selected option carries review-level primer risk. Step 5 will keep that warning visible.",
            tone="info",
        )
    elif quality_grade == "Not Recommended":
        _status_panel(
            "Active option: Not Recommended",
            "Selected option is Not Recommended. Step 5/6 will keep this risk for manual review before export.",
            tone="warn",
        )


def _has_unknown_structural_risk(result: dict) -> bool:
    if str(result.get("hetero_dimer_risk") or "").strip() == "Unknown":
        return True
    for primer in result.get("primers", []):
        if not isinstance(primer, dict):
            continue
        if str(primer.get("hairpin_risk") or "").strip() == "Unknown":
            return True
        if str(primer.get("self_dimer_risk") or "").strip() == "Unknown":
            return True
    return False


def _render_ranked_options_explainer() -> None:
    with st.expander("How to interpret primer option summary", expanded=False):
        st.markdown(
            "- Options summarize existing primer metrics: Tm deviation, Tm gap, GC balance, issue count, and interaction risk.\n"
            "- Pass-range = review value 85–100.\n"
            "- Review required = review value 60–84 and requires manual review.\n"
            "- Not Recommended = review value 0–59 and should require manual review before export.\n"
            "- Step 5 and Step 6 use only the active selected option.\n"
            "- This review context does not certify experimental readiness or replace manual review."
        )


def _render_unknown_structural_risk_note(results: list[dict]) -> None:
    if any(_has_unknown_structural_risk(result) for result in results if isinstance(result, dict)):
        st.caption("Unknown means the structural risk could not be evaluated, not that it is risk-free.")


def _render_best_plan_summary(ds) -> None:
    assembly_summary = build_step4_assembly_plan_summary(ds)
    has_summary = any(
        assembly_summary.get(key) not in (None, "", 0, "Not available")
        for key in (
            "final_construct_length",
            "expected_product_size",
            "primer_count",
            "selected_overlap_len",
            "selected_target_tm",
            "tried_combinations",
            "quality_summary",
        )
    )
    if not has_summary:
        return

    _section_label("Assembly Review Summary")
    cols = st.columns(4)
    cols[0].metric("Assembly method", assembly_summary["assembly_method"])
    cols[1].metric(
        "Insert length",
        f"{assembly_summary['insert_length']:,} bp" if assembly_summary["insert_length"] is not None else "—",
    )
    cols[2].metric(
        "Final construct length",
        f"{assembly_summary['final_construct_length']:,} bp" if assembly_summary["final_construct_length"] else "—",
    )
    cols[3].metric(
        "Expected product size",
        f"{assembly_summary['expected_product_size']:,} bp" if assembly_summary["expected_product_size"] else "—",
    )

    context_cols = st.columns(5)
    context_cols[0].metric("Host", assembly_summary["host"] or "—")
    context_cols[1].metric("Vector / backbone", assembly_summary.get("vector_backbone_name") or assembly_summary.get("vector_backbone") or "—")
    context_cols[2].metric("Backbone source", assembly_summary.get("backbone_source") or "—")
    context_cols[3].metric("Stale status", assembly_summary["stale_status"])
    context_cols[4].metric("Design status", "Generated")

    active_quality_grade = _active_primer_quality_grade(ds.primers if isinstance(ds.primers, list) else [])
    quality_cols = st.columns(1)
    quality_cols[0].metric("Quality status", _display_quality_grade(active_quality_grade))

    primer_cols = st.columns(4)
    primer_cols[0].metric("Primer count", assembly_summary["primer_count"])
    primer_cols[1].metric("Forward primers", assembly_summary["forward_primer_count"])
    primer_cols[2].metric("Reverse primers", assembly_summary["reverse_primer_count"])
    primer_cols[3].metric("Warnings", assembly_summary["warning_count"])

    plan_cols = st.columns(2)
    selected_tm = assembly_summary.get("selected_target_tm")
    if selected_tm is None:
        selected_tm = st.session_state.get("wf_p4_target_tm")
    try:
        selected_tm_label = f"{float(selected_tm):.1f}°C"
    except (TypeError, ValueError):
        selected_tm_label = "Not recorded for this saved snapshot"
    tried = assembly_summary.get("tried_combinations")
    plan_cols[0].metric("Selected target Tm", selected_tm_label)
    plan_cols[1].metric("Tried combinations", str(int(tried)) if tried is not None else "—")

    if assembly_summary.get("quality_summary"):
        st.caption(f"Quality summary: {assembly_summary['quality_summary']}")
    readiness_reasons = assembly_summary.get("readiness_reasons") or []
    if readiness_reasons:
        st.caption("Review notes: " + " | ".join(str(reason) for reason in readiness_reasons))
    if assembly_summary.get("best_plan_summary"):
        st.caption(str(assembly_summary["best_plan_summary"]))


def _render_structured_primer_results(results: list[dict]) -> None:
    if not results:
        return

    try:
        import pandas as pd
    except Exception:
        pd = None

    try:
        import plotly.express as px
    except Exception:
        px = None

    ranking_rows = []
    tm_chart_rows = []
    gc_chart_rows = []

    for idx, result in enumerate(results, start=1):
        quality_grade = result.get("quality_grade", "—")
        ranking_rows.append({
            "Option": idx,
            "Quality grade": _display_quality_grade(str(quality_grade)),
            "Review value": result.get("quality_score", "—"),
            "Primary reason": _primary_quality_reason(result),
            "Review status": _review_status_for_grade(str(quality_grade)),
            "Product size": result.get("product_size", "—"),
            "Target Tm": result.get("target_tm", "—"),
            "Tm gap": result.get("tm_gap", "—"),
            "Heterodimer risk": result.get("hetero_dimer_risk", "—"),
        })
        for primer in result.get("primers", []):
            tm_chart_rows.append({
                "Primer": f"{idx}-{primer.get('name', 'Primer')}",
                "Tm": primer.get("tm", 0.0),
                "Role": primer.get("role", "—"),
                "Design": f"Design {idx}",
            })
            gc_chart_rows.append({
                "Primer": f"{idx}-{primer.get('name', 'Primer')}",
                "GC": primer.get("gc_content", 0.0),
                "Role": primer.get("role", "—"),
                "Design": f"Design {idx}",
            })

    _section_label("Review options")
    _render_ranked_options_explainer()
    _render_unknown_structural_risk_note(results)
    if pd is not None:
        st.dataframe(pd.DataFrame(ranking_rows), use_container_width=True, hide_index=True)
    else:
        for row in ranking_rows:
            st.write(row)

    if px is not None and tm_chart_rows and gc_chart_rows:
        chart_col1, chart_col2 = st.columns(2)
        tm_fig = px.bar(pd.DataFrame(tm_chart_rows), x="Design", y="Tm", color="Role", barmode="group", title="Primer Tm distribution")
        gc_fig = px.bar(pd.DataFrame(gc_chart_rows), x="Design", y="GC", color="Role", barmode="group", title="Primer GC distribution")
        chart_col1.plotly_chart(tm_fig, use_container_width=True)
        chart_col2.plotly_chart(gc_fig, use_container_width=True)

    for idx, result in enumerate(results, start=1):
        _section_label(f"Primer review {idx}")
        pair_cols = st.columns(4)
        pair_cols[0].metric("Quality grade", result.get("quality_grade", "—"))
        pair_cols[1].metric("Review value", str(result.get("quality_score") or "—"))
        pair_cols[2].metric("Product size", str(result.get("product_size") or "—"))
        pair_cols[3].metric("Heterodimer risk", result.get("hetero_dimer_risk", "—"))

        st.caption(" | ".join(result.get("quality_reasons", [])) if result.get("quality_reasons") else "No additional quality notes.")

        hetero_dg = result.get("hetero_dimer_dg_kcal_mol")
        if hetero_dg is not None:
            st.caption(f"Heterodimer ΔG: {hetero_dg:.2f} kcal/mol")
        if _has_unknown_structural_risk(result):
            st.caption("Unknown means the structural risk could not be evaluated, not that it is risk-free.")

        primer_rows = []
        for primer in result.get("primers", []):
            primer_rows.append({
                "Primer": primer.get("name", "—"),
                "Role": primer.get("role", "—"),
                "Sequence": primer.get("sequence", ""),
                "Tm (°C)": primer.get("tm", "—"),
                "Tm deviation": primer.get("tm_deviation", "—"),
                "GC (%)": primer.get("gc_content", "—"),
                "GC in range": primer.get("gc_in_range", "—"),
                "Length": primer.get("length", "—"),
                "Hairpin risk": primer.get("hairpin_risk", "—"),
                "Hairpin ΔG": primer.get("hairpin_dg_kcal_mol", "—"),
                "Self-dimer risk": primer.get("self_dimer_risk", "—"),
                "Self-dimer ΔG": primer.get("self_dimer_dg_kcal_mol", "—"),
                "Issues": " | ".join(primer.get("issues", [])) if primer.get("issues") else "—",
            })

        if pd is not None:
            st.dataframe(pd.DataFrame(primer_rows), use_container_width=True, hide_index=True)
        else:
            for row in primer_rows:
                st.write(row)

        pair_warnings = result.get("pair_warnings") or []
        if pair_warnings:
            for warning in pair_warnings:
                st.warning(warning)


def _primer_completion_copy(quality_grade: str) -> tuple[str, str, str]:
    """Return review-oriented Step 4 completion copy."""
    if quality_grade == "Not Recommended":
        return (
            "Primer review completed - review required",
            "Selected primers are Not Recommended. Review quality reasons before Step 5 checks or export.",
            "warn",
        )
    if quality_grade == "Usable with Risk":
        return (
            "Primer review completed - review required",
            "Selected primers require review. Review quality reasons before validation or export.",
            "info",
        )
    if quality_grade == "Recommended":
        return (
            "Primer option recorded for review",
            "Selected primers are in the pass range. Review the active option before continuing to Step 5 checks.",
            "ready",
        )
    return (
        "Primer review completed - review required",
        "Review primer quality details before validation or export.",
        "info",
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def page(ctrl) -> None:
    """Render Step 4 -- Cassette / Boundary Review."""
    _initialize_primer_task_state()
    root = st.empty()
    with root.container():
        ds = ctrl.get()
        stale_state = ds.invalidate_stale_workflow_outputs()
        if any(stale_state.values()):
            ctrl.save(ds)

        active_host = str(st.session_state.get(SK.ACTIVE_HOST, "") or "").strip()
        active_seq = str(st.session_state.get(SK.ACTIVE_SEQ, "") or "").strip().upper()
        frame = ds.frame if isinstance(ds.frame, dict) else {}
        session_frame_seq = (
            frame.get("final_sequence")
            or ds.optimized_seq
            or ds.original_seq
            or ""
        )
        session_frame_seq = str(session_frame_seq).strip().upper()
        session_frame_seq_hash = _seq_hash(session_frame_seq)

        upstream_host, upstream_seq = _hydrate_upstream_context_from_session(ds)
        upstream_seq_hash = _seq_hash(upstream_seq)
        last_used_host = str(ds.primer_context_host or "").strip()
        last_used_seq_hash = str(ds.primer_context_seq_hash or "").strip()

        has_existing_primers = bool(ds.primers)
        upstream_missing = not upstream_host or not upstream_seq
        restored_active_context_matches = (
            has_existing_primers
            and not last_used_host
            and not last_used_seq_hash
            and active_host == str(ds.host or "").strip()
            and bool(active_seq)
            and _seq_hash(active_seq) == session_frame_seq_hash
        )
        upstream_changed = has_existing_primers and not restored_active_context_matches and (
            not last_used_host
            or not last_used_seq_hash
            or last_used_host != upstream_host
            or last_used_seq_hash != upstream_seq_hash
        )

        _step_header(
            4,
            "Cassette / Boundary Review",
            "Review the assembled expression frame, cassette/component order, targeting context, and vector/backbone documentation context produced in Step 3.",
            [
                "Review frame structure, component order, sequence preview, and vector context for documentation.",
                "Plant MVP context: plant expression cassette context, signal peptide, transit peptide, subcellular targeting, and vector/backbone documentation.",
                "Note whether manual primer or design follow-up is needed outside this build.",
                "This step is not a primer design engine, sequence validation, cloning feasibility verification, or experimental readiness approval.",
            ],
        )

        if upstream_missing or upstream_changed or stale_state.get("primer_stale") or stale_state.get("frame_stale"):
            if has_existing_primers and not (stale_state.get("primer_stale") or stale_state.get("frame_stale")):
                _clear_primer_state(ds, ctrl)
            _status_panel(
                "Upstream context is missing or has changed",
                "Complete Steps 1–3 before designing primers. Existing primer results were cleared because the upstream context changed.",
                tone="warn",
            )

        has_frame = isinstance(ds.frame, dict) and ds.frame.get("success")

        _section_label("Frame summary")
        render_flow_strip(
            [
                ("Input", "Expression frame from Step 3"),
                ("Output", "Cassette boundary documentation context for Step 5 and Step 6"),
            ]
        )
        if ds.host:
            st.caption(
                f"Host: **{ds.host}**"
                + (f" | Tag: **{ds.tag}**" if ds.tag else "")
                + (f" | Gene: **{ds.gene_name}**" if ds.gene_name else "")
            )

        if has_frame:
            _frame_summary_card(frame=ds.frame, optimized_seq=ds.optimized_seq)
        else:
            _status_panel(
                "No expression frame is available",
                "Complete expression-frame assembly in Step 3 before reviewing cassette boundaries.",
                tone="warn",
            )

        st.divider()
        _section_label("Construct/cassette map preview")
        st.caption(
            "Documentation map preview for construct/cassette review. This preview is not sequence validation, "
            "not cloning feasibility verification, and not experimental readiness approval."
        )
        seq_for_map = (
            (ds.frame.get("final_sequence") if isinstance(ds.frame, dict) else None)
            or ds.optimized_seq
            or ds.original_seq
        )
        if has_frame and seq_for_map and len(seq_for_map) >= 30:
            try:
                from utils.plasmid_visualizer import PlasmidVisualizer
                viz = PlasmidVisualizer()
                frame = ds.frame if isinstance(ds.frame, dict) else {}
                features, pos = [], 0
                for part in frame.get("parts", []):
                    part_len = len(part.get("seq") or "")
                    if part_len > 0:
                        features.append({
                            "label": part.get("name", "Part"),
                            "start": pos,
                            "end": pos + part_len,
                            "type": part.get("type", "misc"),
                            "strand": 1,
                        })
                        pos += part_len
                if not features:
                    _status_panel(
                        "Map feature documentation follow-up",
                        "The expression frame sequence is present, but feature annotations are not recorded for this map preview. Add feature documentation before using the map for handoff review.",
                        tone="info",
                    )
                    raise ValueError("Feature annotations are required for the documentation map preview.")
                feature_readback = ", ".join(
                    f"{feature.get('label', 'Feature')} ({feature.get('type', 'misc')}, forward)"
                    for feature in features
                )
                st.caption(f"Feature order preview: {feature_readback}. Positions/order are approximate documentation readback.")
                title = f"{ds.gene_name or 'Construct'} — {len(seq_for_map):} bp"
                fig, png = viz.draw_circular_map(sequence=seq_for_map, features=features, title=title)
                fig.set_size_inches(4.5, 4.5)
                with st.expander("Preview construct/cassette map", expanded=False):
                    _left, _map_col, _right = st.columns([1, 2, 1])
                    with _map_col:
                        st.pyplot(fig, use_container_width=True)
                import matplotlib.pyplot as plt
                plt.close(fig)
                st.session_state["wf_plasmid_png"] = png
                st.session_state["wf_plasmid_features"] = features
                st.session_state["wf_plasmid_title"] = title
            except Exception as exc:
                st.caption(f"Construct/cassette map rendering was skipped: {exc}")
        else:
            _status_panel(
                "No construct/cassette map preview yet",
                "A renderable expression-frame sequence with documented features is required before a map preview can be generated.",
                tone="info",
            )

        st.divider()
        _section_label("Optional primer candidate placeholder")

        target_tm = float(st.session_state.get("wf_p4_target_tm", 60.0) or 60.0)

        st.caption(
            "Outer-primer candidate generation is optional and not part of the main cassette boundary review. "
            "When unavailable, any stored target annealing temperature value is retained only as placeholder context and does not affect generated primers."
        )

        primer_backend_status = get_primer3_backend_status(probe=False)
        primer_backend_unavailable = not primer_backend_status.available
        if primer_backend_unavailable:
            with st.expander("Primer candidate placeholder", expanded=False):
                st.caption(
                    "Outer-primer candidate generation is not enabled in this build. "
                    "This step currently supports cassette boundary and documentation review only."
                )
            if not ds.primers:
                _record_primer_backend_unavailable(ds, ctrl, upstream_host, upstream_seq_hash, float(target_tm))
                ds = ctrl.get()

        action_clicked = False
        if not primer_backend_unavailable:
            action_col1, _ = st.columns(2)
            action_clicked = _column_aware_button(
                action_col1,
                "Review primer candidates",
                type="secondary",
                key="wf_p4_design_sync",
                use_container_width=True,
                disabled=not has_frame,
            )

        if action_clicked:
            if not has_frame:
                st.error("Current frame is unavailable for primer candidate review.")
            else:
                try:
                    primer_design = design_outer_primers_for_cassette(
                        session_frame_seq,
                        target_tm=float(target_tm),
                        tm_tolerance=2.0,
                        min_length=18,
                        max_length=30,
                        num_designs=5,
                    )
                    structured_results = _normalize_structured_results_for_expression_cassette(
                        primer_design.get("results") or []
                    )
                    selected_result_index = int(primer_design.get("selected_result_index", 0) or 0)
                    primers = _primer_rows_from_structured_results(
                        structured_results,
                        selected_index=selected_result_index,
                    )

                    ds.cloning_method = "Gibson Assembly"
                    ds.primers = primers if primers else []
                    ds.primer_design_status = "generated" if primers else ""
                    ds.primer_backend_available = True
                    ds.active_primer_pair = primers[0] if primers else None
                    ds.primer_context_host = upstream_host
                    ds.primer_context_seq_hash = upstream_seq_hash
                    ds.primer_context_signature = ds.current_primer_context_signature()
                    st.session_state[SK.PRIMER_TASK_CONTEXT_SIGNATURE] = ds.primer_context_signature
                    st.session_state["primer_task_started_for_gene"] = str(ds.gene_name or "")
                    st.session_state["primer_task_started_for_frame"] = str(ds.frame.get("total_length", "") if isinstance(ds.frame, dict) else "")
                    st.session_state["primer_task_started_for_host"] = str(ds.host or upstream_host or "")
                    ds.step4_plan_summary = {
                        "design_scope": "expression_cassette",
                        "selected_result_index": selected_result_index,
                        "selected_overlap_len": None,
                        "selected_target_tm": float(target_tm),
                        "tried_combinations": len(structured_results) if structured_results else None,
                        "best_plan_summary": primer_design.get("best_plan_summary") or "Review option prepared for the complete expression cassette.",
                        "structured_results": structured_results,
                    }
                    ctrl.save(ds)
                    _clear_primer_task_state_all()

                    if not primers:
                        ds.primers = []
                        ds.primer_design_status = ""
                        ds.primer_backend_available = True
                        ds.active_primer_pair = None
                        ctrl.save(ds)
                        _reason = primer_design.get("error") or "Primer design returned no primers."
                        _status_panel(
                            "0 primer pairs returned",
                            f"{_reason} Adjust the construct or primer parameters and try again.",
                            tone="warn",
                        )
                    else:
                        st.success(f"Primer candidate review recorded with {len(primers)} cassette-level primer pair(s).")

                except Exception as exc:
                    ds.primers = []
                    ds.step4_plan_summary = {}
                    ds.primer_design_status = ""
                    ds.primer_backend_available = True
                    ds.active_primer_pair = None
                    ctrl.save(ds)
                    st.session_state["primer_task_status"] = "failed"
                    st.session_state["primer_task_result"] = None
                    st.session_state["primer_task_error"] = str(exc)
                    st.session_state["primer_task_poll_count"] = 0
                    st.error(f"Primer candidate review failed: {exc}")

        stored_plan = _stored_step4_plan_summary(ds)
        structured_results = stored_plan.get("structured_results") or []
        if structured_results:
            _section_label("Active primer option")
            st.caption(
                "Choose exactly one cassette outer primer pair. Step 5 validation and Step 6 export use only this active option."
            )
            selected_index = int(stored_plan.get("selected_result_index", 0) or 0)
            option_labels = [
                _primer_option_label(idx, item)
                for idx, item in enumerate(structured_results)
            ]
            safe_selected_index = max(0, min(len(option_labels) - 1, selected_index))
            chosen_label = st.selectbox(
                "Selected review option",
                options=option_labels,
                index=safe_selected_index,
                key="wf_p4_selected_option",
            )
            chosen_index = option_labels.index(chosen_label)
            if chosen_index != safe_selected_index:
                applied = _apply_selected_structured_design(ds, ctrl, chosen_index, upstream_host, upstream_seq_hash)
                if applied:
                    st.success(f"Primer option {chosen_index + 1} is now active for Step 5/Step 6 documentation review.")
                    ds = ctrl.get()

            selected_result = structured_results[chosen_index] if 0 <= chosen_index < len(structured_results) else structured_results[safe_selected_index]
            _render_active_option_risk_panel(selected_result)
            st.caption(
                f"Active option: {selected_result.get('quality_grade', 'Not set')} · "
                f"review value {selected_result.get('quality_score', '—')} · "
                f"Tm gap {selected_result.get('tm_gap', '—')}"
            )

        _poll_primer_task_if_needed(ds, ctrl, upstream_host, upstream_seq_hash)

        task_status = str(st.session_state.get("primer_task_status") or "idle")
        task_presenter = build_async_status_presenter(
            "primer_task",
            title="Primer async task",
            status=task_status,
            progress_builder=_primer_task_progress,
            detail_builder=_primer_task_detail,
            session_state=st.session_state,
            include_result_ready=True,
        )

        if task_status != "idle":
            st.caption("Async task status")
            render_async_task_feedback(
                title=task_presenter["title"],
                status=task_presenter["status"],
                progress=task_presenter["progress"],
                detail=task_presenter["detail"],
                task_id=task_presenter["task_id"],
                error_text=task_presenter["error_text"],
            )
            status_col1, status_col2, status_col3, status_col4 = st.columns(4)
            status_col1.metric("Task ID", task_presenter["task_id"] or "—")
            status_col2.metric("Task status", task_presenter["status"] or "idle")
            status_col3.metric("Result available", "Yes" if task_presenter["result_ready"] else "No")
            status_col4.metric("Poll cycles", task_presenter["poll_count"])

            if task_presenter["poll_enabled"] and task_status in {"queued", "started", "deferred"}:
                poll_delay = _primer_poll_interval_seconds(task_presenter["poll_count"])
                _schedule_async_refresh(poll_delay)

        if ds.primers:
            active_quality_grade = _active_primer_quality_grade(ds.primers)
            status_title, status_body, status_tone = _primer_completion_copy(active_quality_grade)
            _status_panel(
                status_title,
                status_body,
                tone=status_tone,
            )
            _render_best_plan_summary(ds)
            _render_primer_quality_summary(ds.primers)
            _render_primer_table(ds.primers)
            _render_structured_primer_results(stored_plan.get("structured_results") or [])

            st.divider()
            _section_label("Design report")
            try:
                from services.report_service import generate_report_content, render_markdown_report

                report = generate_report_content(ds)
                md_report = render_markdown_report(report)
                report_presenter = report.get("report_presenter") or {}

                render_report_preview_container(
                    report_presenter,
                    step_keys=["step4", "step5", "step6"],
                    section_title="Preview design report",
                )
                render_report_download_button(
                    report_presenter,
                    md_report,
                    button_key="wf_p4_report_md",
                )
            except Exception as report_error:
                _status_panel("Report preview unavailable", f"Unable to generate the report: {report_error}", tone="info")
        else:
            if str(getattr(ds, "primer_design_status", "") or "").strip().lower() == "unavailable":
                st.caption(
                    "No primer candidate rows are recorded because outer-primer candidate generation is not enabled in this build."
                )
            else:
                _status_panel(
                    "No primer candidate review is recorded",
                    "The main Step 4 record remains the cassette boundary and documentation review. Optional primer candidate rows appear here only when generation is enabled.",
                    tone="info",
                )
