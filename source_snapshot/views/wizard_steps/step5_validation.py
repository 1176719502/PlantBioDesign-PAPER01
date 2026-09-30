# -*- coding: utf-8 -*-
"""
views/wizard_steps/step5_validation.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Step 5 -- Validation Report.
"""
from __future__ import annotations

import time

import streamlit as st

from core.session_keys import SK
from services.async_task_service import (
    handle_task_active_poll_state,
    handle_task_exception_state,
    handle_task_non_polling_state,
    handle_task_poll_update,
    handle_task_submission,
    handle_task_terminal_error_state,
)
from services.task_polling_service import (
    build_task_detail,
    build_task_progress,
    initialize_task_state,
    reset_task_runtime_state,
    reset_task_state,
    should_poll_task,
)
from services.async_status_presenter import build_async_status_presenter
from services.validation_api_client import get_validation_task
from services.validation_runner import run_or_enqueue_validation
from services.validation_summary_service import (
    PRIMER_HIGH_RISK_CODE,
    PRIMER_REVIEW_CODE,
    PRIMER_UNAVAILABLE_CODE,
    build_primer_risk_summary,
    build_validation_conclusion,
    merge_validation_with_primer_risk,
)
from services.wizard_task_context_guard import (
    build_stale_validation_task_message,
    should_apply_task_result,
)
from views.wizard_steps._shared import (
    _show_issues,
    _section_label,
    _status_panel,
    _step_header,
    render_flow_strip,
    render_async_task_feedback,
    render_report_download_button,
    render_report_preview_container,
)


_VALIDATION_TASK_PROGRESS = {
    "idle": 0,
    "queued": 20,
    "started": 65,
    "finished": 100,
    "failed": 100,
    "not_found": 100,
    "unknown": 5,
}

_VALIDATION_TASK_DETAIL = {
    "idle": "Review checks have not started yet.",
    "queued": "Review checks have been queued and will be polled automatically.",
    "started": "Review checks are running. This panel refreshes automatically until results are available for review.",
    "finished": "Review checks are complete. The latest results are shown below.",
    "failed": "Review checks failed. Review the error details below, then retry.",
    "not_found": "The review-check task could not be found. Submit a new task if needed.",
    "unknown": "The review-check task status is being checked.",
}

STEP5_COPY = {
    "step_title": "Review Checks",
    "step_purpose": "Run final documentation checks before export review, including plant-specific evidence/provenance gaps and the primer-risk summary identified in Step 4.",
    "step_bullets": [
        "Run the review checks for the current construct.",
        "Review blocking issues, warnings, and suggested next actions.",
        "Plant MVP context: evidence/provenance gaps and manual review checks.",
        "Carry over the Step 4 primer-quality summary so high-risk primer sets are not mistaken for a full pass.",
    ],
    "main_action": "Primary action",
    "validation_input_missing_title": "No construct is available for review checks",
    "validation_input_missing_body": "Review checks depend on the assembled expression construct from previous steps. Complete the upstream assembly first.",
    "validation_input_ready_title": "Review-check input available",
    "validation_input_ready_body": "Run review checks below to merge construct checks with the Step 4 primer-risk summary.",
    "run_validation": "Run review checks",
    "validation_error_prefix": "Review checks failed: ",
    "validation_result": "Review-check result",
    "blocking_detected_title": "Blocking issues detected",
    "high_risk_review_title": "Review checks complete - high-risk primers still require review",
    "review_required_title": "Review checks complete - manual review required",
    "validation_passed_title": "Documentation checks completed",
    "no_result_title": "No review-check result yet",
    "no_result_body": "Run review checks above to generate the final summary, including primer-risk information carried over from Step 4.",
    "no_final_result_title": "No final review-check result yet",
    "no_final_result_body": "The previous review-check output is no longer current for the active primer option.",
    "validation_stale_title": "Review checks need rerun",
    "validation_stale_reason": "Active primer option changed after the last review-check run",
    "validation_stale_action": "Run review checks again before delivery/export",
    "primer_summary": "Primer risk summary",
    "primer_high_risk_title": "High-risk primer pairs detected",
    "primer_high_risk_body": "Step 4 reported at least one Not Recommended primer pair. Review primer quality before export.",
    "primer_review_title": "Primer quality review remains open",
    "primer_review_body": "Step 4 reported usable-but-risky primer pairs. Manual review remains open before export.",
    "primer_unavailable_title": "Primer candidate generation not enabled",
    "primer_unavailable_body": "Step 4 recorded cassette boundary review context only; no primer candidate rows are recorded in this build.",
    "primer_no_extra_warning_title": "Primer quality adds no extra warning",
    "primer_no_extra_warning_body": "All Step 4 primer pairs are in the Step 4 pass range, so Step 5 adds no extra primer-related warning.",
    "recommended_pairs": "Pass-range pairs",
    "usable_with_risk_pairs": "Usable with Risk pairs",
    "not_recommended_pairs": "Not Recommended pairs",
    "affected_fragments": "Affected fragments: ",
    "top_risk_signals": "Top risk signals: ",
    "critical_issues": "Critical issues",
    "warnings": "Warnings",
    "info": "Info",
    "next": "Next actions",
    "no_cds_title": "No CDS is available to send",
    "no_cds_body": "Complete the upstream steps first, then send the CDS sequence to the protein-structure workspace.",
    "structure_ready_title": "Structure-analysis input available",
    "send_structure": "Send to Protein Structure Analysis",
}


def _build_primer_risk_summary(primers: list[dict]) -> dict:
    """Backward-compatible wrapper around services.validation_summary_service."""
    return build_primer_risk_summary(primers)


def _with_primer_unavailable_status(summary: dict, ds) -> dict:
    if str(getattr(ds, "primer_design_status", "") or "").strip().lower() != "unavailable":
        return summary
    if getattr(ds, "primer_backend_available", None) is not False:
        return summary
    return {
        **summary,
        "primer_design_status": "unavailable",
    }


def _merge_validation_with_primer_risk(base_issues: list[dict], primers: list[dict], ds=None) -> tuple[list[dict], dict]:
    """Backward-compatible wrapper around services.validation_summary_service."""
    return merge_validation_with_primer_risk(base_issues, primers, ds)


def _build_validation_conclusion(issues: list[dict]) -> dict:
    """Backward-compatible wrapper around services.validation_summary_service."""
    return build_validation_conclusion(
        issues,
        copy={
            "blocking_detected_title": STEP5_COPY["blocking_detected_title"],
            "high_risk_review_title": STEP5_COPY["high_risk_review_title"],
            "review_required_title": STEP5_COPY["review_required_title"],
            "validation_passed_title": STEP5_COPY["validation_passed_title"],
        },
    )


def _render_primer_risk_summary(summary: dict) -> None:
    """Render the Step 4 primer-quality summary inside Step 5."""
    total = summary["recommended"] + summary["usable_with_risk"] + summary["not_recommended"]
    if summary.get("primer_design_status") == "unavailable":
        _section_label(STEP5_COPY["primer_summary"])
        _status_panel(
            STEP5_COPY["primer_unavailable_title"],
            STEP5_COPY["primer_unavailable_body"],
            tone="info",
        )
        return
    if not total:
        return

    _section_label(STEP5_COPY["primer_summary"])
    if summary["not_recommended"]:
        _status_panel(
            STEP5_COPY["primer_high_risk_title"],
            STEP5_COPY["primer_high_risk_body"],
            tone="warn",
        )
    elif summary["usable_with_risk"]:
        _status_panel(
            STEP5_COPY["primer_review_title"],
            STEP5_COPY["primer_review_body"],
            tone="info",
        )
    else:
        _status_panel(
            STEP5_COPY["primer_no_extra_warning_title"],
            STEP5_COPY["primer_no_extra_warning_body"],
            tone="ready",
        )

    c1, c2, c3 = st.columns(3)
    c1.metric(STEP5_COPY["recommended_pairs"], summary["recommended"])
    c2.metric(STEP5_COPY["usable_with_risk_pairs"], summary["usable_with_risk"])
    c3.metric(STEP5_COPY["not_recommended_pairs"], summary["not_recommended"])

    if summary["affected_fragments"]:
        st.caption(STEP5_COPY["affected_fragments"] + ", ".join(summary["affected_fragments"]))
    if summary["top_reasons"]:
        st.caption(STEP5_COPY["top_risk_signals"] + " | ".join(summary["top_reasons"]))


def _initialize_validation_task_state() -> None:
    initialize_task_state(
        "validation_task",
        defaults={
            "id": "",
            "status": "idle",
            "progress": 0,
            "detail": "Review checks have not started yet.",
            "error": "",
            "result": None,
            "poll_enabled": False,
            "last_polled_at": 0.0,
            "poll_count": 0,
            "context_signature": "",
        },
    )


def _reset_validation_task_runtime_state() -> None:
    reset_task_runtime_state("validation_task")


def _clear_validation_task_state_all() -> None:
    st.session_state["validation_task_id"] = ""
    st.session_state["validation_task_status"] = "idle"
    st.session_state["validation_task_progress"] = 0
    st.session_state["validation_task_detail"] = "Review checks have not started yet."
    st.session_state["validation_task_error"] = ""
    st.session_state["validation_task_result"] = None
    st.session_state["validation_task_poll_count"] = 0
    st.session_state[SK.VALIDATION_TASK_CONTEXT_SIGNATURE] = ""
    _reset_validation_task_runtime_state()


def _reset_validation_task_state() -> None:
    _clear_validation_task_state_all()


def _schedule_validation_refresh(delay_seconds: float = 1.5) -> None:
    time.sleep(delay_seconds)
    st.rerun()


def _is_finished_validation_result_payload(result_payload: dict | None) -> bool:
    payload = result_payload if isinstance(result_payload, dict) else {}
    issues = payload.get("issues")
    return isinstance(issues, list)


def _has_completed_validation_result(ds, stale_state: dict) -> bool:
    if stale_state.get("validation_stale"):
        return False
    return bool(ds.validation_results) or (
        isinstance(ds.validation_results, list) and bool(ds.validation_context_signature)
    )


def _validation_poll_interval_seconds(poll_count: int) -> float:
    if poll_count < 3:
        return 1.0
    if poll_count < 8:
        return 1.5
    return 2.0


def _validation_task_progress(status: str) -> int:
    return build_task_progress(status, _VALIDATION_TASK_PROGRESS)


def _validation_task_detail(status: str, poll_count: int) -> str:
    detail = build_task_detail(status, poll_count, _VALIDATION_TASK_DETAIL, {"queued", "started"})
    return detail


def _normalize_validation_task_payload(task_payload: dict | None) -> tuple[str, dict | None, str]:
    payload = task_payload if isinstance(task_payload, dict) else {}
    status = str(payload.get("status") or "unknown").strip().lower()
    result = payload.get("result")
    error = payload.get("error")
    if error in (None, ""):
        error = payload.get("message")
    error_text = str(error).strip() if error not in (None, "") else ""
    return status, result if isinstance(result, dict) else None, error_text


def _apply_finished_validation_task_result(ds, ctrl, result_payload: dict | None) -> None:
    task_signature = st.session_state.get(SK.VALIDATION_TASK_CONTEXT_SIGNATURE)
    current_signature = ds.current_validation_context_signature()
    if not should_apply_task_result(task_signature, current_signature):
        st.session_state["validation_task_result"] = None
        st.session_state["validation_task_error"] = build_stale_validation_task_message()
        st.session_state["validation_task_status"] = "idle"
        _reset_validation_task_runtime_state()
        st.warning(build_stale_validation_task_message())
        return

    payload = result_payload if isinstance(result_payload, dict) else {}
    base_issues = payload.get("issues") or []
    if not isinstance(base_issues, list):
        base_issues = []
    primers = ds.primers if isinstance(ds.primers, list) else []
    merged_issues, _ = _merge_validation_with_primer_risk(base_issues, primers, ds)
    ds.validation_results = merged_issues
    ds.validation_context_signature = current_signature
    ctrl.save(ds)
    st.session_state["validation_task_result"] = payload
    st.session_state["validation_task_error"] = ""
    st.session_state["validation_task_status"] = "finished"
    st.session_state["validation_task_progress"] = 100
    st.session_state["validation_task_detail"] = _VALIDATION_TASK_DETAIL["finished"]
    _reset_validation_task_runtime_state()


def _start_validation_task(ds, ctrl) -> None:
    validation_task_context_signature = ds.current_validation_context_signature()
    st.session_state[SK.VALIDATION_TASK_CONTEXT_SIGNATURE] = validation_task_context_signature
    payload = {
        "frame": ds.frame if isinstance(ds.frame, dict) else {},
        "primers": ds.primers if isinstance(ds.primers, list) else [],
    }
    try:
        response = run_or_enqueue_validation(payload)
        mode = str(response.get("mode") or "local").strip().lower()
        if mode == "async":
            task_payload = response.get("task") if isinstance(response.get("task"), dict) else {}
            handle_task_submission(
                "validation_task",
                response=task_payload,
                fallback_status="queued",
                progress_map=_VALIDATION_TASK_PROGRESS,
                detail_builder=_validation_task_detail,
            )
            return

        result_payload = response.get("result") if isinstance(response.get("result"), dict) else {}
        if not _is_finished_validation_result_payload(result_payload):
            raise RuntimeError("Local review checks finished, but the result payload is missing the expected 'issues' list.")
        _apply_finished_validation_task_result(ds, ctrl, result_payload)
    except Exception as exc:
        error_text = f"Review-check tool unavailable or review-check task failed: {exc}"
        handle_task_exception_state(
            "validation_task",
            error=RuntimeError(error_text),
            failed_progress=100,
            failed_detail=_VALIDATION_TASK_DETAIL["failed"],
        )
        st.error(error_text)


def _refresh_validation_task_status(ds, ctrl) -> None:
    task_id = str(st.session_state.get("validation_task_id") or "").strip()
    if not task_id:
        _reset_validation_task_runtime_state()
        return

    try:
        task_response = get_validation_task(task_id)
        task_status, task_result, task_error = _normalize_validation_task_payload(task_response)
        handle_task_poll_update(
            "validation_task",
            status=task_status,
            now=time.time(),
            progress_map=_VALIDATION_TASK_PROGRESS,
            detail_builder=_validation_task_detail,
        )

        if task_status in {"queued", "started"}:
            handle_task_active_poll_state("validation_task")
        elif task_status == "finished":
            if not _is_finished_validation_result_payload(task_result):
                handle_task_terminal_error_state(
                    "validation_task",
                    status="failed",
                    error_text="Review checks finished, but the result payload is missing the expected 'issues' list.",
                )
                return
            _apply_finished_validation_task_result(ds, ctrl, task_result)
            issues = ctrl.get().validation_results
            criticals = [i for i in issues if i.get("severity") == "critical"]
            high_risk = any(i.get("code") == PRIMER_HIGH_RISK_CODE for i in issues)
            warnings = [i for i in issues if i.get("severity") == "warning"]
            if criticals:
                st.warning(f"Review checks completed with {len(criticals)} critical issue(s).")
            elif high_risk:
                st.warning("Review checks completed, but high-risk primer pairs still require review before export.")
            elif warnings:
                st.warning(f"Review checks completed with {len(warnings)} warning(s).")
            else:
                st.info("Review completed with no reported issues in this computational preview only; this does not certify experimental readiness.")
        elif task_status in {"failed", "not_found"}:
            handle_task_terminal_error_state(
                "validation_task",
                status=task_status,
                error_text=task_error or f"Review-check task returned status: {task_status}.",
            )
        else:
            handle_task_non_polling_state("validation_task", result=task_result, error_text=task_error)
    except Exception as exc:
        handle_task_exception_state(
            "validation_task",
            error=exc,
            failed_progress=100,
            failed_detail=_VALIDATION_TASK_DETAIL["failed"],
        )



def _clear_validation_outputs(ds, ctrl) -> None:
    ds.clear_step5_outputs()
    ctrl.save(ds)
    _reset_validation_task_state()
    _reset_validation_task_runtime_state()

def _poll_validation_task_if_needed(ds, ctrl) -> None:
    poll_count = int(st.session_state.get("validation_task_poll_count") or 0)
    if not should_poll_task(
        "validation_task",
        active_statuses={"queued", "started"},
        now=time.time(),
        min_interval_seconds=_validation_poll_interval_seconds(poll_count),
    ):
        return

    _refresh_validation_task_status(ds, ctrl)


def page(ctrl) -> None:
    """Render Step 5 -- Validation Report."""
    _initialize_validation_task_state()
    ds = ctrl.get()
    stale_state = ds.invalidate_stale_workflow_outputs()
    if any(stale_state.values()):
        ctrl.save(ds)
        if stale_state.get("validation_stale") or stale_state.get("primer_stale") or stale_state.get("frame_stale"):
            _clear_validation_task_state_all()
    primers = ds.primers if isinstance(ds.primers, list) else []
    primer_summary = _with_primer_unavailable_status(_build_primer_risk_summary(primers), ds)

    _step_header(
        5,
        STEP5_COPY["step_title"],
        STEP5_COPY["step_purpose"],
        STEP5_COPY["step_bullets"],
    )

    has_frame = bool(isinstance(ds.frame, dict) and ds.frame.get("final_sequence"))
    render_flow_strip(
        [
            ("Input", "Assembled expression construct and active primer option"),
            ("Output", "Review-check result plus primer-risk summary"),
        ]
    )

    if stale_state.get("validation_stale"):
        _status_panel(
            STEP5_COPY["validation_stale_title"],
            f"{STEP5_COPY['validation_stale_reason']}. {STEP5_COPY['validation_stale_action']}.",
            tone="warn",
        )

    _section_label(STEP5_COPY["main_action"])
    if not has_frame:
        _status_panel(
            STEP5_COPY["validation_input_missing_title"],
            STEP5_COPY["validation_input_missing_body"],
            tone="warn",
        )
    else:
        _status_panel(
            STEP5_COPY["validation_input_ready_title"],
            STEP5_COPY["validation_input_ready_body"],
            tone="ready",
        )

    if st.button(
        STEP5_COPY["run_validation"],
        type="primary",
        key="wf_p5_validate",
        use_container_width=True,
        disabled=not has_frame,
    ):
        _start_validation_task(ds, ctrl)

    _poll_validation_task_if_needed(ds, ctrl)

    validation_complete = _has_completed_validation_result(ds, stale_state)
    validation_status = str(st.session_state.get("validation_task_status") or "idle")
    has_leftover_finished_task = validation_status == "finished" and not validation_complete
    validation_display_stale = bool(stale_state.get("validation_stale") or has_leftover_finished_task)
    if validation_display_stale and validation_status == "finished":
        validation_status = "idle"
    validation_presenter = build_async_status_presenter(
        "validation_task",
        title="Review-check task",
        status=validation_status,
        progress_builder=_validation_task_progress,
        detail_builder=_validation_task_detail,
        session_state=st.session_state,
    )
    if validation_status != "idle":
        render_async_task_feedback(
            title=validation_presenter["title"],
            status=validation_presenter["status"],
            progress=validation_presenter["progress"],
            detail=validation_presenter["detail"],
            task_id=validation_presenter["task_id"],
            error_text=validation_presenter["error_text"],
        )
        status_cols = st.columns(4)
        status_cols[0].metric("Task ID", validation_presenter["task_id"] or "—")
        status_cols[1].metric("Task status", validation_presenter["status"] or "idle")
        status_cols[2].metric("Progress", f"{validation_presenter['progress']}%")
        status_cols[3].metric("Poll cycles", validation_presenter["poll_count"])
        if validation_presenter["poll_enabled"]:
            poll_delay = _validation_poll_interval_seconds(validation_presenter["poll_count"])
            _schedule_validation_refresh(poll_delay)

    st.divider()
    _section_label(STEP5_COPY["validation_result"])
    if validation_complete:
        primer_summary = _with_primer_unavailable_status(_build_primer_risk_summary(primers), ds)
        validation_issues = ds.validation_results if isinstance(ds.validation_results, list) else []
        conclusion = _build_validation_conclusion(validation_issues)
        criticals = [i for i in validation_issues if i.get("severity") == "critical"]
        warnings = [i for i in validation_issues if i.get("severity") == "warning"]
        infos = [i for i in validation_issues if i.get("severity") == "info"]

        _status_panel(
            conclusion["title"],
            conclusion["summary"],
            tone=conclusion["tone"],
        )

        m1, m2, m3 = st.columns(3)
        m1.metric(STEP5_COPY["critical_issues"], len(criticals))
        m2.metric(STEP5_COPY["warnings"], len(warnings))
        m3.metric(STEP5_COPY["info"], len(infos))

        if criticals:
            color, bg, border = "#dc2626", "#fef2f2", "#fca5a5"
            text = (
                f"<strong>{len(criticals)} blocking issue(s)</strong> must be resolved before export."
                + (f" There {'is' if len(warnings) == 1 else 'are'} also {len(warnings)} warning(s)." if warnings else "")
            )
        elif conclusion["status"] == "high_risk_primer_review":
            color, bg, border = "#b45309", "#fff7ed", "#fdba74"
            text = (
                "Documentation checks completed, but primer risks require review. "
                "Step 4 still contains <strong>high-risk primer pairs</strong>. "
                "Do not treat this construct as documentation-review complete until the primer quality has been reviewed."
            )
        elif warnings:
            color, bg, border = "#d97706", "#fff7ed", "#fde68a"
            text = (
                f"No blocking issue was detected, but there {'is' if len(warnings) == 1 else 'are'} <strong>{len(warnings)} warning(s)</strong>. "
                "Manual review is recommended before export."
            )
        else:
            color, bg, border = "#15803d", "#f0fdf4", "#bbf7d0"
            text = "Current documentation checks found no recorded blockers; export records can be generated for review." + (
                f" You can also review {len(infos)} informational item(s)." if infos else ""
            )

        st.markdown(
            f"<div style='background:{bg};border:1px solid {border};border-radius:8px;padding:10px 14px;margin:8px 0 14px 0;font-size:.88rem;color:{color}'>{text}</div>",
            unsafe_allow_html=True,
        )

        _render_primer_risk_summary(primer_summary)
        _show_issues(validation_issues)
    else:
        if validation_display_stale:
            _status_panel(
                STEP5_COPY["validation_stale_title"],
                f"{STEP5_COPY['validation_stale_reason']}. {STEP5_COPY['validation_stale_action']}.",
                tone="warn",
            )
            _status_panel(
                STEP5_COPY["no_final_result_title"],
                STEP5_COPY["no_final_result_body"],
                tone="info",
            )
        else:
            _status_panel(
                STEP5_COPY["no_result_title"],
                STEP5_COPY["no_result_body"],
                tone="info",
            )
        _render_primer_risk_summary(primer_summary)

    st.divider()
    _section_label(STEP5_COPY["next"])

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
            button_key="wf_p5_report_md",
        )
    except Exception:
        pass

    _status_panel(
        "Protein structure analysis is deferred",
        "Protein structure analysis is deferred in the current MVP.",
        tone="info",
    )

