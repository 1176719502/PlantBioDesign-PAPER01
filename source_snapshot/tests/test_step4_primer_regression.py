# -*- coding: utf-8 -*-
"""
tests/test_step4_primer_regression.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Focused regression tests for Step 4 primer-design warning/failure behavior.

Run with:
    python -m pytest tests/test_step4_primer_regression.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from core.design_session import DesignSession, SessionController
from core.primer_utils import Primer3BackendStatus
from core.session_keys import SK
from core.assembly_planner import AssemblyPlanner


def _mark_primer_backend_available(monkeypatch, step4_module) -> None:
    monkeypatch.setattr(
        step4_module,
        'get_primer3_backend_status',
        lambda *, probe=False: Primer3BackendStatus(True, ''),
    )


class TestStep4PrimerPlannerWarnings:
    """Targeted warning-path coverage through the active AssemblyPlanner path."""

    @staticmethod
    def _construct_for_two_fragments(seq: str, split_at: int) -> dict:
        return {
            'final_sequence': seq,
            'features': [
                {'name': 'FragA', 'start': 1, 'end': split_at},
                {'name': 'FragB', 'start': split_at + 1, 'end': len(seq)},
            ],
        }

    def test_recommended_grade_for_balanced_primers(self, monkeypatch):
        import core.assembly_planner as assembly_mod

        seq = ('ATGGCCATGGCCATTA' * 9)[:144]
        construct = {
            'final_sequence': seq,
            'features': [
                {'name': 'FragA', 'start': 1, 'end': 48},
                {'name': 'FragB', 'start': 49, 'end': 96},
                {'name': 'FragC', 'start': 97, 'end': 144},
            ],
        }

        monkeypatch.setattr(assembly_mod, '_pair_warnings', lambda fwd, rev: [])
        monkeypatch.setattr(assembly_mod, '_homology_warnings', lambda arm, full, label: [])

        plan = AssemblyPlanner().plan_gibson_assembly(
            construct_result=construct,
            overlap_len=18,
            target_tm=56.0,
        )

        assert plan['primers'], 'Precondition: planner should produce primer rows'
        assert all(
            p.get('Quality Grade') in {'Recommended', 'Usable with Risk'}
            for p in plan['primers']
        ), f'Expected non-blocking primer quality grades, got: {plan["primers"]}'

    def test_usable_with_risk_grade_for_non_unique_overlap(self, monkeypatch):
        """Planner should classify overlap reuse as usable but risky."""
        import core.assembly_planner as assembly_mod

        full_seq = 'ATATAT' * 10
        construct = {
            'final_sequence': full_seq,
            'features': [
                {'name': 'FragA', 'start': 1, 'end': 30},
                {'name': 'FragB', 'start': 31, 'end': 60},
            ],
        }

        monkeypatch.setattr(assembly_mod, '_pair_warnings', lambda fwd, rev: [])

        def _mock_homology_warnings(arm_seq: str, full_seq: str, label: str) -> list[str]:
            if arm_seq:
                return [f'{label} overlap may be non-unique in construct (2 matches).']
            return []

        monkeypatch.setattr(assembly_mod, '_homology_warnings', _mock_homology_warnings)

        plan = AssemblyPlanner().plan_gibson_assembly(
            construct_result=construct,
            overlap_len=6,
            target_tm=44.0,
        )

        assert plan['primers'], 'Precondition: planner should still produce primer rows'
        risky_pairs = [p for p in plan['primers'] if p.get('Quality Grade') == 'Usable with Risk']
        assert risky_pairs, f'Expected usable-with-risk pair, got: {plan["primers"]}'
        assert any('overlap may be non-unique' in w for w in (plan.get('warnings') or [])), (
            f'Expected non-unique overlap warning, got: {plan.get("warnings")}'
        )
        assert any(
            any('non-unique' in reason for reason in p.get('Quality Reasons', []))
            for p in risky_pairs
        )

    def test_not_recommended_grade_for_cross_dimer_warning(self):
        """Planner should mark high pair interaction risk as not recommended."""
        seq = ('GCGTACGCGTAC' * 8)[:96]
        construct = self._construct_for_two_fragments(seq, split_at=48)

        plan = AssemblyPlanner().plan_gibson_assembly(
            construct_result=construct,
            overlap_len=20,
            target_tm=60.0,
        )

        joined = ' | '.join(plan.get('warnings') or [])
        assert 'cross-dimer risk' in joined, f'Expected cross-dimer warning, got: {plan.get("warnings")}'
        not_recommended_pairs = [p for p in plan['primers'] if p.get('Quality Grade') == 'Not Recommended']
        assert not_recommended_pairs, f'Expected not-recommended pair, got: {plan["primers"]}'
        assert any(
            any('cross-dimer risk' in reason for reason in p.get('Quality Reasons', []))
            for p in not_recommended_pairs
        )

    def test_cross_dimer_warning_path_from_planner(self):
        """Planner warnings should surface cross-dimer risk for complementary primer pairs."""
        # Repetitive motif raises the chance of long complementary k-mers across primers.
        seq = ('GCGTACGCGTAC' * 8)[:96]
        construct = self._construct_for_two_fragments(seq, split_at=48)

        plan = AssemblyPlanner().plan_gibson_assembly(
            construct_result=construct,
            overlap_len=20,
            target_tm=60.0,
        )

        joined = ' | '.join(plan.get('warnings') or [])
        assert 'cross-dimer risk' in joined, f'Expected cross-dimer warning, got: {plan.get("warnings")}'

    def test_3prime_complementarity_warning_path_from_planner(self):
        """Planner warnings should surface 3' complementarity risk when primer tails can pair."""
        # Symmetric repeat-rich sequence tends to produce complementary primer 3' tails.
        seq = ('AACCTTGGTTAACCTTGGTT' * 6)[:120]
        construct = self._construct_for_two_fragments(seq, split_at=60)

        plan = AssemblyPlanner().plan_gibson_assembly(
            construct_result=construct,
            overlap_len=20,
            target_tm=60.0,
        )

        joined = ' | '.join(plan.get('warnings') or [])
        assert "3' complementarity risk" in joined, (
            f"Expected 3' complementarity warning, got: {plan.get('warnings')}"
        )

    def test_non_unique_overlap_warning_path(self):
        """Planner should emit overlap non-unique warnings for repetitive construct overlaps."""
        full_seq = 'ATATAT' * 10  # highly repetitive; overlap will be non-unique
        construct = {
            'final_sequence': full_seq,
            'features': [
                {'name': 'FragA', 'start': 1, 'end': 30},
                {'name': 'FragB', 'start': 31, 'end': 60},
            ],
        }

        plan = AssemblyPlanner().plan_gibson_assembly(
            construct_result=construct,
            overlap_len=6,
            target_tm=60.0,
        )

        assert plan['primers'], 'Precondition: planner should still produce primer rows'
        assert any('overlap may be non-unique' in w for w in (plan.get('warnings') or [])), (
            f'Expected non-unique overlap warning, got: {plan.get("warnings")}'
        )


class TestStep4ZeroPrimerWizardRegression:
    """Wizard-level regression for Step 4 zero-primer failure messaging and blocking."""

    @pytest.fixture(autouse=True)
    def _patch_streamlit_session(self, monkeypatch):
        import streamlit as _st
        fake_state = {}
        monkeypatch.setattr(_st, 'session_state', fake_state)
        monkeypatch.setattr(_st, 'rerun', lambda: None)

    def _ctrl_with(self, ds: DesignSession) -> SessionController:
        import streamlit as st
        st.session_state.clear()
        st.session_state['design_session'] = ds
        return SessionController()

    def test_step4_establishes_root_container_before_rendering_main_body(self, monkeypatch):
        import streamlit as st
        import views.wizard_steps.step4_cloning_primers as step4

        ds = DesignSession(
            step=4,
            gene_name='RootContainerCase',
            original_seq='ATG' + 'A' * 30 + 'TAA',
            optimized_seq='ATG' + 'A' * 30 + 'TAA',
            host='E.coli BL21(DE3)',
            tag='No tag',
            frame={
                'success': True,
                'final_sequence': 'ATG' + 'A' * 30 + 'TAA',
                'parts': [],
                'features': [],
                'total_length': 36,
                'gc_content': 5.6,
            },
        )
        ctrl = self._ctrl_with(ds)

        st.session_state[SK.ACTIVE_HOST] = ds.host
        st.session_state[SK.ACTIVE_SEQ] = ds.frame['final_sequence']

        events = []

        class _StopRender(Exception):
            pass

        class _FakeRoot:
            def container(self):
                events.append('root.container.called')

                class _Ctx:
                    def __enter__(self_inner):
                        events.append('root.container.enter')
                        return self_inner

                    def __exit__(self_inner, exc_type, exc, tb):
                        events.append('root.container.exit')
                        return False

                return _Ctx()

        def _capture_step_header(*args, **kwargs):
            events.append('step_header')
            raise _StopRender()

        monkeypatch.setattr(step4.st, 'empty', lambda: _FakeRoot())
        monkeypatch.setattr(step4, '_step_header', _capture_step_header)

        with pytest.raises(_StopRender):
            step4.page(ctrl)

        assert events[:3] == [
            'root.container.called',
            'root.container.enter',
            'step_header',
        ], f'Expected Step 4 root container to be established before body render, got: {events}'
        assert 'root.container.exit' in events, f'Expected root container context to close cleanly, got: {events}'

    def test_step4_keeps_loaded_primers_when_dashboard_restores_matching_active_context(self, monkeypatch):
        import streamlit as st
        import views.wizard_steps.step4_cloning_primers as step4

        final_seq = 'ATGCGTACGTAGCTAGCTAGCTAG'
        primers = [
            {
                'Fragment Name': 'FragA',
                "Forward Primer (5'->3')": 'ATGCGTACGTAGCTAGCTAG',
                "Reverse Primer (5'->3')": 'CTAGCTAGCTACGTACGCAT',
                'Fwd Anneal Tm (°C)': 60.0,
                'Rev Anneal Tm (°C)': 60.0,
                'Warnings': [],
            }
        ]
        ds = DesignSession(
            step=4,
            gene_name='DashboardReloadCase',
            original_seq=final_seq,
            optimized_seq=final_seq,
            host='E.coli BL21(DE3)',
            tag='No tag',
            frame={
                'success': True,
                'final_sequence': final_seq,
                'parts': [],
                'features': [],
                'total_length': len(final_seq),
                'gc_content': 50.0,
            },
            primers=primers.copy(),
            primer_context_host='',
            primer_context_seq_hash='',
        )
        ctrl = self._ctrl_with(ds)

        st.session_state[SK.ACTIVE_HOST] = ds.host
        st.session_state[SK.ACTIVE_SEQ] = final_seq

        panel_calls = []
        summary_calls = []
        table_calls = []

        def _capture_status(title: str, body: str, tone: str = 'info'):
            panel_calls.append({'title': title, 'body': body, 'tone': tone})

        def _capture_summary(primers):
            summary_calls.append(list(primers))

        def _capture_table(primers):
            table_calls.append(list(primers))

        monkeypatch.setattr(step4, '_step_header', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_section_label', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_frame_summary_card', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_render_primer_quality_summary', _capture_summary)
        monkeypatch.setattr(step4, '_render_primer_table', _capture_table)
        monkeypatch.setattr(step4, '_status_panel', _capture_status)
        monkeypatch.setattr(step4.st, 'divider', lambda: None)
        monkeypatch.setattr(step4.st, 'caption', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'slider', lambda *a, **k: a[3])
        monkeypatch.setattr(step4.st, 'button', lambda *a, **k: False)
        monkeypatch.setattr(step4.st, 'warning', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'error', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'success', lambda *a, **k: None)

        step4.page(ctrl)

        updated = ctrl.get()
        assert updated.primers == primers
        assert ctrl.can_advance is True
        assert summary_calls and table_calls, 'Expected Step 4 to render quality summary and table'
        assert not any('Upstream context missing or changed' in c['title'] for c in panel_calls), (
            f'Expected no stale-context warning, got: {panel_calls}'
        )

    def test_step4_zero_primers_shows_failure_message_and_blocks_next(self, monkeypatch):
        import streamlit as st
        import views.wizard_steps.step4_cloning_primers as step4

        ds = DesignSession(
            step=4,
            gene_name='Step4FailCase',
            original_seq='ATG' + 'A' * 30 + 'TAA',
            host='E.coli BL21(DE3)',
            tag='No tag',
            frame={
                'success': True,
                'final_sequence': 'ATGCGTACGTAGCTAGCTAGCTAG',  # <30 bp to skip plasmid-map rendering
                'parts': [],
                'features': [],
                'total_length': 24,
                'gc_content': 50.0,
            },
            primers=[{'name': 'stale'}],
        )
        ctrl = self._ctrl_with(ds)

        st.session_state[SK.ACTIVE_HOST] = ds.host
        st.session_state[SK.ACTIVE_SEQ] = ds.frame['final_sequence']

        panel_calls = []

        def _capture_status(title: str, body: str, tone: str = 'info'):
            panel_calls.append({'title': title, 'body': body, 'tone': tone})

        def _fake_primer_design(*args, **kwargs):
            return {
                'success': False,
                'error': 'No valid primer design candidates were generated.',
                'input_length': 24,
                'results': [],
            }

        monkeypatch.setattr(step4, '_step_header', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_section_label', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_frame_summary_card', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_status_panel', _capture_status)
        monkeypatch.setattr(step4.st, 'divider', lambda: None)
        monkeypatch.setattr(step4.st, 'caption', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'slider', lambda *a, **k: a[3])
        monkeypatch.setattr(step4.st, 'button', lambda *a, **k: True)
        monkeypatch.setattr(step4.st, 'success', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'warning', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'error', lambda *a, **k: None)
        monkeypatch.setattr(step4, 'design_outer_primers_for_cassette', _fake_primer_design)
        _mark_primer_backend_available(monkeypatch, step4)

        step4.page(ctrl)

        updated = ctrl.get()
        assert updated.primers == []
        assert ctrl.can_advance is False, 'Step 4 must remain blocked when no primers are returned'

        failure_panels = [c for c in panel_calls if c['tone'] == 'warn' and '0' in c['title']]
        assert failure_panels, f'Expected zero-primer failure panel, got: {panel_calls}'
        assert any('No valid primer design candidates' in c['body'] for c in failure_panels), (
            f'Expected primer-service reason in failure body, got: {failure_panels}'
        )


class TestStep4BestPlanSearch:
    def test_search_best_plan_prefers_fewer_not_recommended_pairs(self, monkeypatch):
        planner = AssemblyPlanner()

        def _fake_single_plan(self, construct_result, overlap_len=20, target_tm=60.0):
            if overlap_len == 20 and target_tm == 60.0:
                primers = [
                    {'Quality Grade': 'Not Recommended', 'Warnings': ['High cross-dimer risk between primers (8 bp complementarity).'], 'Fwd Anneal Tm (°C)': 60.0, 'Rev Anneal Tm (°C)': 60.0},
                    {'Quality Grade': 'Not Recommended', 'Warnings': ['High 3\' complementarity risk between primers (6 bp).'], 'Fwd Anneal Tm (°C)': 60.0, 'Rev Anneal Tm (°C)': 59.0},
                ]
            else:
                primers = [
                    {'Quality Grade': 'Recommended', 'Warnings': [], 'Fwd Anneal Tm (°C)': target_tm, 'Rev Anneal Tm (°C)': target_tm},
                    {'Quality Grade': 'Usable with Risk', 'Warnings': ['Moderate cross-dimer risk between primers (6 bp complementarity).'], 'Fwd Anneal Tm (°C)': target_tm - 1.0, 'Rev Anneal Tm (°C)': target_tm},
                ]
            return {
                'method': 'Gibson Assembly (linear)',
                'parameters': {'overlap_len': overlap_len, 'target_tm': float(target_tm)},
                'primers': primers,
                'warnings': [],
            }

        monkeypatch.setattr(AssemblyPlanner, 'plan_gibson_assembly', _fake_single_plan)

        best_plan = planner.search_best_gibson_assembly_plan(
            construct_result={'final_sequence': 'ATGC', 'features': [{'name': 'A', 'start': 1, 'end': 2}, {'name': 'B', 'start': 3, 'end': 4}]},
            overlap_len=20,
            target_tm=60.0,
        )

        assert best_plan['quality_summary']['not_recommended'] == 0
        assert best_plan['selected_overlap_len'] != 20 or best_plan['selected_target_tm'] != 60.0
        assert best_plan['tried_combinations'] == 9
        assert '0 Not Recommended' in best_plan['best_plan_summary']

    def test_search_best_plan_keeps_default_when_already_best(self, monkeypatch):
        planner = AssemblyPlanner()

        def _fake_single_plan(self, construct_result, overlap_len=20, target_tm=60.0):
            not_recommended = 0 if overlap_len == 20 and target_tm == 60.0 else 1
            primers = [
                {
                    'Quality Grade': 'Recommended' if not_recommended == 0 else 'Not Recommended',
                    'Warnings': [] if not_recommended == 0 else ['High cross-dimer risk between primers (8 bp complementarity).'],
                    'Fwd Anneal Tm (°C)': float(target_tm),
                    'Rev Anneal Tm (°C)': float(target_tm),
                }
            ]
            return {
                'method': 'Gibson Assembly (linear)',
                'parameters': {'overlap_len': overlap_len, 'target_tm': float(target_tm)},
                'primers': primers,
                'warnings': [],
            }

        monkeypatch.setattr(AssemblyPlanner, 'plan_gibson_assembly', _fake_single_plan)

        best_plan = planner.search_best_gibson_assembly_plan(
            construct_result={'final_sequence': 'ATGC', 'features': [{'name': 'A', 'start': 1, 'end': 2}, {'name': 'B', 'start': 3, 'end': 4}]},
            overlap_len=20,
            target_tm=60.0,
        )

        assert best_plan['selected_overlap_len'] == 20
        assert best_plan['selected_target_tm'] == 60.0
        assert best_plan['quality_summary']['not_recommended'] == 0

    def test_search_best_plan_returns_least_bad_option_when_all_candidates_risky(self, monkeypatch):
        planner = AssemblyPlanner()

        def _fake_single_plan(self, construct_result, overlap_len=20, target_tm=60.0):
            not_recommended = 1 if overlap_len == 18 else 2
            primers = [
                {
                    'Quality Grade': 'Not Recommended',
                    'Warnings': ['High cross-dimer risk between primers (8 bp complementarity).'],
                    'Fwd Anneal Tm (°C)': float(target_tm),
                    'Rev Anneal Tm (°C)': float(target_tm - not_recommended),
                }
                for _ in range(not_recommended)
            ]
            return {
                'method': 'Gibson Assembly (linear)',
                'parameters': {'overlap_len': overlap_len, 'target_tm': float(target_tm)},
                'primers': primers,
                'warnings': [],
            }

        monkeypatch.setattr(AssemblyPlanner, 'plan_gibson_assembly', _fake_single_plan)

        best_plan = planner.search_best_gibson_assembly_plan(
            construct_result={'final_sequence': 'ATGC', 'features': [{'name': 'A', 'start': 1, 'end': 2}, {'name': 'B', 'start': 3, 'end': 4}]},
            overlap_len=20,
            target_tm=60.0,
        )

        assert best_plan['quality_summary']['not_recommended'] == 1
        assert best_plan['selected_overlap_len'] == 18
        assert best_plan['tried_combinations'] == 9

    def test_step4_default_design_uses_expression_cassette_outer_primers(self, monkeypatch):
        import streamlit as st
        import views.wizard_steps.step4_cloning_primers as step4

        final_seq = 'ATG' + 'GCC' * 30 + 'TAA'
        ds = DesignSession(
            step=4,
            gene_name='BestPlanSummaryCase',
            original_seq=final_seq,
            optimized_seq=final_seq,
            host='E.coli BL21(DE3)',
            tag='No tag',
            frame={
                'success': True,
                'final_sequence': final_seq,
                'parts': [],
                'features': [
                    {'name': 'T7 Promoter', 'start': 1, 'end': 17},
                    {'name': 'Shine-Dalgarno B0034', 'start': 18, 'end': 29},
                    {'name': 'CDS', 'start': 30, 'end': 122},
                    {'name': 'rrnB T1 Terminator', 'start': 123, 'end': len(final_seq)},
                ],
                'total_length': len(final_seq),
                'gc_content': 65.0,
            },
        )
        st.session_state.clear()
        st.session_state['design_session'] = ds
        ctrl = SessionController()

        st.session_state[SK.ACTIVE_HOST] = ds.host
        st.session_state[SK.ACTIVE_SEQ] = ds.frame['final_sequence']

        rendered_summary = []

        def _fake_primer_design(*args, **kwargs):
            return {
                'success': True,
                'error': '',
                'input_length': len(final_seq),
                'results': [
                    {
                        'quality_grade': 'Recommended',
                        'quality_score': 94,
                        'quality_reasons': ['Primer metrics are aligned with target Tm 60.0°C.'],
                        'product_size': len(final_seq),
                        'template_length': len(final_seq),
                        'target_tm': 60.0,
                        'tm_gap': 0.2,
                        'hetero_dimer_risk': 'Low',
                        'pair_warnings': [],
                        'primers': [
                            {'name': 'Forward Primer', 'role': 'forward', 'sequence': 'ATGGCCGCCGCCGCCGCC', 'tm': 60.0},
                            {'name': 'Reverse Primer', 'role': 'reverse', 'sequence': 'TTAGGCGGCGGCGGCGGC', 'tm': 60.1},
                        ],
                    }
                ],
            }

        monkeypatch.setattr(step4, '_step_header', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_section_label', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_frame_summary_card', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_render_primer_quality_summary', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_render_primer_table', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_status_panel', lambda *a, **k: None)
        monkeypatch.setattr(
            step4,
            '_render_best_plan_summary',
            lambda ds_arg: rendered_summary.append(
                step4.build_step4_assembly_plan_summary(ds_arg)
            ),
        )
        monkeypatch.setattr(step4, 'design_outer_primers_for_cassette', _fake_primer_design)
        monkeypatch.setattr(step4.st, 'divider', lambda: None)
        monkeypatch.setattr(step4.st, 'caption', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'slider', lambda *a, **k: a[3])
        monkeypatch.setattr(step4.st, 'button', lambda *a, **k: k.get('key') == 'wf_p4_design_sync')
        monkeypatch.setattr(step4.st, 'success', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'warning', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'error', lambda *a, **k: None)
        _mark_primer_backend_available(monkeypatch, step4)

        step4.page(ctrl)

        updated = ctrl.get()
        fragment_names = [primer.get('Fragment Name') for primer in updated.primers]
        assert len(updated.primers) == 1
        assert fragment_names == ['Expression cassette']
        assert 'T7 Promoter' not in fragment_names
        assert 'Shine-Dalgarno B0034' not in fragment_names
        assert 'rrnB T1 Terminator' not in fragment_names
        assert updated.primer_context_signature
        assert updated.primer_context_signature == updated.current_primer_context_signature()
        assert updated.step4_plan_summary['design_scope'] == 'expression_cassette'
        assert updated.step4_plan_summary['selected_result_index'] == 0
        assert updated.step4_plan_summary['structured_results']
        assert updated.step4_plan_summary['structured_results'][0]['name'] == 'Expression cassette'
        assert updated.step4_plan_summary['selected_overlap_len'] is None
        assert updated.step4_plan_summary['selected_target_tm'] == 60.0
        assert rendered_summary and rendered_summary[0]['selected_target_tm'] == 60.0

    def test_step4_selection_keeps_only_active_primer_pair_for_downstream(self, monkeypatch):
        import streamlit as st
        import views.wizard_steps.step4_cloning_primers as step4

        final_seq = 'ATG' + 'GCCGAACTGATC' * 12 + 'TAA'
        ds = DesignSession(
            step=4,
            gene_name='ActiveSelectionCase',
            original_seq=final_seq,
            optimized_seq=final_seq,
            host='E.coli BL21(DE3)',
            tag='No tag',
            frame={
                'success': True,
                'final_sequence': final_seq,
                'parts': [],
                'features': [],
                'total_length': len(final_seq),
                'gc_content': 50.0,
            },
            primers=[
                {
                    'Fragment Name': 'Expression cassette',
                    "Forward Primer (5'->3')": 'ATGGCCGAACTGATCGCC',
                    "Reverse Primer (5'->3')": 'TTAGATCAGTTCGGCCAT',
                    'Quality Grade': 'Recommended',
                    'Quality Reasons': ['Initial option'],
                    'Warnings': [],
                }
            ],
            step4_plan_summary={
                'design_scope': 'expression_cassette',
                'selected_result_index': 0,
                'structured_results': [
                    {
                        'name': 'Expression cassette',
                        'quality_grade': 'Recommended',
                        'quality_score': 95,
                        'quality_reasons': ['Initial option'],
                        'product_size': len(final_seq),
                        'target_tm': 60.0,
                        'tm_gap': 0.1,
                        'pair_warnings': [],
                        'primers': [
                            {'name': 'Forward Primer', 'role': 'forward', 'sequence': 'ATGGCCGAACTGATCGCC', 'tm': 60.0},
                            {'name': 'Reverse Primer', 'role': 'reverse', 'sequence': 'TTAGATCAGTTCGGCCAT', 'tm': 60.1},
                        ],
                    },
                    {
                        'name': 'Expression cassette',
                        'quality_grade': 'Usable with Risk',
                        'quality_score': 72,
                        'quality_reasons': ['Moderate review required'],
                        'product_size': len(final_seq),
                        'target_tm': 61.0,
                        'tm_gap': 1.8,
                        'pair_warnings': ['Moderate review required'],
                        'primers': [
                            {'name': 'Forward Primer', 'role': 'forward', 'sequence': 'ATGGCCGAACTGATCGCCGAA', 'tm': 61.2},
                            {'name': 'Reverse Primer', 'role': 'reverse', 'sequence': 'TTAGATCAGTTCGGCCATGGC', 'tm': 59.4},
                        ],
                    },
                ],
            },
        )
        st.session_state.clear()
        st.session_state['design_session'] = ds
        ctrl = SessionController()
        st.session_state[SK.ACTIVE_HOST] = ds.host
        st.session_state[SK.ACTIVE_SEQ] = final_seq

        monkeypatch.setattr(step4, '_step_header', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_section_label', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_frame_summary_card', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_render_primer_quality_summary', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_render_primer_table', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_render_structured_primer_results', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_render_best_plan_summary', lambda *a, **k: None)
        monkeypatch.setattr(step4, '_status_panel', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'divider', lambda: None)
        monkeypatch.setattr(step4.st, 'caption', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'slider', lambda *a, **k: a[3])
        monkeypatch.setattr(step4.st, 'button', lambda *a, **k: False)
        monkeypatch.setattr(step4.st, 'selectbox', lambda *a, **k: k['options'][1])
        monkeypatch.setattr(step4.st, 'success', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'warning', lambda *a, **k: None)
        monkeypatch.setattr(step4.st, 'error', lambda *a, **k: None)

        step4.page(ctrl)

        updated = ctrl.get()
        assert updated.step4_plan_summary['selected_result_index'] == 1
        assert len(updated.primers) == 1
        active = updated.primers[0]
        assert active["Forward Primer (5'->3')"] == 'ATGGCCGAACTGATCGCCGAA'
        assert active["Reverse Primer (5'->3')"] == 'TTAGATCAGTTCGGCCATGGC'
        assert active['Quality Grade'] == 'Usable with Risk'
        assert active['Quality Reasons'] == ['Moderate review required']

    def test_build_step4_assembly_plan_summary_normalizes_existing_plan_fields(self):
        import views.wizard_steps.step4_cloning_primers as step4

        final_seq = 'ATG' + 'GCC' * 20 + 'TAA'
        ds = DesignSession(
            step=4,
            gene_name='AssemblySummaryCase',
            original_seq='ATG' + 'AAA' * 10 + 'TAA',
            optimized_seq='ATG' + 'GCC' * 10 + 'TAA',
            host='E.coli BL21(DE3)',
            cloning_method='Gibson Assembly',
            frame={
                'success': True,
                'final_sequence': final_seq,
                'total_length': len(final_seq),
                'vector_suggestion': 'pET-style backbone',
            },
            primers=[
                {
                    'Fragment Name': 'FragA',
                    "Forward Primer (5'->3')": 'ATGGCCGCCGCCGCCGCC',
                    "Reverse Primer (5'->3')": 'TTAGGCGGCGGCGGCGGC',
                    'Quality Grade': 'Recommended',
                    'Warnings': [],
                },
                {
                    'Fragment Name': 'FragB',
                    "Forward Primer (5'->3')": 'GCCGCCGCCGCCGCCGCC',
                    "Reverse Primer (5'->3')": 'GGCGGCGGCGGCGGCTTA',
                    'Quality Grade': 'Usable with Risk',
                    'Warnings': ['Moderate cross-dimer risk between primers (6 bp complementarity).'],
                },
            ],
            primer_context_signature='',
            step4_plan_summary={
                'selected_overlap_len': 18,
                'selected_target_tm': 58.0,
                'tried_combinations': 9,
                'best_plan_summary': 'Review summary recorded 0 Not Recommended, 1 Usable with Risk, and 1 Recommended primer pair(s).',
                'structured_results': [
                    {
                        'product_size': len(final_seq),
                        'quality_grade': 'Recommended',
                        'quality_score': 92,
                        'pair_warnings': [],
                    }
                ],
            },
        )

        summary = step4.build_step4_assembly_plan_summary(ds)

        assert summary['assembly_method'] == 'Gibson Assembly'
        assert summary['insert_length'] == len(ds.optimized_seq)
        assert summary['final_construct_length'] == len(final_seq)
        assert summary['expected_product_size'] == len(final_seq)
        assert summary['host'] == 'E.coli BL21(DE3)'
        assert summary['vector_backbone'] == 'pET-style backbone'
        assert summary['primer_count'] == 4
        assert summary['forward_primer_count'] == 2
        assert summary['reverse_primer_count'] == 2
        assert summary['warning_count'] == 1
        assert '1 Recommended' in summary['quality_summary']
        assert '1 Usable with Risk' in summary['quality_summary']
        assert summary['stale_status'] == 'Current'
        assert summary['context_signature_status'] == 'Not recorded'
        assert summary['selected_overlap_len'] == 18
        assert summary['selected_target_tm'] == 58.0
        assert summary['tried_combinations'] == 9

    def test_step4_primer_option_copy_is_review_context_not_score_claim(self):
        import views.wizard_steps.step4_cloning_primers as step4

        label = step4._primer_option_label(
            0,
            {
                'quality_grade': 'Recommended',
                'quality_score': 88,
                'tm_gap': 0.3,
                'hetero_dimer_risk': 'Low',
            },
        )

        assert 'Review value 88' in label
        assert 'Score 88' not in label

        source = Path(ROOT, 'views', 'wizard_steps', 'step4_cloning_primers.py').read_text(encoding='utf-8')
        assert 'How to interpret primer option summary' in source
        assert 'This review context does not certify experimental readiness' in source
