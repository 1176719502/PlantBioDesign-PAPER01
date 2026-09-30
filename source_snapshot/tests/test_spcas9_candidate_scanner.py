from __future__ import annotations

from services.crispr_v1_contract import (
    CandidateWarningCode,
    CrisprStrand,
    CrisprTargetSequence,
    EvidenceStatus,
    ReviewState,
)
import services.spcas9_candidate_scanner as scanner_module
from services.spcas9_candidate_scanner import scan_spcas9_candidates


def _scan(sequence: str):
    target = CrisprTargetSequence.from_raw(
        sequence,
        target_id="target-1",
        display_name="Target 1",
        reference_pack_id="fixture-reference-v1",
        contig="fixture-contig",
    )
    return scan_spcas9_candidates(target)


def test_known_forward_candidate_has_exact_spacer_pam_and_coordinates() -> None:
    sequence = "AAA" + "ACGT" * 5 + "TGG" + "CCC"
    result = _scan(sequence)
    candidate = next(item for item in result.candidates if item.strand is CrisprStrand.PLUS)

    assert candidate.spacer == "ACGT" * 5
    assert (candidate.spacer_start, candidate.spacer_end) == (3, 23)
    assert candidate.pam_context.pam == "TGG"
    assert (candidate.pam_context.pam_start, candidate.pam_context.pam_end) == (23, 26)
    assert (candidate.pam_context.context_start, candidate.pam_context.context_end) == (3, 26)
    assert candidate.pam_context.reference_context == "ACGT" * 5 + "TGG"
    assert candidate.pam_context.guide_context == "ACGT" * 5 + "TGG"


def test_known_reverse_candidate_uses_forward_reference_coordinates() -> None:
    # Forward reference is CCN + protospacer; emitted guide is its reverse complement.
    sequence = "AAA" + "CCA" + "ACGT" * 5 + "TTT"
    result = _scan(sequence)
    candidate = next(item for item in result.candidates if item.strand is CrisprStrand.MINUS)

    assert candidate.spacer == "ACGT" * 5
    assert (candidate.spacer_start, candidate.spacer_end) == (6, 26)
    assert candidate.pam_context.pam == "TGG"
    assert (candidate.pam_context.pam_start, candidate.pam_context.pam_end) == (3, 6)
    assert (candidate.pam_context.context_start, candidate.pam_context.context_end) == (3, 26)
    assert candidate.pam_context.reference_context == "CCA" + "ACGT" * 5
    assert candidate.pam_context.guide_context == "ACGT" * 5 + "TGG"


def test_multiple_overlapping_pams_are_all_retained() -> None:
    result = _scan("A" * 20 + "GGGG")

    plus = [item for item in result.candidates if item.strand is CrisprStrand.PLUS]
    assert [(item.spacer_start, item.pam_context.pam) for item in plus] == [
        (0, "GGG"),
        (1, "GGG"),
    ]


def test_no_pam_and_short_boundary_inputs_return_completed_empty_results() -> None:
    no_pam = _scan("A" * 50)
    too_short = _scan("A" * 22)

    assert no_pam.candidates == ()
    assert too_short.candidates == ()
    assert len(no_pam.provenance.output_sha256) == 64
    assert len(too_short.provenance.output_sha256) == 64


def test_candidates_at_both_sequence_boundaries_are_included() -> None:
    forward = _scan("A" * 20 + "AGG")
    reverse = _scan("CCA" + "A" * 20)

    plus = next(item for item in forward.candidates if item.strand is CrisprStrand.PLUS)
    minus = next(item for item in reverse.candidates if item.strand is CrisprStrand.MINUS)
    assert (plus.pam_context.context_start, plus.pam_context.context_end) == (0, 23)
    assert (minus.pam_context.context_start, minus.pam_context.context_end) == (0, 23)


def test_mixed_strand_candidates_have_stable_coordinate_order() -> None:
    sequence = "CCA" + "A" * 17 + "TGG" + "A" * 20 + "AGG"
    first = _scan(sequence)
    second = _scan(sequence.lower())

    first_identity = [
        (candidate.spacer_start, candidate.strand.value, candidate.guide_id)
        for candidate in first.candidates
    ]
    second_identity = [
        (candidate.spacer_start, candidate.strand.value, candidate.guide_id)
        for candidate in second.candidates
    ]
    assert first_identity == second_identity
    assert first_identity == sorted(
        first_identity,
        key=lambda item: (item[0], 0 if item[1] == "+" else 1, item[2]),
    )
    assert first.provenance.output_sha256 == second.provenance.output_sha256


def test_gc_and_sequence_warnings_are_non_predictive_facts() -> None:
    result = _scan("TTTTTATATATATATACCCC" + "AGG")
    candidate = next(item for item in result.candidates if item.strand is CrisprStrand.PLUS)
    warning_codes = {warning.code for warning in candidate.warnings}

    assert candidate.gc_fraction == 4 / 20
    assert candidate.gc_evidence_status is EvidenceStatus.HEURISTIC
    assert CandidateWarningCode.POLY_T in warning_codes
    assert CandidateWarningCode.HOMOPOLYMER in warning_codes
    assert CandidateWarningCode.SIMPLE_SEQUENCE in warning_codes
    assert all(
        warning.evidence_status is EvidenceStatus.HEURISTIC
        for warning in candidate.warnings
    )
    assert candidate.review_state is ReviewState.REVIEW_REQUIRED
    assert candidate.review_trigger_ids == tuple(
        warning.code.value for warning in candidate.warnings
    )


def test_warning_free_candidate_has_no_readiness_or_recommendation_state() -> None:
    candidate = next(
        item
        for item in _scan("ACGT" * 5 + "TGG").candidates
        if item.strand is CrisprStrand.PLUS
    )

    assert candidate.warnings == ()
    assert candidate.review_state is None
    assert candidate.review_trigger_ids == ()


def test_scanner_does_not_import_or_emit_standalone_mock_data() -> None:
    result = _scan("ACGT" * 5 + "TGG")
    scanner_names = set(scanner_module.__dict__)

    assert len(result.candidates) == 1
    assert result.candidates[0].candidate_source == "local_scan"
    assert result.candidates[0].spacer == "ACGT" * 5
    assert "mock" not in result.candidates[0].guide_id
    assert "MockAdapter" not in scanner_names
    assert not any(name.lower().startswith("mock") for name in scanner_names)
