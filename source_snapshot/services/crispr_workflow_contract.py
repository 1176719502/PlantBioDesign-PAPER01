"""Versioned, persistence-independent CRISPR V1 aggregate workflow contract.

This module composes the adopted deterministic scanner and Cas-OFFinder adapter.
It owns identity binding, coordinate scope, explicit state, selection integrity,
freshness, and deterministic JSON serialization; it does not implement science.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

from services.cas_offinder_adapter import (
    BULGE_POLICY,
    CAS_OFFINDER_CPU_MODE,
    CAS_OFFINDER_ENGINE,
    CAS_OFFINDER_TAG_COMMIT,
    CAS_OFFINDER_VERSION,
    OPENCL_RUNTIME_REQUIRED,
    SPCAS9_PATTERN,
    CasOffinderExecutableIdentity,
    CasOffinderRequest,
    CasOffinderRunResult,
    EnumeratedOffTargetHit,
    OffTargetComputationStatus,
    build_cas_offinder_input,
    canonical_result_sha256,
    parse_cas_offinder_v241_output,
    run_cas_offinder,
)
from services.crispr_reference_contract import (
    InstalledReferenceIdentity,
    ReferenceFastaFile,
)
from services.crispr_v1_contract import (
    AlgorithmIdentity,
    COORDINATE_SYSTEM_ID,
    CrisprContractError,
    CrisprScannerResultV1,
    CrisprStrand,
    CrisprTargetSequence,
    EvidenceStatus,
    PamContext,
    ReviewState,
    SCANNER_ALGORITHM_ID,
    SCANNER_ALGORITHM_VERSION,
    SpCas9CandidateGuide,
    SpCas9Configuration,
    canonical_sha256,
    sha256_text,
)
from services.spcas9_candidate_scanner import scan_spcas9_candidates


WORKFLOW_SCHEMA_NAME = "CrisprV1AggregateWorkflow"
WORKFLOW_SCHEMA_VERSION = "1.0.0"
INTERVAL_SEMANTICS = "zero_based_half_open"


class CrisprWorkflowContractError(ValueError):
    """Raised when aggregate workflow identity or state invariants fail."""


class CoordinateOrigin(StrEnum):
    TARGET_LOCAL = "target_sequence_local"
    REFERENCE_CONTIG = "reference_contig"


class WorkflowState(StrEnum):
    NOT_RUN = "not_run"
    COMPUTED = "computed"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


_ADAPTER_STATE_COMPATIBILITY: dict[OffTargetComputationStatus, WorkflowState] = {
    OffTargetComputationStatus.NOT_COMPUTED: WorkflowState.NOT_RUN,
    OffTargetComputationStatus.COMPUTED: WorkflowState.COMPUTED,
    OffTargetComputationStatus.UNAVAILABLE: WorkflowState.UNAVAILABLE,
    OffTargetComputationStatus.EXECUTION_FAILED: WorkflowState.FAILED,
    OffTargetComputationStatus.PARSE_FAILED: WorkflowState.FAILED,
}


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CrisprWorkflowContractError(f"{name} must be a non-empty string")


def _require_sha256(name: str, value: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise CrisprWorkflowContractError(f"{name} must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class CrisprReferenceBinding:
    """Exact installed-reference identity used by one workflow."""

    reference: InstalledReferenceIdentity
    identity_sha256: str
    assembly_accession: str
    assembly_version: str

    @classmethod
    def from_reference(cls, reference: InstalledReferenceIdentity) -> "CrisprReferenceBinding":
        if not isinstance(reference, InstalledReferenceIdentity):
            raise CrisprWorkflowContractError(
                "reference must be an InstalledReferenceIdentity"
            )
        return cls(
            reference=reference,
            identity_sha256=reference.identity_sha256,
            assembly_accession=reference.assembly_accession,
            assembly_version=reference.assembly_version,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.reference, InstalledReferenceIdentity):
            raise CrisprWorkflowContractError("reference binding must be typed")
        _require_sha256("identity_sha256", self.identity_sha256)
        _require_text("assembly_accession", self.assembly_accession)
        _require_text("assembly_version", self.assembly_version)
        if self.identity_sha256 != self.reference.identity_sha256:
            raise CrisprWorkflowContractError(
                "reference binding hash does not match installed reference"
            )
        if self.assembly_accession != self.reference.assembly_accession:
            raise CrisprWorkflowContractError("reference accession binding is stale")
        if self.assembly_version != self.reference.assembly_version:
            raise CrisprWorkflowContractError("reference version binding is stale")


@dataclass(frozen=True, slots=True)
class TargetCoordinateOrigin:
    """Declares whether scanner-local coordinates map to a contig interval."""

    origin: CoordinateOrigin
    contig: str
    offset: int | None
    interval_semantics: str = INTERVAL_SEMANTICS

    def __post_init__(self) -> None:
        if not isinstance(self.origin, CoordinateOrigin):
            raise CrisprWorkflowContractError("origin must be typed")
        _require_text("contig", self.contig)
        if self.offset is not None and (
            not isinstance(self.offset, int) or isinstance(self.offset, bool) or self.offset < 0
        ):
            raise CrisprWorkflowContractError("offset must be a non-negative integer")
        if self.interval_semantics != INTERVAL_SEMANTICS:
            raise CrisprWorkflowContractError("only zero-based half-open intervals are supported")
        if self.origin is CoordinateOrigin.REFERENCE_CONTIG and self.offset is None:
            raise CrisprWorkflowContractError(
                "reference-contig origin requires an explicit forward-reference offset"
            )
        if self.origin is CoordinateOrigin.TARGET_LOCAL and self.offset is not None:
            raise CrisprWorkflowContractError(
                "target-local origin must not claim a whole-contig offset"
            )

    def interval_for(self, start: int, end: int) -> tuple[int, int] | None:
        if self.origin is CoordinateOrigin.TARGET_LOCAL:
            return None
        assert self.offset is not None
        return (self.offset + start, self.offset + end)


@dataclass(frozen=True, slots=True)
class CrisprExecutionIntent:
    """User/configuration intent; no ranking or recommendation is represented."""

    scan_requested: bool = True
    off_target_requested: bool = False
    maximum_mismatches: int = 4
    timeout_seconds: float = 120.0
    executable_path: str | None = None
    expected_executable_sha256: str | None = None
    observed_executable_path: str | None = None
    observed_executable_sha256: str | None = None
    observed_engine_banner: str | None = None
    observed_engine: str | None = None
    observed_engine_version: str | None = None
    observed_runtime_mode: str | None = None

    def __post_init__(self) -> None:
        for name in ("scan_requested", "off_target_requested"):
            if not isinstance(getattr(self, name), bool):
                raise CrisprWorkflowContractError(f"{name} must be boolean")
        if (
            not isinstance(self.maximum_mismatches, int)
            or isinstance(self.maximum_mismatches, bool)
            or not 0 <= self.maximum_mismatches <= 20
        ):
            raise CrisprWorkflowContractError("maximum_mismatches must be an integer in 0..20")
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise CrisprWorkflowContractError("timeout_seconds must be a positive finite number")
        if self.executable_path is not None:
            _require_text("executable_path", self.executable_path)
        if self.expected_executable_sha256 is not None:
            _require_sha256(
                "expected_executable_sha256",
                self.expected_executable_sha256,
            )
        observed = (
            self.observed_executable_path,
            self.observed_executable_sha256,
            self.observed_engine_banner,
            self.observed_engine,
            self.observed_engine_version,
        )
        if any(value is not None for value in observed) and not all(
            value is not None for value in observed
        ):
            raise CrisprWorkflowContractError(
                "observed executable identity must be complete when supplied"
            )
        if self.observed_executable_path is not None:
            _require_text("observed_executable_path", self.observed_executable_path)
            _require_sha256("observed_executable_sha256", self.observed_executable_sha256)
            _require_text("observed_engine_banner", self.observed_engine_banner)
            _require_text("observed_engine", self.observed_engine)
            _require_text("observed_engine_version", self.observed_engine_version)
        if self.observed_runtime_mode is not None:
            _require_text("observed_runtime_mode", self.observed_runtime_mode)
            if self.observed_executable_path is None:
                raise CrisprWorkflowContractError(
                    "observed runtime mode requires observed executable identity"
                )


@dataclass(frozen=True, slots=True)
class CrisprWorkflowInput:
    schema_name: str
    schema_version: str
    target: CrisprTargetSequence
    reference_binding: CrisprReferenceBinding
    coordinate_origin: TargetCoordinateOrigin
    configuration: SpCas9Configuration
    execution_intent: CrisprExecutionIntent

    @classmethod
    def create(
        cls,
        *,
        target: CrisprTargetSequence,
        reference: InstalledReferenceIdentity,
        coordinate_origin: TargetCoordinateOrigin,
        configuration: SpCas9Configuration | None = None,
        execution_intent: CrisprExecutionIntent | None = None,
    ) -> "CrisprWorkflowInput":
        return cls(
            schema_name=WORKFLOW_SCHEMA_NAME,
            schema_version=WORKFLOW_SCHEMA_VERSION,
            target=target,
            reference_binding=CrisprReferenceBinding.from_reference(reference),
            coordinate_origin=coordinate_origin,
            configuration=configuration or SpCas9Configuration(),
            execution_intent=execution_intent or CrisprExecutionIntent(),
        )

    def __post_init__(self) -> None:
        if self.schema_name != WORKFLOW_SCHEMA_NAME or self.schema_version != WORKFLOW_SCHEMA_VERSION:
            raise CrisprWorkflowContractError("unexpected workflow schema identity")
        if not isinstance(self.target, CrisprTargetSequence):
            raise CrisprWorkflowContractError("target must be typed")
        if not isinstance(self.reference_binding, CrisprReferenceBinding):
            raise CrisprWorkflowContractError("reference_binding must be typed")
        if not isinstance(self.coordinate_origin, TargetCoordinateOrigin):
            raise CrisprWorkflowContractError("coordinate_origin must be typed")
        if self.coordinate_origin.contig != self.target.contig:
            raise CrisprWorkflowContractError("target and coordinate origin contig differ")
        if self.target.contig not in self.reference_binding.reference.contig_to_relative_path:
            raise CrisprWorkflowContractError("target contig is absent from exact reference manifest")
        if not isinstance(self.configuration, SpCas9Configuration):
            raise CrisprWorkflowContractError("configuration must be typed")
        if not isinstance(self.execution_intent, CrisprExecutionIntent):
            raise CrisprWorkflowContractError("execution_intent must be typed")

    @property
    def source_hash(self) -> str:
        return canonical_sha256(
            {
                "target_id": self.target.target_id,
                "target_sequence_sha256": self.target.sequence_sha256,
                "target_contig": self.target.contig,
                "reference_pack_id": self.target.reference_pack_id,
                "coordinate_origin": self.coordinate_origin.origin.value,
                "coordinate_offset": self.coordinate_origin.offset,
                "interval_semantics": self.coordinate_origin.interval_semantics,
            }
        )

    @property
    def configuration_hash(self) -> str:
        return canonical_sha256(
            {
                "configuration_sha256": self.configuration.configuration_sha256,
                "scanner_algorithm_id": SCANNER_ALGORITHM_ID,
                "scanner_algorithm_version": SCANNER_ALGORITHM_VERSION,
                "off_target_engine": CAS_OFFINDER_ENGINE,
                "off_target_engine_version": CAS_OFFINDER_VERSION,
                "off_target_engine_tag_commit": CAS_OFFINDER_TAG_COMMIT,
                "off_target_cpu_mode": CAS_OFFINDER_CPU_MODE,
                "off_target_opencl_runtime_required": OPENCL_RUNTIME_REQUIRED,
                "off_target_pattern": SPCAS9_PATTERN,
                "off_target_bulge_policy": BULGE_POLICY,
                "executable_path": self.execution_intent.executable_path,
                "expected_executable_sha256": self.execution_intent.expected_executable_sha256,
                "observed_executable_path": self.execution_intent.observed_executable_path,
                "observed_executable_sha256": self.execution_intent.observed_executable_sha256,
                "observed_engine_banner": self.execution_intent.observed_engine_banner,
                "observed_engine": self.execution_intent.observed_engine,
                "observed_engine_version": self.execution_intent.observed_engine_version,
                "observed_runtime_mode": self.execution_intent.observed_runtime_mode,
                "maximum_mismatches": self.execution_intent.maximum_mismatches,
                "off_target_requested": self.execution_intent.off_target_requested,
                "scan_requested": self.execution_intent.scan_requested,
                "timeout_seconds": self.execution_intent.timeout_seconds,
            }
        )

    @property
    def reference_hash(self) -> str:
        return self.reference_binding.identity_sha256

    @property
    def freshness_hash(self) -> str:
        return canonical_sha256(
            {
                "configuration_hash": self.configuration_hash,
                "reference_hash": self.reference_hash,
                "source_hash": self.source_hash,
            }
        )

    @property
    def workflow_id(self) -> str:
        return f"crispr-workflow-{self.freshness_hash[:24]}"


@dataclass(frozen=True, slots=True)
class CandidateProvenanceReference:
    target_sequence_sha256: str
    reference_identity_sha256: str
    configuration_sha256: str
    scanner_output_sha256: str
    coordinate_system: str = COORDINATE_SYSTEM_ID

    def __post_init__(self) -> None:
        for name in (
            "target_sequence_sha256",
            "reference_identity_sha256",
            "configuration_sha256",
            "scanner_output_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        if self.coordinate_system != COORDINATE_SYSTEM_ID:
            raise CrisprWorkflowContractError("candidate coordinate convention is not SpCas9 V1")


@dataclass(frozen=True, slots=True)
class CrisprCandidateRecord:
    candidate_id: str
    guide_sequence: str
    pam: str
    strand: CrisprStrand
    spacer_start: int
    spacer_end: int
    pam_start: int
    pam_end: int
    coordinate_convention: str
    interval_semantics: str
    off_target_state: WorkflowState
    provenance: CandidateProvenanceReference
    _guide: SpCas9CandidateGuide

    def __post_init__(self) -> None:
        _require_text("candidate_id", self.candidate_id)
        if not isinstance(self.strand, CrisprStrand):
            raise CrisprWorkflowContractError("candidate strand must be typed")
        if len(self.guide_sequence) != 20 or any(base not in "ACGT" for base in self.guide_sequence):
            raise CrisprWorkflowContractError("candidate guide_sequence must be 20 uppercase bases")
        if len(self.pam) != 3 or self.pam[1:] != "GG":
            raise CrisprWorkflowContractError("candidate PAM must be an observed NGG")
        for name, value in (
            ("spacer_start", self.spacer_start),
            ("spacer_end", self.spacer_end),
            ("pam_start", self.pam_start),
            ("pam_end", self.pam_end),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise CrisprWorkflowContractError(f"{name} must be non-negative")
        if self.spacer_end - self.spacer_start != 20 or self.pam_end - self.pam_start != 3:
            raise CrisprWorkflowContractError("candidate intervals have invalid spans")
        if self.coordinate_convention != COORDINATE_SYSTEM_ID:
            raise CrisprWorkflowContractError("candidate coordinate convention is not SpCas9 V1")
        if self.interval_semantics != INTERVAL_SEMANTICS:
            raise CrisprWorkflowContractError("candidate interval semantics are not half-open")
        if not isinstance(self.off_target_state, WorkflowState):
            raise CrisprWorkflowContractError("candidate off-target state must be typed")
        if not isinstance(self.provenance, CandidateProvenanceReference):
            raise CrisprWorkflowContractError("candidate provenance must be typed")
        if not isinstance(self._guide, SpCas9CandidateGuide):
            raise CrisprWorkflowContractError("candidate source guide must be typed")
        if (
            self._guide.guide_id != self.candidate_id
            or self._guide.spacer != self.guide_sequence
            or self._guide.pam_context.pam != self.pam
            or self._guide.strand is not self.strand
            or self._guide.spacer_start != self.spacer_start
            or self._guide.spacer_end != self.spacer_end
            or self._guide.pam_context.pam_start != self.pam_start
            or self._guide.pam_context.pam_end != self.pam_end
        ):
            raise CrisprWorkflowContractError("candidate projection does not match scanner guide")


@dataclass(frozen=True, slots=True)
class CrisprSelection:
    candidate_id: str
    candidate: CrisprCandidateRecord
    workflow_id: str
    scanner_output_sha256: str
    reference_identity_sha256: str
    configuration_sha256: str

    def __post_init__(self) -> None:
        if self.candidate_id != self.candidate.candidate_id:
            raise CrisprWorkflowContractError("selection candidate ID does not match candidate")
        if self.workflow_id.startswith("crispr-workflow-") is False:
            raise CrisprWorkflowContractError("selection workflow_id is malformed")
        for name in ("scanner_output_sha256", "reference_identity_sha256", "configuration_sha256"):
            _require_sha256(name, getattr(self, name))
        if self.candidate.provenance.scanner_output_sha256 != self.scanner_output_sha256:
            raise CrisprWorkflowContractError("selection scanner provenance is stale")
        if self.candidate.provenance.reference_identity_sha256 != self.reference_identity_sha256:
            raise CrisprWorkflowContractError("selection reference provenance is stale")
        if self.candidate.provenance.configuration_sha256 != self.configuration_sha256:
            raise CrisprWorkflowContractError("selection configuration provenance is stale")


@dataclass(frozen=True, slots=True)
class CrisprScanEnvelope:
    state: WorkflowState
    candidates: tuple[CrisprCandidateRecord, ...]
    scanner_output_sha256: str | None
    freshness_hash: str
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.state is WorkflowState.COMPUTED:
            if self.scanner_output_sha256 is None:
                raise CrisprWorkflowContractError("computed scan requires output identity")
            if self.error_message is not None:
                raise CrisprWorkflowContractError("computed scan cannot carry an error")
        elif self.candidates:
            raise CrisprWorkflowContractError("non-computed scan cannot expose candidates")
        if self.scanner_output_sha256 is not None:
            _require_sha256("scanner_output_sha256", self.scanner_output_sha256)
        _require_sha256("freshness_hash", self.freshness_hash)


@dataclass(frozen=True, slots=True)
class CrisprOffTargetEnvelope:
    state: WorkflowState
    adapter_status: OffTargetComputationStatus
    request: CasOffinderRequest
    hits: tuple[EnumeratedOffTargetHit, ...]
    hit_count: int | None
    freshness_hash: str
    input_sha256: str
    output_sha256: str | None
    executable: CasOffinderExecutableIdentity | None
    invocation: tuple[str, ...] | None
    raw_output_text: str | None
    stdout: str
    stderr: str
    error_code: str | None
    error_message: str | None

    @property
    def result_sha256(self) -> str | None:
        if self.state is WorkflowState.COMPUTED:
            return canonical_result_sha256(self.request, self.hits)
        return None

    def __post_init__(self) -> None:
        if not isinstance(self.adapter_status, OffTargetComputationStatus):
            raise CrisprWorkflowContractError("adapter_status must be typed")
        _require_sha256("freshness_hash", self.freshness_hash)
        _require_sha256("input_sha256", self.input_sha256)
        if self.input_sha256 != build_cas_offinder_input(self.request)[1]:
            raise CrisprWorkflowContractError("off-target input identity is stale")
        if self.output_sha256 is not None:
            _require_sha256("output_sha256", self.output_sha256)
        if self.raw_output_text is None:
            if self.output_sha256 is not None:
                raise CrisprWorkflowContractError("off-target output hash requires raw output")
        elif self.output_sha256 != sha256_text(self.raw_output_text):
            raise CrisprWorkflowContractError("off-target output identity is stale")
        expected_state = _ADAPTER_STATE_COMPATIBILITY[self.adapter_status]
        if self.state is not expected_state:
            raise CrisprWorkflowContractError(
                "aggregate state is incompatible with adapter status"
            )
        if self.state is WorkflowState.COMPUTED:
            if self.hit_count != len(self.hits):
                raise CrisprWorkflowContractError("computed hit_count must include zero hits")
            expected_result_sha256 = canonical_result_sha256(self.request, self.hits)
            if any(hit.result_sha256 != expected_result_sha256 for hit in self.hits):
                raise CrisprWorkflowContractError(
                    "off-target hits do not share the canonical normalized result identity"
                )
        elif self.hits or self.hit_count is not None:
            raise CrisprWorkflowContractError("non-computed off-target state cannot expose hits")


@dataclass(frozen=True, slots=True)
class CrisprWorkflowResult:
    workflow_input: CrisprWorkflowInput
    workflow_id: str
    scan: CrisprScanEnvelope
    selection: CrisprSelection | None
    off_target: CrisprOffTargetEnvelope | None

    def __post_init__(self) -> None:
        if self.workflow_id != self.workflow_input.workflow_id:
            raise CrisprWorkflowContractError("workflow_id is stale for workflow input")
        if self.scan.freshness_hash != self.workflow_input.freshness_hash:
            raise CrisprWorkflowContractError("scan freshness does not match workflow input")
        _verify_off_target_semantic_consistency(self)
        if len({item.candidate_id for item in self.scan.candidates}) != len(self.scan.candidates):
            raise CrisprWorkflowContractError("scan candidate IDs must be unique")
        for candidate in self.scan.candidates:
            provenance = candidate.provenance
            if provenance.target_sequence_sha256 != self.workflow_input.target.sequence_sha256:
                raise CrisprWorkflowContractError("candidate target provenance is stale")
            if provenance.reference_identity_sha256 != self.workflow_input.reference_hash:
                raise CrisprWorkflowContractError("candidate reference provenance is stale")
            if (
                provenance.configuration_sha256
                != self.workflow_input.configuration.configuration_sha256
            ):
                raise CrisprWorkflowContractError("candidate configuration provenance is stale")
            if provenance.scanner_output_sha256 != self.scan.scanner_output_sha256:
                raise CrisprWorkflowContractError("candidate scanner provenance is stale")
            if (
                candidate._guide.target_id != self.workflow_input.target.target_id
                or candidate._guide.reference_pack_id
                != self.workflow_input.target.reference_pack_id
                or candidate._guide.contig != self.workflow_input.target.contig
            ):
                raise CrisprWorkflowContractError("candidate guide belongs to another target")
        if self.selection is not None:
            if self.scan.state is not WorkflowState.COMPUTED:
                raise CrisprWorkflowContractError("selection requires a computed scan")
            if self.selection.workflow_id != self.workflow_id:
                raise CrisprWorkflowContractError("selection belongs to another workflow result")
            if self.selection.reference_identity_sha256 != self.workflow_input.reference_hash:
                raise CrisprWorkflowContractError("selection belongs to another reference")
            if (
                self.selection.configuration_sha256
                != self.workflow_input.configuration.configuration_sha256
            ):
                raise CrisprWorkflowContractError("selection belongs to another configuration")
            matching_candidate = next(
                (item for item in self.scan.candidates if item.candidate_id == self.selection.candidate_id),
                None,
            )
            if matching_candidate is None:
                raise CrisprWorkflowContractError("selection candidate is absent from this scan result")
            if matching_candidate != self.selection.candidate:
                raise CrisprWorkflowContractError("selection candidate is not the exact candidate in this result")
        if self.off_target is not None:
            if self.selection is None:
                raise CrisprWorkflowContractError("off-target result requires an explicit selection")
            if not self.workflow_input.execution_intent.off_target_requested:
                raise CrisprWorkflowContractError(
                    "off-target result requires executable-backed off-target intent"
                )
            if self.off_target.freshness_hash != self.workflow_input.freshness_hash:
                raise CrisprWorkflowContractError("off-target result is stale")
            if self.off_target.request.guide_id != self.selection.candidate_id:
                raise CrisprWorkflowContractError("off-target request guide is not the selected candidate")
            if self.off_target.request.spacer != self.selection.candidate.guide_sequence:
                raise CrisprWorkflowContractError("off-target request spacer is not the selected candidate")
            if self.off_target.request.reference.identity_sha256 != self.workflow_input.reference_hash:
                raise CrisprWorkflowContractError("off-target request reference is not the workflow reference")
            if self.selection.candidate.off_target_state is not self.off_target.state:
                raise CrisprWorkflowContractError("selected candidate off-target state is inconsistent")
            observed = self.workflow_input.execution_intent
            if self.off_target.executable is not None:
                evidence = self.off_target.executable
                invoked_executable_path = (
                    self.off_target.invocation[0]
                    if self.off_target.invocation is not None
                    and len(self.off_target.invocation) >= 1
                    else None
                )
                if (
                    observed.observed_executable_path != evidence.resolved_path
                    or observed.observed_executable_sha256 != evidence.sha256
                    or observed.observed_engine_banner != evidence.observed_banner
                    or observed.observed_engine != CAS_OFFINDER_ENGINE
                    or observed.observed_engine_version != CAS_OFFINDER_VERSION
                    or evidence.resolved_path != invoked_executable_path
                ):
                    raise CrisprWorkflowContractError(
                        "observed executable identity does not match adapter evidence"
                    )
                evidence_runtime_mode = (
                    self.off_target.invocation[2]
                    if self.off_target.invocation is not None
                    and len(self.off_target.invocation) >= 3
                    else None
                )
                if (
                    observed.observed_runtime_mode != evidence_runtime_mode
                    or evidence_runtime_mode != CAS_OFFINDER_CPU_MODE
                ):
                    raise CrisprWorkflowContractError(
                        "observed runtime mode does not match adapter evidence"
                    )
            elif any(
                value is not None
                for value in (
                    observed.observed_executable_path,
                    observed.observed_executable_sha256,
                    observed.observed_engine_banner,
                    observed.observed_engine,
                    observed.observed_engine_version,
                    observed.observed_runtime_mode,
                )
            ):
                raise CrisprWorkflowContractError(
                    "observed executable identity has no adapter evidence"
                )

    def is_fresh_against(self, workflow_input: CrisprWorkflowInput) -> bool:
        return self.workflow_id == workflow_input.workflow_id

    def is_off_target_fresh_against(
        self,
        workflow_input: CrisprWorkflowInput,
        *,
        executable_sha256: str | None,
    ) -> bool:
        if not self.is_fresh_against(workflow_input):
            return False
        if self.off_target is None or self.off_target.executable is None:
            return self.off_target is None
        if executable_sha256 is None:
            return False
        _require_sha256("executable_sha256", executable_sha256)
        return self.off_target.executable.sha256 == executable_sha256

    @property
    def off_target_state(self) -> WorkflowState:
        return WorkflowState.NOT_RUN if self.off_target is None else self.off_target.state


def _verify_off_target_semantic_consistency(result: CrisprWorkflowResult) -> None:
    """Reject retained executable-backed state when off-target intent is false."""
    intent = result.workflow_input.execution_intent
    if intent.off_target_requested:
        return
    executable_intent = (
        intent.executable_path,
        intent.expected_executable_sha256,
        intent.observed_executable_path,
        intent.observed_executable_sha256,
        intent.observed_engine_banner,
        intent.observed_engine,
        intent.observed_engine_version,
        intent.observed_runtime_mode,
    )
    has_off_target_candidate_state = any(
        candidate.off_target_state is not WorkflowState.NOT_RUN
        for candidate in result.scan.candidates
    )
    if (
        any(value is not None for value in executable_intent)
        or result.off_target is not None
        or has_off_target_candidate_state
    ):
        raise CrisprWorkflowContractError(
            "off-target semantic consistency requires off_target_requested=false "
            "to have no retained off-target execution state"
        )


def _candidate_projection(
    guide: SpCas9CandidateGuide,
    *,
    input_record: CrisprWorkflowInput,
    scanner_output_sha256: str,
) -> CrisprCandidateRecord:
    return CrisprCandidateRecord(
        candidate_id=guide.guide_id,
        guide_sequence=guide.spacer,
        pam=guide.pam_context.pam,
        strand=guide.strand,
        spacer_start=guide.spacer_start,
        spacer_end=guide.spacer_end,
        pam_start=guide.pam_context.pam_start,
        pam_end=guide.pam_context.pam_end,
        coordinate_convention=COORDINATE_SYSTEM_ID,
        interval_semantics=INTERVAL_SEMANTICS,
        off_target_state=WorkflowState.NOT_RUN,
        provenance=CandidateProvenanceReference(
            target_sequence_sha256=input_record.target.sequence_sha256,
            reference_identity_sha256=input_record.reference_hash,
            configuration_sha256=input_record.configuration.configuration_sha256,
            scanner_output_sha256=scanner_output_sha256,
        ),
        _guide=guide,
    )


def _failed_scan(input_record: CrisprWorkflowInput, message: str) -> CrisprScanEnvelope:
    return CrisprScanEnvelope(
        state=WorkflowState.FAILED,
        candidates=(),
        scanner_output_sha256=None,
        freshness_hash=input_record.freshness_hash,
        error_message=message,
    )


def compute_workflow(
    workflow_input: CrisprWorkflowInput,
    *,
    scanner: Callable[[CrisprTargetSequence, SpCas9Configuration], CrisprScannerResultV1]
    | None = None,
) -> CrisprWorkflowResult:
    """Run only the adopted scanner and return an explicit aggregate state."""
    if not isinstance(workflow_input, CrisprWorkflowInput):
        raise TypeError("workflow_input must be a CrisprWorkflowInput")
    if not workflow_input.execution_intent.scan_requested:
        scan = CrisprScanEnvelope(
            state=WorkflowState.NOT_RUN,
            candidates=(),
            scanner_output_sha256=None,
            freshness_hash=workflow_input.freshness_hash,
        )
    else:
        scan_fn = scanner or scan_spcas9_candidates
        try:
            scanner_result = scan_fn(workflow_input.target, workflow_input.configuration)
            if not isinstance(scanner_result, CrisprScannerResultV1):
                raise CrisprWorkflowContractError("scanner did not return CrisprScannerResultV1")
            if scanner_result.target != workflow_input.target:
                raise CrisprWorkflowContractError("scanner result target is not the workflow target")
            if scanner_result.configuration != workflow_input.configuration:
                raise CrisprWorkflowContractError("scanner result configuration is stale")
            candidates = tuple(
                _candidate_projection(
                    candidate,
                    input_record=workflow_input,
                    scanner_output_sha256=scanner_result.provenance.output_sha256,
                )
                for candidate in scanner_result.candidates
            )
            scan = CrisprScanEnvelope(
                state=WorkflowState.COMPUTED,
                candidates=candidates,
                scanner_output_sha256=scanner_result.provenance.output_sha256,
                freshness_hash=workflow_input.freshness_hash,
            )
        except (CrisprContractError, CrisprWorkflowContractError, TypeError, ValueError) as error:
            scan = _failed_scan(workflow_input, str(error))
    return CrisprWorkflowResult(
        workflow_input=workflow_input,
        workflow_id=workflow_input.workflow_id,
        scan=scan,
        selection=None,
        off_target=None,
    )


def select_candidate(
    result: CrisprWorkflowResult,
    candidate_id: str,
    *,
    current_input: CrisprWorkflowInput | None = None,
) -> CrisprWorkflowResult:
    if current_input is not None and not result.is_fresh_against(current_input):
        raise CrisprWorkflowContractError("cannot select a candidate from a stale workflow result")
    if result.scan.state is not WorkflowState.COMPUTED:
        raise CrisprWorkflowContractError("candidate selection requires a computed scan")
    matched_candidate = next(
        (item for item in result.scan.candidates if item.candidate_id == candidate_id),
        None,
    )
    if matched_candidate is None:
        raise CrisprWorkflowContractError("candidate ID is absent from this workflow result")
    reset_candidates = tuple(
        replace(item, off_target_state=WorkflowState.NOT_RUN)
        for item in result.scan.candidates
    )
    reset_scan = replace(result.scan, candidates=reset_candidates)
    candidate = next(
        item for item in reset_candidates if item.candidate_id == candidate_id
    )
    assert result.scan.scanner_output_sha256 is not None
    selection = CrisprSelection(
        candidate_id=candidate_id,
        candidate=candidate,
        workflow_id=result.workflow_id,
        scanner_output_sha256=result.scan.scanner_output_sha256,
        reference_identity_sha256=result.workflow_input.reference_hash,
        configuration_sha256=result.workflow_input.configuration.configuration_sha256,
    )
    return replace(result, scan=reset_scan, selection=selection, off_target=None)


def _aggregate_state(adapter_status: OffTargetComputationStatus) -> WorkflowState:
    return _ADAPTER_STATE_COMPATIBILITY[adapter_status]


def _rebind_execution_identity(
    result: CrisprWorkflowResult,
    *,
    configured_executable_path: str | None = None,
    observed_executable: CasOffinderExecutableIdentity | None = None,
    observed_runtime_mode: str | None = None,
) -> CrisprWorkflowResult:
    """Return a result whose freshness binds stable executable identity only."""
    intent_updates: dict[str, str | None] = {}
    if configured_executable_path is not None:
        intent_updates["executable_path"] = configured_executable_path
    if observed_executable is not None:
        intent_updates.update(
            {
                "observed_executable_path": observed_executable.resolved_path,
                "observed_executable_sha256": observed_executable.sha256,
                "observed_engine_banner": observed_executable.observed_banner,
                "observed_engine": CAS_OFFINDER_ENGINE,
                "observed_engine_version": CAS_OFFINDER_VERSION,
                "observed_runtime_mode": observed_runtime_mode,
            }
        )
    if not intent_updates:
        return result
    workflow_input = replace(
        result.workflow_input,
        execution_intent=replace(result.workflow_input.execution_intent, **intent_updates),
    )
    if workflow_input == result.workflow_input:
        return result
    scan = replace(result.scan, freshness_hash=workflow_input.freshness_hash)
    selection = None
    if result.selection is not None:
        selection = replace(result.selection, workflow_id=workflow_input.workflow_id)
    off_target = None
    if result.off_target is not None:
        off_target = replace(result.off_target, freshness_hash=workflow_input.freshness_hash)
    return replace(
        result,
        workflow_input=workflow_input,
        workflow_id=workflow_input.workflow_id,
        scan=scan,
        selection=selection,
        off_target=off_target,
    )


def enumerate_off_targets(
    result: CrisprWorkflowResult,
    *,
    current_input: CrisprWorkflowInput | None = None,
    runner: Callable[[CasOffinderRequest], CasOffinderRunResult] | None = None,
    executable_path: str | Path | None = None,
) -> CrisprWorkflowResult:
    """Build a request only from the selected candidate and exact reference."""
    if current_input is not None and not result.is_fresh_against(current_input):
        raise CrisprWorkflowContractError("cannot enumerate off-targets for a stale workflow result")
    if result.selection is None:
        raise CrisprWorkflowContractError("off-target enumeration requires a selected candidate")
    if not result.workflow_input.execution_intent.off_target_requested:
        raise CrisprWorkflowContractError("off-target enumeration was not requested by execution intent")
    if result.scan.state is not WorkflowState.COMPUTED:
        raise CrisprWorkflowContractError("off-target enumeration requires a computed scan")
    selected = result.selection.candidate
    request = CasOffinderRequest(
        guide_id=selected.candidate_id,
        spacer=selected.guide_sequence,
        maximum_mismatches=result.workflow_input.execution_intent.maximum_mismatches,
        reference=result.workflow_input.reference_binding.reference,
    )
    configured_path = executable_path or result.workflow_input.execution_intent.executable_path
    if executable_path is not None:
        result = _rebind_execution_identity(
            result,
            configured_executable_path=str(executable_path),
        )
    if runner is not None:
        run_callable = runner
    else:
        if configured_path is None:
            raise CrisprWorkflowContractError("an executable path or test runner is required")
        result = _rebind_execution_identity(
            result,
            configured_executable_path=str(configured_path),
        )
        run_callable = lambda value: run_cas_offinder(
            value,
            executable_path=configured_path,
            timeout_seconds=result.workflow_input.execution_intent.timeout_seconds,
        )
    try:
        run_result = run_callable(request)
    except OSError as error:
        input_sha256 = build_cas_offinder_input(request)[1]
        envelope = CrisprOffTargetEnvelope(
            state=WorkflowState.FAILED,
            adapter_status=OffTargetComputationStatus.EXECUTION_FAILED,
            request=request,
            hits=(),
            hit_count=None,
            freshness_hash=result.workflow_input.freshness_hash,
            input_sha256=input_sha256,
            output_sha256=None,
            executable=None,
            invocation=None,
            raw_output_text=None,
            stdout="",
            stderr="",
            error_code="ORCHESTRATION_IO_FAILED",
            error_message=str(error),
        )
        updated_candidate = replace(selected, off_target_state=WorkflowState.FAILED)
        updated_scan = replace(
            result.scan,
            candidates=tuple(
                updated_candidate if item.candidate_id == updated_candidate.candidate_id else item
                for item in result.scan.candidates
            ),
        )
        return replace(
            result,
            scan=updated_scan,
            selection=replace(result.selection, candidate=updated_candidate),
            off_target=envelope,
        )
    if not isinstance(run_result, CasOffinderRunResult):
        raise CrisprWorkflowContractError("off-target runner did not return CasOffinderRunResult")
    if run_result.request != request:
        raise CrisprWorkflowContractError("off-target runner returned a cross-reference or stale request")
    for hit in run_result.hits:
        if (
            hit.guide_id != selected.candidate_id
            or hit.reference.identity_sha256 != result.workflow_input.reference_hash
            or hit.query != request.query
            or hit.parameter_identity_sha256 != request.parameter_identity_sha256
            or hit.input_sha256 != run_result.input_sha256
            or hit.result_sha256 != run_result.result_sha256
            or run_result.executable is None
            or hit.executable_sha256 != run_result.executable.sha256
        ):
            raise CrisprWorkflowContractError(
                "off-target hits are not bound to the exact selected candidate, reference, and execution"
            )
    expected_executable = result.workflow_input.execution_intent.expected_executable_sha256
    if (
        expected_executable is not None
        and run_result.executable is not None
        and run_result.executable.sha256 != expected_executable
    ):
        raise CrisprWorkflowContractError("off-target executable identity is stale")
    result = _rebind_execution_identity(
        result,
        observed_executable=run_result.executable,
        observed_runtime_mode=(
            run_result.invocation[2]
            if run_result.invocation is not None and len(run_result.invocation) >= 3
            else None
        ),
    )
    state = _aggregate_state(run_result.status)
    envelope = CrisprOffTargetEnvelope(
        state=state,
        adapter_status=run_result.status,
        request=request,
        hits=run_result.hits,
        hit_count=run_result.hit_count,
        freshness_hash=result.workflow_input.freshness_hash,
        input_sha256=run_result.input_sha256,
        output_sha256=run_result.output_sha256,
        executable=run_result.executable,
        # The adapter retains the exact invocation for debugging.  The
        # persisted aggregate keeps only its stable executable/mode identity.
        invocation=_canonical_invocation(run_result.invocation),
        raw_output_text=run_result.output_text,
        # Run diagnostics are intentionally outside canonical aggregate
        # identity; the adapter run result remains available to callers.
        stdout="",
        stderr="",
        error_code=run_result.error_code,
        error_message=run_result.error_message,
    )
    updated_candidate = replace(selected, off_target_state=state)
    updated_scan = replace(
        result.scan,
        candidates=tuple(
            updated_candidate if item.candidate_id == updated_candidate.candidate_id else item
            for item in result.scan.candidates
        ),
    )
    updated_selection = replace(result.selection, candidate=updated_candidate)
    return replace(
        result,
        scan=updated_scan,
        selection=updated_selection,
        off_target=envelope,
    )


def _reference_to_dict(reference: InstalledReferenceIdentity) -> dict[str, Any]:
    return {
        "organism_scientific_name": reference.organism_scientific_name,
        "taxonomy_id": reference.taxonomy_id,
        "provider": reference.provider,
        "assembly_accession": reference.assembly_accession,
        "assembly_version": reference.assembly_version,
        "fasta_directory": reference.fasta_directory,
        "fasta_files": [
            {"relative_path": item.relative_path, "sha256": item.sha256, "contigs": list(item.contigs)}
            for item in reference.fasta_files
        ],
        "manifest_sha256": reference.manifest_sha256,
        "installation_provenance": reference.installation_provenance,
        "identity_sha256": reference.identity_sha256,
    }


def _reference_from_dict(payload: Mapping[str, Any]) -> InstalledReferenceIdentity:
    files = tuple(
        ReferenceFastaFile(
            relative_path=item["relative_path"],
            sha256=item["sha256"],
            contigs=tuple(item["contigs"]),
        )
        for item in payload["fasta_files"]
    )
    return InstalledReferenceIdentity(
        organism_scientific_name=payload["organism_scientific_name"],
        taxonomy_id=payload["taxonomy_id"],
        provider=payload["provider"],
        assembly_accession=payload["assembly_accession"],
        assembly_version=payload["assembly_version"],
        fasta_directory=payload["fasta_directory"],
        fasta_files=files,
        manifest_sha256=payload["manifest_sha256"],
        installation_provenance=payload["installation_provenance"],
        identity_sha256=payload["identity_sha256"],
    )


def _input_to_dict(value: CrisprWorkflowInput) -> dict[str, Any]:
    return {
        "schema_name": value.schema_name,
        "schema_version": value.schema_version,
        "target": {
            "target_id": value.target.target_id,
            "display_name": value.target.display_name,
            "reference_pack_id": value.target.reference_pack_id,
            "contig": value.target.contig,
            "sequence": value.target.sequence,
            "sequence_sha256": value.target.sequence_sha256,
        },
        "reference": _reference_to_dict(value.reference_binding.reference),
        "coordinate_origin": {
            "origin": value.coordinate_origin.origin.value,
            "contig": value.coordinate_origin.contig,
            "offset": value.coordinate_origin.offset,
            "interval_semantics": value.coordinate_origin.interval_semantics,
        },
        "configuration": {
            "nuclease_profile_id": value.configuration.nuclease_profile_id,
            "pam_pattern": value.configuration.pam_pattern,
            "spacer_length": value.configuration.spacer_length,
            "strand_policy": value.configuration.strand_policy,
            "coordinate_system": value.configuration.coordinate_system,
            "ordering_rule_id": value.configuration.ordering_rule_id,
        },
        "execution_intent": {
            "scan_requested": value.execution_intent.scan_requested,
            "off_target_requested": value.execution_intent.off_target_requested,
            "maximum_mismatches": value.execution_intent.maximum_mismatches,
            "timeout_seconds": value.execution_intent.timeout_seconds,
            "executable_path": value.execution_intent.executable_path,
            "expected_executable_sha256": value.execution_intent.expected_executable_sha256,
            "observed_executable_path": value.execution_intent.observed_executable_path,
            "observed_executable_sha256": value.execution_intent.observed_executable_sha256,
            "observed_engine_banner": value.execution_intent.observed_engine_banner,
            "observed_engine": value.execution_intent.observed_engine,
            "observed_engine_version": value.execution_intent.observed_engine_version,
            "observed_runtime_mode": value.execution_intent.observed_runtime_mode,
        },
    }


def _candidate_to_dict(value: CrisprCandidateRecord) -> dict[str, Any]:
    return {
        "candidate_id": value.candidate_id,
        "guide_sequence": value.guide_sequence,
        "pam": value.pam,
        "strand": value.strand.value,
        "spacer_start": value.spacer_start,
        "spacer_end": value.spacer_end,
        "pam_start": value.pam_start,
        "pam_end": value.pam_end,
        "coordinate_convention": value.coordinate_convention,
        "interval_semantics": value.interval_semantics,
        "off_target_state": value.off_target_state.value,
        "provenance": {
            "target_sequence_sha256": value.provenance.target_sequence_sha256,
            "reference_identity_sha256": value.provenance.reference_identity_sha256,
            "configuration_sha256": value.provenance.configuration_sha256,
            "scanner_output_sha256": value.provenance.scanner_output_sha256,
            "coordinate_system": value.provenance.coordinate_system,
        },
    }


def _canonical_invocation(invocation: tuple[str, ...] | None) -> tuple[str, ...] | None:
    """Remove per-run input/output paths while retaining executable/mode evidence."""
    if invocation is None:
        return None
    if len(invocation) < 3:
        raise CrisprWorkflowContractError("off-target invocation evidence is incomplete")
    return tuple(
        value if index in (0, 2) else "<temporary-path>"
        for index, value in enumerate(invocation)
    )


def _canonicalize_ephemeral_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize legacy diagnostic projections before canonical comparison."""
    normalized = json.loads(json.dumps(payload))
    off_target = normalized.get("off_target")
    if isinstance(off_target, dict):
        off_target["stdout"] = ""
        off_target["stderr"] = ""
        raw_invocation = off_target.get("invocation")
        if raw_invocation is not None:
            off_target["invocation"] = list(_canonical_invocation(tuple(raw_invocation)))
    return normalized


def to_dict(result: CrisprWorkflowResult) -> dict[str, Any]:
    """Return a deterministic, JSON-compatible aggregate projection."""
    if not isinstance(result, CrisprWorkflowResult):
        raise TypeError("result must be a CrisprWorkflowResult")
    payload: dict[str, Any] = {
        "schema_name": WORKFLOW_SCHEMA_NAME,
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "workflow_id": result.workflow_id,
        "off_target_state": result.off_target_state.value,
        "workflow_input": _input_to_dict(result.workflow_input),
        "scan": {
            "state": result.scan.state.value,
            "candidates": [_candidate_to_dict(item) for item in result.scan.candidates],
            "scanner_output_sha256": result.scan.scanner_output_sha256,
            "freshness_hash": result.scan.freshness_hash,
            "error_message": result.scan.error_message,
        },
        "selection": None
        if result.selection is None
        else {
            "candidate_id": result.selection.candidate_id,
            "candidate": _candidate_to_dict(result.selection.candidate),
            "workflow_id": result.selection.workflow_id,
            "scanner_output_sha256": result.selection.scanner_output_sha256,
            "reference_identity_sha256": result.selection.reference_identity_sha256,
            "configuration_sha256": result.selection.configuration_sha256,
        },
        "off_target": None if result.off_target is None else {
            "state": result.off_target.state.value,
            "adapter_status": result.off_target.adapter_status.value,
            "request": {
                "guide_id": result.off_target.request.guide_id,
                "spacer": result.off_target.request.spacer,
                "maximum_mismatches": result.off_target.request.maximum_mismatches,
                "reference_identity_sha256": result.off_target.request.reference.identity_sha256,
                "parameter_identity_sha256": result.off_target.request.parameter_identity_sha256,
                "engine": CAS_OFFINDER_ENGINE,
                "engine_version": CAS_OFFINDER_VERSION,
                "cpu_mode": CAS_OFFINDER_CPU_MODE,
                "opencl_runtime_required": OPENCL_RUNTIME_REQUIRED,
                "pattern": SPCAS9_PATTERN,
                "bulge_policy": BULGE_POLICY,
                "timeout_seconds": result.workflow_input.execution_intent.timeout_seconds,
            },
            "hits": [
                {
                    "guide_id": hit.guide_id,
                    "contig": hit.contig,
                    "start": hit.start,
                    "end": hit.end,
                    "strand": hit.strand.value,
                    "query": hit.query,
                    "matched_sequence": hit.matched_sequence,
                    "guide_oriented_sequence": hit.guide_oriented_sequence,
                    "mismatch_count": hit.mismatch_count,
                    "raw_engine_position": hit.raw_engine_position,
                    "raw_strand": hit.raw_strand,
                    "raw_row": hit.raw_row,
                    "raw_row_number": hit.raw_row_number,
                    "engine": hit.engine,
                    "engine_version": hit.engine_version,
                    "parameter_identity_sha256": hit.parameter_identity_sha256,
                    "input_sha256": hit.input_sha256,
                    "result_sha256": hit.result_sha256,
                    "executable_sha256": hit.executable_sha256,
                }
                for hit in result.off_target.hits
            ],
            "hit_count": result.off_target.hit_count,
            "result_sha256": result.off_target.result_sha256,
            "freshness_hash": result.off_target.freshness_hash,
            "input_sha256": result.off_target.input_sha256,
            "output_sha256": result.off_target.output_sha256,
            "raw_output_text": result.off_target.raw_output_text,
            "stdout": "",
            "stderr": "",
            "error_code": result.off_target.error_code,
            "error_message": result.off_target.error_message,
            "executable": None if result.off_target.executable is None else {
                "resolved_path": result.off_target.executable.resolved_path,
                "sha256": result.off_target.executable.sha256,
                "observed_banner": result.off_target.executable.observed_banner,
            },
            "invocation": None
            if result.off_target.invocation is None
            else list(_canonical_invocation(result.off_target.invocation)),
        },
    }
    return payload


def to_json(result: CrisprWorkflowResult) -> str:
    return json.dumps(
        to_dict(result),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _candidate_from_dict(
    payload: Mapping[str, Any],
    *,
    input_record: CrisprWorkflowInput,
    scanner_output_sha256: str,
    guides_by_id: Mapping[str, SpCas9CandidateGuide],
) -> CrisprCandidateRecord:
    candidate_id = payload["candidate_id"]
    guide = guides_by_id.get(candidate_id)
    if guide is None:
        raise CrisprWorkflowContractError("serialized candidate is absent from deterministic scan")
    candidate = _candidate_projection(
        guide,
        input_record=input_record,
        scanner_output_sha256=scanner_output_sha256,
    )
    expected = _candidate_to_dict(candidate)
    expected["off_target_state"] = payload["off_target_state"]
    if dict(payload) != expected:
        raise CrisprWorkflowContractError(
            "serialized candidate projection does not match deterministic scanner guide"
        )
    return replace(candidate, off_target_state=WorkflowState(payload["off_target_state"]))


def _verify_trusted_executable_authority(
    result: CrisprWorkflowResult,
    *,
    trusted_executable: CasOffinderExecutableIdentity | None,
) -> None:
    """Bind serialized executable projections to an authority outside the payload."""
    _verify_off_target_semantic_consistency(result)
    intent = result.workflow_input.execution_intent
    off_target = result.off_target
    requires_authority = intent.off_target_requested
    if not requires_authority:
        return
    if not isinstance(trusted_executable, CasOffinderExecutableIdentity):
        raise CrisprWorkflowContractError(
            "trusted executable authority is required for executable verification"
        )
    has_serialized_identity_binding = (
        intent.executable_path is not None
        or intent.expected_executable_sha256 is not None
        or off_target is not None and off_target.executable is not None
    )
    if not has_serialized_identity_binding:
        raise CrisprWorkflowContractError(
            "executable-backed off-target intent requires an executable identity binding"
        )
    if (
        intent.expected_executable_sha256 is not None
        and intent.expected_executable_sha256 != trusted_executable.sha256
    ):
        raise CrisprWorkflowContractError(
            "expected executable SHA-256 does not match trusted executable authority"
        )
    if intent.executable_path is not None and (
        Path(intent.executable_path).expanduser().resolve(strict=False)
        != Path(trusted_executable.resolved_path).expanduser().resolve(strict=False)
    ):
        raise CrisprWorkflowContractError(
            "configured executable path does not match trusted executable authority"
        )
    if off_target is None or off_target.executable is None:
        return
    evidence = off_target.executable
    if evidence != trusted_executable:
        raise CrisprWorkflowContractError(
            "serialized executable evidence does not match trusted executable authority"
        )
    invoked_executable_path = (
        off_target.invocation[0]
        if off_target.invocation is not None and len(off_target.invocation) >= 1
        else None
    )
    if invoked_executable_path != trusted_executable.resolved_path:
        raise CrisprWorkflowContractError(
            "invocation executable path does not match trusted executable authority"
        )


def from_json(
    value: str,
    *,
    trusted_executable: CasOffinderExecutableIdentity | None = None,
) -> CrisprWorkflowResult:
    """Deserialize and verify an aggregate against external executable evidence."""
    try:
        payload = json.loads(value)
        if payload["schema_name"] != WORKFLOW_SCHEMA_NAME or payload["schema_version"] != WORKFLOW_SCHEMA_VERSION:
            raise CrisprWorkflowContractError("unsupported workflow serialization schema")
        raw_input = payload["workflow_input"]
        raw_target = raw_input["target"]
        target = CrisprTargetSequence(
            target_id=raw_target["target_id"],
            display_name=raw_target["display_name"],
            reference_pack_id=raw_target["reference_pack_id"],
            contig=raw_target["contig"],
            sequence=raw_target["sequence"],
            sequence_sha256=raw_target["sequence_sha256"],
        )
        raw_config = raw_input["configuration"]
        workflow_input = CrisprWorkflowInput.create(
            target=target,
            reference=_reference_from_dict(raw_input["reference"]),
            coordinate_origin=TargetCoordinateOrigin(
                origin=CoordinateOrigin(raw_input["coordinate_origin"]["origin"]),
                contig=raw_input["coordinate_origin"]["contig"],
                offset=raw_input["coordinate_origin"]["offset"],
                interval_semantics=raw_input["coordinate_origin"]["interval_semantics"],
            ),
            configuration=SpCas9Configuration(**raw_config),
            execution_intent=CrisprExecutionIntent(**raw_input["execution_intent"]),
        )
        raw_scan = payload["scan"]
        scanner_output_sha256 = raw_scan["scanner_output_sha256"]
        raw_scan_state = WorkflowState(raw_scan["state"])
        if raw_scan_state is WorkflowState.COMPUTED:
            deterministic_scan = scan_spcas9_candidates(
                workflow_input.target,
                workflow_input.configuration,
            )
            if scanner_output_sha256 != deterministic_scan.provenance.output_sha256:
                raise CrisprWorkflowContractError(
                    "serialized scanner output identity does not match deterministic scan"
                )
            guides_by_id = {
                candidate.guide_id: candidate
                for candidate in deterministic_scan.candidates
            }
            candidates = tuple(
                _candidate_from_dict(
                    item,
                    input_record=workflow_input,
                    scanner_output_sha256=scanner_output_sha256,
                    guides_by_id=guides_by_id,
                )
                for item in raw_scan["candidates"]
            )
            if tuple(item.candidate_id for item in candidates) != tuple(guides_by_id):
                raise CrisprWorkflowContractError(
                    "serialized candidate set/order does not match deterministic scan"
                )
        else:
            if scanner_output_sha256 is not None or raw_scan["candidates"]:
                raise CrisprWorkflowContractError(
                    "serialized non-computed scan cannot contain scanner output"
                )
            candidates = ()
        scan = CrisprScanEnvelope(
            state=WorkflowState(raw_scan["state"]),
            candidates=candidates,
            scanner_output_sha256=scanner_output_sha256,
            freshness_hash=raw_scan["freshness_hash"],
            error_message=raw_scan["error_message"],
        )
        raw_selection = payload["selection"]
        selection = None
        if raw_selection is not None:
            selected = next(item for item in candidates if item.candidate_id == raw_selection["candidate_id"])
            if raw_selection["candidate"] != _candidate_to_dict(selected):
                raise CrisprWorkflowContractError(
                    "serialized selection candidate does not match deterministic scan candidate"
                )
            selection = CrisprSelection(
                candidate_id=raw_selection["candidate_id"],
                candidate=selected,
                workflow_id=raw_selection["workflow_id"],
                scanner_output_sha256=raw_selection["scanner_output_sha256"],
                reference_identity_sha256=raw_selection["reference_identity_sha256"],
                configuration_sha256=raw_selection["configuration_sha256"],
            )
        # The adapter's full typed run object is intentionally projected into the
        # immutable aggregate.  Rehydrate requests/hits only when evidence exists.
        off_target = None
        raw_off = payload["off_target"]
        if raw_off is not None:
            if selection is None:
                raise CrisprWorkflowContractError("serialized off-target result has no selection")
            adapter_status = OffTargetComputationStatus(raw_off["adapter_status"])
            if WorkflowState(raw_off["state"]) is not _ADAPTER_STATE_COMPATIBILITY[adapter_status]:
                raise CrisprWorkflowContractError(
                    "serialized aggregate state is incompatible with adapter status"
                )
            request = CasOffinderRequest(
                guide_id=selection.candidate_id,
                spacer=selection.candidate.guide_sequence,
                maximum_mismatches=workflow_input.execution_intent.maximum_mismatches,
                reference=workflow_input.reference_binding.reference,
            )
            raw_request = raw_off["request"]
            expected_request = {
                "guide_id": selection.candidate_id,
                "spacer": selection.candidate.guide_sequence,
                "maximum_mismatches": workflow_input.execution_intent.maximum_mismatches,
                "reference_identity_sha256": workflow_input.reference_hash,
                "parameter_identity_sha256": request.parameter_identity_sha256,
                "engine": CAS_OFFINDER_ENGINE,
                "engine_version": CAS_OFFINDER_VERSION,
                "cpu_mode": CAS_OFFINDER_CPU_MODE,
                "opencl_runtime_required": OPENCL_RUNTIME_REQUIRED,
                "pattern": SPCAS9_PATTERN,
                "bulge_policy": BULGE_POLICY,
                "timeout_seconds": workflow_input.execution_intent.timeout_seconds,
            }
            if raw_request != expected_request:
                raise CrisprWorkflowContractError(
                    "serialized off-target request is inconsistent with authoritative workflow input"
                )
            executable = None if raw_off["executable"] is None else CasOffinderExecutableIdentity(**raw_off["executable"])
            if WorkflowState(raw_off["state"]) is WorkflowState.COMPUTED:
                if executable is None or raw_off["raw_output_text"] is None:
                    raise CrisprWorkflowContractError(
                        "serialized computed result lacks executable or raw output evidence"
                    )
                hits = parse_cas_offinder_v241_output(
                    raw_off["raw_output_text"],
                    request,
                    executable_sha256=executable.sha256,
                    input_sha256=raw_off["input_sha256"],
                )
                expected_hits = raw_off["hits"]
                observed_hits = [
                    {
                        "guide_id": hit.guide_id,
                        "contig": hit.contig,
                        "start": hit.start,
                        "end": hit.end,
                        "strand": hit.strand.value,
                        "query": hit.query,
                        "matched_sequence": hit.matched_sequence,
                        "guide_oriented_sequence": hit.guide_oriented_sequence,
                        "mismatch_count": hit.mismatch_count,
                        "raw_engine_position": hit.raw_engine_position,
                        "raw_strand": hit.raw_strand,
                        "raw_row": hit.raw_row,
                        "raw_row_number": hit.raw_row_number,
                        "engine": hit.engine,
                        "engine_version": hit.engine_version,
                        "parameter_identity_sha256": hit.parameter_identity_sha256,
                        "input_sha256": hit.input_sha256,
                        "result_sha256": hit.result_sha256,
                        "executable_sha256": hit.executable_sha256,
                    }
                    for hit in hits
                ]
                if observed_hits != expected_hits:
                    raise CrisprWorkflowContractError(
                        "serialized normalized hits do not match raw adapter output"
                    )
            else:
                hits = ()
                if raw_off["hits"]:
                    raise CrisprWorkflowContractError(
                        "serialized non-computed result cannot contain hits"
                    )
            expected_result_sha256 = (
                canonical_result_sha256(request, tuple(hits))
                if WorkflowState(raw_off["state"]) is WorkflowState.COMPUTED
                else None
            )
            if raw_off.get("result_sha256") != expected_result_sha256:
                raise CrisprWorkflowContractError(
                    "serialized normalized result identity is not canonical"
                )
            off_target = CrisprOffTargetEnvelope(
                state=WorkflowState(raw_off["state"]),
                adapter_status=adapter_status,
                request=request,
                hits=hits,
                hit_count=raw_off["hit_count"],
                freshness_hash=raw_off["freshness_hash"],
                input_sha256=raw_off["input_sha256"],
                output_sha256=raw_off["output_sha256"],
                executable=executable,
                invocation=(
                    None
                    if raw_off["invocation"] is None
                    else _canonical_invocation(tuple(raw_off["invocation"]))
                ),
                raw_output_text=raw_off["raw_output_text"],
                stdout="",
                stderr="",
                error_code=raw_off["error_code"],
                error_message=raw_off["error_message"],
            )
        result = CrisprWorkflowResult(
            workflow_input=workflow_input,
            workflow_id=payload["workflow_id"],
            scan=scan,
            selection=selection,
            off_target=off_target,
        )
        _verify_trusted_executable_authority(
            result,
            trusted_executable=trusted_executable,
        )
        canonical_payload = json.dumps(
            _canonicalize_ephemeral_payload(payload),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if to_json(result) != canonical_payload:
            raise CrisprWorkflowContractError("serialized workflow is not canonical")
        return result
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, CrisprWorkflowContractError):
            raise
        raise CrisprWorkflowContractError("invalid CRISPR workflow serialization") from error


__all__ = [
    "COORDINATE_SYSTEM_ID",
    "CoordinateOrigin",
    "CrisprCandidateRecord",
    "CrisprExecutionIntent",
    "CrisprOffTargetEnvelope",
    "CrisprReferenceBinding",
    "CrisprScanEnvelope",
    "CrisprSelection",
    "CrisprWorkflowContractError",
    "CrisprWorkflowInput",
    "CrisprWorkflowResult",
    "INTERVAL_SEMANTICS",
    "TargetCoordinateOrigin",
    "WORKFLOW_SCHEMA_NAME",
    "WORKFLOW_SCHEMA_VERSION",
    "WorkflowState",
    "compute_workflow",
    "enumerate_off_targets",
    "from_json",
    "select_candidate",
    "to_dict",
    "to_json",
]
