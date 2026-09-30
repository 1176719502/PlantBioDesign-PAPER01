"""Formal-product integration for the adopted CRISPR V1 aggregate workflow.

This module owns product lifecycle wiring only.  Scanner, reference, adapter,
selection, freshness, and canonical aggregate semantics remain in the adopted
CRISPR core services.
"""
from __future__ import annotations

import hashlib
import csv
from io import StringIO
import json
from dataclasses import replace
from pathlib import Path
import subprocess
from typing import Any, Callable

from services.cas_offinder_adapter import (
    CasOffinderExecutableIdentity,
    CasOffinderRunResult,
)
from services.crispr_reference_contract import (
    InstalledReferenceIdentity,
    ReferenceFastaFile,
    V1_FASTA_SUFFIXES,
)
from services.crispr_v1_contract import (
    CrisprScannerResultV1,
    CrisprTargetSequence,
    SpCas9Configuration,
)
from services.crispr_workflow_contract import (
    CoordinateOrigin,
    CrisprExecutionIntent,
    CrisprWorkflowInput,
    CrisprWorkflowResult,
    WorkflowState,
    TargetCoordinateOrigin,
    compute_workflow,
    enumerate_off_targets,
    from_json,
    select_candidate,
    to_json,
)
from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    require_active_project,
)


CRISPR_PRODUCT_STATE_KEY = "crispr_product_workflow_v1"
CRISPR_PRODUCT_STATE_VERSION = "1.0.0"
OFF_TARGET_TSV_COLUMNS = (
    "workflow_id",
    "selected_candidate_id",
    "guide_sequence",
    "reference_identity_sha256",
    "assembly_accession",
    "assembly_version",
    "contig",
    "start_0_based",
    "end_0_based_exclusive",
    "strand",
    "matched_sequence",
    "guide_oriented_sequence",
    "mismatch_count",
    "raw_engine_position",
    "raw_strand",
    "raw_row_number",
    "engine",
    "engine_version",
    "parameter_identity_sha256",
    "result_sha256",
    "executable_sha256",
)


class CrisprProductWorkflowError(ValueError):
    """Raised when formal product lifecycle wiring cannot be verified."""


def _require_text(name: str, value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise CrisprProductWorkflowError(f"{name} is required")
    return text


def _fasta_contigs(data: bytes) -> tuple[str, ...]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CrisprProductWorkflowError("reference FASTA must be UTF-8 text") from exc
    contigs: list[str] = []
    for line in text.splitlines():
        if not line.startswith(">"):
            continue
        contig = line[1:].strip().split(maxsplit=1)[0] if line[1:].strip() else ""
        if not contig:
            raise CrisprProductWorkflowError("reference FASTA contains an empty record identifier")
        contigs.append(contig)
    if not contigs:
        raise CrisprProductWorkflowError("reference FASTA contains no records")
    if len(set(contigs)) != len(contigs):
        raise CrisprProductWorkflowError("reference FASTA record identifiers must be unique")
    return tuple(sorted(contigs))


def installed_reference_from_fasta(
    fasta_path: str | Path,
    *,
    organism_scientific_name: str,
    taxonomy_id: str | None,
    provider: str,
    assembly_accession: str,
    assembly_version: str,
    installation_provenance: str,
) -> InstalledReferenceIdentity:
    """Bind one existing top-level FASTA to the adopted reference identity."""
    path = Path(fasta_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise CrisprProductWorkflowError("configured reference FASTA is unavailable")
    if path.suffix.lower() not in V1_FASTA_SUFFIXES:
        raise CrisprProductWorkflowError("reference FASTA must use .fa, .fasta, or .fna")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CrisprProductWorkflowError("configured reference FASTA could not be read") from exc
    taxonomy = str(taxonomy_id or "").strip() or None
    return InstalledReferenceIdentity.build(
        organism_scientific_name=_require_text(
            "organism scientific name", organism_scientific_name
        ),
        taxonomy_id=taxonomy,
        provider=_require_text("reference provider", provider),
        assembly_accession=_require_text("assembly accession", assembly_accession),
        assembly_version=_require_text("assembly version", assembly_version),
        fasta_directory=path.parent,
        fasta_files=(
            ReferenceFastaFile(
                relative_path=path.name,
                sha256=hashlib.sha256(data).hexdigest(),
                contigs=_fasta_contigs(data),
            ),
        ),
        installation_provenance=_require_text(
            "installation provenance", installation_provenance
        ),
    )


def build_product_workflow_input(
    *,
    target_sequence: str,
    target_id: str,
    target_display_name: str,
    reference_pack_id: str,
    contig: str,
    reference: InstalledReferenceIdentity,
    reference_offset: int | None = None,
    maximum_mismatches: int = 4,
    off_target_requested: bool = True,
    executable_path: str | None = None,
    expected_executable_sha256: str | None = None,
    timeout_seconds: float = 120.0,
) -> CrisprWorkflowInput:
    """Build the exact target/config/reference binding for one product run."""
    resolved_contig = _require_text("reference contig", contig)
    requests_off_targets = bool(off_target_requested)
    target = CrisprTargetSequence.from_raw(
        target_sequence,
        target_id=_require_text("target ID", target_id),
        display_name=_require_text("target display name", target_display_name),
        reference_pack_id=_require_text("reference pack ID", reference_pack_id),
        contig=resolved_contig,
    )
    return CrisprWorkflowInput.create(
        target=target,
        reference=reference,
        coordinate_origin=TargetCoordinateOrigin(
            origin=(
                CoordinateOrigin.TARGET_LOCAL
                if reference_offset is None
                else CoordinateOrigin.REFERENCE_CONTIG
            ),
            contig=resolved_contig,
            offset=reference_offset,
        ),
        configuration=SpCas9Configuration(),
        execution_intent=CrisprExecutionIntent(
            scan_requested=True,
            off_target_requested=requests_off_targets,
            maximum_mismatches=maximum_mismatches,
            timeout_seconds=timeout_seconds,
            executable_path=(
                str(executable_path).strip() or None
                if requests_off_targets and executable_path is not None
                else None
            ),
            expected_executable_sha256=(
                str(expected_executable_sha256).strip() or None
                if requests_off_targets and expected_executable_sha256 is not None
                else None
            ),
        ),
    )


def compute_product_workflow(
    workflow_input: CrisprWorkflowInput,
    *,
    scanner: Callable[[Any, Any], CrisprScannerResultV1] | None = None,
) -> CrisprWorkflowResult:
    """Enter the adopted aggregate through its single scanner orchestration API."""
    return compute_workflow(workflow_input, scanner=scanner)


def select_product_candidate(
    result: CrisprWorkflowResult,
    candidate_id: str,
    *,
    current_input: CrisprWorkflowInput | None = None,
) -> CrisprWorkflowResult:
    """Apply an explicit user selection bound to the current aggregate."""
    if current_input is not None and not result.is_fresh_against(current_input):
        result = invalidate_stale_product_result(result, current_input)
    return select_candidate(result, candidate_id, current_input=current_input)


def enumerate_product_off_targets(
    result: CrisprWorkflowResult,
    *,
    current_input: CrisprWorkflowInput | None = None,
    runner: Callable[[Any], CasOffinderRunResult] | None = None,
    executable_path: str | Path | None = None,
) -> CrisprWorkflowResult:
    """Execute off-target enumeration only through the adopted aggregate."""
    return enumerate_off_targets(
        result,
        current_input=current_input,
        runner=runner,
        executable_path=executable_path,
    )


def invalidate_stale_product_result(
    result: CrisprWorkflowResult,
    current_input: CrisprWorkflowInput,
) -> CrisprWorkflowResult:
    """Refresh only the stale portions of one workflow result."""
    if result.is_fresh_against(current_input):
        return result
    previous_input = result.workflow_input
    preserves_scan_identity = (
        previous_input.target == current_input.target
        and previous_input.reference_binding == current_input.reference_binding
        and previous_input.coordinate_origin == current_input.coordinate_origin
        and previous_input.configuration == current_input.configuration
        and (
            previous_input.execution_intent.maximum_mismatches
            == current_input.execution_intent.maximum_mismatches
        )
    )
    if not preserves_scan_identity:
        return compute_product_workflow(current_input)

    reset_candidates = tuple(
        replace(candidate, off_target_state=WorkflowState.NOT_RUN)
        for candidate in result.scan.candidates
    )
    refreshed_scan = replace(
        result.scan,
        candidates=reset_candidates,
        freshness_hash=current_input.freshness_hash,
    )
    refreshed_selection = None
    if result.selection is not None:
        refreshed_candidate = next(
            (
                candidate
                for candidate in reset_candidates
                if candidate.candidate_id == result.selection.candidate_id
            ),
            None,
        )
        if refreshed_candidate is None:
            return compute_product_workflow(current_input)
        refreshed_selection = replace(
            result.selection,
            candidate=refreshed_candidate,
            workflow_id=current_input.workflow_id,
        )
    return replace(
        result,
        workflow_input=current_input,
        workflow_id=current_input.workflow_id,
        scan=refreshed_scan,
        selection=refreshed_selection,
        off_target=None,
    )


def candidate_projection(result: CrisprWorkflowResult) -> tuple[dict[str, Any], ...]:
    """Return deterministic display rows with no ranking or recommendation fields."""
    return tuple(
        {
            "candidate_id": candidate.candidate_id,
            "guide_sequence": candidate.guide_sequence,
            "pam": candidate.pam,
            "strand": candidate.strand.value,
            "spacer_start": candidate.spacer_start,
            "spacer_end": candidate.spacer_end,
            "gc_fraction": candidate._guide.gc_fraction,
            "gc_percent": candidate._guide.gc_fraction * 100,
            "warning_codes": tuple(
                warning.code.value for warning in candidate._guide.warnings
            ),
            "warning_messages": tuple(
                warning.message for warning in candidate._guide.warnings
            ),
            "review_state": (
                candidate._guide.review_state.value
                if candidate._guide.review_state is not None
                else "review_not_triggered"
            ),
            "scanner_algorithm_id": candidate._guide.scanner.algorithm_id,
            "scanner_algorithm_version": candidate._guide.scanner.version,
            "candidate_source": candidate._guide.candidate_source,
            "target_sequence_sha256": candidate.provenance.target_sequence_sha256,
            "reference_identity_sha256": candidate.provenance.reference_identity_sha256,
            "configuration_sha256": candidate.provenance.configuration_sha256,
            "scanner_output_sha256": candidate.provenance.scanner_output_sha256,
            "coordinate_system": candidate.provenance.coordinate_system,
            "off_target_state": candidate.off_target_state.value,
        }
        for candidate in result.scan.candidates
    )


def off_target_hit_projection(
    result: CrisprWorkflowResult,
) -> tuple[dict[str, Any], ...]:
    """Return normalized hits in the aggregate's canonical order."""
    if not isinstance(result, CrisprWorkflowResult):
        raise TypeError("result must be a CrisprWorkflowResult")
    if result.off_target is None or result.off_target.state.value != "computed":
        return ()
    if result.selection is None:
        raise CrisprProductWorkflowError("computed off-target result has no selected guide")
    reference = result.workflow_input.reference_binding.reference
    return tuple(
        {
            "workflow_id": result.workflow_id,
            "selected_candidate_id": result.selection.candidate_id,
            "guide_sequence": result.selection.candidate.guide_sequence,
            "reference_identity_sha256": reference.identity_sha256,
            "assembly_accession": reference.assembly_accession,
            "assembly_version": reference.assembly_version,
            "contig": hit.contig,
            "start_0_based": hit.start,
            "end_0_based_exclusive": hit.end,
            "strand": hit.strand.value,
            "matched_sequence": hit.matched_sequence,
            "guide_oriented_sequence": hit.guide_oriented_sequence,
            "mismatch_count": hit.mismatch_count,
            "raw_engine_position": hit.raw_engine_position,
            "raw_strand": hit.raw_strand,
            "raw_row_number": hit.raw_row_number,
            "engine": hit.engine,
            "engine_version": hit.engine_version,
            "parameter_identity_sha256": hit.parameter_identity_sha256,
            "result_sha256": hit.result_sha256,
            "executable_sha256": hit.executable_sha256,
        }
        for hit in result.off_target.hits
    )


def off_target_hits_tsv(result: CrisprWorkflowResult) -> str:
    """Serialize computed normalized hits with the accepted P0 TSV contract."""
    if not isinstance(result, CrisprWorkflowResult):
        raise TypeError("result must be a CrisprWorkflowResult")
    if result.off_target is None or result.off_target.state.value != "computed":
        raise CrisprProductWorkflowError(
            "off-target TSV is available only for a computed result"
        )
    output = StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=OFF_TARGET_TSV_COLUMNS,
        delimiter="\t",
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    writer.writerows(off_target_hit_projection(result))
    return output.getvalue()


def guide_confirmation_signature(result: CrisprWorkflowResult) -> str | None:
    if result.selection is None:
        return None
    return hashlib.sha256(f'{result.workflow_id}\0{result.workflow_input.freshness_hash}\0{result.selection.candidate_id}'.encode('utf-8')).hexdigest()


def guide_confirmation_record(result: CrisprWorkflowResult, signature: str | None) -> dict[str, Any] | None:
    if signature is None:
        return None
    if signature != guide_confirmation_signature(result) or result.selection is None:
        raise CrisprProductWorkflowError('guide confirmation does not match the current selection and inputs')
    return {
        'schema_version': 'guide-confirmation-v1',
        'workflow_id': result.workflow_id,
        'freshness_hash': result.workflow_input.freshness_hash,
        'candidate_id': result.selection.candidate_id,
        'binding_sha256': signature,
        'meaning': 'explicit_user_selection_record_only',
    }


def public_crispr_review_projection(result: CrisprWorkflowResult, *, confirmation_signature: str | None = None) -> dict[str, Any]:
    """Allowlisted sharing facts; this projection cannot restore the aggregate."""
    reference = result.workflow_input.reference_binding.reference
    return {
        'projection_version': 'public-crispr-review-v1',
        'purpose': 'design_review_only; not_a_restorable_canonical_aggregate',
        'aggregate_sha256': hashlib.sha256(to_json(result).encode('utf-8')).hexdigest(),
        'workflow_id': result.workflow_id,
        'target_sha256': result.workflow_input.target.sequence_sha256,
        'reference_identity_sha256': result.workflow_input.reference_hash,
        'assembly_accession': reference.assembly_accession,
        'assembly_version': reference.assembly_version,
        'configuration_sha256': result.workflow_input.configuration_hash,
        'freshness_hash': result.workflow_input.freshness_hash,
        'candidates': list(candidate_projection(result)),
        'selected_candidate_id': result.selection.candidate_id if result.selection else None,
        'current_session_confirmation': guide_confirmation_record(result, confirmation_signature),
        'off_target_state': result.off_target_state.value,
        'off_target_hits': list(off_target_hit_projection(result)),
    }


def local_crispr_review_record_json(result: CrisprWorkflowResult, *, confirmation_signature: str | None = None) -> str:
    return json.dumps({
        'record_version': 'local-crispr-review-v1',
        'aggregate_json': to_json(result),
        'confirmation_record': guide_confirmation_record(result, confirmation_signature),
    }, sort_keys=True, ensure_ascii=True, indent=2)


def save_crispr_product_workflow(
    project_id: str,
    result: CrisprWorkflowResult,
    *,
    repository: PlantProjectDraftRepository | None = None,
    confirmation_signature: str | None = None,
) -> Any:
    """Persist one canonical aggregate inside an existing formal project."""
    if not isinstance(result, CrisprWorkflowResult):
        raise TypeError("result must be a CrisprWorkflowResult")
    repo = repository or PlantProjectDraftRepository()
    draft = repo.load(_require_text("project ID", project_id))
    require_active_project(draft)
    aggregate_json = to_json(result)
    review_state = dict(draft.manual_review_state)
    review_state[CRISPR_PRODUCT_STATE_KEY] = {
        "schema_version": CRISPR_PRODUCT_STATE_VERSION,
        "project_id": draft.project_id,
        "aggregate_json": aggregate_json,
        "workflow_id": result.workflow_id,
        "freshness_hash": result.workflow_input.freshness_hash,
        "confirmation_record": guide_confirmation_record(result, confirmation_signature),
    }
    draft.manual_review_state = review_state
    saved = repo.save(draft)
    reopened = repo.load(saved.project_id)
    persisted = dict(reopened.manual_review_state).get(CRISPR_PRODUCT_STATE_KEY)
    if not isinstance(persisted, dict) or persisted.get("aggregate_json") != aggregate_json:
        raise CrisprProductWorkflowError("saved CRISPR workflow could not be verified")
    return saved


def _saved_product_payload(project_id: str, repo: PlantProjectDraftRepository) -> dict[str, Any]:
    draft = repo.load(_require_text("project ID", project_id))
    require_active_project(draft)
    payload = dict(draft.manual_review_state).get(CRISPR_PRODUCT_STATE_KEY)
    if not isinstance(payload, dict):
        raise CrisprProductWorkflowError("project has no saved CRISPR V1 workflow")
    if payload.get("schema_version") != CRISPR_PRODUCT_STATE_VERSION:
        raise CrisprProductWorkflowError("saved CRISPR product state is incompatible")
    if payload.get("project_id") != draft.project_id:
        raise CrisprProductWorkflowError("saved CRISPR workflow belongs to another project")
    aggregate_json = payload.get("aggregate_json")
    if not isinstance(aggregate_json, str) or not aggregate_json:
        raise CrisprProductWorkflowError("saved CRISPR workflow is incomplete")
    return payload


def saved_crispr_product_metadata(
    project_id: str,
    *,
    repository: PlantProjectDraftRepository | None = None,
) -> dict[str, Any]:
    """Read unverified routing metadata without treating it as scientific evidence."""
    repo = repository or PlantProjectDraftRepository()
    payload = _saved_product_payload(project_id, repo)
    try:
        aggregate = json.loads(payload["aggregate_json"])
        intent = aggregate["workflow_input"]["execution_intent"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise CrisprProductWorkflowError("saved CRISPR workflow metadata is malformed") from exc
    return {
        "workflow_id": payload.get("workflow_id"),
        "freshness_hash": payload.get("freshness_hash"),
        "off_target_requested": intent.get("off_target_requested") is True,
        "executable_path": intent.get("executable_path"),
        "expected_executable_sha256": intent.get("expected_executable_sha256"),
        "off_target_state": aggregate.get("off_target_state"),
        "selected_candidate_id": (
            aggregate.get("selection", {}).get("candidate_id")
            if isinstance(aggregate.get("selection"), dict)
            else None
        ),
        "hit_count": (
            aggregate.get("off_target", {}).get("hit_count")
            if isinstance(aggregate.get("off_target"), dict)
            else None
        ),
        "historical_confirmation": payload.get('confirmation_record'),
    }


def open_crispr_product_workflow(
    project_id: str,
    *,
    trusted_executable: CasOffinderExecutableIdentity | None = None,
    repository: PlantProjectDraftRepository | None = None,
) -> CrisprWorkflowResult:
    """Cold-reopen and fully verify one canonical persisted aggregate."""
    repo = repository or PlantProjectDraftRepository()
    payload = _saved_product_payload(project_id, repo)
    result = from_json(
        payload["aggregate_json"],
        trusted_executable=trusted_executable,
    )
    if (
        result.workflow_id != payload.get("workflow_id")
        or result.workflow_input.freshness_hash != payload.get("freshness_hash")
    ):
        raise CrisprProductWorkflowError("saved CRISPR workflow identity is inconsistent")
    historical = payload.get('confirmation_record')
    if historical is not None:
        expected = guide_confirmation_record(result, historical.get('binding_sha256') if isinstance(historical, dict) else '')
        if historical != expected:
            raise CrisprProductWorkflowError('saved guide confirmation binding is inconsistent')
    return result


def verify_cas_offinder_executable_authority(
    executable_path: str | Path,
    *,
    expected_sha256: str | None = None,
    timeout_seconds: float = 10.0,
) -> CasOffinderExecutableIdentity:
    """Re-establish external executable authority before a cold reopen."""
    path = Path(executable_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise CrisprProductWorkflowError("configured Cas-OFFinder executable is unavailable")
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        completed = subprocess.run(
            [str(path)],
            capture_output=True,
            text=True,
            timeout=min(float(timeout_seconds), 10.0),
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CrisprProductWorkflowError(
            "Cas-OFFinder executable authority could not be verified"
        ) from exc
    expected = str(expected_sha256 or "").strip()
    if expected and digest != expected:
        raise CrisprProductWorkflowError("Cas-OFFinder executable SHA-256 has changed")
    lines = [
        line.strip()
        for line in f"{completed.stdout}\n{completed.stderr}".splitlines()
        if line.strip()
    ]
    if not lines:
        raise CrisprProductWorkflowError("Cas-OFFinder version banner is unavailable")
    try:
        return CasOffinderExecutableIdentity(
            resolved_path=str(path),
            sha256=digest,
            observed_banner=lines[0],
        )
    except ValueError as exc:
        raise CrisprProductWorkflowError(
            "configured executable did not report the pinned Cas-OFFinder version"
        ) from exc


__all__ = [
    "CRISPR_PRODUCT_STATE_KEY",
    "CRISPR_PRODUCT_STATE_VERSION",
    "OFF_TARGET_TSV_COLUMNS",
    "CrisprProductWorkflowError",
    "build_product_workflow_input",
    "candidate_projection",
    "compute_product_workflow",
    "enumerate_product_off_targets",
    "installed_reference_from_fasta",
    "invalidate_stale_product_result",
    "off_target_hit_projection",
    "off_target_hits_tsv",
    "open_crispr_product_workflow",
    "save_crispr_product_workflow",
    "saved_crispr_product_metadata",
    "select_product_candidate",
    "verify_cas_offinder_executable_authority",
]
