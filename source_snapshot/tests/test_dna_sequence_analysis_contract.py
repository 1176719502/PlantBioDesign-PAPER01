from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from services.dna_sequence_analysis import (
    DNA_CONSTRUCT_READY_ALPHABET,
    DNA_IUPAC_ANALYSIS_ALPHABET,
    DnaSequenceAnalysisResult,
    InvalidTopologyError,
    SequenceErrorCode,
    SequenceTopology,
    SequenceWarningCode,
    analyze_dna_sequence,
)


def _error_codes(result: DnaSequenceAnalysisResult) -> tuple[SequenceErrorCode, ...]:
    return tuple(finding.code for finding in result.errors)


def _warning_codes(result: DnaSequenceAnalysisResult) -> tuple[SequenceWarningCode, ...]:
    return tuple(finding.code for finding in result.warnings)


@pytest.mark.parametrize("raw", ["", " ", "\n\r\t"])
def test_empty_or_whitespace_only_input_is_not_a_zero_percent_sequence(raw: str) -> None:
    result = analyze_dna_sequence(raw)

    assert result.raw_sequence == raw
    assert result.normalized_sequence == ""
    assert result.normalized_length == 0
    assert result.valid_base_count == 0
    assert result.sequence_length == 0
    assert result.gc_count == 0
    assert result.unambiguous_base_count == 0
    assert result.ambiguous_base_count == 0
    assert result.gc_percent_total is None
    assert result.gc_percent_unambiguous is None
    assert result.reverse_complement is None
    assert result.is_valid_for_analysis is False
    assert result.is_construct_ready is False
    assert result.invalid_characters == ()
    assert _error_codes(result) == (SequenceErrorCode.EMPTY_SEQUENCE,)
    assert result.warnings == ()


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("acgt", "ACGT"),
        ("ACGT", "ACGT"),
        ("aCgT", "ACGT"),
        (" a\nC\rg\tT ", "ACGT"),
    ],
)
def test_normalization_removes_whitespace_and_uppercases_letters(
    raw: str, normalized: str
) -> None:
    result = analyze_dna_sequence(raw)

    assert result.normalized_sequence == normalized
    assert result.normalized_length == 4
    assert result.valid_base_count == 4
    assert result.sequence_length == 4
    assert result.is_valid_for_analysis is True
    assert result.is_construct_ready is True
    assert result.errors == ()
    assert result.warnings == ()


def test_public_alphabets_separate_analysis_from_construct_eligibility() -> None:
    assert DNA_IUPAC_ANALYSIS_ALPHABET == frozenset("ACGTRYSWKMBDHVN")
    assert DNA_CONSTRUCT_READY_ALPHABET == frozenset("ACGT")

    result = analyze_dna_sequence("ACGTRYSWKMBDHVN")

    assert result.is_valid_for_analysis is True
    assert result.is_construct_ready is False
    assert result.sequence_length == 15
    assert result.unambiguous_base_count == 4
    assert result.ambiguous_base_count == 11
    assert _warning_codes(result) == (
        SequenceWarningCode.AMBIGUOUS_BASES_PRESENT,
        SequenceWarningCode.NOT_CONSTRUCT_READY,
    )


@pytest.mark.parametrize("raw", ["N", "RYSWKM", "BDHVN"])
def test_ambiguity_is_analysis_valid_but_not_construct_ready(raw: str) -> None:
    result = analyze_dna_sequence(raw)

    assert result.is_valid_for_analysis is True
    assert result.is_construct_ready is False
    assert result.errors == ()
    assert _warning_codes(result) == (
        SequenceWarningCode.AMBIGUOUS_BASES_PRESENT,
        SequenceWarningCode.NOT_CONSTRUCT_READY,
    )


def test_uracil_has_a_dedicated_error_and_is_never_converted() -> None:
    result = analyze_dna_sequence("aUg")

    assert result.normalized_sequence == "AUG"
    assert result.valid_base_count == 2
    assert result.sequence_length is None
    assert result.invalid_characters[0].character == "U"
    assert result.invalid_characters[0].position == 1
    assert _error_codes(result) == (SequenceErrorCode.SEQUENCE_CONTAINS_URACIL,)
    assert result.is_valid_for_analysis is False
    assert result.is_construct_ready is False
    assert result.gc_count is None
    assert result.gc_percent_total is None
    assert result.gc_percent_unambiguous is None
    assert result.reverse_complement is None


@pytest.mark.parametrize("raw", ["ATG1", "ATG-", "ATGX"])
def test_digits_punctuation_and_other_letters_are_preserved_and_invalid(raw: str) -> None:
    result = analyze_dna_sequence(raw)

    assert result.normalized_sequence == raw
    assert result.normalized_length == 4
    assert result.valid_base_count == 3
    assert result.sequence_length is None
    assert result.invalid_characters[0].character == raw[-1]
    assert result.invalid_characters[0].position == 3
    assert _error_codes(result) == (SequenceErrorCode.INVALID_DNA_CHARACTER,)
    assert result.is_valid_for_analysis is False
    assert result.is_construct_ready is False
    assert result.gc_count is None
    assert result.gc_percent_total is None
    assert result.gc_percent_unambiguous is None
    assert result.reverse_complement is None


def test_all_invalid_characters_use_zero_based_normalized_positions_in_order() -> None:
    result = analyze_dna_sequence("a t g\n-c1")

    assert result.normalized_sequence == "ATG-C1"
    assert result.normalized_length == 6
    assert result.valid_base_count == 4
    assert tuple(
        (item.character, item.position) for item in result.invalid_characters
    ) == (("-", 3), ("1", 5))


def test_uracil_and_other_invalid_characters_have_stable_nonduplicated_errors() -> None:
    result = analyze_dna_sequence("U!2")

    assert tuple(
        (item.character, item.position) for item in result.invalid_characters
    ) == (("U", 0), ("!", 1), ("2", 2))
    assert _error_codes(result) == (
        SequenceErrorCode.SEQUENCE_CONTAINS_URACIL,
        SequenceErrorCode.INVALID_DNA_CHARACTER,
    )
    assert result.warnings == ()


@pytest.mark.parametrize(
    ("sequence", "expected_gc"),
    [("AAAA", 0.0), ("GCGC", 100.0), ("ACGT", 50.0)],
)
def test_unambiguous_gc_percentages_use_the_same_denominator(
    sequence: str, expected_gc: float
) -> None:
    result = analyze_dna_sequence(sequence)

    assert result.gc_percent_total == expected_gc
    assert result.gc_percent_unambiguous == expected_gc


def test_ambiguous_sequence_returns_both_gc_denominators() -> None:
    result = analyze_dna_sequence("ACGTN")

    assert result.gc_count == 2
    assert result.sequence_length == 5
    assert result.unambiguous_base_count == 4
    assert result.ambiguous_base_count == 1
    assert result.gc_percent_total == 40.0
    assert result.gc_percent_unambiguous == 50.0


def test_all_ambiguous_sequence_has_no_unambiguous_gc_denominator() -> None:
    result = analyze_dna_sequence("RYSWKMBDHVN")

    assert result.gc_count == 0
    assert result.sequence_length == 11
    assert result.unambiguous_base_count == 0
    assert result.ambiguous_base_count == 11
    assert result.gc_percent_total == 0.0
    assert result.gc_percent_unambiguous is None


def test_full_iupac_reverse_complement_is_defined() -> None:
    result = analyze_dna_sequence("ACGTRYSWKMBDHVN")

    assert result.reverse_complement == "NBDHVKMWSRYACGT"


@pytest.mark.parametrize(
    "sequence",
    ["ACGTRYSWKMBDHVN", "ACGTN", "ACGTA", "ACGTAC"],
)
def test_reverse_complement_is_an_involution_for_valid_analysis_sequences(
    sequence: str,
) -> None:
    first = analyze_dna_sequence(sequence).reverse_complement
    assert first is not None

    second = analyze_dna_sequence(first).reverse_complement
    assert second == sequence


@pytest.mark.parametrize(
    ("topology", "expected"),
    [
        ("unknown", SequenceTopology.UNKNOWN),
        ("linear", SequenceTopology.LINEAR),
        ("circular", SequenceTopology.CIRCULAR),
        (SequenceTopology.LINEAR, SequenceTopology.LINEAR),
    ],
)
def test_topology_is_explicit_metadata_and_does_not_change_analysis(
    topology: str | SequenceTopology, expected: SequenceTopology
) -> None:
    baseline = analyze_dna_sequence("ACGTN")
    result = analyze_dna_sequence("ACGTN", topology=topology)

    assert result.topology is expected
    assert result.normalized_sequence == baseline.normalized_sequence
    assert result.gc_percent_total == baseline.gc_percent_total
    assert result.reverse_complement == baseline.reverse_complement


@pytest.mark.parametrize("topology", ["plasmid", "LINEAR", "", None, 1])
def test_invalid_topology_is_an_explicit_programming_error(topology: object) -> None:
    with pytest.raises(InvalidTopologyError) as exc_info:
        analyze_dna_sequence("ACGT", topology=topology)  # type: ignore[arg-type]

    assert exc_info.value.code is SequenceErrorCode.INVALID_TOPOLOGY


@pytest.mark.parametrize("raw", [None, b"ACGT", 123, ["A", "C"]])
def test_non_string_sequence_is_an_explicit_programming_error(raw: object) -> None:
    with pytest.raises(TypeError, match="raw_sequence must be a string"):
        analyze_dna_sequence(raw)  # type: ignore[arg-type]


def test_result_and_nested_records_are_immutable() -> None:
    result = analyze_dna_sequence("ATG-")

    with pytest.raises(FrozenInstanceError):
        result.normalized_sequence = "ATG"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.invalid_characters[0].position = 0  # type: ignore[misc]


def test_repeated_calls_are_equal_with_stable_finding_order() -> None:
    first = analyze_dna_sequence(" u N ! ", topology="circular")
    second = analyze_dna_sequence(" u N ! ", topology="circular")

    assert first == second
    assert _error_codes(first) == (
        SequenceErrorCode.SEQUENCE_CONTAINS_URACIL,
        SequenceErrorCode.INVALID_DNA_CHARACTER,
    )


def test_analysis_has_no_file_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    before = tuple(tmp_path.iterdir())

    analyze_dna_sequence("ACGTN", topology="circular")

    assert tuple(tmp_path.iterdir()) == before


def test_public_service_has_no_database_streamlit_or_environment_result_fields() -> None:
    source = Path(__file__).resolve().parents[1].joinpath(
        "services", "dna_sequence_analysis.py"
    ).read_text(encoding="utf-8")
    result_fields = {item.name for item in fields(DnaSequenceAnalysisResult)}

    assert "streamlit" not in source
    assert "sqlite" not in source
    assert "random" not in source
    assert "datetime" not in source
    assert "timestamp" not in result_fields
    assert "path" not in result_fields
    assert "environment" not in result_fields
