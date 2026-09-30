from __future__ import annotations

import os
import subprocess
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from core.design_session import DesignSession, SessionController
from core.primer_utils import Primer3BackendStatus
from views.wizard_steps import step4_cloning_primers as step4


ASYNC_PRIMER_PHASE4_REASON = "Deferred Phase 4 async primer queue / polling UI; not part of current MVP gate."


class _FakeContainer:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeExpander(_FakeContainer):
    pass


class _FakeEmpty:
    def container(self):
        return _FakeContainer()


class _FakeColumn:
    def __init__(self, button_results: list[bool] | None = None):
        self._button_results = list(button_results or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def metric(self, *args, **kwargs):
        return None

    def plotly_chart(self, *args, **kwargs):
        return None

    def button(self, *args, **kwargs):
        if self._button_results:
            return self._button_results.pop(0)
        return False


class _ButtonColumnsFactory:
    def __init__(self, mapping: dict[int, list[bool]] | None = None):
        self._mapping = {key: list(value) for key, value in (mapping or {}).items()}

    def __call__(self, spec):
        if isinstance(spec, int):
            count = spec
        else:
            count = len(spec)
        button_results = self._mapping.get(count, [])
        return tuple(_FakeColumn([button_results[idx]] if idx < len(button_results) else []) for idx in range(count))


class _DirectButtonFactory:
    def __init__(self, mapping: dict[str, list[bool] | bool] | None = None):
        self._mapping: dict[str, list[bool]] = {}
        for key, value in (mapping or {}).items():
            if isinstance(value, list):
                self._mapping[key] = list(value)
            else:
                self._mapping[key] = [value]

    def __call__(self, label, *args, **kwargs):
        key = kwargs.get('key') or label
        values = self._mapping.get(key, [])
        if values:
            return values.pop(0)
        return False


@pytest.fixture(autouse=True)
def _patch_streamlit_session(monkeypatch):
    import streamlit as st

    monkeypatch.setattr(st, 'session_state', {})
    monkeypatch.setattr(st, 'rerun', lambda: None)


def _ctrl_with(ds: DesignSession) -> SessionController:
    import streamlit as st

    st.session_state.clear()
    st.session_state['design_session'] = ds
    return SessionController()


def _prime_step4_page(
    monkeypatch,
    *,
    button_map: dict[int, list[bool]] | None = None,
    direct_button_map: dict[str, list[bool] | bool] | None = None,
    patch_plan_summary: bool = True,
):
    monkeypatch.setattr(step4.st, 'empty', lambda: _FakeEmpty())
    monkeypatch.setattr(step4.st, 'columns', _ButtonColumnsFactory(button_map))
    monkeypatch.setattr(step4.st, 'button', _DirectButtonFactory(direct_button_map))
    monkeypatch.setattr(step4.st, 'caption', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'divider', lambda: None)
    monkeypatch.setattr(step4.st, 'slider', lambda label, *args, **kwargs: kwargs.get('value', args[2] if len(args) >= 3 else args[0]))
    monkeypatch.setattr(step4.st, 'success', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'warning', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'error', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'info', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'dataframe', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'code', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'pyplot', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'progress', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'expander', lambda *args, **kwargs: _FakeExpander())
    monkeypatch.setattr(step4, '_step_header', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, '_section_label', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, '_status_panel', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, '_frame_summary_card', lambda *args, **kwargs: None)
    if patch_plan_summary:
        monkeypatch.setattr(step4, '_render_best_plan_summary', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, '_render_primer_quality_summary', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, '_render_primer_table', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, '_render_structured_primer_results', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, 'render_async_task_feedback', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, '_schedule_async_refresh', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, 'get_primer3_backend_status', lambda *, probe=False: Primer3BackendStatus(True, ""))


def _make_step4_session() -> tuple[DesignSession, SessionController]:
    import streamlit as st

    ds = DesignSession(
        step=4,
        gene_name='PrimerAsync',
        original_seq='ATG' + 'GCC' * 30 + 'TAA',
        optimized_seq='ATG' + 'GCC' * 30 + 'TAA',
        host='E.coli BL21(DE3)',
        tag='No tag',
        frame={
            'success': True,
            'final_sequence': 'ATG' + 'GCC' * 30 + 'TAA',
            'parts': [],
            'total_length': 96,
            'gc_content': 60.0,
        },
    )
    ctrl = _ctrl_with(ds)
    st.session_state[step4.SK.ACTIVE_HOST] = ds.host
    st.session_state[step4.SK.ACTIVE_SEQ] = ds.frame['final_sequence']
    return ds, ctrl


def test_step4_reframed_as_cassette_boundary_review_with_frame_content(monkeypatch):
    import streamlit as st
    from core.i18n import t
    from views.wizard_steps._shared import _steps

    ds, ctrl = _make_step4_session()
    ds.frame['parts'] = [
        {'name': 'Promoter', 'type': 'promoter', 'seq': 'TTGACA' * 3},
        {'name': 'CDS', 'type': 'CDS', 'seq': ds.optimized_seq},
        {'name': 'Terminator', 'type': 'terminator', 'seq': 'GCATGC' * 3},
    ]
    ds.frame['final_sequence'] = ''.join(part['seq'] for part in ds.frame['parts'])
    ds.frame['total_length'] = len(ds.frame['final_sequence'])
    ctrl.save(ds)
    st.session_state[step4.SK.ACTIVE_SEQ] = ds.frame['final_sequence']

    original_frame_summary = step4._frame_summary_card
    header_calls: list[tuple[int, str, str, list[str]]] = []
    section_calls: list[str] = []
    caption_calls: list[str] = []
    metric_calls: list[tuple[str, object]] = []
    expander_calls: list[str] = []
    button_calls: list[str] = []

    _prime_step4_page(monkeypatch, button_map={2: [False, False]})
    monkeypatch.setattr(
        step4,
        '_step_header',
        lambda step, title, purpose, bullets=None: header_calls.append((step, title, purpose, list(bullets or []))),
    )
    monkeypatch.setattr(step4, '_section_label', lambda text: section_calls.append(str(text)))
    monkeypatch.setattr(step4, '_frame_summary_card', original_frame_summary)
    monkeypatch.setattr(step4.st, 'caption', lambda body, *args, **kwargs: caption_calls.append(str(body)))
    monkeypatch.setattr(step4.st, 'expander', lambda label, *args, **kwargs: expander_calls.append(str(label)) or _FakeExpander())
    monkeypatch.setattr(_FakeColumn, 'metric', lambda self, label, value, *args, **kwargs: metric_calls.append((str(label), value)))
    monkeypatch.setattr(step4, '_column_aware_button', lambda column, label, **kwargs: button_calls.append(str(label)) or False)
    monkeypatch.setattr(
        step4,
        'get_primer3_backend_status',
        lambda *, probe=False: Primer3BackendStatus(False, 'backend unavailable'),
    )
    monkeypatch.setattr(step4, '_poll_primer_task_if_needed', lambda *args, **kwargs: None)

    step4.page(ctrl)

    assert t('wizard.step4.short') == 'Cassette / Boundary Review'
    assert _steps()[3] == 'Cassette / Boundary Review'
    assert header_calls
    header_text = ' '.join([header_calls[0][1], header_calls[0][2], *header_calls[0][3]])
    assert 'Cassette / Boundary Review' in header_text
    assert 'assembled expression frame' in header_text
    assert 'not a primer design engine' in header_text
    assert 'sequence validation' in header_text
    assert 'cloning feasibility verification' in header_text
    assert 'experimental readiness approval' in header_text
    assert 'Cassette Outer-Primer Design' not in header_text

    assert 'Frame summary' in section_calls
    assert 'Construct/cassette map preview' in section_calls
    assert 'Optional primer candidate placeholder' in section_calls
    assert ('Frame length', f"{ds.frame['total_length']:,} bp") in metric_calls
    assert ('GC content', '60.0%') in metric_calls
    assert ('CDS length', f"{len(ds.optimized_seq):,} bp") in metric_calls
    assert 'View assembled sequence' in expander_calls
    assert 'Preview construct/cassette map' in expander_calls

    rendered = ' '.join(caption_calls + button_calls)
    assert 'Outer-primer candidate generation is not enabled in this build' in rendered
    assert 'does not affect generated primers' in rendered
    assert 'Review primers' not in rendered
    assert 'Primer design engine unavailable' not in rendered
    assert 'ready for execution' not in rendered.lower()
    assert 'experiment-ready' not in rendered.lower()
    assert 'production-ready' not in rendered.lower()
    assert 'validated construct' not in rendered.lower()
    assert 'optimized pathway' not in rendered.lower()
    assert 'yield prediction' not in rendered.lower()
    assert ctrl.can_advance is True


def test_step4_not_recommended_primer_copy_requires_review(monkeypatch):
    ds, ctrl = _make_step4_session()
    ds.primers = [
        {
            'Fragment Name': 'Expression cassette',
            "Forward Primer (5'->3')": 'ATGGCCATGGCCATGGCC',
            "Reverse Primer (5'->3')": 'TTACCGGTTAACCGGTTA',
            'Quality Grade': 'Not Recommended',
            'Quality Reasons': ['High cross-dimer risk between primers.'],
            'Warnings': ['High cross-dimer risk between primers.'],
        }
    ]
    ds.step4_plan_summary = {
        'design_scope': 'expression_cassette',
        'selected_result_index': 0,
        'selected_target_tm': 60.0,
        'structured_results': [
            {
                'name': 'Expression cassette',
                'quality_grade': 'Not Recommended',
                'quality_score': 42,
                'quality_reasons': ['High cross-dimer risk between primers.'],
                'product_size': len(ds.frame['final_sequence']),
                'target_tm': 60.0,
                'tm_gap': 4.5,
                'hetero_dimer_risk': 'High',
                'pair_warnings': ['High cross-dimer risk between primers.'],
                'primers': [],
            }
        ],
    }
    ds.primer_context_host = ds.host
    ds.primer_context_seq_hash = step4._seq_hash(ds.frame['final_sequence'])
    ds.primer_context_signature = ds.current_primer_context_signature()
    ctrl.save(ds)

    status_calls: list[tuple[str, str, str]] = []
    metric_calls: list[tuple[str, object]] = []

    _prime_step4_page(monkeypatch, button_map={2: [False, False]}, patch_plan_summary=False)
    monkeypatch.setattr(step4, '_status_panel', lambda title, body, tone='info': status_calls.append((title, body, tone)))
    monkeypatch.setattr(_FakeColumn, 'metric', lambda self, label, value, *args, **kwargs: metric_calls.append((label, value)))
    monkeypatch.setattr(step4, '_poll_primer_task_if_needed', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, 'render_report_preview_container', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, 'render_report_download_button', lambda *args, **kwargs: None)

    step4.page(ctrl)

    rendered_status_text = ' '.join(f'{title} {body}' for title, body, _tone in status_calls)
    rendered_metrics = ' '.join(f'{label}: {value}' for label, value in metric_calls)
    rendered_text = f'{rendered_status_text} {rendered_metrics}'

    assert 'Primer option recorded for review' not in rendered_text
    assert 'Readiness: Ready' not in rendered_text
    assert 'review required' in rendered_text
    assert 'Quality status: Not Recommended' in rendered_text


def test_importing_wizard_flow_does_not_import_primer3():
    script = (
        "import sys; "
        "sys.modules.pop('primer3', None); "
        "import views.wizard_flow; "
        "raise SystemExit(1 if 'primer3' in sys.modules else 0)"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_step4_page_renders_backend_unavailable_message_without_design(monkeypatch):
    ds, ctrl = _make_step4_session()
    caption_calls: list[str] = []
    design_calls = {"count": 0}

    _prime_step4_page(monkeypatch, button_map={2: [False, False]})
    monkeypatch.setattr(
        step4,
        "get_primer3_backend_status",
        lambda *, probe=False: Primer3BackendStatus(
            False,
            "Primer design engine is unavailable in this environment. You can continue reviewing documentation fields.",
        ),
    )
    monkeypatch.setattr(step4.st, "caption", lambda body, *args, **kwargs: caption_calls.append(str(body)))
    monkeypatch.setattr(step4, "_poll_primer_task_if_needed", lambda *args, **kwargs: None)

    def _unexpected_design(*args, **kwargs):
        design_calls["count"] += 1
        raise AssertionError("primer design should not run while backend is unavailable")

    monkeypatch.setattr(step4, "design_outer_primers_for_cassette", _unexpected_design)

    step4.page(ctrl)

    rendered = " ".join(caption_calls)
    assert "Outer-primer candidate generation is not enabled in this build" in rendered
    assert "cassette boundary and documentation review only" in rendered
    assert design_calls["count"] == 0


def test_async_finished_primer_success_copy_uses_review_context(monkeypatch):
    import streamlit as st

    ds, ctrl = _make_step4_session()
    st.session_state['primer_task_id'] = 'task-finished'
    st.session_state[step4.SK.PRIMER_TASK_CONTEXT_SIGNATURE] = ds.current_primer_context_signature()
    success_messages: list[str] = []

    _prime_step4_page(monkeypatch, button_map={2: [False, False]})
    monkeypatch.setattr(step4, 'get_primer_design_task', lambda task_id: {
        'task_id': task_id,
        'status': 'finished',
        'result': {
            'success': True,
            'results': [
                {
                    'quality_grade': 'Recommended',
                    'quality_score': 91,
                    'quality_reasons': ['Async result is available for review.'],
                    'product_size': 96,
                    'target_tm': 60.0,
                    'tm_gap': 0.3,
                    'hetero_dimer_risk': 'Low',
                    'pair_warnings': [],
                    'primers': [
                        {
                            'name': 'Forward Primer',
                            'role': 'forward',
                            'sequence': 'ATGGCCATGGCCATGGCC',
                            'tm': 60.1,
                            'tm_deviation': 0.1,
                            'gc_content': 55.6,
                            'gc_in_range': True,
                            'length': 18,
                            'hairpin_risk': 'Low',
                            'hairpin_dg_kcal_mol': -1.0,
                            'self_dimer_risk': 'Low',
                            'self_dimer_dg_kcal_mol': -1.5,
                            'issues': [],
                        },
                        {
                            'name': 'Reverse Primer',
                            'role': 'reverse',
                            'sequence': 'TTACCGGTTAACCGGTTA',
                            'tm': 60.4,
                            'tm_deviation': 0.4,
                            'gc_content': 50.0,
                            'gc_in_range': True,
                            'length': 18,
                            'hairpin_risk': 'Low',
                            'hairpin_dg_kcal_mol': -1.1,
                            'self_dimer_risk': 'Low',
                            'self_dimer_dg_kcal_mol': -1.8,
                            'issues': [],
                        },
                    ],
                }
            ],
        },
        'error': '',
    })
    monkeypatch.setattr(step4.st, 'success', lambda body, **kwargs: success_messages.append(str(body)))

    step4._refresh_primer_task_status(
        ds,
        ctrl,
        ds.host,
        step4._seq_hash(ds.frame['final_sequence']),
    )

    assert success_messages == [
        "Async primer design results are available for review with 1 primer pair(s)."
    ]


def test_step4_recommended_primer_copy_can_show_ready(monkeypatch):
    ds, ctrl = _make_step4_session()
    ds.primers = [
        {
            'Fragment Name': 'Expression cassette',
            "Forward Primer (5'->3')": 'ATGGCCATGGCCATGGCC',
            "Reverse Primer (5'->3')": 'TTACCGGTTAACCGGTTA',
            'Quality Grade': 'Recommended',
            'Quality Reasons': ['Primer metrics are aligned with target Tm 60.0°C.'],
            'Warnings': [],
        }
    ]
    ds.step4_plan_summary = {
        'design_scope': 'expression_cassette',
        'selected_result_index': 0,
        'selected_target_tm': 60.0,
        'structured_results': [
            {
                'name': 'Expression cassette',
                'quality_grade': 'Recommended',
                'quality_score': 95,
                'quality_reasons': ['Primer metrics are aligned with target Tm 60.0°C.'],
                'product_size': len(ds.frame['final_sequence']),
                'target_tm': 60.0,
                'tm_gap': 0.2,
                'hetero_dimer_risk': 'Low',
                'pair_warnings': [],
                'primers': [],
            }
        ],
    }
    ds.primer_context_host = ds.host
    ds.primer_context_seq_hash = step4._seq_hash(ds.frame['final_sequence'])
    ds.primer_context_signature = ds.current_primer_context_signature()
    ctrl.save(ds)

    status_calls: list[tuple[str, str, str]] = []
    metric_calls: list[tuple[str, object]] = []

    _prime_step4_page(monkeypatch, button_map={2: [False, False]}, patch_plan_summary=False)
    monkeypatch.setattr(step4, '_status_panel', lambda title, body, tone='info': status_calls.append((title, body, tone)))
    monkeypatch.setattr(_FakeColumn, 'metric', lambda self, label, value, *args, **kwargs: metric_calls.append((label, value)))
    monkeypatch.setattr(step4, '_poll_primer_task_if_needed', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, 'render_report_preview_container', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, 'render_report_download_button', lambda *args, **kwargs: None)

    step4.page(ctrl)

    rendered_status_text = ' '.join(f'{title} {body}' for title, body, _tone in status_calls)
    rendered_metrics = ' '.join(f'{label}: {value}' for label, value in metric_calls)

    assert 'Primer option recorded for review' in rendered_status_text
    assert 'Quality status: Pass-range' in rendered_metrics


def test_render_structured_primer_results_renders_dataframe(monkeypatch):
    captured_frames = []

    monkeypatch.setattr(step4.st, 'dataframe', lambda df, **kwargs: captured_frames.append(df))
    monkeypatch.setattr(step4.st, 'columns', lambda n: tuple(_FakeColumn() for _ in range(n)))
    monkeypatch.setattr(step4.st, 'caption', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'warning', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4, '_section_label', lambda *args, **kwargs: None)

    step4._render_structured_primer_results([
        {
            'quality_grade': 'Recommended',
            'quality_score': 95,
            'quality_reasons': ['Primer metrics are aligned with target Tm 60.0°C.'],
            'product_size': 120,
            'backend': 'primer3-py',
            'target_tm': 60.0,
            'tm_gap': 0.4,
            'hetero_dimer_risk': 'Low',
            'hetero_dimer_dg_kcal_mol': -1.2,
            'pair_warnings': [],
            'primers': [
                {
                    'name': 'Forward Primer',
                    'role': 'forward',
                    'sequence': 'ATGGCCATGGCCATGGCC',
                    'tm': 60.1,
                    'tm_deviation': 0.1,
                    'gc_content': 55.6,
                    'gc_in_range': True,
                    'length': 18,
                    'hairpin_risk': 'Low',
                    'hairpin_dg_kcal_mol': -1.0,
                    'self_dimer_risk': 'Low',
                    'self_dimer_dg_kcal_mol': -1.5,
                    'issues': [],
                },
                {
                    'name': 'Reverse Primer',
                    'role': 'reverse',
                    'sequence': 'TTACCGGTTAACCGGTTA',
                    'tm': 60.4,
                    'tm_deviation': 0.4,
                    'gc_content': 50.0,
                    'gc_in_range': True,
                    'length': 18,
                    'hairpin_risk': 'Low',
                    'hairpin_dg_kcal_mol': -1.1,
                    'self_dimer_risk': 'Low',
                    'self_dimer_dg_kcal_mol': -1.8,
                    'issues': [],
                },
            ],
        }
    ])

    assert captured_frames
    assert 'Primer' in captured_frames[-1].columns


def test_step4_page_uses_whole_cassette_primer_results(monkeypatch):
    import streamlit as st

    ds = DesignSession(
        step=4,
        gene_name='PrimerAPI',
        original_seq='ATG' + 'GCC' * 30 + 'TAA',
        optimized_seq='ATG' + 'GCC' * 30 + 'TAA',
        host='E.coli BL21(DE3)',
        tag='No tag',
        frame={
            'success': True,
            'final_sequence': 'ATG' + 'GCC' * 30 + 'TAA',
            'parts': [],
            'features': [
                {'name': 'FragA', 'start': 1, 'end': 48},
                {'name': 'FragB', 'start': 49, 'end': 96},
            ],
            'total_length': 96,
            'gc_content': 60.0,
        },
    )
    ctrl = _ctrl_with(ds)
    st.session_state[step4.SK.ACTIVE_HOST] = ds.host
    st.session_state[step4.SK.ACTIVE_SEQ] = ds.frame['final_sequence']

    mock_plan = {
        'primers': [
            {
                'Fragment Name': 'FragA',
                'Forward Primer (5\'->3\')': 'ATGGCCATGGCCATGGCC',
                'Reverse Primer (5\'->3\')': 'TTACCGGTTAACCGGTTA',
                'Quality Grade': 'Recommended',
                'Quality Reasons': ['No major warning triggered.'],
                'Fwd Anneal Tm (°C)': 60.0,
                'Rev Anneal Tm (°C)': 60.0,
                'Warnings': [],
            }
        ],
        'warnings': [],
        'selected_overlap_len': 20,
        'selected_target_tm': 60.0,
        'tried_combinations': 3,
        'best_plan_summary': 'Balanced primer plan selected.',
    }

    _prime_step4_page(monkeypatch, button_map={2: [True, False]})

    class _FakePlanner:
        def search_best_gibson_assembly_plan(self, **kwargs):
            return mock_plan

    monkeypatch.setattr(step4, 'design_outer_primers_for_cassette', lambda *args, **kwargs: {
        'success': True,
        'results': [
            {
                'quality_grade': 'Recommended',
                'quality_score': 93,
                'quality_reasons': ['Primer metrics are aligned with target Tm 60.0°C.'],
                'product_size': 96,
                'backend': 'primer3-py',
                'target_tm': 60.0,
                'tm_gap': 0.2,
                'hetero_dimer_risk': 'Low',
                'hetero_dimer_dg_kcal_mol': -1.2,
                'pair_warnings': [],
                'primers': [
                    {'name': 'Forward Primer', 'role': 'forward', 'sequence': 'ATGGCCATGGCCATGGCC', 'tm': 60.0},
                    {'name': 'Reverse Primer', 'role': 'reverse', 'sequence': 'TTACCGGTTAACCGGTTA', 'tm': 60.2},
                ],
            }
        ],
    })
    monkeypatch.setitem(sys.modules, 'core.assembly_planner', type('M', (), {'AssemblyPlanner': _FakePlanner}))

    step4.page(ctrl)

    saved_session = ctrl.get()
    saved = saved_session.step4_plan_summary
    assert saved['structured_results']
    assert saved['design_scope'] == 'expression_cassette'
    assert saved['structured_results'][0]['quality_score'] == 93
    assert saved['design_scope'] == 'expression_cassette'
    assert saved['structured_results'][0]['name'] == 'Expression cassette'
    assert saved_session.primers[0]['Fragment Name'] == 'Expression cassette'
    assert saved['structured_results'][0]['name'] == 'Expression cassette'
    assert saved_session.primers[0]['Fragment Name'] == 'Expression cassette'
    assert st.session_state['primer_task_id'] == ''
    assert st.session_state['primer_task_status'] == 'idle'
    assert st.session_state['primer_task_result'] is None
    assert st.session_state['primer_task_error'] == ''


def test_step4_default_sync_uses_cassette_outer_primer_helper(monkeypatch):
    import streamlit as st

    _, ctrl = _make_step4_session()
    calls = {"cassette": 0, "generic": 0}

    _prime_step4_page(monkeypatch, button_map={2: [True, False]})

    def _fake_cassette_helper(*args, **kwargs):
        calls["cassette"] += 1
        sequence = args[0]
        return {
            'success': True,
            'results': [
                {
                    'name': 'Expression cassette',
                    'design_scope': 'expression_cassette',
                    'quality_grade': 'Usable with Risk',
                    'quality_score': 82,
                    'quality_reasons': ['Tm deviation exceeds preferred range (3.50°C).'],
                    'product_size': len(sequence),
                    'product_start': 0,
                    'product_end': len(sequence),
                    'forward_start': 0,
                    'reverse_start': len(sequence) - 18,
                    'backend': 'edge-window',
                    'target_tm': 60.0,
                    'tm_gap': 0.2,
                    'hetero_dimer_risk': 'Low',
                    'hetero_dimer_dg_kcal_mol': -1.2,
                    'pair_warnings': [],
                    'primers': [
                        {'name': 'Forward Primer', 'role': 'forward', 'sequence': 'ATGGCCATGGCCATGGCC', 'tm': 60.0},
                        {'name': 'Reverse Primer', 'role': 'reverse', 'sequence': 'TTACCGGTTAACCGGTTA', 'tm': 60.2},
                    ],
                }
            ],
        }

    monkeypatch.setattr(step4, 'design_outer_primers_for_cassette', _fake_cassette_helper)
    monkeypatch.setattr(step4, '_poll_primer_task_if_needed', lambda *args, **kwargs: None)

    step4.page(ctrl)

    saved = ctrl.get()
    assert calls["cassette"] == 1
    assert saved.primers
    assert saved.primers[0]['Fragment Name'] == 'Expression cassette'
    assert saved.step4_plan_summary['structured_results'][0]['product_size'] == len(saved.frame['final_sequence'])
    assert saved.step4_plan_summary['structured_results'][0]['product_start'] == 0
    assert saved.step4_plan_summary['structured_results'][0]['product_end'] == len(saved.frame['final_sequence'])
    assert saved.primer_context_signature == saved.current_primer_context_signature()



@pytest.mark.skip(reason=ASYNC_PRIMER_PHASE4_REASON)
def test_step4_page_submits_async_primer_job(monkeypatch):
    import streamlit as st

    _, ctrl = _make_step4_session()

    _prime_step4_page(monkeypatch, button_map={2: [False, True]})
    captured_payload = {}

    def _fake_enqueue(payload):
        captured_payload.update(payload)
        return {
            'task_id': 'task-123',
            'status': 'queued',
        }

    monkeypatch.setattr(step4, 'enqueue_primer_design_task', _fake_enqueue)
    monkeypatch.setattr(step4, '_poll_primer_task_if_needed', lambda *args, **kwargs: None)

    step4.page(ctrl)

    assert captured_payload['design_scope'] == 'expression_cassette'
    assert st.session_state['primer_task_id'] == 'task-123'
    assert st.session_state['primer_task_status'] == 'queued'
    assert st.session_state['primer_task_result'] is None
    assert st.session_state['primer_task_error'] == ''
    assert st.session_state['primer_task_poll_enabled'] is True


@pytest.mark.skip(reason=ASYNC_PRIMER_PHASE4_REASON)
def test_check_async_status_calls_status_endpoint(monkeypatch):
    import streamlit as st

    _, ctrl = _make_step4_session()
    st.session_state['primer_task_id'] = 'task-xyz'
    st.session_state['primer_task_status'] = 'queued'

    _prime_step4_page(monkeypatch, button_map={2: [False, False]}, direct_button_map={'wf_p4_check_async_status': True})
    called = {}

    def _fake_get_task(task_id):
        called['task_id'] = task_id
        return {'task_id': task_id, 'status': 'queued', 'result': None, 'error': ''}

    monkeypatch.setattr(step4, 'get_primer_design_task', _fake_get_task)

    step4.page(ctrl)

    assert called['task_id'] == 'task-xyz'


@pytest.mark.skip(reason=ASYNC_PRIMER_PHASE4_REASON)
def test_check_async_status_updates_running_state(monkeypatch):
    import streamlit as st

    _, ctrl = _make_step4_session()
    st.session_state['primer_task_id'] = 'task-running'
    st.session_state['primer_task_status'] = 'queued'
    st.session_state['primer_task_result'] = {'stale': True}
    st.session_state['primer_task_error'] = 'old error'

    _prime_step4_page(monkeypatch, button_map={2: [False, False]}, direct_button_map={'wf_p4_check_async_status': True})
    monkeypatch.setattr(step4, 'get_primer_design_task', lambda task_id: {
        'task_id': task_id,
        'status': 'started',
        'result': None,
        'error': '',
    })

    step4.page(ctrl)

    assert st.session_state['primer_task_status'] == 'started'
    assert st.session_state['primer_task_result'] is None
    assert st.session_state['primer_task_error'] == ''


@pytest.mark.skip(reason=ASYNC_PRIMER_PHASE4_REASON)
def test_check_async_status_stores_finished_result_and_reuses_step4_views(monkeypatch):
    import streamlit as st

    _, ctrl = _make_step4_session()
    st.session_state['primer_task_id'] = 'task-finished'

    rendered = {'quality': 0, 'table': 0, 'structured': 0}
    _prime_step4_page(monkeypatch, button_map={2: [False, False]}, direct_button_map={'wf_p4_check_async_status': True})
    monkeypatch.setattr(step4, '_render_primer_quality_summary', lambda primers: rendered.__setitem__('quality', len(primers)))
    monkeypatch.setattr(step4, '_render_primer_table', lambda primers: rendered.__setitem__('table', len(primers)))
    monkeypatch.setattr(step4, '_render_structured_primer_results', lambda results: rendered.__setitem__('structured', len(results)))

    finished_result = {
        'success': True,
        'results': [
            {
                'quality_grade': 'Recommended',
                'quality_score': 91,
                'quality_reasons': ['Async result is ready.'],
                'product_size': 96,
                'target_tm': 60.0,
                'tm_gap': 0.3,
                'hetero_dimer_risk': 'Low',
                'pair_warnings': [],
                'primers': [
                    {
                        'name': 'Forward Primer',
                        'role': 'forward',
                        'sequence': 'ATGGCCATGGCCATGGCC',
                        'tm': 60.1,
                        'tm_deviation': 0.1,
                        'gc_content': 55.6,
                        'gc_in_range': True,
                        'length': 18,
                        'hairpin_risk': 'Low',
                        'hairpin_dg_kcal_mol': -1.0,
                        'self_dimer_risk': 'Low',
                        'self_dimer_dg_kcal_mol': -1.5,
                        'issues': [],
                    },
                    {
                        'name': 'Reverse Primer',
                        'role': 'reverse',
                        'sequence': 'TTACCGGTTAACCGGTTA',
                        'tm': 60.4,
                        'tm_deviation': 0.4,
                        'gc_content': 50.0,
                        'gc_in_range': True,
                        'length': 18,
                        'hairpin_risk': 'Low',
                        'hairpin_dg_kcal_mol': -1.1,
                        'self_dimer_risk': 'Low',
                        'self_dimer_dg_kcal_mol': -1.8,
                        'issues': [],
                    },
                ],
            }
        ],
    }
    monkeypatch.setattr(step4, 'get_primer_design_task', lambda task_id: {
        'task_id': task_id,
        'status': 'finished',
        'result': finished_result,
        'error': '',
    })

    step4.page(ctrl)

    saved = ctrl.get()
    assert st.session_state['primer_task_status'] == 'finished'
    assert st.session_state['primer_task_result'] == finished_result
    assert st.session_state['primer_task_error'] == ''
    assert saved.primers
    assert saved.step4_plan_summary['structured_results'][0]['quality_score'] == 91
    assert rendered['quality'] == 1
    assert rendered['table'] == 1
    assert rendered['structured'] == 1


@pytest.mark.skip(reason=ASYNC_PRIMER_PHASE4_REASON)
def test_check_async_status_stores_failed_error(monkeypatch):
    import streamlit as st

    _, ctrl = _make_step4_session()
    st.session_state['primer_task_id'] = 'task-failed'

    _prime_step4_page(monkeypatch, button_map={2: [False, False]}, direct_button_map={'wf_p4_check_async_status': True})
    monkeypatch.setattr(step4, 'get_primer_design_task', lambda task_id: {
        'task_id': task_id,
        'status': 'failed',
        'result': None,
        'error': 'worker crashed',
    })

    step4.page(ctrl)

    assert st.session_state['primer_task_status'] == 'failed'
    assert st.session_state['primer_task_result'] is None
    assert st.session_state['primer_task_error'] == 'worker crashed'


@pytest.mark.skip(reason=ASYNC_PRIMER_PHASE4_REASON)
def test_auto_polling_refreshes_running_async_primer_task(monkeypatch):
    import streamlit as st

    _, ctrl = _make_step4_session()
    st.session_state['primer_task_id'] = 'task-auto'
    st.session_state['primer_task_status'] = 'queued'
    st.session_state['primer_task_poll_enabled'] = True
    st.session_state['primer_task_last_polled_at'] = 0.0
    st.session_state['primer_task_poll_count'] = 0

    _prime_step4_page(monkeypatch, button_map={2: [False, False]})
    monkeypatch.setattr(step4.time, 'time', lambda: 5.0)
    called = {}

    def _fake_refresh(ds, ctrl_obj, upstream_host, upstream_seq_hash):
        called['refreshed'] = True
        st.session_state['primer_task_status'] = 'started'
        st.session_state['primer_task_poll_count'] = 1

    monkeypatch.setattr(step4, '_refresh_primer_task_status', _fake_refresh)
    schedule_calls = {'count': 0}
    monkeypatch.setattr(step4, '_schedule_async_refresh', lambda *args, **kwargs: schedule_calls.__setitem__('count', schedule_calls['count'] + 1))

    step4.page(ctrl)

    assert called['refreshed'] is True
    assert schedule_calls['count'] == 1


@pytest.mark.skip(reason=ASYNC_PRIMER_PHASE4_REASON)
def test_manual_status_refresh_is_secondary_entry_with_help_copy(monkeypatch):
    import streamlit as st

    _, ctrl = _make_step4_session()
    st.session_state['primer_task_id'] = 'task-help'

    expander_calls: list[tuple[str, bool]] = []
    caption_calls: list[str] = []

    _prime_step4_page(monkeypatch, button_map={2: [False, False]})
    monkeypatch.setattr(step4.st, 'expander', lambda label, expanded=False, **kwargs: expander_calls.append((label, expanded)) or _FakeExpander())
    monkeypatch.setattr(step4.st, 'caption', lambda text, *args, **kwargs: caption_calls.append(text))
    monkeypatch.setattr(step4, '_poll_primer_task_if_needed', lambda *args, **kwargs: None)

    step4.page(ctrl)

    assert ('Manual status refresh (optional)', False) in expander_calls
    assert any('Automatic polling is enabled' in text for text in caption_calls)


@pytest.mark.skip(reason=ASYNC_PRIMER_PHASE4_REASON)
def test_check_async_status_marks_invalid_finished_payload_as_failed(monkeypatch):
    import streamlit as st

    _, ctrl = _make_step4_session()
    st.session_state['primer_task_id'] = 'task-invalid-finished'
    st.session_state['primer_task_poll_enabled'] = True

    _prime_step4_page(monkeypatch, button_map={2: [False, False]}, direct_button_map={'wf_p4_check_async_status': True})
    monkeypatch.setattr(step4, 'get_primer_design_task', lambda task_id: {
        'task_id': task_id,
        'status': 'finished',
        'result': {'success': True},
        'error': '',
    })

    step4.page(ctrl)

    assert st.session_state['primer_task_status'] == 'failed'
    assert st.session_state['primer_task_result'] is None
    assert "expected 'results' list" in st.session_state['primer_task_error']
    assert st.session_state['primer_task_poll_enabled'] is False


def test_ranked_structured_primer_option_switch_applies_selected_design(monkeypatch):
    import streamlit as st

    ds, ctrl = _make_step4_session()
    structured_results = [
        {
            'name': 'Option 1',
            'quality_grade': 'Recommended',
            'quality_score': 90,
            'quality_reasons': ['Initial option.'],
            'product_size': 96,
            'target_tm': 60.0,
            'tm_gap': 0.4,
            'hetero_dimer_risk': 'Low',
            'pair_warnings': [],
            'primers': [
                {'name': 'Forward Primer', 'role': 'forward', 'sequence': 'ATGGCCATGGCCATGGCC', 'tm': 60.0},
                {'name': 'Reverse Primer', 'role': 'reverse', 'sequence': 'TTACCGGTTAACCGGTTA', 'tm': 60.2},
            ],
        },
        {
            'name': 'Option 2',
            'quality_grade': 'Usable with Risk',
            'quality_score': 82,
            'quality_reasons': ['Alternative ranked option.'],
            'product_size': 96,
            'target_tm': 61.0,
            'tm_gap': 0.8,
            'hetero_dimer_risk': 'Medium',
            'pair_warnings': ['Review before ordering.'],
            'primers': [
                {'name': 'Forward Primer', 'role': 'forward', 'sequence': 'GCCGCCGCCGCCGCCGCC', 'tm': 61.0},
                {'name': 'Reverse Primer', 'role': 'reverse', 'sequence': 'TAATAATAATAATAATAA', 'tm': 61.1},
            ],
        },
    ]
    ds.primers = step4._primer_rows_from_structured_results(structured_results, selected_index=0)
    ds.primer_context_host = ds.host
    ds.primer_context_seq_hash = step4._seq_hash(ds.frame['final_sequence'])
    ds.primer_context_signature = ds.current_primer_context_signature()
    ds.step4_plan_summary = {
        'selected_result_index': 0,
        'selected_overlap_len': 20,
        'selected_target_tm': 60.0,
        'tried_combinations': 2,
        'best_plan_summary': 'Two ranked options are available.',
        'structured_results': structured_results,
    }
    ctrl.save(ds)

    _prime_step4_page(monkeypatch, button_map={2: [False, False]})
    monkeypatch.setattr(step4, '_poll_primer_task_if_needed', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'selectbox', lambda label, options, index=0, **kwargs: options[1])

    step4.page(ctrl)

    saved = ctrl.get()
    assert saved.primers[0]["Forward Primer (5'->3')"] == 'GCCGCCGCCGCCGCCGCC'
    assert saved.primers[0]["Reverse Primer (5'->3')"] == 'TAATAATAATAATAATAA'
    assert saved.step4_plan_summary['selected_result_index'] == 1
    assert saved.primer_context_signature
    assert saved.primer_context_signature == saved.current_primer_context_signature()
    assert saved.step4_plan_summary['structured_results'] == structured_results


def test_step4_backend_unavailable_hides_primary_design_action_and_allows_continue(monkeypatch):
    ds, ctrl = _make_step4_session()
    button_calls: list[tuple[str, object]] = []
    caption_calls: list[str] = []

    _prime_step4_page(monkeypatch, button_map={2: [False, False]})
    monkeypatch.setattr(
        step4,
        'get_primer3_backend_status',
        lambda *, probe=False: Primer3BackendStatus(False, 'backend unavailable'),
    )
    monkeypatch.setattr(step4.st, 'caption', lambda body, *args, **kwargs: caption_calls.append(str(body)))

    def _capture_button(column, label, **kwargs):
        button_calls.append((label, kwargs.get('disabled')))
        return False

    monkeypatch.setattr(step4, '_column_aware_button', _capture_button)
    monkeypatch.setattr(step4, '_poll_primer_task_if_needed', lambda *args, **kwargs: None)

    step4.page(ctrl)

    saved = ctrl.get()
    rendered = ' '.join(caption_calls)
    assert button_calls == []
    assert 'Review primers' not in rendered
    assert 'Outer-primer candidate generation is not enabled in this build' in rendered
    assert 'cassette boundary and documentation review only' in rendered
    assert saved.primer_design_status == 'unavailable'
    assert saved.primer_backend_available is False
    assert saved.active_primer_pair is None
    assert saved.primers == []
    assert saved.step4_plan_summary['primer_design_status'] == 'unavailable'
    assert saved.step4_plan_summary['best_plan_summary'] == (
        'Outer-primer candidate generation is not enabled in this build. '
        'This step currently supports cassette boundary and documentation review only.'
    )
    assert ctrl.can_advance is True


def test_ranked_structured_primer_option_switch_marks_validation_stale(monkeypatch):
    ds, ctrl = _make_step4_session()
    structured_results = [
        {
            'name': 'Option 1',
            'quality_grade': 'Recommended',
            'quality_score': 90,
            'quality_reasons': ['Initial option.'],
            'product_size': 96,
            'target_tm': 60.0,
            'tm_gap': 0.4,
            'hetero_dimer_risk': 'Low',
            'pair_warnings': [],
            'primers': [
                {'name': 'Forward Primer', 'role': 'forward', 'sequence': 'ATGGCCATGGCCATGGCC', 'tm': 60.0},
                {'name': 'Reverse Primer', 'role': 'reverse', 'sequence': 'TTACCGGTTAACCGGTTA', 'tm': 60.2},
            ],
        },
        {
            'name': 'Option 2',
            'quality_grade': 'Usable with Risk',
            'quality_score': 82,
            'quality_reasons': ['Alternative ranked option.'],
            'product_size': 96,
            'target_tm': 61.0,
            'tm_gap': 0.8,
            'hetero_dimer_risk': 'Medium',
            'pair_warnings': ['Review before ordering.'],
            'primers': [
                {'name': 'Forward Primer', 'role': 'forward', 'sequence': 'GCCGCCGCCGCCGCCGCC', 'tm': 61.0},
                {'name': 'Reverse Primer', 'role': 'reverse', 'sequence': 'TAATAATAATAATAATAA', 'tm': 61.1},
            ],
        },
    ]
    ds.primers = step4._primer_rows_from_structured_results(structured_results, selected_index=0)
    ds.primer_context_host = ds.host
    ds.primer_context_seq_hash = step4._seq_hash(ds.frame['final_sequence'])
    ds.primer_context_signature = ds.current_primer_context_signature()
    ds.step4_plan_summary = {
        'selected_result_index': 0,
        'selected_overlap_len': 20,
        'selected_target_tm': 60.0,
        'tried_combinations': 2,
        'best_plan_summary': 'Two ranked options are available.',
        'structured_results': structured_results,
    }
    ds.validation_results = []
    ds.validation_context_signature = ds.current_validation_context_signature()
    assert ds.validation_is_stale() is False
    ctrl.save(ds)

    _prime_step4_page(monkeypatch, button_map={2: [False, False]})
    monkeypatch.setattr(step4, '_poll_primer_task_if_needed', lambda *args, **kwargs: None)
    monkeypatch.setattr(step4.st, 'selectbox', lambda label, options, index=0, **kwargs: options[1])

    step4.page(ctrl)

    saved = ctrl.get()
    assert saved.primers[0]["Forward Primer (5'->3')"] == 'GCCGCCGCCGCCGCCGCC'
    assert saved.primers[0]["Reverse Primer (5'->3')"] == 'TAATAATAATAATAATAA'
    assert saved.step4_plan_summary['selected_result_index'] == 1
    assert saved.primer_context_signature
    assert saved.primer_context_signature == saved.current_primer_context_signature()
    assert saved.validation_is_stale() is True

