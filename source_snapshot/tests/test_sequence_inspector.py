"""Targeted tests for the Sequence Inspector MVP."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.sequence_inspector import WIZARD_MINIMUM_SEQUENCE_LENGTH, inspect_sequence


def test_valid_short_cds_needs_review_not_ready_for_wizard():
    result = inspect_sequence("ATGGCTGCTTAA")

    assert result.status == "Needs Review"
    assert result.status != "Ready for Wizard"
    assert result.length == 12
    assert result.valid_bases is True
    assert result.length_divisible_by_3 is True
    assert result.starts_with_atg is True
    assert result.ends_with_stop_codon is True
    assert result.has_internal_stop_codon is False
    assert result.translated_protein_length == 3
    assert result.errors == []
    assert any(
        f"below the Wizard minimum length of {WIZARD_MINIMUM_SEQUENCE_LENGTH} bp" in warning
        for warning in result.warnings
    )


def test_valid_cds_at_or_above_wizard_minimum_is_ready_for_wizard():
    result = inspect_sequence(
        "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCC"
        "ATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA"
    )

    assert result.status == "Ready for Wizard"
    assert result.length >= WIZARD_MINIMUM_SEQUENCE_LENGTH
    assert result.translated_protein_length is not None
    assert result.errors == []
    assert result.warnings == []


def test_invalid_character_is_invalid_sequence():
    result = inspect_sequence("ATGGCXTAA")

    assert result.status == "Invalid Sequence"
    assert result.valid_bases is False
    assert [(item.character, item.count) for item in result.invalid_characters] == [("X", 1)]
    assert any("Invalid character" in error for error in result.errors)


def test_sequence_inspector_status_vocabulary_is_mvp_stable():
    observed_statuses = {
        inspect_sequence(
            "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCC"
            "ATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA"
        ).status,
        inspect_sequence("ATGGCTGCTTAA").status,
        inspect_sequence("ATGGCXTAA").status,
    }

    assert observed_statuses == {
        "Ready for Wizard",
        "Needs Review",
        "Invalid Sequence",
    }


def test_non_3n_length_needs_review_or_invalid():
    result = inspect_sequence("ATGGCTTA")

    assert result.status in {"Needs Review", "Invalid Sequence"}
    assert result.length_divisible_by_3 is False
    assert any("not divisible by 3" in warning for warning in result.warnings)


def test_internal_stop_codon_needs_review_or_invalid():
    result = inspect_sequence("ATGAAATAAGCTTGA")

    assert result.status in {"Needs Review", "Invalid Sequence"}
    assert result.has_internal_stop_codon is True
    assert result.internal_stop_positions == [7]
    assert result.translated_protein_length is None
    assert any("Internal in-frame stop" in warning for warning in result.warnings)


def test_high_gc_repeat_sequence_reports_warning():
    result = inspect_sequence("ATG" + "GCGCGC" * 6 + "TAA")

    assert result.status == "Needs Review"
    assert result.gc_percentage > 70.0
    assert any("High GC content" in warning for warning in result.warnings)
    assert any("Simple repeat" in warning for warning in result.warnings)


def test_sequence_with_n_bases_needs_review_not_ready():
    result = inspect_sequence("ATGGCTNNNTAA")

    assert result.status == "Needs Review"
    assert result.valid_bases is True
    assert result.translated_protein_length is None
    assert any("N bases" in warning for warning in result.warnings)


def test_valid_short_cds_is_not_ready_for_wizard_explicit_target_case():
    result = inspect_sequence("ATGGCTGCTTAA")

    assert result.status == "Needs Review"
    assert result.status != "Ready for Wizard"
    assert result.translated_protein_length == 3

