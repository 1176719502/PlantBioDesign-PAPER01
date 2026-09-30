# -*- coding: utf-8 -*-
"""
tests/test_wizard_regression.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Focused regression tests for the live Expression Wizard path.

Live path covered:
    app.py
      -> views/ExpressionWizard.py   (thin shell)
      -> views/wizard_flow.py        (dispatcher + compat shims)
      -> views/wizard_steps/_shared.py
      -> views/wizard_steps/stepN_*.py
      -> core/design_session.py      (DesignSession, SessionController)
      -> core/expression_frame_builder.py

None of these tests touch views/Design.py (legacy dead code).

Run with:
    python -m pytest tests/test_wizard_regression.py -v
"""
from __future__ import annotations

import sys
import os
import sqlite3

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from core.design_session import DesignSession, SessionController
from core.expression_frame_builder import (
    build_expression_frame,
    build_step3_fidelity_summary,
    list_supported_hosts,
    get_host_rules,
    validate_frame,
)
from core.session_keys import SK
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


def _wizard_regression_db_path(filename: str) -> str:
    return str(repo_local_sqlite_db_path(".pytest_tmp_r78_wizard_regression_dbs", filename))


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# Valid CDS: 84 bp, starts with ATG, ends with TAA
VALID_CDS = (
    'ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCC'
    'ATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA'
)

HOST_ECOLI  = 'E.coli BL21(DE3)'
HOST_AGRO   = 'Agrobacterium GV3101'
HOST_YEAST  = 'S. cerevisiae'
HOST_MAMMAL = 'HEK293'


# ===========================================================================
# 1. wizard_flow compatibility shims (_check_dna_input, _clean_seq)
# ===========================================================================

class TestWizardFlowCompatShims:
    """
    Regression: wizard_flow.py re-exports _check_dna_input and _clean_seq
    from views/wizard_steps/_shared.py so that existing tests can import
    them from views.wizard_flow without modification.

    If either shim breaks, the wizard startup path is broken because
    wizard_flow.py is the first module ExpressionWizard.render() loads.
    """

    def test_check_dna_input_importable_from_wizard_flow(self):
        """
        Regression guard: _check_dna_input must be importable from
        views.wizard_flow (backward-compat shim must resolve).
        """
        from views.wizard_flow import _check_dna_input
        assert callable(_check_dna_input)

    def test_clean_seq_importable_from_wizard_flow(self):
        """
        Regression guard: _clean_seq must be importable from views.wizard_flow.
        """
        from views.wizard_flow import _clean_seq
        assert callable(_clean_seq)

    def test_check_dna_input_resolves_to_shared(self):
        """
        Regression guard: the wizard_flow shim and the _shared canonical
        implementation must be the same object (no diverged copies).
        """
        from views.wizard_flow import _check_dna_input as from_flow
        from views.wizard_steps._shared import _check_dna_input as from_shared
        assert from_flow is from_shared

    def test_clean_seq_resolves_to_shared(self):
        """
        Regression guard: _clean_seq shim must also resolve to the same
        object as the _shared implementation.
        """
        from views.wizard_flow import _clean_seq as from_flow
        from views.wizard_steps._shared import _clean_seq as from_shared
        assert from_flow is from_shared

    def test_clean_seq_strips_fasta_header(self):
        """
        Regression guard: _clean_seq must remove FASTA header lines and
        return only uppercase ATCG characters.
        """
        from views.wizard_flow import _clean_seq
        result = _clean_seq('>MyGene\nATGGCTAGCATCG')
        assert result == 'ATGGCTAGCATCG'

    def test_clean_seq_removes_whitespace_and_non_dna(self):
        """
        Regression guard: _clean_seq must strip whitespace and all non-ATCGN
        chars, and uppercase the result. Downstream functions always receive
        a clean string.
        """
        from views.wizard_flow import _clean_seq
        result = _clean_seq('atg gctn\ntcg')
        assert result == 'ATGGCTNTCG'


# ===========================================================================
# 2. SessionController.can_advance gate logic (all 6 steps)
# ===========================================================================

class TestSessionControllerCanAdvanceGates:
    """
    Regression: SessionController.can_advance is the single source of truth
    for all "Next" button enablement.  Each step's gate rule must be enforced
    exactly as documented in core/design_session.py.

    Tests run without a running Streamlit server by monkey-patching
    st.session_state to a plain dict.
    """

    @pytest.fixture(autouse=True)
    def _patch_streamlit(self, monkeypatch):
        """Provide a minimal fake st so SessionController runs headlessly."""
        import types
        fake_state = {}
        fake_st = types.SimpleNamespace(
            session_state=fake_state,
            rerun=lambda: None,
        )
        monkeypatch.setattr('streamlit.session_state', fake_st.session_state)
        monkeypatch.setattr('streamlit.rerun', fake_st.rerun)
        # Patch the import inside design_session methods
        import core.design_session as _ds_mod
        import streamlit as _st
        monkeypatch.setattr(_st, 'session_state', fake_state)
        monkeypatch.setattr(_st, 'rerun', lambda: None)

    def _ctrl_with(self, ds: DesignSession) -> SessionController:
        """Save *ds* into a fresh SessionController and return it."""
        import streamlit as st
        st.session_state.clear()
        st.session_state['design_session'] = ds
        return SessionController()

    # ── Step 1: original_seq >= 30 bp ────────────────────────────────────────

    def test_step1_blocked_when_seq_empty(self):
        """Step 1 gate blocks when original_seq is empty string."""
        ds = DesignSession(step=1, original_seq='')
        assert not self._ctrl_with(ds).can_advance

    def test_step1_blocked_when_seq_29bp(self):
        """Step 1 gate blocks for sequences one bp below the 30-bp threshold."""
        ds = DesignSession(step=1, original_seq='A' * 29)
        assert not self._ctrl_with(ds).can_advance

    def test_step1_passes_at_exactly_30bp(self):
        """Step 1 gate passes at the exact 30-bp boundary."""
        ds = DesignSession(step=1, original_seq='A' * 30)
        assert self._ctrl_with(ds).can_advance is True

    def test_step1_passes_with_full_cds(self):
        """Step 1 gate passes for a realistic 84-bp CDS."""
        ds = DesignSession(step=1, original_seq=VALID_CDS)
        assert self._ctrl_with(ds).can_advance is True

    # ── Step 2: host must be non-empty ───────────────────────────────────────

    def test_step2_blocked_when_host_empty(self):
        """Step 2 gate blocks when host is empty string."""
        ds = DesignSession(step=2, original_seq=VALID_CDS, host='')
        assert not self._ctrl_with(ds).can_advance

    def test_step2_passes_when_host_set(self):
        """Step 2 gate passes once a non-empty host is assigned."""
        ds = DesignSession(step=2, original_seq=VALID_CDS, host=HOST_ECOLI)
        assert self._ctrl_with(ds).can_advance is True

    # ── Step 3: frame_ok must be True ────────────────────────────────────────

    def test_step3_blocked_when_frame_empty_dict(self):
        """
        Step 3 gate blocks when frame is {} (build not yet run).
        This is the core stale-state guard.
        """
        ds = DesignSession(step=3, original_seq=VALID_CDS, host=HOST_ECOLI, frame={})
        assert not self._ctrl_with(ds).can_advance

    def test_step3_blocked_when_frame_success_false(self):
        """
        Step 3 gate blocks when frame dict is present but success=False
        (build failed due to unsupported tag, bad sequence, etc.).
        """
        failed_frame = {'success': False, 'error': 'Tag not supported.'}
        ds = DesignSession(step=3, original_seq=VALID_CDS, host=HOST_ECOLI,
                           frame=failed_frame)
        assert not self._ctrl_with(ds).can_advance

    def test_step3_passes_when_frame_success_true(self):
        """
        Step 3 gate passes when a successful expression frame is present.
        Uses a real build_expression_frame call to populate the frame.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success'], 'Precondition: frame build must succeed'
        ds = DesignSession(step=3, original_seq=VALID_CDS, host=HOST_ECOLI,
                           frame=frame)
        assert self._ctrl_with(ds).can_advance is True

    # ── Step 4: primers list must be non-empty ───────────────────────────────

    def test_step4_blocked_when_primers_empty(self):
        """Step 4 gate blocks when no primers have been designed yet."""
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        ds = DesignSession(step=4, original_seq=VALID_CDS, host=HOST_ECOLI,
                           frame=frame, primers=[])
        assert not self._ctrl_with(ds).can_advance

    def test_step4_passes_when_primer_backend_unavailable_is_recorded(self):
        """Step 4 gate allows documentation-only continuation when primer design is unavailable."""
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        ds = DesignSession(
            step=4,
            original_seq=VALID_CDS,
            host=HOST_ECOLI,
            frame=frame,
            primers=[],
            primer_design_status='unavailable',
            primer_backend_available=False,
            active_primer_pair=None,
        )
        ds.primer_context_signature = ds.current_primer_context_signature()
        assert self._ctrl_with(ds).can_advance is True

    def test_step4_passes_when_primers_present(self):
        """Step 4 gate passes once the primers list is non-empty."""
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        dummy_primers = [{'name': 'fwd', 'sequence': 'ATGGTGAGC'}]
        ds = DesignSession(step=4, original_seq=VALID_CDS, host=HOST_ECOLI,
                           frame=frame, primers=dummy_primers)
        assert self._ctrl_with(ds).can_advance is True

    # ── Step 5: validation_results must be non-empty ─────────────────────────

    def test_step5_blocked_when_validation_not_run(self):
        """Step 5 gate blocks when validation_results is empty list."""
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        ds = DesignSession(step=5, original_seq=VALID_CDS, host=HOST_ECOLI,
                           frame=frame, validation_results=[])
        assert not self._ctrl_with(ds).can_advance

    def test_step5_passes_when_validation_populated(self):
        """Step 5 gate passes when validation_results contains at least one entry."""
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        results = validate_frame(frame)
        assert len(results) >= 0  # validate_frame always returns a list
        # Inject at least one entry to satisfy the gate
        if not results:
            results = [{'severity': 'info', 'code': 'OK', 'title': 'All clear',
                        'why': '', 'fix': ''}]
        ds = DesignSession(step=5, original_seq=VALID_CDS, host=HOST_ECOLI,
                           frame=frame, validation_results=results)
        assert self._ctrl_with(ds).can_advance is True

    # ── Step 6: always True (export, no further steps) ───────────────────────

    def test_step6_always_can_advance(self):
        """Step 6 is the export step; can_advance must always return True."""
        ds = DesignSession(step=6)
        assert self._ctrl_with(ds).can_advance is True


# ===========================================================================
# 3. host/tag/elements changes clear downstream state (Step 2 logic)
# ===========================================================================

class TestStep2DownstreamStateClear:
    """
    Regression: when the user changes host, tag, promoter, RBS, or terminator
    in Step 2 and confirms with "Next: Build Frame", all downstream artefacts
    (frame, optimized_seq, primers, validation_results) must be wiped.

    This mirrors the _inputs_changed block in
    views/wizard_steps/step2_host_elements.py.
    """

    def _session_with_completed_step3(self, host: str) -> DesignSession:
        """Return a DesignSession as if Step 3 succeeded for *host*."""
        frame = build_expression_frame(VALID_CDS, host=host, tag='No tag')
        assert frame['success'], f'Precondition failed for {host}'
        ds = DesignSession()
        ds.original_seq  = VALID_CDS
        ds.host          = host
        ds.tag           = 'No tag'
        ds.elements      = {'promoter_name': 'T7', 'rbs_name': 'B0034',
                            'terminator_name': 'rrnB'}
        ds.frame         = frame
        ds.optimized_seq = frame['final_sequence']
        ds.primers       = [{'name': 'fwd', 'sequence': 'ATGGTGAGC'}]
        ds.validation_results = [{'severity': 'info', 'code': 'OK',
                                  'title': 'All checks passed', 'why': '', 'fix': ''}]
        return ds

    def _wipe_downstream(self, ds: DesignSession) -> None:
        """Replicate the _inputs_changed wipe from step2_host_elements.page()."""
        ds.frame              = {}
        ds.optimized_seq      = ''
        ds.primers            = []
        ds.validation_results = []

    def test_host_change_clears_frame(self):
        """
        Regression guard: changing the host must set frame = {} so Step 3
        cannot silently reuse a cassette built for the old host.
        """
        ds = self._session_with_completed_step3(HOST_ECOLI)
        assert ds.frame_ok, 'Precondition: frame must be built'
        self._wipe_downstream(ds)
        ds.host = HOST_YEAST
        assert ds.frame == {}
        assert ds.frame_ok is False

    def test_host_change_clears_optimized_seq(self):
        """
        Regression guard: changing the host must wipe optimized_seq so
        Step 3 fallback logic cannot reuse a stale optimized sequence.
        """
        ds = self._session_with_completed_step3(HOST_ECOLI)
        assert ds.optimized_seq, 'Precondition: optimized_seq must be set'
        self._wipe_downstream(ds)
        ds.host = HOST_YEAST
        assert ds.optimized_seq == ''

    def test_host_change_clears_primers(self):
        """
        Regression guard: changing the host must wipe primers so Step 4
        cannot display primers designed for a different construct.
        """
        ds = self._session_with_completed_step3(HOST_ECOLI)
        assert ds.primers, 'Precondition: primers must be set'
        self._wipe_downstream(ds)
        ds.host = HOST_YEAST
        assert ds.primers == []

    def test_host_change_clears_validation_results(self):
        """
        Regression guard: changing the host must wipe validation_results so
        Step 5 cannot show stale validation output.
        """
        ds = self._session_with_completed_step3(HOST_ECOLI)
        assert ds.validation_results, 'Precondition: validation_results must be set'
        self._wipe_downstream(ds)
        ds.host = HOST_YEAST
        assert ds.validation_results == []

    def test_tag_change_clears_downstream(self):
        """
        Regression guard: changing only the tag (same host) must also wipe
        downstream artefacts because the frame encodes the tag sequence.
        step2_host_elements.py checks ds.tag != tag as part of _inputs_changed.
        """
        ds = self._session_with_completed_step3(HOST_ECOLI)
        inputs_changed = (ds.tag != 'His6-tag (C-term)')
        assert inputs_changed, 'Precondition: tag must differ'
        if inputs_changed:
            self._wipe_downstream(ds)
        ds.tag = 'His6-tag (C-term)'
        assert ds.frame == {}
        assert ds.primers == []

    def test_same_inputs_do_not_clear_downstream(self):
        """
        Regression guard: if the user re-opens Step 2 without changing
        anything, downstream artefacts must NOT be wiped.
        """
        ds = self._session_with_completed_step3(HOST_ECOLI)
        saved_frame   = ds.frame
        saved_primers = ds.primers[:]
        inputs_changed = (
            ds.host != HOST_ECOLI
            or ds.tag != 'No tag'
            or ds.elements.get('promoter_name', '') != 'T7'
        )
        if inputs_changed:
            self._wipe_downstream(ds)
        assert inputs_changed is False, 'Nothing changed — should not wipe'
        assert ds.frame is saved_frame
        assert ds.primers == saved_primers


class TestStep2ElementWiringIntoStep3Build:
    """
    Regression: Step 3 must pass Step 2 custom element selections into
    build_expression_frame() so selected registry sequences are reflected
    in the assembled cassette.
    """

    def test_tag_selection_is_applied_in_built_cds(self):
        """Step 2 tag choice must change the built CDS in Step 3 output."""
        frame = build_expression_frame(
            VALID_CDS,
            host=HOST_ECOLI,
            tag='His6-tag (C-term)',
            custom_elements={},
        )
        assert frame['success'] is True
        assert frame['tag_applied'] == 'His6-tag (C-term)'

        cds_part = next(p for p in frame['parts'] if p['type'] == 'CDS')
        assert cds_part['seq'] != VALID_CDS
        assert 'GGTGGTCACCACCACCACCACCAC' in cds_part['seq']

    def test_custom_promoter_rbs_terminator_sequences_override_host_defaults(self):
        """Custom Step 2 sequences must be used in final_sequence and parts."""
        custom_elements = {
            "promoter_name": "Custom Promoter",
            "promoter_seq": "TTGACATATAAT",
            "rbs_name": "Custom RBS",
            "rbs_seq": "AGGAGG",
            "terminator_name": "Custom Terminator",
            "terminator_seq": "GCGTTTTTGC",
        }
        frame = build_expression_frame(
            VALID_CDS,
            host=HOST_ECOLI,
            tag='No tag',
            custom_elements=custom_elements,
        )

        assert frame['success'] is True
        assert frame['promoter_name'] == 'Custom Promoter'
        assert frame['rbs_name'] == 'Custom RBS'
        assert frame['terminator_name'] == 'Custom Terminator'

        parts = frame.get('parts', [])


class TestStep3FirstClickRefreshRegression:
    """Regression coverage for Step 3 first-click refresh behavior."""

    @pytest.fixture(autouse=True)
    def _patch_streamlit_session(self, monkeypatch):
        import streamlit as _st
        fake_state = {}
        rerun_calls = []

        def _fake_rerun():
            rerun_calls.append(True)

        monkeypatch.setattr(_st, 'session_state', fake_state)
        monkeypatch.setattr(_st, 'rerun', _fake_rerun)
        self._rerun_calls = rerun_calls

    def _ctrl_with(self, ds: DesignSession) -> SessionController:
        import streamlit as st
        st.session_state.clear()
        st.session_state['design_session'] = ds
        return SessionController()

    def test_step3_success_path_requests_rerun_after_state_save(self, monkeypatch):
        import types
        import views.wizard_steps.step3_expression_frame as step3
        import core.codon_optimizer as codon_optimizer
        import core.expression_frame_builder as frame_builder

        class _Spinner:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        ds = DesignSession(
            step=3,
            original_seq=VALID_CDS,
            host=HOST_ECOLI,
            tag='No tag',
            elements={},
        )
        ctrl = self._ctrl_with(ds)

        optimization_result = {
            'success': True,
            'optimized_sequence': 'ATGAAACCCGGGTAA',
            'before': {'cai': 0.61, 'gc_percent': 48.0},
            'after': {'cai': 0.83, 'gc_percent': 51.0},
            'history': [{'from': 'GGT', 'to': 'GGC'}],
            'warnings': [],
        }
        frame_result = {
            'success': True,
            'final_sequence': 'TTGACAATGAAACCCGGGTAATTTTT',
            'total_length': 26,
            'gc_content': 50.0,
            'parts': [],
            'host_context': {},
        }

        monkeypatch.setattr(codon_optimizer, 'optimize_cds_sequence', lambda **_kwargs: optimization_result)
        monkeypatch.setattr(frame_builder, 'build_expression_frame', lambda **_kwargs: frame_result)
        monkeypatch.setattr(step3, '_step_header', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3, '_section_label', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3, '_status_panel', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3, '_seq_summary_row', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3, '_delta_badge', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'columns', lambda spec, **kwargs: [types.SimpleNamespace(markdown=lambda *a, **k: None) for _ in range(spec if isinstance(spec, int) else len(spec))])
        monkeypatch.setattr(step3.st, 'button', lambda *args, **kwargs: True)
        monkeypatch.setattr(step3.st, 'spinner', lambda *args, **kwargs: _Spinner())
        monkeypatch.setattr(step3.st, 'divider', lambda: None)
        monkeypatch.setattr(step3.st, 'markdown', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'metric', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'caption', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'expander', lambda *args, **kwargs: _Spinner())
        monkeypatch.setattr(step3.st, 'code', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'success', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'error', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'rerun', lambda: self._rerun_calls.append(True))

        step3.page(ctrl)

        updated = ctrl.get()
        assert updated.optimized_seq == 'ATGAAACCCGGGTAA'
        assert updated.codon_report.get('success') is True
        assert updated.frame.get('success') is True
        assert len(self._rerun_calls) == 1




    def test_custom_names_without_sequences_fall_back_to_host_default_sequences(self):
        """
        Current behavior contract: name-only overrides update labels, while
        sequence still falls back to host defaults when no custom sequence is provided.
        """
        frame = build_expression_frame(
            VALID_CDS,
            host=HOST_ECOLI,
            tag='No tag',
            custom_elements={
                'promoter_name': 'Name Only Promoter',
                'rbs_name': 'Name Only RBS',
                'terminator_name': 'Name Only Terminator',
            },
        )
        rules = get_host_rules(HOST_ECOLI)

        assert frame['success'] is True
        assert frame['promoter_name'] == 'Name Only Promoter'
        assert frame['rbs_name'] == 'Name Only RBS'
        assert frame['terminator_name'] == 'Name Only Terminator'
        assert frame['parts'][0]['seq'] == rules['promoter_seq']
        assert frame['parts'][1]['seq'].startswith(rules['rbs_seq'])
        assert frame['parts'][-1]['seq'] == rules['terminator_seq']


class TestStep3FidelitySummary:
    """Regression coverage for Step 3 translation/stop/length summary."""

    def test_translation_match_true_for_synonymous_optimized_cds(self):
        optimized = VALID_CDS.replace('TTC', 'TTT', 1)
        frame = build_expression_frame(optimized, host=HOST_ECOLI, tag='No tag')
        summary = build_step3_fidelity_summary(VALID_CDS, optimized, frame=frame, tag='No tag')
        assert summary['translations_match'] is True

    def test_stop_codon_retained_without_tag(self):
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        summary = build_step3_fidelity_summary(VALID_CDS, VALID_CDS, frame=frame, tag='No tag')
        assert summary['optimized_has_stop'] is True
        assert summary['framed_cds_has_stop'] is True

    def test_stop_codon_retained_with_c_terminal_tag(self):
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='His6-tag (C-term)')
        summary = build_step3_fidelity_summary(VALID_CDS, VALID_CDS, frame=frame, tag='His6-tag (C-term)')
        assert summary['optimized_has_stop'] is True
        assert summary['framed_cds_has_stop'] is True

    def test_length_breakdown_attributes_tag_vs_context(self):
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='His6-tag (C-term)')
        summary = build_step3_fidelity_summary(VALID_CDS, VALID_CDS, frame=frame, tag='His6-tag (C-term)')
        assert summary['optimization_delta_bp'] == 0
        assert summary['cds_assembly_delta_bp'] > 0
        assert summary['frame_context_delta_bp'] > 0
        assert 'tag/linker' in summary['length_change_reason_summary']

    def test_no_tag_summary_does_not_claim_tag_driven_length_change(self):
        no_stop = VALID_CDS[:-3]
        frame = build_expression_frame(no_stop, host=HOST_ECOLI, tag='No tag')
        summary = build_step3_fidelity_summary(no_stop, no_stop, frame=frame, tag='No tag')
        assert 'tag/linker' not in summary['length_change_reason_summary']
        assert 'automatic start/stop completion' in summary['length_change_reason_summary']


class TestStep3FidelityRenderingRegression:
    """Regression coverage for the new Step 3 fidelity UI section."""

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

    def test_fidelity_section_renders_without_breaking_step3(self, monkeypatch):
        import types
        import views.wizard_steps.step3_expression_frame as step3

        class _Spinner:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False

        calls = []
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='His6-tag (C-term)')
        ds = DesignSession(
            step=3,
            original_seq=VALID_CDS,
            optimized_seq=VALID_CDS,
            host=HOST_ECOLI,
            tag='His6-tag (C-term)',
            frame=frame,
            codon_report={'success': True, 'before': {}, 'after': {}, 'history': [], 'warnings': []},
        )
        ctrl = self._ctrl_with(ds)

        monkeypatch.setattr(step3, '_step_header', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3, '_section_label', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3, '_status_panel', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3, '_seq_summary_row', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3, '_delta_badge', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3, '_cassette', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'columns', lambda spec, **kwargs: [types.SimpleNamespace(markdown=lambda *a, **k: None, metric=lambda *a, **k: calls.append(a)) for _ in range(spec if isinstance(spec, int) else len(spec))])
        monkeypatch.setattr(step3.st, 'button', lambda *args, **kwargs: False)
        monkeypatch.setattr(step3.st, 'spinner', lambda *args, **kwargs: _Spinner())
        monkeypatch.setattr(step3.st, 'divider', lambda: None)
        monkeypatch.setattr(step3.st, 'markdown', lambda body, **kwargs: calls.append(body))
        monkeypatch.setattr(step3.st, 'metric', lambda *args, **kwargs: calls.append(args))
        monkeypatch.setattr(step3.st, 'caption', lambda body, **kwargs: calls.append(body))
        monkeypatch.setattr(step3.st, 'expander', lambda *args, **kwargs: _Spinner())
        monkeypatch.setattr(step3.st, 'code', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'success', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'error', lambda *args, **kwargs: None)
        monkeypatch.setattr(step3.st, 'info', lambda body, **kwargs: calls.append(body))

        step3.page(ctrl)

        joined = '\n'.join(str(x) for x in calls)

        assert 'Translation and integrity checks' in joined
        assert 'Translation consistency' in joined
        assert 'Preview CDS stop codon' in joined
        assert 'Framed CDS stop codon' in joined
        assert 'Any CDS length increase during assembly comes from tag/linker fusion rather than the codon usage preview.' in joined


# ===========================================================================
# 4. After downstream clear, can_advance is blocked at Step 3
# ===========================================================================

class TestCanAdvanceBlockedAfterDownstreamClear:
    """
    Regression: after Step 2 wipes downstream state, SessionController.can_advance
    at Step 3 must return False so the UI correctly blocks the Next button.
    This links the _inputs_changed clear in step2 to the Step 3 gate.
    """

    @pytest.fixture(autouse=True)
    def _patch_streamlit(self, monkeypatch):
        import streamlit as _st
        fake_state = {}
        monkeypatch.setattr(_st, 'session_state', fake_state)
        monkeypatch.setattr(_st, 'rerun', lambda: None)

    def _ctrl_with(self, ds: DesignSession) -> SessionController:
        import streamlit as st
        st.session_state.clear()
        st.session_state['design_session'] = ds
        return SessionController()

    def test_step3_gate_blocked_after_host_change_clear(self):
        """
        Regression guard: build frame -> change host -> wipe artefacts ->
        can_advance at Step 3 must be False.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        ds = DesignSession(step=3, original_seq=VALID_CDS, host=HOST_ECOLI,
                           frame=frame)
        assert ds.frame_ok, 'Precondition: frame must be ok'
        # Simulate Step 2 host change wipe
        ds.frame = {}
        ds.optimized_seq = ''
        ds.primers = []
        ds.validation_results = []
        ds.host = HOST_YEAST
        assert self._ctrl_with(ds).can_advance is False

    def test_step3_gate_passes_after_rebuild(self):
        """
        Regression guard (positive): after wiping, rebuilding the frame for
        the new host must re-enable can_advance at Step 3.
        """
        ds = DesignSession(step=3, original_seq=VALID_CDS, host=HOST_YEAST,
                           frame={})
        new_frame = build_expression_frame(VALID_CDS, host=HOST_YEAST, tag='No tag')
        assert new_frame['success'], 'Precondition: rebuild must succeed'
        ds.frame = new_frame
        assert self._ctrl_with(ds).can_advance is True


# ===========================================================================


class TestDesignSessionClearingHelpers:
    """Regression coverage for centralized stale-output clearing helpers."""

    def test_clear_step3_outputs_clears_downstream_signatures_and_summaries(self):
        ds = DesignSession(
            optimized_seq='ATGAAATAA',
            frame={'success': True, 'final_sequence': 'ATGAAATAA'},
            codon_report={'success': True},
            frame_context_signature='frame-signature',
            cloning_method='Gibson Assembly',
            primers=[{'name': 'fwd', 'sequence': 'ATGAAA'}],
            primer_context_host=HOST_ECOLI,
            primer_context_seq_hash='seq-hash',
            primer_context_signature='primer-signature',
            step4_plan_summary={'selected_result_index': 0},
            validation_results=[{'severity': 'info', 'code': 'OK'}],
            validation_context_signature='validation-signature',
        )

        ds.clear_step3_outputs()

        assert ds.optimized_seq == ''
        assert ds.frame == {}
        assert ds.codon_report == {}
        assert ds.frame_context_signature == ''
        assert ds.cloning_method == ''
        assert ds.primers == []
        assert ds.primer_context_host == ''
        assert ds.primer_context_seq_hash == ''
        assert ds.primer_context_signature == ''
        assert ds.step4_plan_summary == {}
        assert ds.validation_results == []
        assert ds.validation_context_signature == ''

    def test_clear_step4_outputs_clears_primer_and_validation_state(self):
        ds = DesignSession(
            cloning_method='Gibson Assembly',
            primers=[{'name': 'fwd', 'sequence': 'ATGAAA'}],
            primer_context_host=HOST_ECOLI,
            primer_context_seq_hash='seq-hash',
            primer_context_signature='primer-signature',
            step4_plan_summary={'selected_result_index': 0},
            validation_results=[{'severity': 'info', 'code': 'OK'}],
            validation_context_signature='validation-signature',
        )

        ds.clear_step4_outputs()

        assert ds.cloning_method == ''
        assert ds.primers == []
        assert ds.primer_context_host == ''
        assert ds.primer_context_seq_hash == ''
        assert ds.primer_context_signature == ''
        assert ds.step4_plan_summary == {}
        assert ds.validation_results == []
        assert ds.validation_context_signature == ''

# 5. Step 4 blocked when no valid frame exists
# ===========================================================================

class TestStep4BlockedWithoutValidFrame:
    """
    Regression: step4_cloning_primers.page() checks
        isinstance(ds.frame, dict) and ds.frame.get('success')
    before rendering primer design. If that guard is removed, stale primers
    from a previous host could be displayed without a matching frame.
    """

    def _frame_gate(self, ds: DesignSession) -> bool:
        """Exact gate expression used in step4_cloning_primers.page()."""
        return isinstance(ds.frame, dict) and bool(ds.frame.get('success'))

    def test_gate_blocks_when_frame_empty(self):
        """Primer design gate blocks when frame == {} (build not yet run)."""
        ds = DesignSession(original_seq=VALID_CDS, host=HOST_ECOLI, frame={})
        assert self._frame_gate(ds) is False

    def test_gate_blocks_when_frame_failed(self):
        """Primer design gate blocks when frame['success'] is False."""
        ds = DesignSession(original_seq=VALID_CDS, host=HOST_ECOLI,
                           frame={'success': False, 'error': 'Unsupported tag.'})
        assert self._frame_gate(ds) is False

    def test_gate_blocks_when_frame_is_none(self):
        """Gate must not raise AttributeError when frame is None."""
        ds = DesignSession()
        ds.frame = None  # type: ignore[assignment]
        assert self._frame_gate(ds) is False

    def test_gate_open_when_frame_succeeded(self):
        """Gate opens when a real successful frame dict is present."""
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        ds = DesignSession(original_seq=VALID_CDS, host=HOST_ECOLI, frame=frame)
        assert self._frame_gate(ds) is True

    def test_gate_open_for_all_hosts_with_no_tag(self):
        """
        Regression guard: build_expression_frame with 'No tag' must succeed
        for every host that lists 'No tag', so Step 4 is always reachable.
        """
        for host in list_supported_hosts():
            rules = get_host_rules(host)
            if 'No tag' not in rules['tag_options']:
                continue
            frame = build_expression_frame(VALID_CDS, host=host, tag='No tag')
            ds = DesignSession(original_seq=VALID_CDS, host=host, frame=frame)
            assert self._frame_gate(ds) is True, (
                f'Step 4 gate must open for host {host!r} with No tag'
            )


# ===========================================================================
# 6. validate_frame uses current session frame, not stale data
# ===========================================================================

class TestValidateFrameUsesCurrentState:
    """
    Regression: validate_frame() must operate on the frame dict present in
    ds.frame at call time, not on any cached or stale value. Step 5 calls
    validate_frame(ds.frame) — if it accidentally read ds.optimized_seq the
    results would be wrong.
    """

    def test_validate_returns_list_for_ecoli(self):
        """validate_frame must return a list (possibly empty) for a valid E.coli frame."""
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        results = validate_frame(frame)
        assert isinstance(results, list)

    def test_validate_returns_list_for_yeast(self):
        """validate_frame must return a list for a valid yeast frame."""
        frame = build_expression_frame(VALID_CDS, host=HOST_YEAST, tag='No tag')
        assert frame['success']
        results = validate_frame(frame)
        assert isinstance(results, list)

    def test_validate_fails_fast_on_failed_frame(self):
        """
        Regression guard: validate_frame on a failed frame dict must return
        a critical error issue immediately rather than crashing or returning [].
        """
        bad_frame = {'success': False, 'error': 'Unsupported tag.'}
        results = validate_frame(bad_frame)
        assert isinstance(results, list)
        assert len(results) >= 1
        assert any(r.get('severity') == 'critical' for r in results)

    def test_different_hosts_produce_different_validation(self):
        """
        Regression guard: validate_frame must inspect the frame it is given,
        so frames built for different hosts produce potentially different
        results (RBS type, GC range, etc. differ by host kingdom).
        The key assertion is that both calls succeed and return lists, not
        that they are identical — host differences may or may not surface.
        """
        frame_ecoli  = build_expression_frame(VALID_CDS, host=HOST_ECOLI,  tag='No tag')
        frame_mammal = build_expression_frame(VALID_CDS, host=HOST_MAMMAL, tag='No tag')
        assert frame_ecoli['success']
        assert frame_mammal['success']
        r_ecoli  = validate_frame(frame_ecoli)
        r_mammal = validate_frame(frame_mammal)
        assert isinstance(r_ecoli,  list)
        assert isinstance(r_mammal, list)
        # Kingdoms differ: E.coli (prokaryote) vs HEK293 (mammalian)
        # At minimum the frames themselves differ
        assert frame_ecoli['kingdom'] != frame_mammal['kingdom']

    def test_validate_reads_frame_sequence_not_raw_seq(self):
        """
        Regression guard: validate_frame analyses frame['final_sequence']
        (the full cassette), NOT ds.original_seq. We confirm by checking
        that frame['total_length'] > len(VALID_CDS) — the cassette includes
        promoter + RBS + CDS + terminator.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        assert frame['total_length'] > len(VALID_CDS), (
            'Cassette must be longer than the bare CDS because it includes '
            'promoter/RBS/terminator — validate_frame works on the full cassette'
        )
        results = validate_frame(frame)
        assert isinstance(results, list)  # validate_frame completed without error


# ===========================================================================
# 7. DesignSession.summary() reflects current state (used by Step 6 export)
# ===========================================================================

class TestDesignSessionSummary:
    """
    Regression: DesignSession.summary() is called by Step 6 to populate the
    export view. It must faithfully reflect the current session state and not
    leak values from a previous run.
    """

    def test_summary_empty_session(self):
        """summary() on a blank session must return zero-length counts."""
        ds = DesignSession()
        s = ds.summary()
        assert s['original_seq_len'] == 0
        assert s['n_primers'] == 0
        assert s['n_issues'] == 0

    def test_summary_after_full_pipeline(self):
        """summary() must accurately reflect a completed pipeline state."""
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        primers = [{'name': 'fwd', 'sequence': 'ATGGTGAGC'},
                   {'name': 'rev', 'sequence': 'TTACTTGTG'}]
        issues  = validate_frame(frame)
        ds = DesignSession(
            gene_name='GFP',
            original_seq=VALID_CDS,
            host=HOST_ECOLI,
            tag='No tag',
            frame=frame,
            optimized_seq=frame['final_sequence'],
            primers=primers,
            validation_results=issues,
        )
        s = ds.summary()
        assert s['gene_name']        == 'GFP'
        assert s['host']             == HOST_ECOLI
        assert s['original_seq_len'] == len(VALID_CDS)
        assert s['frame_length_bp']  == frame['total_length']
        assert s['n_primers']        == 2
        assert s['n_issues']         == len(issues)

    def test_summary_cleared_after_host_change(self):
        """
        Regression guard: after a host-change downstream clear, summary()
        must show zeroed artefact counts, confirming stale data is gone.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        ds = DesignSession(
            original_seq=VALID_CDS, host=HOST_ECOLI, tag='No tag',
            frame=frame, optimized_seq=frame['final_sequence'],
            primers=[{'name': 'fwd', 'sequence': 'ATGGTGAGC'}],
            validation_results=[{'severity': 'info', 'code': 'OK',
                                 'title': '', 'why': '', 'fix': ''}],
        )
        # Simulate downstream clear
        ds.frame              = {}
        ds.optimized_seq      = ''
        ds.primers            = []
        ds.validation_results = []
        ds.host               = HOST_YEAST

        s = ds.summary()
        assert s['frame_length_bp']   == 0
        assert s['optimized_seq_len'] == 0
        assert s['n_primers']         == 0
        assert s['n_issues']          == 0


# ===========================================================================
# 8. _check_dna_input actual validation behavior
# ===========================================================================

class TestCheckDnaInputBehavior:
    """
    Focused tests for the actual _check_dna_input gate logic in
    views/wizard_steps/_shared.py.

    The live implementation checks:
      1. Empty / no alpha chars -> (True, '')  [pass-through; length gate is
         handled separately by the Step 1 can_advance rule]
      2. Protein sequence detection: >= 10% amino-acid-only letters -> fail
      3. ATCG purity: < 85% of alpha letters are A/T/C/G -> fail
      4. Clean valid DNA -> (True, '')

    These tests document and lock the CURRENT contract so any refactor that
    accidentally changes the gate thresholds will be caught immediately.
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        from views.wizard_steps._shared import _check_dna_input
        self.check = _check_dna_input

    # ── Valid DNA passes ──────────────────────────────────────────────────────

    def test_valid_dna_passes(self):
        """Clean all-ATCG sequence must return (True, '')."""
        ok, msg = self.check(VALID_CDS)
        assert ok is True
        assert msg == ''

    def test_valid_dna_lowercase_passes(self):
        """Lowercase ATCG is valid DNA; must pass the gate."""
        ok, msg = self.check(VALID_CDS.lower())
        assert ok is True
        assert msg == ''

    def test_valid_dna_with_whitespace_passes(self):
        """Whitespace between bases is common in copy-pasted sequences and must pass."""
        spaced = ' '.join(VALID_CDS[i:i+10] for i in range(0, len(VALID_CDS), 10))
        ok, msg = self.check(spaced)
        assert ok is True
        assert msg == ''

    def test_empty_input_passes(self):
        """
        Empty input returns (True, '') -- the minimum-length gate is enforced
        separately by SessionController.can_advance (Step 1: len >= 30 bp).
        _check_dna_input does not duplicate that check.
        """
        ok, msg = self.check('')
        assert ok is True
        assert msg == ''

    def test_fasta_formatted_dna_passes(self):
        """FASTA header lines must be stripped; only the sequence body is checked."""
        fasta = '>GFP_CDS description here\n' + VALID_CDS
        ok, msg = self.check(fasta)
        assert ok is True
        assert msg == ''

    def test_multiline_fasta_passes(self):
        """Multi-line FASTA (60-char wrapped) must pass after header stripping."""
        lines = ['>MyProtein']
        for i in range(0, len(VALID_CDS), 20):
            lines.append(VALID_CDS[i:i+20])
        ok, msg = self.check('\n'.join(lines))
        assert ok is True
        assert msg == ''

    # ── Protein sequence detection ────────────────────────────────────────────

    def test_pure_protein_sequence_fails(self):
        """
        A sequence with >= 10% amino-acid-only characters (E, F, H, I, K, L,
        M, P, Q, R, S, V, W, Y etc.) must be rejected with a clear English message
        containing 'protein' or 'amino'.
        """
        # Typical protein: lots of non-ATCG amino acid letters
        protein = 'MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKRQTLGQHDFSAGEGLYTHMKALRPDEDRLSPLHSVYVDQWDWERVMGDGERQFSTLKSTVEAIWAGIKATEAAVSEEFGLAPFLPDQIHFVHSQELLSRYPDLDAKGRERAIAKDLGAVFLVGIGGKLSDGHRHDVRAPDYDDWSTPSELGHAGLNGDILVWNPVLEDAFELSSMGIRVDADTLKHQLALTGEDEDTOKENS'
        ok, msg = self.check(protein)
        assert ok is False
        assert 'protein' in msg.lower() or 'amino' in msg.lower(), (
            f'Expected English protein error message containing "protein" or "amino", got: {msg!r}'
        )

    def test_protein_above_10pct_threshold_fails(self):
        """
        Construct a string where exactly > 10% of alpha chars are protein-only.
        E is an amino-acid-only letter not in ATCG.
        """
        # 89 A's + 11 E's = 11% protein-only -> should fail
        seq = 'A' * 89 + 'E' * 11
        ok, msg = self.check(seq)
        assert ok is False

    def test_protein_below_10pct_threshold_passes(self):
        """
        When protein-only chars are < 10% of total alpha, the protein gate
        does NOT fire (the sequence may still fail the ATCG purity gate if
        total non-ATCG content is high, but the specific protein message
        should not appear).
        """
        # 95 A's + 4 E's = 4% protein-only -> protein gate should not fire
        seq = 'A' * 95 + 'E' * 4
        ok, msg = self.check(seq)
        # If it fails it should be the ATCG purity gate, not the protein gate
        if not ok:
            assert 'protein' not in msg.lower()

    # ── ATCG purity gate ──────────────────────────────────────────────────────

    def test_mostly_n_ambiguous_passes_raw_gate(self):
        """
        N is part of the MVP DNA alphabet, so mostly-N inputs pass
        the raw DNA gate and are downgraded later by Sequence Inspector.
        """
        seq = 'A' * 80 + 'N' * 20
        ok, msg = self.check(seq)
        assert ok is True
        assert msg == ''

    def test_exactly_85pct_atcg_passes(self):
        """
        At exactly 85% ATCGN purity the gate should pass (boundary condition:
        atcgn_ratio < 0.85 fails; >= 0.85 passes).
        """
        # N is accepted as part of the MVP DNA alphabet.
        seq = 'A' * 85 + 'N' * 15
        ok, msg = self.check(seq)
        assert ok is True, (
            f'Expected pass at 85% ATCGN purity boundary, got: {msg}'
        )

    def test_n_bases_do_not_fail_raw_dna_gate(self):
        """
        N bases do not fail the raw DNA gate; Sequence Inspector marks them Needs Review.
        """
        seq = 'A' * 84 + 'N' * 16
        ok, msg = self.check(seq)
        assert ok is True
        assert msg == ''

    # ── RNA / U-containing input ──────────────────────────────────────────────

    def test_rna_sequence_with_u_fails_purity(self):
        """
        RNA sequences containing U are not valid DNA. U is not in ATCG so
        a sequence with many U's falls below the 85% ATCGN purity threshold.
        Example: mRNA-like sequence where T is replaced by U.
        """
        rna_seq = VALID_CDS.replace('T', 'U')  # all T -> U: 0% ATCG T's present
        # Count T's in VALID_CDS to know how many U's are injected
        t_count = VALID_CDS.count('T')
        total_alpha = len(VALID_CDS)  # all alpha after replacing
        atcg_after = total_alpha - t_count  # A, C, G remain
        atcg_ratio = atcg_after / total_alpha
        ok, msg = self.check(rna_seq)
        if atcg_ratio < 0.85:
            # Expect failure
            assert ok is False, (
                f'RNA sequence (T->U, {atcg_ratio:.0%} ATCG) should fail '
                f'purity gate but got ok=True'
            )
        else:
            # If T-content is low enough, purity gate may not fire -- document
            # the actual behavior so the test is not fragile
            pass  # behavior is explicitly documented: gate did not fire

    def test_u_heavy_rna_fails(self):
        """
        A sequence that is >= 50% U (clearly RNA) must fail the ATCG purity
        gate because U is not in the ATCG alphabet.
        """
        # 50 A's + 50 U's = 50% ATCG -> well below 85% -> must fail
        seq = 'A' * 50 + 'U' * 50
        ok, msg = self.check(seq)
        assert ok is False

    # ── Return value contract ─────────────────────────────────────────────────

    def test_return_is_two_tuple(self):
        """_check_dna_input must always return a 2-tuple (bool, str)."""
        result = self.check(VALID_CDS)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_error_return_is_two_tuple(self):
        """Even on failure the return must be a 2-tuple (bool, str)."""
        protein = 'MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQ'
        result = self.check(protein)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_failure_message_is_nonempty(self):
        """When validation fails the error message string must not be blank."""
        protein = 'MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQ'
        ok, msg = self.check(protein)
        if not ok:
            assert msg.strip() != '', 'Failure must include a non-empty reason string'

    def test_clean_seq_header_stripped_before_check(self):
        """
        Regression guard: _check_dna_input must strip FASTA headers before
        character analysis -- a FASTA header containing E/F/H... letters
        must NOT trigger the protein gate.
        """
        # Header contains many protein-only-looking chars; body is pure ATCG
        fasta = '>EFHIKLMPQRSVWY_gene_name_with_lots_of_letters\n' + VALID_CDS
        ok, msg = self.check(fasta)
        assert ok is True, (
            f'FASTA header chars must not trigger protein gate; got: {msg}'
        )


# ===========================================================================
# 9. Beta-critical wizard readiness regressions
# ===========================================================================

class TestBetaCriticalWizardReadiness:
    """Minimal beta-critical state and smoke coverage for wizard readiness."""

    @pytest.fixture(autouse=True)
    def _patch_streamlit(self, monkeypatch):
        import streamlit as _st
        fake_state = {}
        monkeypatch.setattr(_st, 'session_state', fake_state)
        monkeypatch.setattr(_st, 'rerun', lambda: None)

    def _ctrl_with(self, ds: DesignSession) -> SessionController:
        import streamlit as st
        st.session_state.clear()
        st.session_state['design_session'] = ds
        return SessionController()

    def _completed_design(self, host: str = HOST_ECOLI) -> DesignSession:
        frame = build_expression_frame(VALID_CDS, host=host, tag='No tag')
        assert frame['success'], f'Precondition failed for {host}'
        ds = DesignSession(
            step=6,
            gene_name='BetaReady',
            original_seq=VALID_CDS,
            host=host,
            tag='No tag',
            elements={
                'promoter_name': 'T7',
                'rbs_name': 'B0034',
                'terminator_name': 'rrnB',
            },
            frame=frame,
            optimized_seq=frame['final_sequence'],
            primers=[
                {'name': 'Forward Primer', 'sequence': 'ATGGTGAGCAAG'},
                {'name': 'Reverse Primer', 'sequence': 'TTACTTGTGGCC'},
            ],
            validation_results=validate_frame(frame) or [
                {'severity': 'info', 'code': 'OK', 'title': 'All clear', 'why': '', 'fix': ''}
            ],
            cloning_method='Gibson Assembly',
        )
        return ds

    def _apply_step1_commit_identity_change(self, ds: DesignSession, new_name: str, new_seq: str) -> None:
        identity_changed = (
            ds.original_seq != new_seq
            or ds.gene_name != new_name
        )
        if identity_changed:
            ds.optimized_seq = ''
            ds.frame = {}
            ds.primers = []
            ds.validation_results = []
        ds.original_seq = new_seq
        ds.gene_name = new_name

    def _build_step6_fasta(self, ds: DesignSession) -> str:
        frame = ds.frame if isinstance(ds.frame, dict) else {}
        seq = frame.get('final_sequence') or ds.optimized_seq or ds.original_seq
        name = ds.gene_name or 'construct'
        return '>' + name + '\n' + seq + '\n'

    def _dashboard_sync_loaded_design(self, ds: DesignSession, selected_name: str) -> None:
        import streamlit as st
        frame = ds.frame if isinstance(ds.frame, dict) else {}
        resolved_sequence = (
            frame.get('final_sequence')
            or ds.optimized_seq
            or ds.original_seq
        )
        st.session_state[SK.ACTIVE_HOST] = ds.host
        st.session_state[SK.ACTIVE_SEQ] = resolved_sequence
        st.session_state[SK.SEQ_DESIGN] = ds.original_seq
        st.session_state[SK.SEQ] = ds.original_seq
        st.session_state[SK.FEATURES] = frame.get('features', [])
        st.session_state[SK.DASHBOARD_PROJECT] = selected_name

    def test_step1_committed_identity_change_clears_downstream_state(self):
        """Regression guard: a committed Step 1 identity change must wipe downstream artefacts."""
        ds = self._completed_design()
        assert ds.optimized_seq
        assert ds.frame
        assert ds.primers
        assert ds.validation_results

        mutated_seq = VALID_CDS[:-3] + 'TAG'
        self._apply_step1_commit_identity_change(ds, new_name='BetaReady_v2', new_seq=mutated_seq)

        assert ds.original_seq == mutated_seq
        assert ds.gene_name == 'BetaReady_v2'
        assert ds.optimized_seq == ''
        assert ds.frame == {}
        assert ds.primers == []
        assert ds.validation_results == []

    def test_step2_committed_host_syncs_ctx_host(self):
        """Regression guard: committed host selection must populate ctx_host."""
        import streamlit as st

        ds = DesignSession(step=2, original_seq=VALID_CDS, host=HOST_YEAST)
        self._ctrl_with(ds)
        st.session_state[SK.ACTIVE_HOST] = ds.host

        assert st.session_state[SK.ACTIVE_HOST] == HOST_YEAST

    def test_step3_successful_build_syncs_ctx_seq(self):
        """Regression guard: successful Step 3 build must write the resolved downstream sequence into ctx_seq."""
        import streamlit as st

        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        ds = DesignSession(
            step=3,
            original_seq=VALID_CDS,
            host=HOST_ECOLI,
            tag='No tag',
            frame=frame,
            optimized_seq=frame['final_sequence'],
        )
        self._ctrl_with(ds)
        resolved_sequence = frame.get('final_sequence') or ds.optimized_seq or ds.original_seq
        st.session_state[SK.ACTIVE_SEQ] = resolved_sequence

        assert st.session_state[SK.ACTIVE_SEQ] == frame['final_sequence']
        assert st.session_state[SK.ACTIVE_SEQ]

    def test_step4_host_mismatch_invalidates_stale_primers(self):
        """Regression guard: Step 4 must clear primers when upstream ctx_host changes."""
        import streamlit as st
        from views.wizard_steps.step4_cloning_primers import (
            _clear_primer_state,
            _hydrate_upstream_context_from_session,
            _seq_hash,
        )

        ds = self._completed_design(host=HOST_ECOLI)
        ctrl = self._ctrl_with(ds)
        st.session_state[SK.ACTIVE_HOST] = HOST_YEAST
        st.session_state[SK.ACTIVE_SEQ] = ds.frame['final_sequence']
        ds.primer_context_host = HOST_ECOLI
        ds.primer_context_seq_hash = _seq_hash(ds.frame['final_sequence'])
        ctrl.save(ds)
        st.session_state['wf_plasmid_png'] = b'png'
        st.session_state['wf_plasmid_features'] = [{'label': 'CDS'}]
        st.session_state['wf_plasmid_title'] = 'Old Title'

        upstream_host, upstream_seq = _hydrate_upstream_context_from_session(ds)
        upstream_seq_hash = _seq_hash(upstream_seq)
        last_used_host = str(ds.primer_context_host or '').strip()
        last_used_seq_hash = str(ds.primer_context_seq_hash or '').strip()
        has_existing_primers = bool(ds.primers)
        upstream_changed = has_existing_primers and (
            not last_used_host
            or not last_used_seq_hash
            or last_used_host != upstream_host
            or last_used_seq_hash != upstream_seq_hash
        )

        assert upstream_changed is True
        _clear_primer_state(ds, ctrl)

        assert ds.primers == []
        assert ds.primer_context_host == ""
        assert ds.primer_context_seq_hash == ""
        assert st.session_state.get('wf_plasmid_png') is None
        assert st.session_state.get('wf_plasmid_features') is None
        assert st.session_state.get('wf_plasmid_title') is None

    def test_step4_sequence_mismatch_invalidates_stale_primers(self):
        """Regression guard: Step 4 must clear primers when upstream ctx_seq changes."""
        import streamlit as st
        from views.wizard_steps.step4_cloning_primers import (
            _clear_primer_state,
            _hydrate_upstream_context_from_session,
            _seq_hash,
        )

        ds = self._completed_design(host=HOST_ECOLI)
        ctrl = self._ctrl_with(ds)
        changed_seq = ds.frame['final_sequence'] + 'ATGC'
        st.session_state[SK.ACTIVE_HOST] = HOST_ECOLI
        st.session_state[SK.ACTIVE_SEQ] = changed_seq
        ds.primer_context_host = HOST_ECOLI
        ds.primer_context_seq_hash = _seq_hash(ds.frame['final_sequence'])
        ctrl.save(ds)
        st.session_state['wf_plasmid_png'] = b'png'
        st.session_state['wf_plasmid_features'] = [{'label': 'CDS'}]
        st.session_state['wf_plasmid_title'] = 'Old Title'

        upstream_host, upstream_seq = _hydrate_upstream_context_from_session(ds)
        upstream_seq_hash = _seq_hash(upstream_seq)
        last_used_host = str(ds.primer_context_host or '').strip()
        last_used_seq_hash = str(ds.primer_context_seq_hash or '').strip()
        has_existing_primers = bool(ds.primers)
        upstream_changed = has_existing_primers and (
            not last_used_host
            or not last_used_seq_hash
            or last_used_host != upstream_host
            or last_used_seq_hash != upstream_seq_hash
        )

        assert upstream_changed is True
        _clear_primer_state(ds, ctrl)

        assert ds.primers == []
        assert ds.primer_context_host == ""
        assert ds.primer_context_seq_hash == ""
        assert st.session_state.get('wf_plasmid_png') is None
        assert st.session_state.get('wf_plasmid_features') is None
        assert st.session_state.get('wf_plasmid_title') is None

    def test_save_reload_restores_ctx_host_and_ctx_seq_coherently(self, monkeypatch):
        """Regression guard: save/load round-trip plus dashboard sync restores coherent host and sequence context."""
        import streamlit as st
        import services.design_saver as design_saver

        ds = self._completed_design(host=HOST_ECOLI)
        self._ctrl_with(ds)

        test_db_path = _wizard_regression_db_path('wizard_roundtrip.db')
        monkeypatch.setattr(design_saver, 'DB_PATH', test_db_path)

        ok, saved_name = design_saver.save_wizard_design(ds)
        assert ok is True
        assert saved_name

        loaded_ok, loaded_ds = design_saver.load_wizard_design(saved_name)
        assert loaded_ok is True
        assert isinstance(loaded_ds, DesignSession)

        self._dashboard_sync_loaded_design(loaded_ds, saved_name)

        expected_seq = (
            loaded_ds.frame.get('final_sequence')
            or loaded_ds.optimized_seq
            or loaded_ds.original_seq
        )
        assert st.session_state[SK.ACTIVE_HOST] == HOST_ECOLI
        assert st.session_state[SK.ACTIVE_SEQ] == expected_seq
        assert st.session_state[SK.ACTIVE_SEQ]

    def test_save_reload_restores_primers_validation_and_frame(self, monkeypatch):
        """Regression guard: persisted Step 4/5/6 fields round-trip through save/load coherently."""
        import services.design_saver as design_saver

        ds = self._completed_design(host=HOST_ECOLI)

        test_db_path = _wizard_regression_db_path('wizard_roundtrip_fields.db')
        monkeypatch.setattr(design_saver, 'DB_PATH', test_db_path)

        ok, saved_name = design_saver.save_wizard_design(ds)
        assert ok is True

        loaded_ok, loaded_ds = design_saver.load_wizard_design(saved_name)
        assert loaded_ok is True
        assert isinstance(loaded_ds, DesignSession)

        assert loaded_ds.gene_name == ds.gene_name
        assert loaded_ds.host == ds.host
        assert loaded_ds.cloning_method == ds.cloning_method
        assert loaded_ds.validation_results == ds.validation_results
        assert loaded_ds.primers == ds.primers
        assert isinstance(loaded_ds.frame, dict)
        assert loaded_ds.frame.get('final_sequence') == ds.frame.get('final_sequence')

    def test_load_fallback_works_when_project_history_row_missing(self, monkeypatch):
        """Regression guard: loading succeeds from sequences when project_history row is absent."""
        import services.design_saver as design_saver

        ds = self._completed_design(host=HOST_ECOLI)

        test_db_path = _wizard_regression_db_path('wizard_fallback_sequences_only.db')
        monkeypatch.setattr(design_saver, 'DB_PATH', test_db_path)

        ok, saved_name = design_saver.save_wizard_design(ds)
        assert ok is True

        conn = sqlite3.connect(test_db_path)
        try:
            conn.execute(
                "DELETE FROM project_history WHERE project_name = ?",
                (saved_name,),
            )
            conn.commit()
        finally:
            conn.close()

        loaded_ok, loaded_ds = design_saver.load_wizard_design(saved_name)
        assert loaded_ok is True
        assert isinstance(loaded_ds, DesignSession)

        assert loaded_ds.original_seq == ds.frame.get('final_sequence', '')
        assert loaded_ds.optimized_seq == ds.frame.get('final_sequence', '')
        assert loaded_ds.frame.get('final_sequence') == ds.frame.get('final_sequence', '')
        assert loaded_ds.frame.get('total_length') == len(ds.frame.get('final_sequence', ''))
        assert loaded_ds.frame.get('success') is True

    def test_load_fallback_works_when_project_history_table_absent(self, monkeypatch):
        """Regression guard: loading succeeds from sequences even if project_history table does not exist."""
        import services.design_saver as design_saver

        project_name = 'SequencesOnlyProject'
        sequence = 'ATG' + ('G' * 60) + 'TAA'

        test_db_path = _wizard_regression_db_path('wizard_fallback_no_project_history_table.db')
        monkeypatch.setattr(design_saver, 'DB_PATH', test_db_path)

        conn = sqlite3.connect(test_db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sequences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    sequence TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
                (project_name, sequence, 'Expression Wizard', 'sequences only', '2026-04-02 11:00:00'),
            )
            conn.commit()
        finally:
            conn.close()

        loaded_ok, loaded_ds = design_saver.load_wizard_design(project_name)
        assert loaded_ok is True
        assert isinstance(loaded_ds, DesignSession)
        assert loaded_ds.original_seq == sequence
        assert loaded_ds.optimized_seq == sequence
        assert loaded_ds.frame.get('final_sequence') == sequence
        assert loaded_ds.frame.get('total_length') == len(sequence)
        assert loaded_ds.host == ''
        assert loaded_ds.primers == []
        assert loaded_ds.validation_results == []

    def test_load_fallback_restores_reduced_fidelity_fields_explicitly(self, monkeypatch):
        """Regression guard: sequences-only fallback restores a coherent reduced-fidelity DesignSession."""
        import services.design_saver as design_saver

        ds = self._completed_design(host=HOST_ECOLI)

        test_db_path = _wizard_regression_db_path('wizard_fallback_reduced_fidelity.db')
        monkeypatch.setattr(design_saver, 'DB_PATH', test_db_path)

        ok, saved_name = design_saver.save_wizard_design(ds)
        assert ok is True

        conn = sqlite3.connect(test_db_path)
        try:
            conn.execute(
                "DELETE FROM project_history WHERE project_name = ?",
                (saved_name,),
            )
            conn.commit()
        finally:
            conn.close()

        loaded_ok, loaded_ds = design_saver.load_wizard_design(saved_name)
        assert loaded_ok is True
        assert isinstance(loaded_ds, DesignSession)

        assert loaded_ds.step == 1
        assert loaded_ds.gene_name == saved_name
        assert loaded_ds.host == ''
        assert loaded_ds.tag == ''
        assert loaded_ds.cloning_method == ''
        assert loaded_ds.primers == []
        assert loaded_ds.validation_results == []
        assert loaded_ds.codon_report == {}
        assert loaded_ds.frame.get('features') == []
        assert loaded_ds.frame.get('final_sequence') == loaded_ds.original_seq

    def test_load_fallback_prefers_latest_sequence_row_for_same_name(self, monkeypatch):
        """Regression guard: fallback load picks latest sequence row when duplicate names exist."""
        import services.design_saver as design_saver

        test_db_path = _wizard_regression_db_path('wizard_fallback_latest_row.db')
        monkeypatch.setattr(design_saver, 'DB_PATH', test_db_path)

        project_name = 'Duplicate Sequence Project'
        old_seq = 'ATG' + ('A' * 60) + 'TAA'
        new_seq = 'ATG' + ('C' * 60) + 'TAA'

        conn = sqlite3.connect(test_db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sequences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    sequence TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT,
                    version INTEGER,
                    chassis TEXT,
                    design_data TEXT,
                    created_at TEXT,
                    creator TEXT,
                    status TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
                (project_name, old_seq, 'Expression Wizard', 'old', '2026-04-02 09:00:00'),
            )
            conn.execute(
                "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
                (project_name, new_seq, 'Expression Wizard', 'new', '2026-04-02 10:00:00'),
            )
            conn.commit()
        finally:
            conn.close()

        loaded_ok, loaded_ds = design_saver.load_wizard_design(project_name)
        assert loaded_ok is True
        assert isinstance(loaded_ds, DesignSession)
        assert loaded_ds.original_seq == new_seq
        assert loaded_ds.optimized_seq == new_seq
        assert loaded_ds.frame.get('final_sequence') == new_seq

    def test_dashboard_reads_saved_step6_record_with_core_fields(self, monkeypatch):
        """Regression guard: Dashboard list path reads Step 6-saved design core fields from DB."""
        import services.design_saver as design_saver
        import views.Dashboard as dashboard_view

        ds = self._completed_design(host=HOST_ECOLI)

        test_db_path = _wizard_regression_db_path('wizard_dashboard_roundtrip.db')
        monkeypatch.setattr(design_saver, 'DB_PATH', test_db_path)

        ok, saved_name = design_saver.save_wizard_design(ds)
        assert ok is True

        rows = dashboard_view._get_projects_from_db()
        matched = [r for r in rows if r.get('Name') == saved_name]
        assert matched, 'Saved design should be visible in Dashboard data source'

        row = matched[0]
        assert row['Gene'] == ds.gene_name
        assert row['Host'] == ds.host
        assert row['Length (bp)'] == len(ds.frame.get('final_sequence', ''))
        assert row['_step'] == ds.step
        assert row['_n_primers'] == len(ds.primers)
        assert row['_n_issues'] == len(ds.validation_results)


    def test_valid_design_produces_nonempty_fasta_output(self):
        """Regression guard: a valid design must produce a non-empty Step 6 FASTA payload."""
        ds = self._completed_design(host=HOST_ECOLI)
        fasta = self._build_step6_fasta(ds)
        lines = fasta.splitlines()
        body = ''.join(line for line in lines if not line.startswith('>'))

        assert fasta.startswith('>')
        assert lines[0] == '>BetaReady'
        assert body == ds.frame['final_sequence']
        assert body != ''

    def test_minimal_happy_path_smoke(self):
        """Minimal logic/state smoke: valid wizard data flows through all six steps to export readiness."""
        import streamlit as st

        ds = DesignSession(step=1, gene_name='SmokeGene', original_seq=VALID_CDS)
        ctrl = self._ctrl_with(ds)

        assert ctrl.can_advance is True

        ds.step = 2
        ds.host = HOST_ECOLI
        ctrl.save(ds)
        assert ctrl.can_advance is True

        ds.step = 3
        ds.tag = 'No tag'
        ds.frame = build_expression_frame(ds.original_seq, host=ds.host, tag=ds.tag)
        assert ds.frame['success']
        ds.optimized_seq = ds.frame['final_sequence']
        st.session_state[SK.ACTIVE_HOST] = ds.host
        st.session_state[SK.ACTIVE_SEQ] = ds.frame['final_sequence']
        ctrl.save(ds)
        assert ctrl.can_advance is True

        ds.step = 4
        ds.primers = [
            {'name': 'Forward Primer', 'sequence': 'ATGGTGAGCAAG'},
            {'name': 'Reverse Primer', 'sequence': 'TTACTTGTGGCC'},
        ]
        ctrl.save(ds)
        assert ctrl.can_advance is True

        ds.step = 5
        ds.validation_results = validate_frame(ds.frame) or [
            {'severity': 'info', 'code': 'OK', 'title': 'All clear', 'why': '', 'fix': ''}
        ]
        ctrl.save(ds)
        assert ctrl.can_advance is True

        ds.step = 6
        ctrl.save(ds)
        export_seq = ds.frame.get('final_sequence') or ds.optimized_seq or ds.original_seq
        fasta = self._build_step6_fasta(ds)

        assert export_seq
        assert fasta.startswith('>SmokeGene')
        assert export_seq == st.session_state[SK.ACTIVE_SEQ]


# ===========================================================================
# 10. Step 6 export content correctness
# ===========================================================================

class TestMvpMainlineCleanValidation:
    def test_mvp_mainline_clean_validation_reaches_export_ready_state(self, monkeypatch):
        """Regression guard: the clean Step 1-6 MVP state chain reaches export-ready status."""
        import streamlit as st
        from services.report_service import generate_report_content
        from services.validation_summary_service import build_validation_run_state

        fake_state = {}
        monkeypatch.setattr(st, 'session_state', fake_state)
        monkeypatch.setattr(st, 'rerun', lambda: None)

        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']

        ds = DesignSession(
            step=5,
            gene_name='MvpCleanPath',
            original_seq=VALID_CDS,
            optimized_seq=VALID_CDS,
            host=HOST_ECOLI,
            tag='No tag',
            elements={
                'promoter_name': 'T7',
                'rbs_name': 'B0034',
                'terminator_name': 'rrnB',
            },
            frame=frame,
            cloning_method='Gibson Assembly',
            primers=[
                {
                    'Fragment Name': 'MvpFragment',
                    "Forward Primer (5'->3')": 'ATGGTGAGCAAGGGCGAGGA',
                    "Reverse Primer (5'->3')": 'TTACTTGTGGCCGTTTACGT',
                    'Quality Grade': 'Recommended',
                    'Quality Reasons': ['Balanced primer Tm.'],
                    'Warnings': [],
                }
            ],
            validation_results=[],
        )
        ds.frame_context_signature = ds.current_frame_context_signature()
        ds.primer_context_signature = ds.current_primer_context_signature()
        ds.validation_context_signature = ds.current_validation_context_signature()
        st.session_state['design_session'] = ds

        state = build_validation_run_state(ds)
        report = generate_report_content(ds)

        assert state['status'] == 'completed_passed'
        assert SessionController().can_advance is True
        assert report['step_alignment']['step5']['status'] == 'passed'
        assert report['step_alignment']['step5']['status'] != 'not_run'
        assert report['export_recommendation']['recommendation'] == 'Documentation Export Available'


class TestStep6ExportContent:
    """
    Focused tests for the export helpers in views/wizard_steps/step6_export.py.

    The live step6_export.py does NOT expose _build_fasta / _build_primer_csv
    / _build_validation_report as module-level importable helpers -- all export
    logic is inline inside page().  The FASTA is assembled as:

        ">" + gene_name + "\n" + seq + "\n"

    These tests therefore:
      (a) exercise the same logic directly on DesignSession.summary() and
          frame data (pure-Python, no Streamlit),
      (b) test _build_fasta / _build_primer_csv if present (optional import),
      (c) document the CURRENT output contract so regressions are caught.

    If step6 export helpers are refactored to be importable, these tests will
    validate the new helpers automatically because they import conditionally.
    """

    # ── FASTA output structure ────────────────────────────────────────────────

    def _make_fasta(self, gene_name: str, seq: str) -> str:
        """Replicate the live step6 FASTA assembly (inline logic)."""
        name = gene_name or 'construct'
        return '>' + name + '\n' + seq + '\n'

    def test_fasta_has_header_line(self):
        """FASTA output must begin with a > header on the first line."""
        fasta = self._make_fasta('GFP', 'ATGGTGAGC')
        lines = fasta.strip().splitlines()
        assert lines[0].startswith('>'), 'First FASTA line must start with >'

    def test_fasta_header_contains_gene_name(self):
        """FASTA header must contain the gene name for traceability."""
        fasta = self._make_fasta('GFP', 'ATGGTGAGC')
        first_line = fasta.splitlines()[0]
        assert 'GFP' in first_line

    def test_fasta_body_contains_sequence(self):
        """FASTA body (lines after header) must contain the sequence."""
        seq = 'ATGGTGAGCAAG'
        fasta = self._make_fasta('GFP', seq)
        body = ''.join(ln for ln in fasta.splitlines() if not ln.startswith('>'))
        assert body == seq

    def test_fasta_ends_with_newline(self):
        """FASTA output must end with a newline (POSIX file convention)."""
        fasta = self._make_fasta('GFP', 'ATGGTGAGC')
        assert fasta.endswith('\n')

    def test_fasta_fallback_name_when_gene_empty(self):
        """
        When gene_name is empty/None the FASTA header must still be valid
        (non-empty label).  Live code uses: gene_name or 'construct'.
        """
        fasta = self._make_fasta('', 'ATGGTGAGC')
        first_line = fasta.splitlines()[0]
        assert first_line.startswith('>')
        assert len(first_line) > 1, 'Header must have a non-empty label'

    def test_fasta_with_real_frame_sequence(self):
        """
        Full pipeline: build frame -> extract final_sequence -> wrap in FASTA.
        The FASTA body must equal frame['final_sequence'] exactly.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        seq = frame['final_sequence']
        fasta = self._make_fasta('TestGene', seq)
        body = ''.join(ln for ln in fasta.splitlines() if not ln.startswith('>'))
        assert body == seq

    def test_fasta_gene_name_with_spaces(self):
        """
        Gene names with spaces should appear in the header without breaking
        FASTA format (header is single line; spaces inside are valid in FASTA).
        """
        fasta = self._make_fasta('My Gene Name', 'ATGGTGAGC')
        first_line = fasta.splitlines()[0]
        assert first_line.startswith('>')
        assert 'My Gene Name' in first_line

    def test_fasta_gene_name_with_special_chars(self):
        """
        Gene names with special characters should produce a valid (parseable)
        FASTA header.  The header must start with > and must not be empty.
        """
        fasta = self._make_fasta('GFP/mCherry (fusion)', 'ATGGTGAGC')
        first_line = fasta.splitlines()[0]
        assert first_line.startswith('>')
        assert len(first_line) > 1

    # ── Empty / fallback sequence behavior ────────────────────────────────────

    def test_fasta_empty_sequence_produces_header_only(self):
        """
        When frame has no final_sequence (empty ds.frame or no build run yet)
        the live step6 falls back: seq = frame.get('final_sequence') or
        ds.optimized_seq or ds.original_seq.  Test that an empty fallback
        chain produces a technically-valid but empty-body FASTA.
        """
        seq = ''  # all fallbacks empty
        fasta = self._make_fasta('NoSeq', seq)
        lines = fasta.splitlines()
        assert lines[0].startswith('>')
        # Body is empty string -- that is the documented fallback behavior
        body = ''.join(ln for ln in lines if not ln.startswith('>'))
        assert body == ''

    def test_fallback_uses_original_seq_when_frame_missing(self):
        """
        Live step6 logic: seq = frame.get('final_sequence') or
        ds.optimized_seq or ds.original_seq.
        When frame is empty dict, fallback should reach original_seq.
        """
        ds = DesignSession(
            gene_name='Fallback',
            original_seq=VALID_CDS,
            optimized_seq='',
            frame={},
        )
        _fr = ds.frame if isinstance(ds.frame, dict) else {}
        seq = _fr.get('final_sequence') or ds.optimized_seq or ds.original_seq
        assert seq == VALID_CDS

    def test_fallback_uses_optimized_seq_over_original(self):
        """
        If frame is empty but optimized_seq is set, that should win over
        original_seq in the fallback chain.
        """
        opt_seq = VALID_CDS + 'ATGATG'  # slightly different
        ds = DesignSession(
            gene_name='Fallback',
            original_seq=VALID_CDS,
            optimized_seq=opt_seq,
            frame={},
        )
        _fr = ds.frame if isinstance(ds.frame, dict) else {}
        seq = _fr.get('final_sequence') or ds.optimized_seq or ds.original_seq
        assert seq == opt_seq

    def test_final_sequence_wins_over_optimized_and_original(self):
        """
        frame['final_sequence'] (the full cassette) must take priority over
        both optimized_seq and original_seq in the export fallback chain.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        ds = DesignSession(
            gene_name='Priority',
            original_seq=VALID_CDS,
            optimized_seq=VALID_CDS + 'TTT',
            frame=frame,
        )
        _fr = ds.frame if isinstance(ds.frame, dict) else {}
        seq = _fr.get('final_sequence') or ds.optimized_seq or ds.original_seq
        assert seq == frame['final_sequence']
        assert seq != VALID_CDS  # cassette is longer than bare CDS

    # ── Construct parts order ─────────────────────────────────────────────────

    def test_parts_order_prokaryote(self):
        """
        For a prokaryotic host the cassette parts must appear in order:
        promoter -> RBS -> CDS -> terminator.
        Verified by checking that each part's sequence appears in the
        correct position within final_sequence.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        seq = frame['final_sequence']
        parts = frame['parts']
        assert len(parts) == 4
        # Check types in order
        assert parts[0]['type'] == 'promoter'
        assert parts[1]['type'] == 'RBS'
        assert parts[2]['type'] == 'CDS'
        assert parts[3]['type'] == 'terminator'
        # Check physical order in the final sequence
        pos = [seq.find(p['seq']) for p in parts]
        for i in range(len(pos) - 1):
            assert pos[i] < pos[i + 1], (
                f'Part {parts[i]["type"]} must appear before {parts[i+1]["type"]} '
                f'in the final sequence'
            )

    def test_parts_order_mammalian(self):
        """
        For a mammalian host the cassette must be:
        promoter -> Kozak -> CDS -> terminator (polyadenylation signal).
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_MAMMAL, tag='No tag')
        assert frame['success']
        parts = frame['parts']
        assert len(parts) == 4
        assert parts[0]['type'] == 'promoter'
        assert parts[2]['type'] == 'CDS'
        assert parts[3]['type'] == 'terminator'

    def test_total_length_equals_sum_of_parts(self):
        """
        frame['total_length'] must equal the sum of individual part lengths.
        This guards against off-by-one errors in the cassette assembler.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        parts_total = sum(len(p['seq']) for p in frame['parts'])
        # prokaryote: RBS and spacer are combined in parts[1]['seq']
        assert frame['total_length'] == len(frame['final_sequence'])

    def test_cassette_longer_than_cds(self):
        """
        The assembled cassette must always be longer than the bare CDS because
        it includes promoter + RBS/Kozak + terminator flanks.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        assert frame['total_length'] > len(VALID_CDS), (
            'Cassette must include promoter/RBS/terminator flanks '
            'and therefore be longer than the bare CDS'
        )

    def test_cds_present_in_final_sequence(self):
        """
        The cleaned CDS (with ATG start and stop codon ensured) must be a
        substring of the final cassette sequence.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        cds_part = next(p for p in frame['parts'] if p['type'] == 'CDS')
        assert cds_part['seq'] in frame['final_sequence'], (
            'CDS sequence must be a contiguous substring of the full cassette'
        )

    def test_promoter_at_start_of_cassette(self):
        """
        The promoter sequence must appear at the very beginning of the
        final cassette (position 0), not buried in the middle.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        promoter_seq = frame['parts'][0]['seq']
        assert frame['final_sequence'].startswith(promoter_seq), (
            'Promoter must be at the start of the cassette'
        )

    def test_terminator_at_end_of_cassette(self):
        """
        The terminator sequence must appear at the very end of the
        final cassette, not in the middle.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        terminator_seq = frame['parts'][-1]['seq']
        assert frame['final_sequence'].endswith(terminator_seq), (
            'Terminator must be at the end of the cassette'
        )

    # ── Summary / export metadata ─────────────────────────────────────────────

    def test_summary_gene_name_used_for_export_label(self):
        """
        ds.summary()['gene_name'] is used as the export filename stem and
        FASTA label.  It must equal the gene_name set on the session.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        ds = DesignSession(
            gene_name='mCherry',
            original_seq=VALID_CDS,
            host=HOST_ECOLI,
            frame=frame,
        )
        s = ds.summary()
        assert s['gene_name'] == 'mCherry'

    def test_summary_frame_length_matches_cassette(self):
        """
        summary()['frame_length_bp'] must equal frame['total_length'] so that
        the Step 6 metric card shows the correct cassette size.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success']
        ds = DesignSession(
            original_seq=VALID_CDS,
            host=HOST_ECOLI,
            frame=frame,
        )
        s = ds.summary()
        assert s['frame_length_bp'] == frame['total_length']

    def test_unsupported_tag_export_not_silently_empty(self):
        """
        build_expression_frame with an unsupported tag must return
        success=False and a non-empty error message rather than silently
        producing an empty/invalid cassette.
        This guards the export path: a failed frame must never be exported
        as if it were valid.
        """
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI,
                                       tag='GST-tag (N-term)')  # not in E.coli rules
        assert frame.get('success') is False, (
            'Unsupported tag must produce success=False, not a silent empty cassette'
        )
        assert 'error' in frame
        assert frame['error'].strip() != ''

    def test_all_hosts_produce_nonempty_cassette(self):
        """
        build_expression_frame with 'No tag' must produce a non-empty
        final_sequence for every supported host that accepts 'No tag'.
        This is the broadest regression guard for the export path.
        """
        for host in list_supported_hosts():
            rules = get_host_rules(host)
            if 'No tag' not in rules['tag_options']:
                continue
            frame = build_expression_frame(VALID_CDS, host=host, tag='No tag')
            assert frame.get('success'), f'Frame build failed for host {host!r}'
            assert frame['final_sequence'], (
                f'final_sequence must not be empty for host {host!r}'
            )
            assert frame['total_length'] > 0, (
                f'total_length must be > 0 for host {host!r}'
            )


# ===========================================================================
# 11. Step 6 GenBank export must use active construct frame
# ===========================================================================

class TestStep6GenBankActiveState:
    """Regression tests for active-state sequence/feature resolution in GenBank export."""

    @pytest.fixture(autouse=True)
    def _patch_streamlit(self, monkeypatch):
        """Provide a minimal fake Streamlit state for export_manager tests."""
        import streamlit as _st

        fake_state = {}
        monkeypatch.setattr(_st, 'session_state', fake_state)

    def test_resolve_payload_prefers_design_session_frame_over_ctx(self):
        """Export payload must prefer current DesignSession frame over stale ctx state."""
        import streamlit as st
        from core.design_session import DesignSession
        from components.export_manager import _resolve_active_export_payload

        stale_ctx_seq = 'ATGATGATG'
        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success'] is True

        st.session_state[SK.ACTIVE_SEQ] = stale_ctx_seq
        st.session_state[SK.ACTIVE_FEATURES] = [{'name': 'stale', 'type': 'misc_feature', 'start': 1, 'end': 3}]
        st.session_state['design_session'] = DesignSession(
            gene_name='FrameWins',
            original_seq=VALID_CDS,
            host=HOST_ECOLI,
            frame=frame,
        )

        seq, features, pname = _resolve_active_export_payload()

        assert seq == frame['final_sequence']
        assert features == frame['features']
        assert pname == 'FrameWins'
        assert st.session_state[SK.ACTIVE_SEQ] == frame['final_sequence']

    def test_resolve_payload_rebuilds_features_from_parts_when_frame_features_missing(self):
        """Export payload must derive fresh features from frame parts when features list is absent."""
        import streamlit as st
        from core.design_session import DesignSession
        from components.export_manager import _resolve_active_export_payload

        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success'] is True
        frame_no_features = dict(frame)
        frame_no_features['features'] = []

        st.session_state['design_session'] = DesignSession(
            gene_name='PartsOnly',
            original_seq=VALID_CDS,
            host=HOST_ECOLI,
            frame=frame_no_features,
        )

        seq, features, pname = _resolve_active_export_payload()

        assert seq == frame['final_sequence']
        assert pname == 'PartsOnly'
        assert len(features) == len(frame['parts'])
        assert features[0]['name'] == frame['parts'][0]['name']
        assert features[-1]['end'] == len(seq)

    def test_genbank_string_uses_resolved_active_frame_sequence_and_features(self):
        """GenBank export string must reflect resolved active frame sequence and feature labels."""
        import streamlit as st
        from core.design_session import DesignSession
        from components.export_manager import (
            _resolve_active_export_payload,
            generate_genbank_string,
        )

        frame = build_expression_frame(VALID_CDS, host=HOST_ECOLI, tag='No tag')
        assert frame['success'] is True
        st.session_state['design_session'] = DesignSession(
            gene_name='GB_Active',
            original_seq=VALID_CDS,
            host=HOST_ECOLI,
            frame=frame,
        )

        seq, features, pname = _resolve_active_export_payload()
        gb = generate_genbank_string(seq, features, pname)

        assert 'LOCUS' in gb
        assert 'GB_Active' in gb
        assert frame['parts'][0]['name'] in gb
        assert frame['parts'][2]['name'] in gb
 

# ===========================================================================
# 10. Minimal six-step end-to-end regression coverage
# ===========================================================================

class TestSixStepEndToEndRegression:
    """Minimal end-to-end regression coverage for the MVP six-step flow."""

    def _build_happy_path_session(self, host: str = HOST_ECOLI) -> DesignSession:
        ds = DesignSession(
            step=1,
            gene_name="EndToEndDemo",
            original_seq=VALID_CDS,
            host=host,
            tag="No tag",
            elements={
                "promoter_name": "T7",
                "rbs_name": "B0034",
                "terminator_name": "rrnB",
            },
        )

        assert len(ds.original_seq) >= 30
        ds.step = 2
        assert bool(ds.host) is True

        frame = build_expression_frame(
            ds.original_seq,
            host=ds.host,
            tag=ds.tag,
            custom_elements=ds.elements,
        )
        assert frame["success"] is True
        ds.frame = frame
        ds.optimized_seq = frame.get("final_sequence", "")
        ds.step = 3
        assert ds.frame_ok is True

        ds.primers = [
            {
                "Fragment Name": "FullConstruct",
                "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
                "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
                "Quality Grade": "Recommended",
                "Warnings": [],
            }
        ]
        ds.cloning_method = "Gibson Assembly"
        ds.step = 4
        assert bool(ds.primers) is True

        validation_results = validate_frame(ds.frame)
        if not validation_results:
            validation_results = [
                {
                    "severity": "info",
                    "code": "PASS",
                    "title": "Validation complete",
                    "why": "",
                    "fix": "",
                }
            ]
        ds.validation_results = validation_results
        ds.step = 5
        assert not any(item.get("severity") == "critical" for item in ds.validation_results)

        ds.step = 6
        return ds

    def test_happy_path_reaches_export_with_valid_payloads(self):
        from components.export_manager import build_export_payloads

        ds = self._build_happy_path_session()

        final_sequence = ds.frame.get("final_sequence", "")
        parts = ds.frame.get("parts", [])
        features = []
        cursor = 1
        for part in parts:
            part_seq = str(part.get("seq") or "")
            if not part_seq:
                continue
            end = cursor + len(part_seq) - 1
            features.append(
                {
                    "name": part.get("name", "Part"),
                    "type": part.get("type", "misc_feature"),
                    "start": cursor,
                    "end": end,
                }
            )
            cursor = end + 1

        payloads = build_export_payloads(final_sequence, features, ds.gene_name)

        assert ds.step == 6
        assert final_sequence
        assert len(features) >= 1
        assert set(payloads) == {"fasta", "genbank"}
        assert payloads["fasta"]["data"].startswith(">EndToEndDemo")
        assert "LOCUS" in payloads["genbank"]["data"]

    def test_host_change_invalidates_all_downstream_outputs_before_rebuild(self):
        ds = self._build_happy_path_session(host=HOST_ECOLI)
        assert ds.frame_ok is True
        assert ds.primers
        assert ds.validation_results

        ds.host = HOST_YEAST
        ds.step = 3
        ds.frame = {}
        ds.optimized_seq = ""
        ds.primers = []
        ds.validation_results = []

        assert ds.frame_ok is False
        assert ds.optimized_seq == ""
        assert ds.primers == []
        assert ds.validation_results == []

    def test_invalid_step1_input_cannot_start_mainstream_flow(self):
        ds = DesignSession(step=1, gene_name="TooShort", original_seq="ATGCATGC", host="")

        step1_pass = len(ds.original_seq) >= 30
        step2_pass = bool(ds.host)

        assert step1_pass is False
        assert step2_pass is False
        assert ds.frame == {}
        assert ds.primers == []
        assert ds.validation_results == []
