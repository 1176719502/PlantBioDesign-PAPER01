"""Typed, persistence-independent contract for deterministic CRISPR V1 scanning.

Coordinates are zero-based, half-open intervals on the forward reference
sequence.  Strand describes the orientation of the emitted spacer and PAM;
sequence fields are always written in that guide orientation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from typing import Any


CRISPR_V1_SCHEMA_NAME = "CrisprScannerResultV1"
CRISPR_V1_SCHEMA_VERSION = "1.0.0"
SPCAS9_PROFILE_ID = "spcas9_ngg_20nt_v1"
COORDINATE_SYSTEM_ID = "zero_based_half_open_reference_forward_v1"
ORDERING_RULE_ID = "reference_coordinate_order_v1"
SCANNER_ALGORITHM_ID = "SpCas9CandidateScannerV1"
SCANNER_ALGORITHM_VERSION = "1.0.0"


class CrisprContractError(ValueError):
    """Raised when a value cannot enter the typed CRISPR V1 contract."""


class CrisprStrand(StrEnum):
    PLUS = "+"
    MINUS = "-"


class EvidenceStatus(StrEnum):
    COMPUTED = "computed"
    EXTERNAL_IMPORT = "external_import"
    HEURISTIC = "heuristic"
    NOT_COMPUTED = "not_computed"
    UNAVAILABLE = "unavailable"
    MOCK = "mock"


class ComputationMode(StrEnum):
    LOCAL = "local"
    EXTERNAL_IMPORT = "external_import"
    MIXED = "mixed"


class ComputationStatus(StrEnum):
    COMPLETED = "completed"


class ReviewState(StrEnum):
    REVIEW_REQUIRED = "review_required"


class CandidateWarningCode(StrEnum):
    POLY_T = "POLY_T_PRESENT"
    HOMOPOLYMER = "HOMOPOLYMER_PRESENT"
    SIMPLE_SEQUENCE = "SIMPLE_SEQUENCE_PRESENT"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(encoded)


def _require_text(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CrisprContractError(f"{field_name} must be a non-empty string")


def _require_non_negative_coordinate(field_name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CrisprContractError(f"{field_name} must be a non-negative integer")


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


@dataclass(frozen=True, slots=True)
class AlgorithmIdentity:
    algorithm_id: str
    version: str

    def __post_init__(self) -> None:
        _require_text("algorithm_id", self.algorithm_id)
        _require_text("version", self.version)


@dataclass(frozen=True, slots=True)
class CrisprTargetSequence:
    target_id: str
    display_name: str
    reference_pack_id: str
    contig: str
    sequence: str
    sequence_sha256: str

    @classmethod
    def from_raw(
        cls,
        raw_sequence: str,
        *,
        target_id: str,
        display_name: str,
        reference_pack_id: str,
        contig: str,
    ) -> "CrisprTargetSequence":
        if not isinstance(raw_sequence, str):
            raise TypeError("raw_sequence must be a string")
        normalized = "".join(
            character.upper()
            for character in raw_sequence
            if not character.isspace()
        )
        if not normalized:
            raise CrisprContractError(
                "target sequence is empty after whitespace normalization"
            )
        for position, character in enumerate(normalized):
            if character not in "ACGT":
                raise CrisprContractError(
                    "target sequence must contain only unambiguous A/C/G/T; "
                    f"found {character!r} at normalized position {position}"
                )
        return cls(
            target_id=target_id,
            display_name=display_name,
            reference_pack_id=reference_pack_id,
            contig=contig,
            sequence=normalized,
            sequence_sha256=sha256_text(normalized),
        )

    def __post_init__(self) -> None:
        for field_name in (
            "target_id",
            "display_name",
            "reference_pack_id",
            "contig",
        ):
            _require_text(field_name, getattr(self, field_name))
        if not self.sequence or any(base not in "ACGT" for base in self.sequence):
            raise CrisprContractError(
                "sequence must be normalized, non-empty, unambiguous DNA"
            )
        if self.sequence_sha256 != sha256_text(self.sequence):
            raise CrisprContractError("sequence_sha256 does not match sequence")


@dataclass(frozen=True, slots=True)
class SpCas9Configuration:
    nuclease_profile_id: str = SPCAS9_PROFILE_ID
    pam_pattern: str = "NGG"
    spacer_length: int = 20
    strand_policy: str = "both"
    coordinate_system: str = COORDINATE_SYSTEM_ID
    ordering_rule_id: str = ORDERING_RULE_ID

    def __post_init__(self) -> None:
        expected = (
            SPCAS9_PROFILE_ID,
            "NGG",
            20,
            "both",
            COORDINATE_SYSTEM_ID,
            ORDERING_RULE_ID,
        )
        observed = (
            self.nuclease_profile_id,
            self.pam_pattern,
            self.spacer_length,
            self.strand_policy,
            self.coordinate_system,
            self.ordering_rule_id,
        )
        if observed != expected:
            raise CrisprContractError(
                "CRISPR V1 supports only the frozen SpCas9 20-nt/NGG, "
                "both-strand configuration"
            )

    @property
    def configuration_sha256(self) -> str:
        return canonical_sha256(
            {
                "coordinate_system": self.coordinate_system,
                "nuclease_profile_id": self.nuclease_profile_id,
                "ordering_rule_id": self.ordering_rule_id,
                "pam_pattern": self.pam_pattern,
                "spacer_length": self.spacer_length,
                "strand_policy": self.strand_policy,
            }
        )


@dataclass(frozen=True, slots=True)
class NotComputedPredictiveValue:
    value: None = None
    evidence_status: EvidenceStatus = EvidenceStatus.NOT_COMPUTED

    def __post_init__(self) -> None:
        if self.value is not None or self.evidence_status is not EvidenceStatus.NOT_COMPUTED:
            raise CrisprContractError(
                "unsupported predictive values must be null with evidence_status "
                "not_computed"
            )


@dataclass(frozen=True, slots=True)
class CandidateWarning:
    code: CandidateWarningCode
    rule: AlgorithmIdentity
    message: str
    trigger: str
    evidence_status: EvidenceStatus = EvidenceStatus.HEURISTIC

    def __post_init__(self) -> None:
        if not isinstance(self.code, CandidateWarningCode):
            raise CrisprContractError("warning code must be a CandidateWarningCode")
        if not isinstance(self.rule, AlgorithmIdentity):
            raise CrisprContractError("warning rule must be an AlgorithmIdentity")
        _require_text("message", self.message)
        _require_text("trigger", self.trigger)
        if self.evidence_status is not EvidenceStatus.HEURISTIC:
            raise CrisprContractError(
                "candidate sequence warnings must be declared heuristics"
            )


@dataclass(frozen=True, slots=True)
class PamContext:
    pam: str
    pam_start: int
    pam_end: int
    reference_context: str
    guide_context: str
    context_start: int
    context_end: int
    reference_context_sha256: str

    def __post_init__(self) -> None:
        for field_name in ("pam_start", "pam_end", "context_start", "context_end"):
            _require_non_negative_coordinate(field_name, getattr(self, field_name))
        if not isinstance(self.pam, str) or any(base not in "ACGT" for base in self.pam):
            raise CrisprContractError("PAM must contain only unambiguous DNA bases")
        if len(self.pam) != 3 or self.pam[1:] != "GG":
            raise CrisprContractError("PAM must be an observed SpCas9 NGG sequence")
        if self.pam_end - self.pam_start != 3:
            raise CrisprContractError("PAM coordinates must span exactly 3 nt")
        if self.context_end - self.context_start != 23:
            raise CrisprContractError("candidate context must span exactly 23 nt")
        if not isinstance(self.reference_context, str) or not isinstance(
            self.guide_context, str
        ):
            raise CrisprContractError("candidate context sequences must be strings")
        if len(self.reference_context) != 23 or len(self.guide_context) != 23:
            raise CrisprContractError("candidate context sequences must be 23 nt")
        if any(
            base not in "ACGT"
            for sequence in (self.reference_context, self.guide_context)
            for base in sequence
        ):
            raise CrisprContractError(
                "candidate context sequences must be unambiguous DNA"
            )
        if self.pam != self.guide_context[-3:]:
            raise CrisprContractError("PAM must match the guide-oriented context")
        if self.reference_context_sha256 != sha256_text(self.reference_context):
            raise CrisprContractError(
                "reference_context_sha256 does not match reference_context"
            )


@dataclass(frozen=True, slots=True)
class SpCas9CandidateGuide:
    guide_id: str
    target_id: str
    reference_pack_id: str
    contig: str
    nuclease_profile_id: str
    spacer: str
    spacer_start: int
    spacer_end: int
    strand: CrisprStrand
    pam_context: PamContext
    gc_fraction: float
    gc_evidence_status: EvidenceStatus
    gc_rule: AlgorithmIdentity
    warnings: tuple[CandidateWarning, ...]
    review_state: ReviewState | None
    review_trigger_ids: tuple[str, ...]
    candidate_source: str
    scanner: AlgorithmIdentity
    on_target_score: NotComputedPredictiveValue = NotComputedPredictiveValue()
    specificity_score: NotComputedPredictiveValue = NotComputedPredictiveValue()

    def __post_init__(self) -> None:
        for field_name in ("guide_id", "target_id", "reference_pack_id", "contig"):
            _require_text(field_name, getattr(self, field_name))
        if self.nuclease_profile_id != SPCAS9_PROFILE_ID:
            raise CrisprContractError(
                "CRISPR V1 candidates must use the frozen SpCas9 profile"
            )
        if not isinstance(self.strand, CrisprStrand):
            raise CrisprContractError("strand must be a CrisprStrand")
        if not isinstance(self.pam_context, PamContext):
            raise CrisprContractError("pam_context must be a PamContext")
        for field_name in ("spacer_start", "spacer_end"):
            _require_non_negative_coordinate(field_name, getattr(self, field_name))
        if not isinstance(self.spacer, str) or len(self.spacer) != 20 or any(
            base not in "ACGT" for base in self.spacer
        ):
            raise CrisprContractError("spacer must be exactly 20 unambiguous DNA bases")
        if self.spacer_end - self.spacer_start != 20:
            raise CrisprContractError("spacer coordinates must span exactly 20 nt")
        context = self.pam_context
        if context.guide_context != self.spacer + context.pam:
            raise CrisprContractError(
                "guide context must reconstruct the emitted spacer and PAM"
            )
        if self.strand is CrisprStrand.PLUS:
            coherent_coordinates = (
                context.context_start == self.spacer_start
                and self.spacer_end == context.pam_start
                and context.pam_end == context.context_end
            )
            coherent_context = context.reference_context == context.guide_context
        else:
            coherent_coordinates = (
                context.context_start == context.pam_start
                and context.pam_end == self.spacer_start
                and self.spacer_end == context.context_end
            )
            coherent_context = (
                context.guide_context == _reverse_complement(context.reference_context)
            )
        if not coherent_coordinates:
            raise CrisprContractError(
                "spacer, PAM, and context coordinates are incoherent for strand"
            )
        if not coherent_context:
            raise CrisprContractError(
                "reference and guide contexts are incoherent for strand"
            )
        if (
            not isinstance(self.gc_fraction, (int, float))
            or isinstance(self.gc_fraction, bool)
            or not 0.0 <= self.gc_fraction <= 1.0
        ):
            raise CrisprContractError("gc_fraction must be between 0 and 1")
        expected_gc_fraction = (self.spacer.count("G") + self.spacer.count("C")) / 20
        if self.gc_fraction != expected_gc_fraction:
            raise CrisprContractError("gc_fraction does not match spacer sequence")
        if self.gc_evidence_status is not EvidenceStatus.HEURISTIC:
            raise CrisprContractError("GC fraction must be a deterministic heuristic")
        if self.gc_rule != AlgorithmIdentity("spacer_gc_fraction_v1", "1.0.0"):
            raise CrisprContractError("unexpected GC rule identity")
        if self.candidate_source != "local_scan":
            raise CrisprContractError("production scanner candidates must be local_scan")
        if self.scanner != AlgorithmIdentity(
            SCANNER_ALGORITHM_ID,
            SCANNER_ALGORITHM_VERSION,
        ):
            raise CrisprContractError("unexpected CRISPR V1 scanner identity")
        for field_name in ("on_target_score", "specificity_score"):
            value = getattr(self, field_name)
            if not isinstance(value, NotComputedPredictiveValue):
                raise CrisprContractError(
                    f"{field_name} must be an explicit not-computed record"
                )
            if (
                value.value is not None
                or value.evidence_status is not EvidenceStatus.NOT_COMPUTED
            ):
                raise CrisprContractError(
                    f"{field_name} must remain explicitly not_computed"
                )
        if not isinstance(self.warnings, tuple) or not all(
            isinstance(warning, CandidateWarning) for warning in self.warnings
        ):
            raise CrisprContractError("warnings must be a tuple of CandidateWarning")
        expected_triggers = tuple(warning.code.value for warning in self.warnings)
        if self.review_trigger_ids != expected_triggers:
            raise CrisprContractError("review triggers must exactly match candidate warnings")
        expected_state = ReviewState.REVIEW_REQUIRED if self.warnings else None
        if self.review_state is not expected_state:
            raise CrisprContractError("review_state does not match candidate warnings")


@dataclass(frozen=True, slots=True)
class ScannerProvenance:
    scanner: AlgorithmIdentity
    warning_rules: tuple[AlgorithmIdentity, ...]
    target_sequence_sha256: str
    configuration_sha256: str
    request_sha256: str
    output_sha256: str
    computation_mode: ComputationMode
    computation_status: ComputationStatus

    def __post_init__(self) -> None:
        if self.computation_mode is not ComputationMode.LOCAL:
            raise CrisprContractError("production scanner computation_mode must be local")
        if self.computation_status is not ComputationStatus.COMPLETED:
            raise CrisprContractError("scanner result must be completed")
        for field_name in (
            "target_sequence_sha256",
            "configuration_sha256",
            "request_sha256",
            "output_sha256",
        ):
            value = getattr(self, field_name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise CrisprContractError(f"{field_name} must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class CrisprScannerResultV1:
    schema_name: str
    schema_version: str
    target: CrisprTargetSequence
    configuration: SpCas9Configuration
    candidates: tuple[SpCas9CandidateGuide, ...]
    provenance: ScannerProvenance

    def __post_init__(self) -> None:
        if self.schema_name != CRISPR_V1_SCHEMA_NAME:
            raise CrisprContractError("unexpected CRISPR scanner schema_name")
        if self.schema_version != CRISPR_V1_SCHEMA_VERSION:
            raise CrisprContractError("unexpected CRISPR scanner schema_version")
        if self.provenance.target_sequence_sha256 != self.target.sequence_sha256:
            raise CrisprContractError("provenance target hash does not match target")
        if (
            self.provenance.configuration_sha256
            != self.configuration.configuration_sha256
        ):
            raise CrisprContractError("provenance configuration hash does not match")


__all__ = [
    "AlgorithmIdentity",
    "COORDINATE_SYSTEM_ID",
    "CRISPR_V1_SCHEMA_NAME",
    "CRISPR_V1_SCHEMA_VERSION",
    "CandidateWarning",
    "CandidateWarningCode",
    "ComputationMode",
    "ComputationStatus",
    "CrisprContractError",
    "CrisprScannerResultV1",
    "CrisprStrand",
    "CrisprTargetSequence",
    "EvidenceStatus",
    "NotComputedPredictiveValue",
    "ORDERING_RULE_ID",
    "PamContext",
    "ReviewState",
    "SCANNER_ALGORITHM_ID",
    "SCANNER_ALGORITHM_VERSION",
    "SPCAS9_PROFILE_ID",
    "ScannerProvenance",
    "SpCas9CandidateGuide",
    "SpCas9Configuration",
    "canonical_sha256",
    "sha256_text",
]
