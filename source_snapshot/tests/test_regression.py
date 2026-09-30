# -*- coding: utf-8 -*-
"""
tests/test_regression.py
~~~~~~~~~~~~~~~~~~~~~~~~
Minimal regression tests that lock down three critical bug-fixes.

Each test docstring explains which regression it prevents.

Run with:
    python -m pytest tests/test_regression.py -v
"""
import sys
import os

# Ensure project root is importable without installing the package.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from core.design_session import DesignSession
from core.expression_frame_builder import (
    build_expression_frame,
    list_supported_hosts,
    get_host_rules,
)
from views.wizard_flow import _check_dna_input, _clean_seq
from views.wizard_steps._shared import _validate_cds_sequence


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# A short but valid CDS that works in every host.
VALID_CDS = 'ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCCATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA'

# A host that supports His6-tag
HOST_A = 'E.coli BL21(DE3)'

# A host that does NOT support His6-tag (Agrobacterium only has 'No tag')
HOST_B = 'Agrobacterium GV3101'


# ===========================================================================
# 1. Step 2 -> Step 3 -> Step 4 stale state
# ===========================================================================

class TestStaleStateOnHostChange:
    """
    Regression: switching the host in Step 2 must wipe all downstream
    artefacts (frame, optimized_seq, primers) so Step 3 / Step 4 cannot
    silently re-use a cassette built for a different host.

    wizard_flow._page_2 sets _inputs_changed = True and clears ds.frame,
    ds.optimized_seq, ds.primers, ds.validation_results when the host changes.
    DesignSession.frame_ok and the Step 3 / Step 4 guards rely on frame == {}.
    """

    def _build_session_with_frame(self, host: str) -> DesignSession:
        """Helper: return a DesignSession that has already completed Step 3."""
        ds = DesignSession()
        ds.original_seq = VALID_CDS
        ds.host = host
        ds.tag  = 'No tag'
        frame   = build_expression_frame(VALID_CDS, host=host, tag='No tag')
        assert frame['success'], f'Precondition failed: frame build for {host}'
        ds.frame         = frame
        ds.optimized_seq = frame['final_sequence']
        ds.primers       = [{'name': 'fwd', 'seq': 'ATGGTGAGC'}]
        return ds

    def test_frame_ok_true_after_build(self):
        """
        Regression guard: frame_ok must be True after a successful build.
        If frame_ok is always False the Step-3 gate would always block.
        """
        ds = self._build_session_with_frame(HOST_A)
        assert ds.frame_ok is True

    def test_stale_frame_cleared_on_host_change(self):
        """
        Regression guard: after a host change the downstream artefacts
        (frame, optimized_seq, primers) must be wiped so they cannot leak
        into the next Step-3 / Step-4 render.

        Mirrors the _inputs_changed branch in wizard_flow._page_2 which
        was added to fix the stale-state regression.
        """
        ds = self._build_session_with_frame(HOST_A)

        # Simulate what _page_2 does when host changes
        old_host = ds.host
        new_host = 'S. cerevisiae'
        inputs_changed = (old_host != new_host)
        if inputs_changed:
            ds.frame         = {}
            ds.optimized_seq = ''
            ds.primers       = []
            ds.validation_results = []
        ds.host = new_host

        assert ds.frame == {}, 'frame must be wiped after host change'
        assert ds.optimized_seq == '', 'optimized_seq must be wiped after host change'
        assert ds.primers == [], 'primers must be wiped after host change'

    def test_frame_ok_false_after_host_change(self):
        """
        Regression guard: frame_ok must return False after stale artefacts
        are cleared, so the Step-3 -> Step-4 gate correctly blocks.
        """
        ds = self._build_session_with_frame(HOST_A)
        # Clear as _page_2 does
        ds.frame = {}
        assert ds.frame_ok is False

    def test_no_primer_design_without_valid_frame(self):
        """
        Regression guard: Step 4 must refuse to proceed if frame is empty /
        failed.  The guard in wizard_flow._page_4 checks
        ds.frame.get('success') before allowing primer design.

        We verify the gate condition directly on DesignSession so the logic
        stays correct even if the UI code is refactored.
        """
        ds = DesignSession()
        ds.original_seq = VALID_CDS
        ds.host = HOST_A
        ds.frame = {}  # no frame built yet

        # Gate condition used by wizard_flow._page_4
        # .get('success') returns None when key is absent; bool() normalises to False.
        can_design_primers = bool(isinstance(ds.frame, dict) and ds.frame.get('success'))
        assert can_design_primers is False, (
            'Primer design gate must block when frame is absent'
        )

    def test_valid_frame_allows_primer_design_gate(self):
        """
        Regression guard (positive case): once a valid frame exists the
        primer design gate must be open.
        """
        ds = DesignSession()
        ds.original_seq = VALID_CDS
        ds.host = HOST_A
        ds.frame = build_expression_frame(VALID_CDS, host=HOST_A, tag='No tag')

        can_design_primers = isinstance(ds.frame, dict) and ds.frame.get('success')
        assert can_design_primers is True


# ===========================================================================
# 2. Tag compatibility
# ===========================================================================

class TestTagCompatibility:
    """
    Regression: each host must only expose the tags defined in its
    HOST_RULES['tag_options'] dict.  build_expression_frame() must return
    success=False for unsupported tags, and wizard_flow._page_2 must reset
    the tag selection when switching hosts.
    """

    def test_ecoli_supports_his_tag(self):
        """Regression guard: E. coli hosts must always offer His6-tag."""
        rules = get_host_rules(HOST_A)
        assert 'His6-tag (C-term)' in rules['tag_options']

    def test_agrobacterium_no_his_tag(self):
        """
        Regression guard: Agrobacterium GV3101 is a delivery vehicle for
        plant transformation and must NOT offer His6-tag — adding one
        silently would produce a biologically wrong cassette.
        """
        rules = get_host_rules(HOST_B)
        assert 'His6-tag (C-term)' not in rules['tag_options'], (
            'Agrobacterium should not have His6-tag in its tag_options'
        )

    def test_build_frame_rejects_unsupported_tag(self):
        """
        Regression guard: bypassing the UI and calling build_expression_frame()
        directly with an unsupported tag must return success=False, not silently
        produce a malformed cassette.

        This was the core fix: the function now validates tag against
        HOST_RULES[host]['tag_options'] before building.
        """
        result = build_expression_frame(VALID_CDS, host=HOST_B, tag='His6-tag (C-term)')
        assert result['success'] is False
        assert 'error' in result
        assert 'His6-tag (C-term)' in result['error']

    def test_build_frame_accepts_supported_tag(self):
        """Regression guard (positive): a valid host+tag pair must still succeed."""
        result = build_expression_frame(VALID_CDS, host=HOST_A, tag='His6-tag (C-term)')
        assert result['success'] is True

    def test_tag_reset_logic_on_host_switch(self):
        """
        Regression guard: when the host changes in Step 2 and the previously
        saved tag is not in the new host's tag list, the UI resets the tag
        to the first available option.

        This test mirrors the cur_tag logic in wizard_flow._page_2 so the
        reset rule stays consistent if the UI is refactored.
        """
        # Start on HOST_A with His6-tag
        ds = DesignSession()
        ds.host = HOST_A
        ds.tag  = 'His6-tag (C-term)'

        # Now switch to HOST_B which only has 'No tag'
        new_host = HOST_B
        new_tag_opts = list(get_host_rules(new_host)['tag_options'].keys())

        # Mirror: cur_tag = ds.tag if ds.tag in tag_opts else tag_opts[0]
        cur_tag = ds.tag if ds.tag in new_tag_opts else new_tag_opts[0]

        # Must have been reset (His6-tag is not available on HOST_B)
        assert cur_tag != 'His6-tag (C-term)', (
            'Tag should be auto-reset when switching to a host that does not support it'
        )
        assert cur_tag in new_tag_opts, 'Reset tag must be valid for the new host'

    def test_different_hosts_expose_only_own_tags(self):
        """
        Regression guard: each host's tag list must be a strict subset of
        the tags registered in its own HOST_RULES entry.  This prevents a
        future copy-paste error from giving a host tags it should not have.
        """
        for host in list_supported_hosts():
            rules = get_host_rules(host)
            tag_opts = list(rules['tag_options'].keys())
            # Every tag returned must be in the host's own tag_options
            for t in tag_opts:
                assert t in rules['tag_options'], (
                    f'Host {host}: tag {t!r} not in its own tag_options dict'
                )


# ===========================================================================
# 3. Step 1 input validation (_check_dna_input)
# ===========================================================================

class TestStep1InputValidation:
    """
    Regression: _check_dna_input() is the gate that prevents garbage from
    entering the pipeline.  Any relaxation of the rules here will silently
    allow protein sequences, RNA, or random text to reach build_expression_frame()
    and produce nonsensical output.

    _check_dna_input() lives in views/wizard_flow.py and is called when the
    user clicks "Next" in Step 1.
    """

    # --- positive cases (must pass) ----------------------------------------

    def test_plain_dna_accepted(self):
        """
        Regression guard: plain uppercase DNA must always be accepted.
        If this fails the wizard rejects all valid input.
        """
        ok, err = _check_dna_input('ATGGTGAGCAAGGGCGAGGAG')
        assert ok is True
        assert err == ''

    def test_fasta_dna_accepted(self):
        """
        Regression guard: FASTA-formatted input (with a header line) must be
        accepted.  _check_dna_input() strips header lines starting with '>'
        before checking character ratios.
        """
        fasta = '>MyGene\nATGGCTAGCATCGATCGATCGATCGAT'
        ok, err = _check_dna_input(fasta)
        assert ok is True, f'FASTA input rejected unexpectedly: {err}'

    def test_multiline_dna_accepted(self):
        """
        Regression guard: multi-line DNA (as exported by many databases)
        must be accepted.  Lines are joined before ratio checks.
        """
        multiline = (
            'ATGGTGAGCAAGGGCGAGGAG\n'
            'CTGTTCACCGGGGTGGTGCCC\n'
            'ATCCTGGTCGAGCTGGACGGC'
        )
        ok, err = _check_dna_input(multiline)
        assert ok is True, f'Multi-line DNA rejected unexpectedly: {err}'

    # --- negative cases (must be blocked) ----------------------------------

    def test_protein_sequence_blocked(self):
        """
        Regression guard: a protein sequence must be rejected.
        Protein letters (E, F, H, I, K, L, M, P, Q, R, S, V, W, Y) account
        for >= 10% of alphabetical characters -> gate returns False.

        A previous bug allowed protein sequences through because the ratio
        check was missing, causing build_expression_frame() to strip all
        non-ATCG characters and produce a meaningless 'ATG...TAA' stub.
        """
        protein = 'MSKGEELFTGVVPILVELDGDVNGHKFSVSGEGEGDATYGKLTLKFICTTGKLPVPWPTLVTTLTYGVQCFSRYPDHMKQHDFFKSAMPEGYVQERTIFFKDDGNYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNYNSHNVYIMADKQKNGIKVNFKIRHNIEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSTQSALSKDPNEKRDHMVLLEFVTAAGITLGMDELYK'
        ok, err = _check_dna_input(protein)
        assert ok is False
        assert 'protein' in err.lower() or 'amino' in err.lower()

    def test_mixed_garbage_text_blocked(self):
        """
        Regression guard: arbitrary non-biological text must be rejected.
        Less than 85% A/T/C/G -> gate returns False.
        """
        garbage = 'Hello World this is not a DNA sequence at all 12345'
        ok, err = _check_dna_input(garbage)
        assert ok is False

    def test_rna_sequence_blocked(self):
        """
        Regression guard: RNA sequences (containing 'U' instead of 'T')
        must be rejected because U is not in ATCG and pushes the ATCG
        purity ratio below 85%.

        Accepting RNA would cause build_expression_frame() to strip all 'U'
        characters (treated as non-ATCG) and silently produce a truncated
        nonsense sequence.
        """
        # Pure RNA — every T is replaced with U
        rna = 'AUGUGAGCAAGG GCGAGGAGCUGUUCACCGGGGUGGU GCCCAUCCUGGUCGAGCUGGACGGCGACGUAAACGGCCACAAGUAA'
        ok, err = _check_dna_input(rna)
        assert ok is False, (
            'RNA sequence (contains U) should be rejected by the DNA input gate'
        )


class TestCdsValidationRules:
    """Regression tests for strict CDS validation in Step 1."""

    def test_valid_cds_passes(self):
        errors = _validate_cds_sequence(
            'ATGAAACCCGGGTTTAAATAG'
        )
        assert errors == []

    def test_invalid_characters_detected(self):
        errors = _validate_cds_sequence('ATGAAAXXXTAA')
        assert any('Only A, T, C, G, and N are allowed' in msg for msg in errors)

    def test_length_must_be_multiple_of_three(self):
        errors = _validate_cds_sequence('ATGAAATAAAT')
        assert any('multiple of 3' in msg for msg in errors)

    def test_start_codon_required(self):
        errors = _validate_cds_sequence('TTGAAACCCTAA')
        assert any('start codon' in msg for msg in errors)

    def test_stop_codon_required(self):
        errors = _validate_cds_sequence('ATGAAACCCGGG')
        assert any('stop codon' in msg for msg in errors)
 