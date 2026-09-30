from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession, SessionController
from services.export_recommendation_service import build_export_recommendation
from services.report_service import generate_report_content
from services.validation_summary_service import PRIMER_UNAVAILABLE_CODE, build_validation_run_state
from views.wizard_steps import step6_export


def _base_session() -> DesignSession:
    sequence = "ATG" + ("GCC" * 20) + "TAA"
    ds = DesignSession(
        step=6,
        gene_name="Step6StateCase",
        original_seq=sequence,
        optimized_seq=sequence,
        host="E.coli BL21(DE3)",
        frame={
            "success": True,
            "final_sequence": sequence,
            "total_length": len(sequence),
            "gc_content": 51.2,
            "parts": [{"name": "CDS", "type": "CDS", "seq": sequence}],
        },
        cloning_method="Gibson Assembly",
        primers=[
            {
                "Fragment Name": "FragA",
                "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
                "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
                "Quality Grade": "Recommended",
                "Quality Reasons": ["Balanced primer Tm."],
                "Warnings": [],
            }
        ],
        validation_results=[],
        validation_context_signature="",
    )
    ds.primer_context_signature = ds.current_primer_context_signature()
    return ds


def _delivery_ready(ds: DesignSession, state: dict) -> bool:
    return bool(
        ds.final_sequence
        and state["is_complete"]
        and not state["is_stale"]
        and not state["is_running"]
        and not state["is_failed"]
        and state["critical_count"] == 0
    )


def test_validation_not_run_is_not_ready_and_report_is_not_run():
    ds = _base_session()

    state = build_validation_run_state(ds)
    recommendation = build_export_recommendation(
        ds.validation_results,
        ds.primers,
        ds.final_sequence,
        validation_complete=state["is_complete"],
    )
    report = generate_report_content(ds)

    assert state["status"] == "not_run"
    assert _delivery_ready(ds, state) is False
    assert recommendation["recommendation"] == "Review blocked by unresolved risk signals"
    assert report["step_alignment"]["step5"]["status"] == "not_run"
    assert report["file_export_notes"]["validation_complete"] is False


def test_step5_can_advance_with_completed_empty_validation_result(monkeypatch):
    import streamlit as st

    fake_state = {}
    monkeypatch.setattr(st, "session_state", fake_state)
    monkeypatch.setattr(st, "rerun", lambda: None)

    ds = _base_session()
    ds.step = 5
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()
    st.session_state["design_session"] = ds

    state = build_validation_run_state(ds)

    assert state["status"] == "completed_passed"
    assert SessionController().can_advance is True

    ds = _base_session()
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()

    state = build_validation_run_state(ds)
    recommendation = build_export_recommendation(
        ds.validation_results,
        ds.primers,
        ds.final_sequence,
        validation_complete=state["is_complete"],
    )
    report = generate_report_content(ds)

    assert state["status"] == "completed_passed"
    assert state["critical_count"] == 0
    assert state["warning_count"] == 0
    assert _delivery_ready(ds, state) is True
    assert recommendation["recommendation"] == "Documentation Export Available"
    assert report["step_alignment"]["step5"]["status"] == "passed"
    assert report["file_export_notes"]["validation_complete"] is True


def test_step6_blocks_ready_when_active_primer_is_not_recommended_even_if_validation_lacks_primer_issue():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "ActiveHighRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Not Recommended",
            "Quality Reasons": ["High primer interaction risk."],
        }
    ]
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()

    state = build_validation_run_state(ds)
    recommendation = build_export_recommendation(
        ds.validation_results,
        ds.primers,
        ds.final_sequence,
        validation_complete=state["is_complete"],
    )
    report = generate_report_content(ds)

    assert state["status"] == "completed_passed"
    assert recommendation["recommendation"] == "Review blocked by unresolved risk signals"
    assert recommendation["primer_high_risk_count"] == 1
    assert recommendation["primer_review_count"] == 0
    assert recommendation["primer_action_required_count"] == 1
    assert report["export_recommendation"]["recommendation"] == "Review blocked by unresolved risk signals"
    assert report["step_alignment"]["step6"]["status"] == "Review blocked by unresolved risk signals"


def test_step6_keeps_unavailable_primer_status_documentation_only():
    ds = _base_session()
    ds.primers = []
    ds.primer_design_status = "unavailable"
    ds.primer_backend_available = False
    ds.active_primer_pair = None
    ds.primer_context_signature = ds.current_primer_context_signature()
    ds.validation_results = [
        {
            "severity": "warning",
            "code": PRIMER_UNAVAILABLE_CODE,
            "title": "Primer candidate generation not enabled",
            "why": "Step 4 recorded cassette boundary review context only; no primer candidate rows are recorded in this build.",
            "fix": "Continue documentation-only review without treating primer status as generated.",
        }
    ]
    ds.validation_context_signature = ds.current_validation_context_signature()

    state = build_validation_run_state(ds)
    recommendation = build_export_recommendation(
        ds.validation_results,
        ds.primers,
        ds.final_sequence,
        validation_complete=state["is_complete"],
    )
    report = generate_report_content(ds)

    assert state["status"] == "completed_review"
    assert recommendation["recommendation"] == "Export with Review Required"
    assert "documentation-only" in recommendation["conclusion"]
    assert report["export_recommendation"]["recommendation"] == "Export with Review Required"


def test_failed_validation_task_without_completed_result_is_not_ready():
    ds = _base_session()

    state = build_validation_run_state(
        ds,
        task_status="failed",
        task_error="Validation tool unavailable or validation task failed",
    )

    assert state["status"] == "failed"
    assert state["is_failed"] is True
    assert _delivery_ready(ds, state) is False


def test_running_validation_task_without_completed_result_is_not_ready():
    ds = _base_session()

    state = build_validation_run_state(ds, task_status="queued")

    assert state["status"] == "running"
    assert state["is_running"] is True
    assert _delivery_ready(ds, state) is False


def test_stale_validation_is_not_reported_as_passed_or_ready():
    ds = _base_session()
    ds.validation_results = []
    ds.validation_context_signature = "stale-validation-signature"

    state = build_validation_run_state(ds)
    recommendation = build_export_recommendation(
        ds.validation_results,
        ds.primers,
        ds.final_sequence,
        validation_complete=state["is_complete"],
    )
    report = generate_report_content(ds)

    assert state["status"] == "stale"
    assert state["is_stale"] is True
    assert _delivery_ready(ds, state) is False
    assert recommendation["recommendation"] == "Review blocked by unresolved risk signals"
    assert report["step_alignment"]["step5"]["status"] == "stale"
    assert report["file_export_notes"]["validation_complete"] is False


def test_critical_validation_issue_blocks_delivery_and_export_recommendation():
    ds = _base_session()
    ds.validation_results = [
        {
            "severity": "critical",
            "code": "FRAME_ERROR",
            "title": "Frame issue",
            "why": "A blocking issue was detected.",
            "fix": "Resolve the frame issue.",
        }
    ]
    ds.validation_context_signature = ds.current_validation_context_signature()

    state = build_validation_run_state(ds)
    recommendation = build_export_recommendation(
        ds.validation_results,
        ds.primers,
        ds.final_sequence,
        validation_complete=state["is_complete"],
    )

    assert state["status"] == "completed_blocked"
    assert state["critical_count"] == 1
    assert _delivery_ready(ds, state) is False
    assert recommendation["recommendation"] == "Review blocked by unresolved risk signals"


def test_step6_treats_validation_from_old_primer_option_as_stale_not_ready():
    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "OptionA",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Recommended",
        }
    ]
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()
    assert build_validation_run_state(ds)["status"] == "completed_passed"

    ds.primers = [
        {
            "Fragment Name": "OptionB",
            "Forward Primer (5'->3')": "GCCGCCGCCGCCGCCGCC",
            "Reverse Primer (5'->3')": "TAATAATAATAATAATAA",
            "Quality Grade": "Usable with Risk",
        }
    ]

    state = build_validation_run_state(ds)
    recommendation = build_export_recommendation(
        ds.validation_results,
        ds.primers,
        ds.final_sequence,
        validation_complete=state["is_complete"],
    )

    assert state["status"] == "stale"
    assert state["is_stale"] is True
    assert state["is_complete"] is False
    assert _delivery_ready(ds, state) is False
    assert recommendation["recommendation"] == "Review blocked by unresolved risk signals"


def test_step6_handoff_is_disabled_when_final_recommendation_is_not_ready(monkeypatch):
    import streamlit as st

    ds = _base_session()
    ds.primers = [
        {
            "Fragment Name": "ActiveHighRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Not Recommended",
        }
    ]
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()

    button_calls = []
    status_calls = []

    class _FakeColumn:
        def metric(self, *args, **kwargs):
            return None

        def markdown(self, *args, **kwargs):
            return None

        def download_button(self, *args, **kwargs):
            return False

        def button(self, *args, **kwargs):
            return False

    class _FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeController:
        def get(self):
            return ds

    monkeypatch.setattr(st, "session_state", {})
    monkeypatch.setattr(step6_export, "_step_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_section_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        step6_export,
        "_status_panel",
        lambda title, body, tone="info": status_calls.append((title, body, tone)),
    )
    monkeypatch.setattr(
        step6_export.st,
        "columns",
        lambda n: tuple(_FakeColumn() for _ in range(n if isinstance(n, int) else len(n))),
    )
    monkeypatch.setattr(step6_export.st, "metric", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export.st, "divider", lambda: None)
    monkeypatch.setattr(step6_export.st, "expander", lambda *args, **kwargs: _FakeExpander())
    monkeypatch.setattr(step6_export.st, "button", lambda *args, **kwargs: button_calls.append((args, kwargs)) or False)
    monkeypatch.setattr(step6_export.st, "download_button", lambda *args, **kwargs: False)
    monkeypatch.setattr(step6_export.st, "pyplot", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_render_plasmid_png", lambda *args, **kwargs: (object(), b"png"))
    monkeypatch.setattr(step6_export, "_render_step6_report_display", lambda *args, **kwargs: None)

    step6_export.page(_FakeController())

    handoff_buttons = [call for call in button_calls if call[0] and call[0][0] == "Send to Assembly and Cloning"]
    assert handoff_buttons
    assert handoff_buttons[0][1]["disabled"] is True
    help_text = handoff_buttons[0][1]["help"]
    assert "Resolve primer risks" in help_text
    assert "rerun review checks" in help_text
    assert "supporting assembly preview workspace" in help_text
    assert any(
        "Assembly preview workspace" in title
        and "Resolve primer risks" in body
        and "rerun review checks" in body
        and "supporting assembly preview workspace" in body
        for title, body, _tone in status_calls
    )
