from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_gene_input_paste_cleaner_ignores_fasta_header_before_service_cleaning():
    """Pasted FASTA headers must be excluded before service-level cleaning."""
    from views.wizard_steps.step1_gene_input import _clean_pasted_gene_input

    cleaned, warnings = _clean_pasted_gene_input(
        '>SmokeC\nATGGCTGCTGCTGCTGCTGCTGCTGCTGCTTAA',
        use_service_cleaner=True,
    )

    assert cleaned == 'ATGGCTGCTGCTGCTGCTGCTGCTGCTGCTTAA'
    assert all('>' not in warning for warning in warnings)
    assert all('S' not in warning for warning in warnings)


def test_step1_paste_feedback_treats_n_as_retained_base_not_invalid():
    from views.wizard_steps.step1_gene_input import _build_sequence_feedback

    feedback = _build_sequence_feedback('>Gene\nATGGCTNNNTAA', 'ATGGCTNNNTAA')

    assert feedback['kept_bases'] == 12
    assert feedback['invalid_count'] == 0
    assert feedback['invalid_examples'] == []


def test_step1_parsing_preserves_n_for_preflight_visibility():
    from views.wizard_steps.step1_gene_input import _clean_pasted_gene_input

    cleaned, _warnings = _clean_pasted_gene_input('>Gene\nATGGCTNNNTAA', use_service_cleaner=True)

    assert cleaned == 'ATGGCTNNNTAA'


def test_step1_formatting_only_input_has_no_invalid_letters_in_feedback():
    from views.wizard_steps.step1_gene_input import _build_sequence_feedback, _clean_pasted_gene_input

    raw = '>Gene\nATG GCT\n\tAAC-TAA…⋯'
    cleaned, _warnings = _clean_pasted_gene_input(raw, use_service_cleaner=True)
    feedback = _build_sequence_feedback(raw, cleaned)

    assert cleaned == 'ATGGCTAACTAA'
    assert feedback['invalid_count'] == 0
    assert feedback['invalid_examples'] == []
    assert any(token in raw for token in (' ', '\n', '\t', '-', '…', '⋯'))


def test_step1_ui_warning_split_treats_formatting_only_as_info_not_non_dna_warning():
    from views.wizard_steps.step1_gene_input import _clean_pasted_gene_input

    raw = '>Gene\nATG GCT\n\tAAC-TAA…⋯'
    sequence_text = '\n'.join(ln for ln in raw.splitlines() if not ln.strip().startswith('>'))
    cleaned, _warnings = _clean_pasted_gene_input(raw, use_service_cleaner=True)
    removed_non_base_chars = [
        char
        for char in sequence_text
        if char not in {'A', 'T', 'C', 'G', 'N', 'a', 't', 'c', 'g', 'n'}
        and not char.isspace()
        and char not in {'-', '.', '…', '⋯'}
    ]

    formatting_message = 'Whitespace or formatting characters were ignored during parsing.'
    non_dna_warning = f'Removed {len(removed_non_base_chars)} non-DNA character(s) from the input.'

    assert cleaned == 'ATGGCTAACTAA'
    assert removed_non_base_chars == []
    assert formatting_message == 'Whitespace or formatting characters were ignored during parsing.'
    assert 'non-DNA character(s) removed' not in non_dna_warning


def test_step1_ui_warning_split_treats_invalid_letters_as_non_dna_warning_candidate():
    from views.wizard_steps.step1_gene_input import _clean_pasted_gene_input

    raw = '>Gene\nATGGCXYZTAA'
    sequence_text = '\n'.join(ln for ln in raw.splitlines() if not ln.strip().startswith('>'))
    cleaned, _warnings = _clean_pasted_gene_input(raw, use_service_cleaner=True)
    removed_non_base_chars = [
        char
        for char in sequence_text
        if char not in {'A', 'T', 'C', 'G', 'N', 'a', 't', 'c', 'g', 'n'}
        and not char.isspace()
        and char not in {'-', '.', '…', '⋯'}
    ]

    assert cleaned == 'ATGGCTAA'
    assert removed_non_base_chars == ['X', 'Y', 'Z']


def test_step1_raw_paste_with_x_has_invalid_character_preflight_issue():
    from services.sequence_inspector import inspect_sequence
    from views.wizard_steps.step1_gene_input import _clean_pasted_gene_input

    raw = '>Gene\nATGGCXTAA'
    cleaned, _warnings = _clean_pasted_gene_input(raw, use_service_cleaner=True)
    raw_result = inspect_sequence(raw)

    assert cleaned == 'ATGGCTAA'
    assert raw_result.status == 'Invalid Sequence'
    assert [(item.character, item.count) for item in raw_result.invalid_characters] == [('X', 1)]
