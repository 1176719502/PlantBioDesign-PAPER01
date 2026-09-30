from __future__ import annotations

from dataclasses import fields, replace

import pytest

from services.crispr_v1_contract import (
    AlgorithmIdentity,
    COORDINATE_SYSTEM_ID,
    CRISPR_V1_SCHEMA_NAME,
    ComputationMode,
    CrisprContractError,
    CrisprTargetSequence,
    EvidenceStatus,
    NotComputedPredictiveValue,
    SCANNER_ALGORITHM_ID,
    SCANNER_ALGORITHM_VERSION,
    SPCAS9_PROFILE_ID,
    SpCas9CandidateGuide,
    SpCas9Configuration,
)
from services.spcas9_candidate_scanner import scan_spcas9_candidates


def _target(sequence: str) -> CrisprTargetSequence:
    return CrisprTargetSequence.from_raw(
        sequence,
        target_id="target-1",
        display_name="Target 1",
        reference_pack_id="fixture-reference-v1",
        contig="fixture-contig",
    )


def test_target_normalization_and_identity_are_deterministic() -> None:
    first = _target(" aaac\nccgggttt ")
    second = _target("AAACCCGGGTTT")

    assert first.sequence == "AAACCCGGGTTT"
    assert first == second
    assert len(first.sequence_sha256) == 64


@pytest.mark.parametrize("sequence", ["", " \n\t", "ACGTN", "ACGU", "ACG-"])
def test_invalid_or_ambiguous_target_fails_before_scanning(sequence: str) -> None:
    with pytest.raises(CrisprContractError):
        _target(sequence)


def test_non_string_target_is_an_explicit_programming_error() -> None:
    with pytest.raises(TypeError, match="raw_sequence must be a string"):
        _target(None)  # type: ignore[arg-type]


def test_frozen_configuration_rejects_other_nucleases_or_scan_modes() -> None:
    with pytest.raises(CrisprContractError):
        SpCas9Configuration(pam_pattern="TTTV")
    with pytest.raises(CrisprContractError):
        SpCas9Configuration(strand_policy="plus")


def test_predictive_values_cannot_silently_become_zero_or_computed() -> None:
    with pytest.raises(CrisprContractError):
        NotComputedPredictiveValue(value=0)  # type: ignore[arg-type]
    with pytest.raises(CrisprContractError):
        NotComputedPredictiveValue(evidence_status=EvidenceStatus.COMPUTED)
    with pytest.raises(CrisprContractError):
        NotComputedPredictiveValue(evidence_status="not_computed")  # type: ignore[arg-type]


@pytest.mark.parametrize("field_name", ["on_target_score", "specificity_score"])
@pytest.mark.parametrize("invalid_value", [0, None, 0.0, object()])
def test_candidate_rejects_bare_predictive_field_values(
    field_name: str,
    invalid_value: object,
) -> None:
    candidate = scan_spcas9_candidates(_target("ACGT" * 5 + "TGG")).candidates[0]
    constructor_values = {
        field.name: getattr(candidate, field.name)
        for field in fields(SpCas9CandidateGuide)
    }
    constructor_values[field_name] = invalid_value

    with pytest.raises(CrisprContractError, match="explicit not-computed record"):
        SpCas9CandidateGuide(**constructor_values)


@pytest.mark.parametrize("field_name", ["on_target_score", "specificity_score"])
@pytest.mark.parametrize("invalid_value", [0, None])
def test_replace_revalidates_predictive_field_values(
    field_name: str,
    invalid_value: object,
) -> None:
    candidate = scan_spcas9_candidates(_target("ACGT" * 5 + "TGG")).candidates[0]

    with pytest.raises(CrisprContractError, match="explicit not-computed record"):
        replace(candidate, **{field_name: invalid_value})


@pytest.mark.parametrize("field_name", ["on_target_score", "specificity_score"])
def test_candidate_rejects_predictive_record_with_incompatible_status(
    field_name: str,
) -> None:
    candidate = scan_spcas9_candidates(_target("ACGT" * 5 + "TGG")).candidates[0]
    invalid = object.__new__(NotComputedPredictiveValue)
    object.__setattr__(invalid, "value", None)
    object.__setattr__(invalid, "evidence_status", EvidenceStatus.COMPUTED)

    with pytest.raises(CrisprContractError, match="must remain explicitly not_computed"):
        replace(candidate, **{field_name: invalid})


def _forward_candidate() -> SpCas9CandidateGuide:
    return scan_spcas9_candidates(_target("AAA" + "ACGT" * 5 + "TGG" + "AAA")).candidates[0]


def _reverse_candidate() -> SpCas9CandidateGuide:
    return next(
        candidate
        for candidate in scan_spcas9_candidates(
            _target("AAA" + "CCA" + "ACGT" * 5 + "AAA")
        ).candidates
        if candidate.strand.value == "-"
    )


def test_valid_forward_and_reverse_candidates_satisfy_hardened_contract() -> None:
    assert _forward_candidate().nuclease_profile_id == SPCAS9_PROFILE_ID
    assert _reverse_candidate().nuclease_profile_id == SPCAS9_PROFILE_ID


@pytest.mark.parametrize("field_name", ["spacer_start", "spacer_end"])
def test_candidate_rejects_negative_spacer_coordinates(field_name: str) -> None:
    with pytest.raises(CrisprContractError, match="non-negative integer"):
        replace(_forward_candidate(), **{field_name: -1})


@pytest.mark.parametrize("field_name", ["pam_start", "pam_end"])
def test_candidate_rejects_negative_pam_coordinates(field_name: str) -> None:
    context = _forward_candidate().pam_context
    with pytest.raises(CrisprContractError, match="non-negative integer"):
        replace(context, **{field_name: -1})


@pytest.mark.parametrize("field_name", ["context_start", "context_end"])
def test_candidate_rejects_negative_context_coordinates(field_name: str) -> None:
    context = _forward_candidate().pam_context
    with pytest.raises(CrisprContractError, match="non-negative integer"):
        replace(context, **{field_name: -1})


def test_candidate_rejects_invalid_or_empty_ranges() -> None:
    candidate = _forward_candidate()
    with pytest.raises(CrisprContractError, match="span exactly 20 nt"):
        replace(candidate, spacer_end=candidate.spacer_start)
    with pytest.raises(CrisprContractError, match="span exactly 3 nt"):
        replace(
            candidate.pam_context,
            pam_end=candidate.pam_context.pam_start,
        )
    with pytest.raises(CrisprContractError, match="span exactly 23 nt"):
        replace(
            candidate.pam_context,
            context_end=candidate.pam_context.context_start,
        )


def test_candidate_rejects_wrong_nuclease_profile_and_scanner_identity() -> None:
    candidate = _forward_candidate()
    with pytest.raises(CrisprContractError, match="frozen SpCas9 profile"):
        replace(candidate, nuclease_profile_id="other-nuclease")
    with pytest.raises(CrisprContractError, match="scanner identity"):
        replace(candidate, scanner=AlgorithmIdentity("other-scanner", "1.0.0"))


def test_candidate_rejects_pam_context_and_coordinate_mismatches() -> None:
    candidate = _forward_candidate()
    context = candidate.pam_context
    with pytest.raises(CrisprContractError, match="PAM must match"):
        replace(context, pam="AGG", guide_context=context.guide_context[:-3] + "TGG")
    with pytest.raises(CrisprContractError, match="coordinates are incoherent"):
        replace(
            candidate,
            pam_context=replace(
                context,
                pam_start=context.pam_start + 1,
                pam_end=context.pam_end + 1,
            ),
        )


def test_all_scanner_generated_records_revalidate_through_public_replace() -> None:
    result = scan_spcas9_candidates(
        _target("CCA" + "A" * 17 + "TGG" + "A" * 20 + "AGG")
    )

    assert result.candidates
    for candidate in result.candidates:
        assert replace(candidate) == candidate
        assert candidate.scanner == AlgorithmIdentity(
            SCANNER_ALGORITHM_ID,
            SCANNER_ALGORITHM_VERSION,
        )


def test_scanner_contract_has_no_ranking_recommendation_or_overall_score_fields() -> None:
    field_names = {field.name for field in fields(SpCas9CandidateGuide)}

    assert "overall_score" not in field_names
    assert "rank" not in field_names
    assert "ranking" not in field_names
    assert "recommended" not in field_names
    assert "is_recommended" not in field_names


def test_result_exposes_complete_computation_and_algorithm_identity() -> None:
    result = scan_spcas9_candidates(_target("A" * 20 + "TGG"))
    candidate = result.candidates[0]

    assert result.schema_name == CRISPR_V1_SCHEMA_NAME
    assert result.configuration.coordinate_system == COORDINATE_SYSTEM_ID
    assert result.provenance.scanner.algorithm_id == "SpCas9CandidateScannerV1"
    assert result.provenance.scanner.version == "1.0.0"
    assert result.provenance.computation_mode is ComputationMode.LOCAL
    assert len(result.provenance.configuration_sha256) == 64
    assert len(result.provenance.request_sha256) == 64
    assert len(result.provenance.output_sha256) == 64
    assert candidate.on_target_score.value is None
    assert candidate.on_target_score.evidence_status is EvidenceStatus.NOT_COMPUTED
    assert candidate.specificity_score.value is None
    assert candidate.specificity_score.evidence_status is EvidenceStatus.NOT_COMPUTED


def test_mock_is_not_a_formal_computation_mode_or_candidate_source() -> None:
    assert "mock" not in {mode.value for mode in ComputationMode}
    result = scan_spcas9_candidates(_target("A" * 20 + "TGG"))
    assert {candidate.candidate_source for candidate in result.candidates} == {
        "local_scan"
    }
