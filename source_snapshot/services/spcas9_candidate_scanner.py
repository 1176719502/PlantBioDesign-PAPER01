"""Pure deterministic SpCas9 candidate scanning for the CRISPR V1 contract."""
from __future__ import annotations

from dataclasses import asdict

from services.crispr_v1_contract import (
    AlgorithmIdentity,
    CRISPR_V1_SCHEMA_NAME,
    CRISPR_V1_SCHEMA_VERSION,
    CandidateWarning,
    CandidateWarningCode,
    ComputationMode,
    ComputationStatus,
    CrisprScannerResultV1,
    CrisprStrand,
    CrisprTargetSequence,
    EvidenceStatus,
    PamContext,
    ReviewState,
    SCANNER_ALGORITHM_ID,
    SCANNER_ALGORITHM_VERSION,
    SPCAS9_PROFILE_ID,
    ScannerProvenance,
    SpCas9CandidateGuide,
    SpCas9Configuration,
    canonical_sha256,
    sha256_text,
)


_COMPLEMENT = str.maketrans("ACGT", "TGCA")
_SCANNER = AlgorithmIdentity(SCANNER_ALGORITHM_ID, SCANNER_ALGORITHM_VERSION)
_GC_RULE = AlgorithmIdentity("spacer_gc_fraction_v1", "1.0.0")
_POLY_T_RULE = AlgorithmIdentity("poly_t_4_run_v1", "1.0.0")
_HOMOPOLYMER_RULE = AlgorithmIdentity("homopolymer_5_run_v1", "1.0.0")
_SIMPLE_SEQUENCE_RULE = AlgorithmIdentity("dinucleotide_4_repeat_v1", "1.0.0")
_WARNING_RULES = (_POLY_T_RULE, _HOMOPOLYMER_RULE, _SIMPLE_SEQUENCE_RULE)


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(_COMPLEMENT)[::-1]


def _candidate_warnings(spacer: str) -> tuple[CandidateWarning, ...]:
    warnings: list[CandidateWarning] = []
    if "TTTT" in spacer:
        warnings.append(
            CandidateWarning(
                code=CandidateWarningCode.POLY_T,
                rule=_POLY_T_RULE,
                message="Spacer contains a run of at least four thymidines.",
                trigger="TTTT",
            )
        )
    homopolymer = next(
        (base * 5 for base in "ACGT" if base * 5 in spacer),
        None,
    )
    if homopolymer is not None:
        warnings.append(
            CandidateWarning(
                code=CandidateWarningCode.HOMOPOLYMER,
                rule=_HOMOPOLYMER_RULE,
                message="Spacer contains a homopolymer run of at least five bases.",
                trigger=homopolymer,
            )
        )
    repeated_dinucleotide = next(
        (
            spacer[index : index + 2]
            for index in range(len(spacer) - 7)
            if spacer[index : index + 2] * 4 == spacer[index : index + 8]
        ),
        None,
    )
    if repeated_dinucleotide is not None:
        warnings.append(
            CandidateWarning(
                code=CandidateWarningCode.SIMPLE_SEQUENCE,
                rule=_SIMPLE_SEQUENCE_RULE,
                message="Spacer contains a dinucleotide repeated at least four times.",
                trigger=repeated_dinucleotide * 4,
            )
        )
    return tuple(warnings)


def _guide_id(
    target: CrisprTargetSequence,
    configuration: SpCas9Configuration,
    *,
    spacer: str,
    spacer_start: int,
    spacer_end: int,
    strand: CrisprStrand,
    pam: str,
) -> str:
    digest = canonical_sha256(
        {
            "contig": target.contig,
            "nuclease_profile_id": configuration.nuclease_profile_id,
            "pam": pam,
            "reference_pack_id": target.reference_pack_id,
            "spacer": spacer,
            "spacer_end": spacer_end,
            "spacer_start": spacer_start,
            "strand": strand.value,
            "target_id": target.target_id,
            "target_sequence_sha256": target.sequence_sha256,
        }
    )
    return f"spcas9-guide-{digest[:24]}"


def _make_candidate(
    target: CrisprTargetSequence,
    configuration: SpCas9Configuration,
    *,
    spacer: str,
    spacer_start: int,
    spacer_end: int,
    strand: CrisprStrand,
    pam: str,
    pam_start: int,
    pam_end: int,
    context_start: int,
    context_end: int,
) -> SpCas9CandidateGuide:
    reference_context = target.sequence[context_start:context_end]
    guide_context = (
        reference_context
        if strand is CrisprStrand.PLUS
        else _reverse_complement(reference_context)
    )
    if guide_context != spacer + pam:
        raise AssertionError("scanner context does not reconstruct spacer and PAM")
    warnings = _candidate_warnings(spacer)
    return SpCas9CandidateGuide(
        guide_id=_guide_id(
            target,
            configuration,
            spacer=spacer,
            spacer_start=spacer_start,
            spacer_end=spacer_end,
            strand=strand,
            pam=pam,
        ),
        target_id=target.target_id,
        reference_pack_id=target.reference_pack_id,
        contig=target.contig,
        nuclease_profile_id=SPCAS9_PROFILE_ID,
        spacer=spacer,
        spacer_start=spacer_start,
        spacer_end=spacer_end,
        strand=strand,
        pam_context=PamContext(
            pam=pam,
            pam_start=pam_start,
            pam_end=pam_end,
            reference_context=reference_context,
            guide_context=guide_context,
            context_start=context_start,
            context_end=context_end,
            reference_context_sha256=sha256_text(reference_context),
        ),
        gc_fraction=(spacer.count("G") + spacer.count("C")) / 20,
        gc_evidence_status=EvidenceStatus.HEURISTIC,
        gc_rule=_GC_RULE,
        warnings=warnings,
        review_state=ReviewState.REVIEW_REQUIRED if warnings else None,
        review_trigger_ids=tuple(warning.code.value for warning in warnings),
        candidate_source="local_scan",
        scanner=_SCANNER,
    )


def scan_spcas9_candidates(
    target: CrisprTargetSequence,
    configuration: SpCas9Configuration | None = None,
) -> CrisprScannerResultV1:
    """Scan both strands and return a stable, non-ranked candidate record.

    A plus-strand candidate is ``spacer[20] + NGG`` on the forward reference.
    A minus-strand candidate is ``CCN + protospacer[20]`` on the forward
    reference; emitted spacer/PAM sequences are reverse-complemented into the
    guide orientation.  All coordinate fields remain forward-reference,
    zero-based, half-open intervals.
    """
    if not isinstance(target, CrisprTargetSequence):
        raise TypeError("target must be a CrisprTargetSequence")
    config = configuration or SpCas9Configuration()
    if not isinstance(config, SpCas9Configuration):
        raise TypeError("configuration must be a SpCas9Configuration")

    sequence = target.sequence
    candidates: list[SpCas9CandidateGuide] = []
    for context_start in range(max(0, len(sequence) - 22)):
        context_end = context_start + 23
        if context_end > len(sequence):
            break
        context = sequence[context_start:context_end]
        plus_pam = context[20:23]
        if plus_pam[1:] == "GG":
            candidates.append(
                _make_candidate(
                    target,
                    config,
                    spacer=context[:20],
                    spacer_start=context_start,
                    spacer_end=context_start + 20,
                    strand=CrisprStrand.PLUS,
                    pam=plus_pam,
                    pam_start=context_start + 20,
                    pam_end=context_end,
                    context_start=context_start,
                    context_end=context_end,
                )
            )
        if context[:2] == "CC":
            candidates.append(
                _make_candidate(
                    target,
                    config,
                    spacer=_reverse_complement(context[3:23]),
                    spacer_start=context_start + 3,
                    spacer_end=context_end,
                    strand=CrisprStrand.MINUS,
                    pam=_reverse_complement(context[:3]),
                    pam_start=context_start,
                    pam_end=context_start + 3,
                    context_start=context_start,
                    context_end=context_end,
                )
            )

    candidates.sort(
        key=lambda candidate: (
            candidate.spacer_start,
            0 if candidate.strand is CrisprStrand.PLUS else 1,
            candidate.spacer,
            candidate.guide_id,
        )
    )
    candidate_tuple = tuple(candidates)
    request_sha256 = canonical_sha256(
        {
            "configuration_sha256": config.configuration_sha256,
            "contig": target.contig,
            "reference_pack_id": target.reference_pack_id,
            "target_id": target.target_id,
            "target_sequence_sha256": target.sequence_sha256,
        }
    )
    output_sha256 = canonical_sha256(
        [asdict(candidate) for candidate in candidate_tuple]
    )
    return CrisprScannerResultV1(
        schema_name=CRISPR_V1_SCHEMA_NAME,
        schema_version=CRISPR_V1_SCHEMA_VERSION,
        target=target,
        configuration=config,
        candidates=candidate_tuple,
        provenance=ScannerProvenance(
            scanner=_SCANNER,
            warning_rules=_WARNING_RULES,
            target_sequence_sha256=target.sequence_sha256,
            configuration_sha256=config.configuration_sha256,
            request_sha256=request_sha256,
            output_sha256=output_sha256,
            computation_mode=ComputationMode.LOCAL,
            computation_status=ComputationStatus.COMPLETED,
        ),
    )


__all__ = ["scan_spcas9_candidates"]
