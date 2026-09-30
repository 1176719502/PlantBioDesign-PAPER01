from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession, SessionController
from core.session_keys import SK
from services.validation_summary_service import build_validation_run_state
from views.wizard_steps import step5_validation as step5


class _FakeColumn:
    def metric(self, *args, **kwargs):
        return None


class _FakeExpander:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def _patch_streamlit_session(monkeypatch):
    import streamlit as st

    monkeypatch.setattr(st, 'session_state', {})
    monkeypatch.setattr(st, 'rerun', lambda: None)


@pytest.fixture(autouse=True)
def _clear_validation_execution_mode(monkeypatch):
    monkeypatch.delenv('VALIDATION_EXECUTION_MODE', raising=False)


def _ctrl_with(ds: DesignSession) -> SessionController:
    import streamlit as st

    st.session_state.clear()
    st.session_state['design_session'] = ds
    return SessionController()


def _step5_ready_session() -> DesignSession:
    sequence = 'ATG' + 'GCC' * 20 + 'TAA'
    ds = DesignSession(
        step=5,
        gene_name='ValidationCase',
        original_seq=sequence,
        optimized_seq=sequence,
        host='E.coli BL21(DE3)',
        frame={'success': True, 'final_sequence': sequence},
        primers=[],
        validation_results=[],
    )
    ds.frame_context_signature = ds.current_frame_context_signature()
    ds.primer_context_signature = ds.current_primer_context_signature()
    return ds


def test_build_primer_risk_summary_skips_issue_for_all_recommended():
    primers = [
        {'Fragment Name': 'FragA', 'Quality Grade': 'Recommended', 'Quality Reasons': ['No major warning triggered.']},
        {'Fragment Name': 'FragB', 'Quality Grade': 'Recommended', 'Quality Reasons': ['No major warning triggered.']},
    ]

    summary = step5._build_primer_risk_summary(primers)

    assert summary['recommended'] == 2
    assert summary['usable_with_risk'] == 0
    assert summary['not_recommended'] == 0
    assert summary['issue'] is None


def test_build_primer_risk_summary_adds_review_warning_for_usable_with_risk():
    primers = [
        {
            'Fragment Name': 'FragA',
            'Quality Grade': 'Usable with Risk',
            'Quality Reasons': ['Annealing Tm is slightly offset from target (60.0°C).'],
        }
    ]

    summary = step5._build_primer_risk_summary(primers)

    assert summary['usable_with_risk'] == 1
    assert summary['issue'] is not None
    assert summary['issue']['severity'] == 'warning'
    assert summary['issue']['code'] == step5.PRIMER_REVIEW_CODE


def test_build_primer_risk_summary_adds_high_risk_warning_for_not_recommended():
    primers = [
        {
            'Fragment Name': 'FragA',
            'Quality Grade': 'Not Recommended',
            'Quality Reasons': ['High cross-dimer risk between primers (8 bp complementarity).'],
        }
    ]

    summary = step5._build_primer_risk_summary(primers)

    assert summary['not_recommended'] == 1
    assert summary['issue'] is not None
    assert summary['issue']['severity'] == 'warning'
    assert summary['issue']['code'] == step5.PRIMER_HIGH_RISK_CODE


def test_merge_validation_with_primer_risk_preserves_non_blocking_gate_behavior():
    base_issues = [
        {
            'severity': 'info',
            'code': 'PASS',
            'title': 'All validation checks passed',
            'why': 'No biological logic errors detected.',
            'fix': 'Proceed to primer design and cloning strategy.',
        }
    ]
    primers = [
        {
            'Fragment Name': 'FragA',
            'Quality Grade': 'Not Recommended',
            'Quality Reasons': ['High cross-dimer risk between primers (8 bp complementarity).'],
        }
    ]

    merged, _summary = step5._merge_validation_with_primer_risk(base_issues, primers)
    criticals = [issue for issue in merged if issue.get('severity') == 'critical']

    assert any(issue.get('code') == step5.PRIMER_HIGH_RISK_CODE for issue in merged)
    assert not criticals


def test_merge_validation_records_unavailable_primer_status():
    ds = _step5_ready_session()
    ds.primer_design_status = 'unavailable'
    ds.primer_backend_available = False
    ds.active_primer_pair = None
    ds.frame_context_signature = ds.current_frame_context_signature()
    ds.primer_context_signature = ds.current_primer_context_signature()
    base_issues = [
        {
            'severity': 'info',
            'code': 'PASS',
            'title': 'All validation checks passed',
            'why': 'No biological logic errors detected.',
            'fix': 'Continue documentation review.',
        }
    ]

    merged, summary = step5._merge_validation_with_primer_risk(base_issues, [], ds)

    assert any(issue.get('code') == step5.PRIMER_UNAVAILABLE_CODE for issue in merged)
    assert not any(issue.get('code') == 'PASS' for issue in merged)
    assert summary['primer_design_status'] == 'unavailable'


def test_step5_page_displays_unavailable_primer_status_safely(monkeypatch):
    ds = _step5_ready_session()
    ds.primer_design_status = 'unavailable'
    ds.primer_backend_available = False
    ds.active_primer_pair = None
    ds.frame_context_signature = ds.current_frame_context_signature()
    ds.primer_context_signature = ds.current_primer_context_signature()
    ds.validation_results = [
        {
            'severity': 'warning',
            'code': step5.PRIMER_UNAVAILABLE_CODE,
            'title': 'Primer candidate generation not enabled',
            'why': 'Step 4 recorded cassette boundary review context only; no primer candidate rows are recorded in this build.',
            'fix': 'Continue documentation-only review without treating primer status as generated.',
        }
    ]
    ds.validation_context_signature = ds.current_validation_context_signature()
    ctrl = _ctrl_with(ds)

    status_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(step5, '_step_header', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_section_label', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_show_issues', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_status_panel', lambda title, body, tone='info': status_calls.append((title, body, tone)))
    monkeypatch.setattr(step5.st, 'button', lambda *args, **kwargs: False)
    monkeypatch.setattr(step5.st, 'divider', lambda: None)
    monkeypatch.setattr(step5.st, 'columns', lambda n: tuple(_FakeColumn() for _ in range(n)))
    monkeypatch.setattr(step5.st, 'caption', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'markdown', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'progress', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'error', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'warning', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'success', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'expander', lambda *args, **kwargs: _FakeExpander())
    monkeypatch.setattr(step5.st, 'dataframe', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_schedule_validation_refresh', lambda *args, **kwargs: None)

    step5.page(ctrl)

    assert any(title == 'Primer candidate generation not enabled' and tone == 'info' for title, _body, tone in status_calls)
    assert any(
        title == step5.STEP5_COPY['review_required_title']
        for title, _body, _tone in status_calls
    )
    assert not any('Primer quality adds no extra warning' in title for title, _body, _tone in status_calls)


def test_step5_page_does_not_render_green_pass_copy_when_high_risk_primer_exists(monkeypatch):
    import streamlit as st

    ds = DesignSession(
        step=5,
        gene_name='RiskCase',
        original_seq='ATG' + 'GCC' * 20 + 'TAA',
        optimized_seq='ATG' + 'GCC' * 20 + 'TAA',
        host='E.coli BL21(DE3)',
        frame={
            'success': True,
            'final_sequence': 'ATG' + 'GCC' * 20 + 'TAA',
            'gc_content': 60.0,
            'gc_optimal_range': (40, 65),
            'kingdom': 'prokaryote',
            'features': [{'name': 'Target Gene (CDS)', 'type': 'CDS', 'start': 1, 'end': 66}],
            'rbs_name': 'Shine-Dalgarno B0034',
        },
        primers=[
            {
                'Fragment Name': 'FragA',
                'Quality Grade': 'Not Recommended',
                'Quality Reasons': ['High cross-dimer risk between primers (8 bp complementarity).'],
                'Warnings': ['High cross-dimer risk between primers (8 bp complementarity).'],
            }
        ],
        validation_results=[
            {
                'severity': 'warning',
                'code': step5.PRIMER_HIGH_RISK_CODE,
                'title': 'High-risk primer pair(s) detected',
                'why': 'Step 4 marked 1 primer pair as Not Recommended.',
                'fix': 'Return to Step 4 to review primer design before export.',
            },
            {
                'severity': 'info',
                'code': 'PASS',
                'title': 'All validation checks passed',
                'why': 'No biological logic errors detected.',
                'fix': 'Proceed to primer design and cloning strategy.',
            },
        ],
    )
    ctrl = _ctrl_with(ds)

    markdown_calls: list[str] = []
    status_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(step5, '_step_header', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_section_label', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_show_issues', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_status_panel', lambda title, body, tone='info': status_calls.append((title, body, tone)))
    monkeypatch.setattr(step5.st, 'button', lambda *args, **kwargs: False)
    monkeypatch.setattr(step5.st, 'divider', lambda: None)
    monkeypatch.setattr(step5.st, 'columns', lambda n: tuple(_FakeColumn() for _ in range(n)))
    monkeypatch.setattr(step5.st, 'caption', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'markdown', lambda text, **kwargs: markdown_calls.append(text))
    monkeypatch.setattr(step5.st, 'progress', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'error', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'warning', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'success', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'expander', lambda *args, **kwargs: _FakeExpander())
    monkeypatch.setattr(step5.st, 'dataframe', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_schedule_validation_refresh', lambda *args, **kwargs: None)

    step5.page(ctrl)

    assert any('high-risk primers still require review' in title for title, _body, _tone in status_calls)
    assert any('high-risk primer pairs' in text for text in markdown_calls)
    assert any('Documentation checks completed, but primer risks require review' in text for text in markdown_calls)
    assert not any('All validation checks passed' in text for text in markdown_calls)
    assert not any('Current documentation checks found no recorded blockers; export records can be generated for review.' in text for text in markdown_calls)


def test_start_validation_task_local_sync_clean_validation(monkeypatch):
    import streamlit as st

    st.session_state.clear()
    step5._initialize_validation_task_state()
    ds = _step5_ready_session()
    ctrl = _ctrl_with(ds)

    monkeypatch.setattr(
        step5,
        'run_or_enqueue_validation',
        lambda payload: {
            'mode': 'local',
            'status': 'finished',
            'result': {'issues': [], 'primer_summary': {}},
        },
    )

    step5._start_validation_task(ds, ctrl)

    updated = ctrl.get()
    assert updated.validation_results == []
    assert updated.validation_context_signature == updated.current_validation_context_signature()
    assert st.session_state['validation_task_status'] == 'finished'
    assert st.session_state['validation_task_progress'] == 100
    assert st.session_state['validation_task_poll_enabled'] is False
    assert build_validation_run_state(updated)['status'] == 'completed_passed'


def test_start_validation_task_local_sync_warning_validation(monkeypatch):
    ds = _step5_ready_session()
    ctrl = _ctrl_with(ds)

    monkeypatch.setattr(
        step5,
        'run_or_enqueue_validation',
        lambda payload: {
            'mode': 'local',
            'status': 'finished',
            'result': {
                'issues': [
                    {
                        'severity': 'warning',
                        'code': 'MANUAL_REVIEW',
                        'title': 'Manual review',
                        'why': 'A warning was detected.',
                        'fix': 'Review the construct.',
                    }
                ]
            },
        },
    )

    step5._start_validation_task(ds, ctrl)

    assert build_validation_run_state(ctrl.get())['status'] == 'completed_review'


def test_start_validation_task_local_sync_critical_validation(monkeypatch):
    import streamlit as st

    ds = _step5_ready_session()
    ctrl = _ctrl_with(ds)

    monkeypatch.setattr(
        step5,
        'run_or_enqueue_validation',
        lambda payload: {
            'mode': 'local',
            'status': 'finished',
            'result': {
                'issues': [
                    {
                        'severity': 'critical',
                        'code': 'FRAME_ERROR',
                        'title': 'Frame issue',
                        'why': 'A blocking issue was detected.',
                        'fix': 'Resolve the frame issue.',
                    }
                ]
            },
        },
    )

    step5._start_validation_task(ds, ctrl)

    updated = ctrl.get()
    assert build_validation_run_state(updated)['status'] == 'completed_blocked'
    st.session_state['design_session'] = updated
    assert SessionController().can_advance is False


def test_start_validation_task_local_sync_exception(monkeypatch):
    import streamlit as st

    st.session_state.clear()
    ds = _step5_ready_session()
    ctrl = _ctrl_with(ds)
    step5._initialize_validation_task_state()
    error_calls: list[str] = []

    def _raise_validation_error(payload):
        raise RuntimeError('local validation crashed')

    monkeypatch.setattr(step5, 'run_or_enqueue_validation', _raise_validation_error)
    monkeypatch.setattr(step5.st, 'error', lambda text: error_calls.append(text))

    step5._start_validation_task(ds, ctrl)

    updated = ctrl.get()
    assert st.session_state['validation_task_status'] == 'failed'
    assert st.session_state['validation_task_progress'] == 100
    assert st.session_state['validation_task_poll_enabled'] is False
    assert st.session_state['validation_task_error']
    assert updated.validation_context_signature == ''
    assert build_validation_run_state(updated)['status'] != 'completed_passed'
    assert any('Review-check tool unavailable or review-check task failed' in text for text in error_calls)


def test_start_validation_task_async_mode_remains_available(monkeypatch):
    import streamlit as st

    st.session_state.clear()
    ds = _step5_ready_session()
    ctrl = _ctrl_with(ds)
    step5._initialize_validation_task_state()

    monkeypatch.setenv('VALIDATION_EXECUTION_MODE', 'async')
    monkeypatch.setattr(
        step5,
        'run_or_enqueue_validation',
        lambda payload: {
            'mode': 'async',
            'status': 'queued',
            'task': {'task_id': 'task-123', 'status': 'queued'},
        },
    )

    step5._start_validation_task(ds, ctrl)

    assert st.session_state['validation_task_id'] == 'task-123'
    assert st.session_state['validation_task_status'] == 'queued'
    assert st.session_state['validation_task_progress'] == 20
    assert st.session_state['validation_task_poll_enabled'] is True


def test_refresh_validation_task_status_updates_started_state(monkeypatch):
    import streamlit as st

    ds = _step5_ready_session()
    ctrl = _ctrl_with(ds)
    step5._initialize_validation_task_state()
    st.session_state['validation_task_id'] = 'task-123'
    st.session_state['validation_task_poll_enabled'] = True

    monkeypatch.setattr(step5, 'get_validation_task', lambda task_id: {'task_id': task_id, 'status': 'started', 'result': None, 'error': ''})
    monkeypatch.setattr(step5.time, 'time', lambda: 5.0)

    step5._refresh_validation_task_status(ds, ctrl)

    assert st.session_state['validation_task_status'] == 'started'
    assert st.session_state['validation_task_progress'] == 65
    assert st.session_state['validation_task_poll_enabled'] is True
    assert 'Poll cycle 1' in st.session_state['validation_task_detail']


def test_refresh_validation_task_status_applies_finished_results(monkeypatch):
    import streamlit as st

    ds = DesignSession(
        step=5,
        gene_name='ValidateAsync',
        original_seq='ATG' + 'GCC' * 20 + 'TAA',
        optimized_seq='ATG' + 'GCC' * 20 + 'TAA',
        host='E.coli BL21(DE3)',
        frame={'success': True, 'final_sequence': 'ATG' + 'GCC' * 20 + 'TAA'},
        primers=[],
        validation_results=[],
    )
    ctrl = _ctrl_with(ds)
    step5._initialize_validation_task_state()
    st.session_state['validation_task_id'] = 'task-123'
    st.session_state['validation_task_poll_enabled'] = True
    st.session_state[SK.VALIDATION_TASK_CONTEXT_SIGNATURE] = ds.current_validation_context_signature()

    monkeypatch.setattr(step5, 'get_validation_task', lambda task_id: {'task_id': task_id, 'status': 'finished', 'result': {'issues': []}, 'error': ''})
    monkeypatch.setattr(step5.time, 'time', lambda: 5.0)
    monkeypatch.setattr(step5.st, 'success', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'info', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'warning', lambda *args, **kwargs: None)

    step5._refresh_validation_task_status(ds, ctrl)

    updated = ctrl.get()
    assert updated.validation_results == []
    assert updated.validation_context_signature
    assert st.session_state['validation_task_status'] == 'finished'
    assert st.session_state['validation_task_progress'] == 100
    assert st.session_state['validation_task_poll_enabled'] is False


def test_step5_page_treats_empty_issues_as_completed_pass(monkeypatch):
    ds = DesignSession(
        step=5,
        gene_name='EmptyIssueCase',
        original_seq='ATG' + 'GCC' * 20 + 'TAA',
        optimized_seq='ATG' + 'GCC' * 20 + 'TAA',
        host='E.coli BL21(DE3)',
        frame={'success': True, 'final_sequence': 'ATG' + 'GCC' * 20 + 'TAA'},
        primers=[],
        validation_results=[],
    )
    ds.frame_context_signature = ds.current_frame_context_signature()
    ds.primer_context_signature = ds.current_primer_context_signature()
    ds.validation_context_signature = ds.current_validation_context_signature()
    ctrl = _ctrl_with(ds)

    markdown_calls: list[str] = []
    status_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(step5, '_step_header', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_section_label', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_show_issues', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_status_panel', lambda title, body, tone='info': status_calls.append((title, body, tone)))
    monkeypatch.setattr(step5.st, 'button', lambda *args, **kwargs: False)
    monkeypatch.setattr(step5.st, 'divider', lambda: None)
    monkeypatch.setattr(step5.st, 'columns', lambda n: tuple(_FakeColumn() for _ in range(n)))
    monkeypatch.setattr(step5.st, 'caption', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'markdown', lambda text, **kwargs: markdown_calls.append(text))
    monkeypatch.setattr(step5.st, 'progress', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'error', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'warning', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'success', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'expander', lambda *args, **kwargs: _FakeExpander())
    monkeypatch.setattr(step5.st, 'dataframe', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_schedule_validation_refresh', lambda *args, **kwargs: None)

    step5.page(ctrl)

    assert any(title == 'Documentation checks completed' and tone == 'ready' for title, _body, tone in status_calls)
    assert any('Current documentation checks found no recorded blockers; export records can be generated for review.' in text for text in markdown_calls)
    assert not any(title == 'No validation result yet' for title, _body, _tone in status_calls)


def test_step5_page_clears_stale_validation_result(monkeypatch):
    import streamlit as st

    ds = DesignSession(
        step=5,
        gene_name='StaleValidationCase',
        original_seq='ATG' + 'GCC' * 20 + 'TAA',
        optimized_seq='ATG' + 'GCC' * 20 + 'TAA',
        host='E.coli BL21(DE3)',
        tag='No tag',
        frame={
            'success': True,
            'final_sequence': 'ATG' + 'GCC' * 20 + 'TAA',
            'gc_content': 60.0,
            'features': [],
        },
        primers=[
            {
                'Fragment Name': 'FragA',
                "Forward Primer (5'->3')": 'ATGGCCATGGCCATGGCC',
                "Reverse Primer (5'->3')": 'GGCCATGGCCATGGCCAT',
                'Quality Grade': 'Recommended',
            }
        ],
        validation_results=[
            {
                'severity': 'info',
                'code': 'PASS',
                'title': 'All validation checks passed',
                'why': 'No biological logic errors detected.',
                'fix': 'Proceed to primer design and cloning strategy.',
            }
        ],
        validation_context_signature='stale-validation-signature',
    )
    ds.frame_context_signature = ds.current_frame_context_signature()
    ds.primer_context_signature = ds.current_primer_context_signature()
    ctrl = _ctrl_with(ds)

    status_calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(step5, '_step_header', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_section_label', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_show_issues', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_status_panel', lambda title, body, tone='info': status_calls.append((title, body, tone)))
    monkeypatch.setattr(step5.st, 'button', lambda *args, **kwargs: False)
    monkeypatch.setattr(step5.st, 'divider', lambda: None)
    monkeypatch.setattr(step5.st, 'columns', lambda n: tuple(_FakeColumn() for _ in range(n)))
    monkeypatch.setattr(step5.st, 'caption', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'markdown', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'progress', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'error', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'warning', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'success', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'expander', lambda *args, **kwargs: _FakeExpander())
    monkeypatch.setattr(step5.st, 'dataframe', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_schedule_validation_refresh', lambda *args, **kwargs: None)

    step5.page(ctrl)

    updated = ctrl.get()


def test_step5_after_primer_redesign_with_cleared_result_hides_completed_task_status(monkeypatch):
    import streamlit as st

    sequence = 'ATG' + 'GCC' * 20 + 'TAA'
    new_primer = {
        'Fragment Name': 'FragA',
        "Forward Primer (5'->3')": 'GCCGCCGCCGCCGCCGCC',
        "Reverse Primer (5'->3')": 'TAATAATAATAATAATAA',
        'Quality Grade': 'Recommended',
    }
    ds = DesignSession(
        step=5,
        gene_name='PrimerRedesignStaleCase',
        original_seq=sequence,
        optimized_seq=sequence,
        host='E.coli BL21(DE3)',
        tag='No tag',
        frame={
            'success': True,
            'final_sequence': sequence,
            'gc_content': 60.0,
            'features': [],
        },
        primers=[new_primer],
        validation_results=[],
        validation_context_signature='',
    )
    ds.frame_context_signature = ds.current_frame_context_signature()
    ds.primer_context_signature = ds.current_primer_context_signature()
    ctrl = _ctrl_with(ds)

    st.session_state['validation_task_status'] = 'finished'
    st.session_state['validation_task_progress'] = 100
    st.session_state['validation_task_detail'] = 'Validation is complete. The latest results are shown below.'

    status_calls: list[tuple[str, str, str]] = []
    async_feedback_calls: list[dict] = []

    monkeypatch.setattr(step5, '_step_header', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_section_label', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_show_issues', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_status_panel', lambda title, body, tone='info': status_calls.append((title, body, tone)))
    monkeypatch.setattr(step5, 'render_async_task_feedback', lambda **kwargs: async_feedback_calls.append(kwargs))
    monkeypatch.setattr(step5.st, 'button', lambda *args, **kwargs: False)
    monkeypatch.setattr(step5.st, 'divider', lambda: None)
    monkeypatch.setattr(step5.st, 'columns', lambda n: tuple(_FakeColumn() for _ in range(n)))
    monkeypatch.setattr(step5.st, 'caption', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'markdown', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'progress', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'error', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'warning', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'success', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5.st, 'expander', lambda *args, **kwargs: _FakeExpander())
    monkeypatch.setattr(step5.st, 'dataframe', lambda *args, **kwargs: None)
    monkeypatch.setattr(step5, '_schedule_validation_refresh', lambda *args, **kwargs: None)

    step5.page(ctrl)

    updated = ctrl.get()
    assert updated.validation_results == []
    assert updated.validation_context_signature == ''
    assert build_validation_run_state(updated)['status'] == 'not_run'
    assert SessionController().can_advance is False
    assert any(
        title == 'Review checks need rerun'
        and 'Active primer option changed after the last review-check run' in body
        and 'Run review checks again before delivery/export' in body
        and tone == 'warn'
        for title, body, tone in status_calls
    )
    assert any(
        title == 'No final review-check result yet'
        and tone == 'info'
        for title, _body, tone in status_calls
    )
    assert not any(call.get('status') == 'finished' for call in async_feedback_calls)
