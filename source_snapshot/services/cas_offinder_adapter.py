"""Safe local CPU adapter for the frozen Cas-OFFinder 2.4.1 contract."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from services.crispr_reference_contract import InstalledReferenceIdentity
from services.crispr_v1_contract import CrisprStrand


CAS_OFFINDER_ENGINE = "Cas-OFFinder"
CAS_OFFINDER_VERSION = "2.4.1"
CAS_OFFINDER_TAG_COMMIT = "9816b94c20c4cba2e79b039e1e2a6dee684b7b66"
CAS_OFFINDER_CPU_MODE = "C"
OPENCL_RUNTIME_REQUIRED = True
SPCAS9_PATTERN = "NNNNNNNNNNNNNNNNNNNNNGG"
BULGE_POLICY = "excluded_v1"
_BANNER_RE = re.compile(r"^Cas-OFFinder v2\.4\.1 \(.+\)$")
_QUERY_RE = re.compile(r"^[ACGT]{20}NNN$")
_MATCHED_RE = re.compile(r"^[ACGTacgt]{23}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CasOffinderContractError(ValueError):
    """Raised when input or output violates the frozen v2.4.1 contract."""


class OffTargetComputationStatus(StrEnum):
    COMPUTED = "computed"
    UNAVAILABLE = "unavailable"
    EXECUTION_FAILED = "execution_failed"
    PARSE_FAILED = "parse_failed"
    NOT_COMPUTED = "not_computed"


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _require_text(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CasOffinderContractError(f"{field_name} must be a non-empty string")


_CANONICAL_HIT_FIELDS = (
    "guide_id",
    "reference_identity_sha256",
    "contig",
    "start",
    "end",
    "strand",
    "query",
    "matched_sequence",
    "guide_oriented_sequence",
    "mismatch_count",
    "engine",
    "engine_version",
    "parameter_identity_sha256",
)


def _canonical_hit_payload(hit: "EnumeratedOffTargetHit") -> dict[str, Any]:
    """Project one hit to scientific fields, excluding native-row evidence."""
    return {
        "guide_id": hit.guide_id,
        "reference_identity_sha256": hit.reference.identity_sha256,
        "contig": hit.contig,
        "start": hit.start,
        "end": hit.end,
        "strand": hit.strand.value,
        "query": hit.query,
        "matched_sequence": hit.matched_sequence.upper(),
        "guide_oriented_sequence": hit.guide_oriented_sequence,
        "mismatch_count": hit.mismatch_count,
        "engine": hit.engine,
        "engine_version": hit.engine_version,
        "parameter_identity_sha256": hit.parameter_identity_sha256,
    }


def canonical_hit_order(hits: tuple["EnumeratedOffTargetHit", ...]) -> tuple["EnumeratedOffTargetHit", ...]:
    """Return hits in a total order independent of native row ordering."""
    return tuple(
        sorted(
            hits,
            key=lambda hit: tuple(
                _canonical_hit_payload(hit)[field] for field in _CANONICAL_HIT_FIELDS
            ),
        )
    )


def canonical_result_sha256(
    request: "CasOffinderRequest",
    hits: tuple["EnumeratedOffTargetHit", ...],
) -> str:
    """Hash the canonical scientific result while retaining hit multiplicity."""
    ordered_hits = canonical_hit_order(hits)
    return _canonical_sha256(
        {
            "contract": "crispr-cas-offinder-normalized-result",
            "version": 1,
            "request": {
                "guide_id": request.guide_id,
                "query": request.query,
                "maximum_mismatches": request.maximum_mismatches,
                "reference_identity_sha256": request.reference.identity_sha256,
                "parameter_identity_sha256": request.parameter_identity_sha256,
                "engine": CAS_OFFINDER_ENGINE,
                "engine_version": CAS_OFFINDER_VERSION,
                "cpu_mode": CAS_OFFINDER_CPU_MODE,
                "opencl_runtime_required": OPENCL_RUNTIME_REQUIRED,
                "pattern": SPCAS9_PATTERN,
                "bulge_policy": BULGE_POLICY,
            },
            "hits": [_canonical_hit_payload(hit) for hit in ordered_hits],
        }
    )


@dataclass(frozen=True, slots=True)
class CasOffinderRequest:
    guide_id: str
    spacer: str
    maximum_mismatches: int
    reference: InstalledReferenceIdentity

    def __post_init__(self) -> None:
        _require_text("guide_id", self.guide_id)
        if re.fullmatch(r"[ACGT]{20}", self.spacer) is None:
            raise CasOffinderContractError(
                "spacer must be exactly 20 uppercase A/C/G/T bases"
            )
        if (
            not isinstance(self.maximum_mismatches, int)
            or isinstance(self.maximum_mismatches, bool)
            or not 0 <= self.maximum_mismatches <= 20
        ):
            raise CasOffinderContractError(
                "maximum_mismatches must be an integer in 0..20"
            )
        if not isinstance(self.reference, InstalledReferenceIdentity):
            raise CasOffinderContractError(
                "reference must be an InstalledReferenceIdentity"
            )

    @property
    def query(self) -> str:
        return f"{self.spacer}NNN"

    @property
    def parameter_identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "bulge_policy": BULGE_POLICY,
                "cpu_mode": CAS_OFFINDER_CPU_MODE,
                "engine": CAS_OFFINDER_ENGINE,
                "engine_version": CAS_OFFINDER_VERSION,
                "maximum_mismatches": self.maximum_mismatches,
                "opencl_runtime_required": OPENCL_RUNTIME_REQUIRED,
                "pattern": SPCAS9_PATTERN,
                "reference_identity_sha256": self.reference.identity_sha256,
            }
        )


def build_cas_offinder_input(request: CasOffinderRequest) -> tuple[str, str]:
    if not isinstance(request, CasOffinderRequest):
        raise TypeError("request must be a CasOffinderRequest")
    text = (
        f"{request.reference.fasta_directory}\n"
        f"{SPCAS9_PATTERN}\n"
        f"{request.query} {request.maximum_mismatches}\n"
    )
    return text, _sha256_text(text)


@dataclass(frozen=True, slots=True)
class CasOffinderExecutableIdentity:
    resolved_path: str
    sha256: str
    observed_banner: str

    def __post_init__(self) -> None:
        _require_text("resolved_path", self.resolved_path)
        if _SHA256_RE.fullmatch(self.sha256) is None:
            raise CasOffinderContractError(
                "executable sha256 must be a lowercase SHA-256"
            )
        if _BANNER_RE.fullmatch(self.observed_banner) is None:
            raise CasOffinderContractError(
                "executable banner is not Cas-OFFinder v2.4.1"
            )


@dataclass(frozen=True, slots=True)
class EnumeratedOffTargetHit:
    guide_id: str
    reference: InstalledReferenceIdentity
    contig: str
    start: int
    end: int
    strand: CrisprStrand
    query: str
    matched_sequence: str
    guide_oriented_sequence: str
    mismatch_count: int
    engine: str
    engine_version: str
    parameter_identity_sha256: str
    input_sha256: str
    result_sha256: str
    raw_engine_position: int
    raw_strand: str
    raw_row: str
    raw_row_number: int
    executable_sha256: str

    def __post_init__(self) -> None:
        _require_text("guide_id", self.guide_id)
        _require_text("contig", self.contig)
        if self.contig not in self.reference.contig_to_relative_path:
            raise CasOffinderContractError("hit contig is absent from reference manifest")
        if (
            not isinstance(self.start, int)
            or isinstance(self.start, bool)
            or self.start < 0
            or self.raw_engine_position != self.start
        ):
            raise CasOffinderContractError(
                "start must preserve the non-negative raw engine position"
            )
        if self.end != self.start + 23:
            raise CasOffinderContractError("end must equal start + 23")
        if self.strand not in (CrisprStrand.PLUS, CrisprStrand.MINUS):
            raise CasOffinderContractError("strand must be + or -")
        if self.raw_strand != self.strand.value:
            raise CasOffinderContractError("raw_strand must preserve engine evidence")
        if _QUERY_RE.fullmatch(self.query) is None:
            raise CasOffinderContractError("query must be 20 A/C/G/T bases plus NNN")
        if _MATCHED_RE.fullmatch(self.matched_sequence) is None:
            raise CasOffinderContractError(
                "matched_sequence must preserve 23 raw A/C/G/T bases"
            )
        if self.guide_oriented_sequence != self.matched_sequence.upper():
            raise CasOffinderContractError(
                "guide_oriented_sequence must be an explicit uppercase derived field"
            )
        if (
            not isinstance(self.mismatch_count, int)
            or isinstance(self.mismatch_count, bool)
            or not 0 <= self.mismatch_count <= 20
        ):
            raise CasOffinderContractError("mismatch_count must be in 0..20")
        if self.engine != CAS_OFFINDER_ENGINE or self.engine_version != CAS_OFFINDER_VERSION:
            raise CasOffinderContractError("unexpected off-target engine identity")
        for field_name in (
            "parameter_identity_sha256",
            "input_sha256",
            "result_sha256",
            "executable_sha256",
        ):
            if _SHA256_RE.fullmatch(getattr(self, field_name)) is None:
                raise CasOffinderContractError(f"{field_name} must be a SHA-256")
        if not isinstance(self.raw_row_number, int) or self.raw_row_number < 1:
            raise CasOffinderContractError("raw_row_number must be positive")
        _require_text("raw_row", self.raw_row)


@dataclass(frozen=True, slots=True)
class CasOffinderRunResult:
    request: CasOffinderRequest
    status: OffTargetComputationStatus
    hits: tuple[EnumeratedOffTargetHit, ...]
    input_text: str
    input_sha256: str
    output_text: str | None
    output_sha256: str | None
    executable: CasOffinderExecutableIdentity | None
    invocation: tuple[str, ...] | None
    exit_code: int | None
    stdout: str
    stderr: str
    error_code: str | None
    error_message: str | None
    temporary_paths_cleaned: bool

    def __post_init__(self) -> None:
        if not isinstance(self.status, OffTargetComputationStatus):
            raise CasOffinderContractError("status must be typed")
        if self.input_sha256 != _sha256_text(self.input_text):
            raise CasOffinderContractError("input hash does not match input text")
        if self.output_text is None:
            if self.output_sha256 is not None:
                raise CasOffinderContractError("output hash requires output text")
        elif self.output_sha256 != _sha256_text(self.output_text):
            raise CasOffinderContractError("output hash does not match output text")
        if self.status is OffTargetComputationStatus.COMPUTED:
            if self.exit_code != 0 or self.error_code is not None:
                raise CasOffinderContractError(
                    "computed requires exit code zero and no error"
                )
            if self.output_text is None or self.executable is None or self.invocation is None:
                raise CasOffinderContractError(
                    "computed requires output, executable identity, and invocation"
                )
        elif self.hits:
            raise CasOffinderContractError(
                "non-computed states cannot expose computed hits"
            )

    @property
    def hit_count(self) -> int | None:
        if self.status is OffTargetComputationStatus.COMPUTED:
            return len(self.hits)
        return None

    @property
    def result_sha256(self) -> str | None:
        if self.status is OffTargetComputationStatus.COMPUTED:
            return canonical_result_sha256(self.request, self.hits)
        return None


def _parse_non_negative_integer(field_name: str, value: str) -> int:
    if not value or not value.isdecimal():
        raise CasOffinderContractError(
            f"{field_name} must be an unsigned decimal integer"
        )
    return int(value)


def parse_cas_offinder_v241_output(
    output_text: str,
    request: CasOffinderRequest,
    *,
    executable_sha256: str,
    input_sha256: str | None = None,
) -> tuple[EnumeratedOffTargetHit, ...]:
    """Parse only the six-column, no-ID, no-bulge v2.4.1 output."""
    if not isinstance(output_text, str):
        raise TypeError("output_text must be a string")
    if not isinstance(request, CasOffinderRequest):
        raise TypeError("request must be a CasOffinderRequest")
    if _SHA256_RE.fullmatch(executable_sha256) is None:
        raise CasOffinderContractError("executable_sha256 must be a SHA-256")
    expected_input_text, expected_input_sha256 = build_cas_offinder_input(request)
    del expected_input_text
    effective_input_sha256 = input_sha256 or expected_input_sha256
    if effective_input_sha256 != expected_input_sha256:
        raise CasOffinderContractError("input_sha256 does not match the request")
    hits: list[EnumeratedOffTargetHit] = []
    for row_number, raw_row in enumerate(output_text.splitlines(), start=1):
        if not raw_row:
            continue
        columns = raw_row.split("\t")
        if len(columns) != 6:
            raise CasOffinderContractError(
                "Cas-OFFinder v2.4.1 output rows must contain exactly six TAB-separated columns"
            )
        query, contig, raw_position, matched_sequence, raw_strand, raw_mismatch = columns
        if _QUERY_RE.fullmatch(query) is None or query != request.query:
            raise CasOffinderContractError(
                "output query is malformed or does not match the request"
            )
        if contig not in request.reference.contig_to_relative_path:
            raise CasOffinderContractError(
                "output contig is absent from the pinned reference manifest"
            )
        start = _parse_non_negative_integer("raw position", raw_position)
        if _MATCHED_RE.fullmatch(matched_sequence) is None:
            raise CasOffinderContractError(
                "matched sequence must contain exactly 23 A/C/G/T bases"
            )
        if raw_strand not in {"+", "-"}:
            raise CasOffinderContractError("strand must be exactly + or -")
        mismatch_count = _parse_non_negative_integer(
            "mismatch count", raw_mismatch
        )
        if mismatch_count > request.maximum_mismatches:
            raise CasOffinderContractError(
                "mismatch count exceeds the request maximum"
            )
        hits.append(
            EnumeratedOffTargetHit(
                guide_id=request.guide_id,
                reference=request.reference,
                contig=contig,
                start=start,
                end=start + 23,
                strand=CrisprStrand(raw_strand),
                query=query,
                matched_sequence=matched_sequence,
                guide_oriented_sequence=matched_sequence.upper(),
                mismatch_count=mismatch_count,
                engine=CAS_OFFINDER_ENGINE,
                engine_version=CAS_OFFINDER_VERSION,
                parameter_identity_sha256=request.parameter_identity_sha256,
                input_sha256=effective_input_sha256,
                # The normalized result identity is assigned after all rows
                # are parsed and canonically ordered.
                result_sha256="0" * 64,
                raw_engine_position=start,
                raw_strand=raw_strand,
                raw_row=raw_row,
                raw_row_number=row_number,
                executable_sha256=executable_sha256,
            )
        )
    ordered_hits = canonical_hit_order(tuple(hits))
    normalized_sha256 = canonical_result_sha256(request, ordered_hits)
    return tuple(replace(hit, result_sha256=normalized_sha256) for hit in ordered_hits)


def _hash_file_and_contigs(path: Path) -> tuple[str, tuple[str, ...]]:
    digest = hashlib.sha256()
    contigs: list[str] = []
    with path.open("rb") as handle:
        for line in handle:
            digest.update(line)
            if line.startswith(b">"):
                try:
                    header = line[1:].decode("utf-8").strip()
                except UnicodeDecodeError as error:
                    raise CasOffinderContractError(
                        f"FASTA header is not UTF-8 in {path.name}"
                    ) from error
                contig = header.split(maxsplit=1)[0] if header else ""
                if not contig:
                    raise CasOffinderContractError(
                        f"FASTA contains an empty header in {path.name}"
                    )
                contigs.append(contig)
    return digest.hexdigest(), tuple(sorted(contigs))


def validate_installed_reference(reference: InstalledReferenceIdentity) -> None:
    directory = Path(reference.fasta_directory)
    if not directory.is_dir():
        raise FileNotFoundError("reference FASTA directory is unavailable")
    directory_resolved = directory.resolve(strict=True)
    # Cas-OFFinder 2.4.1 attempts every top-level regular file/symlink and
    # recognizes FASTA by its leading '>' byte, not by its suffix.  Inspecting
    # content here closes the effective engine input set while the typed
    # manifest separately limits admitted names to the frozen V1 suffixes.
    searchable_paths: list[str] = []
    for candidate in directory.iterdir():
        if not candidate.is_file():
            continue
        with candidate.open("rb") as handle:
            if handle.read(1) == b">":
                searchable_paths.append(candidate.name)
    actual_searchable = tuple(sorted(searchable_paths))
    manifested_searchable = tuple(
        sorted(item.relative_path for item in reference.fasta_files)
    )
    unexpected = sorted(set(actual_searchable) - set(manifested_searchable))
    if unexpected:
        raise CasOffinderContractError(
            "reference FASTA directory contains unmanifested searchable files: "
            + ", ".join(unexpected)
        )
    missing = sorted(set(manifested_searchable) - set(actual_searchable))
    if missing:
        raise FileNotFoundError(
            "manifested reference FASTA is unavailable or not searchable: "
            + ", ".join(missing)
        )
    for manifest_file in reference.fasta_files:
        path = (directory / manifest_file.relative_path).resolve(strict=False)
        try:
            path.relative_to(directory_resolved)
        except ValueError as error:
            raise CasOffinderContractError(
                "reference FASTA path escapes the installed directory"
            ) from error
        if not path.is_file():
            raise FileNotFoundError(
                f"reference FASTA file is unavailable: {manifest_file.relative_path}"
            )
        actual_sha256, actual_contigs = _hash_file_and_contigs(path)
        if actual_sha256 != manifest_file.sha256:
            raise CasOffinderContractError(
                f"reference FASTA hash mismatch: {manifest_file.relative_path}"
            )
        if actual_contigs != manifest_file.contigs:
            raise CasOffinderContractError(
                f"reference FASTA contig manifest mismatch: {manifest_file.relative_path}"
            )


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def _reference_contexts(
    reference: InstalledReferenceIdentity,
    hits: tuple[EnumeratedOffTargetHit, ...],
) -> dict[tuple[str, int, int], str]:
    required: dict[str, set[tuple[int, int]]] = {}
    for hit in hits:
        required.setdefault(hit.contig, set()).add((hit.start, hit.end))
    contexts: dict[tuple[str, int, int], list[str]] = {
        (contig, start, end): []
        for contig, intervals in required.items()
        for start, end in intervals
    }
    for manifest_file in reference.fasta_files:
        relevant = set(manifest_file.contigs).intersection(required)
        if not relevant:
            continue
        path = Path(reference.fasta_directory) / manifest_file.relative_path
        current_contig: str | None = None
        current_offset = 0
        with path.open("rt", encoding="utf-8", newline=None) as handle:
            for line in handle:
                if line.startswith(">"):
                    current_contig = line[1:].strip().split(maxsplit=1)[0]
                    current_offset = 0
                    continue
                if current_contig not in relevant:
                    continue
                sequence = "".join(line.split()).upper()
                if sequence and re.fullmatch(r"[ACGTN]+", sequence) is None:
                    raise CasOffinderContractError(
                        f"reference FASTA contains malformed DNA in {current_contig}"
                    )
                line_start = current_offset
                line_end = line_start + len(sequence)
                for start, end in sorted(required[current_contig]):
                    overlap_start = max(start, line_start)
                    overlap_end = min(end, line_end)
                    if overlap_start < overlap_end:
                        contexts[(current_contig, start, end)].append(
                            sequence[
                                overlap_start - line_start : overlap_end - line_start
                            ]
                        )
                current_offset = line_end
    return {key: "".join(parts) for key, parts in contexts.items()}


def _validate_hit_reference_evidence(
    reference: InstalledReferenceIdentity,
    hits: tuple[EnumeratedOffTargetHit, ...],
) -> None:
    contexts = _reference_contexts(reference, hits)
    for hit in hits:
        context = contexts.get((hit.contig, hit.start, hit.end), "")
        if len(context) != 23:
            raise CasOffinderContractError(
                "hit interval is outside the pinned forward reference"
            )
        expected = context if hit.strand is CrisprStrand.PLUS else _reverse_complement(context)
        if hit.matched_sequence.upper() != expected:
            raise CasOffinderContractError(
                "matched sequence is inconsistent with pinned reference bytes"
            )


def _decode_process_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _failure_result(
    *,
    request: CasOffinderRequest,
    status: OffTargetComputationStatus,
    input_text: str,
    input_sha256: str,
    error_code: str,
    error_message: str,
    output_text: str | None = None,
    executable: CasOffinderExecutableIdentity | None = None,
    invocation: tuple[str, ...] | None = None,
    exit_code: int | None = None,
    stdout: str = "",
    stderr: str = "",
) -> CasOffinderRunResult:
    return CasOffinderRunResult(
        request=request,
        status=status,
        hits=(),
        input_text=input_text,
        input_sha256=input_sha256,
        output_text=output_text,
        output_sha256=None if output_text is None else _sha256_text(output_text),
        executable=executable,
        invocation=invocation,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        error_code=error_code,
        error_message=error_message,
        temporary_paths_cleaned=True,
    )


def not_computed_result(request: CasOffinderRequest) -> CasOffinderRunResult:
    input_text, input_sha256 = build_cas_offinder_input(request)
    return _failure_result(
        request=request,
        status=OffTargetComputationStatus.NOT_COMPUTED,
        input_text=input_text,
        input_sha256=input_sha256,
        error_code="NOT_COMPUTED",
        error_message="Cas-OFFinder was not invoked",
    )


def run_cas_offinder(
    request: CasOffinderRequest,
    *,
    executable_path: str | Path,
    timeout_seconds: float = 120.0,
) -> CasOffinderRunResult:
    """Run the pinned CPU adapter without shell interpolation."""
    if not isinstance(request, CasOffinderRequest):
        raise TypeError("request must be a CasOffinderRequest")
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        raise CasOffinderContractError("timeout_seconds must be positive")
    input_text, input_sha256 = build_cas_offinder_input(request)
    executable_file = Path(executable_path).expanduser().resolve(strict=False)
    if not executable_file.is_file():
        return _failure_result(
            request=request,
            status=OffTargetComputationStatus.UNAVAILABLE,
            input_text=input_text,
            input_sha256=input_sha256,
            error_code="EXECUTABLE_UNAVAILABLE",
            error_message="configured Cas-OFFinder executable is unavailable",
        )
    try:
        validate_installed_reference(request.reference)
    except (FileNotFoundError, OSError, CasOffinderContractError) as error:
        return _failure_result(
            request=request,
            status=OffTargetComputationStatus.UNAVAILABLE,
            input_text=input_text,
            input_sha256=input_sha256,
            error_code="REFERENCE_UNAVAILABLE",
            error_message=str(error),
        )
    executable_sha256 = _sha256_bytes(executable_file.read_bytes())
    resolved_executable = str(executable_file)
    try:
        preflight = subprocess.run(
            [resolved_executable],
            capture_output=True,
            text=True,
            timeout=min(float(timeout_seconds), 10.0),
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        return _failure_result(
            request=request,
            status=OffTargetComputationStatus.EXECUTION_FAILED,
            input_text=input_text,
            input_sha256=input_sha256,
            error_code="PREFLIGHT_TIMEOUT",
            error_message="Cas-OFFinder version/OpenCL preflight timed out",
            stdout=_decode_process_text(error.stdout),
            stderr=_decode_process_text(error.stderr),
        )
    except OSError as error:
        return _failure_result(
            request=request,
            status=OffTargetComputationStatus.UNAVAILABLE,
            input_text=input_text,
            input_sha256=input_sha256,
            error_code="EXECUTABLE_UNAVAILABLE",
            error_message=str(error),
        )
    preflight_stdout = _decode_process_text(preflight.stdout)
    preflight_stderr = _decode_process_text(preflight.stderr)
    banner_lines = [
        line.strip()
        for line in (preflight_stdout + "\n" + preflight_stderr).splitlines()
        if line.strip()
    ]
    if not banner_lines or _BANNER_RE.fullmatch(banner_lines[0]) is None:
        observed_first_line = banner_lines[0] if banner_lines else ""
        if (
            not observed_first_line.startswith("Cas-OFFinder v")
            and (preflight.returncode != 0 or bool(preflight_stderr.strip()))
        ):
            return _failure_result(
                request=request,
                status=OffTargetComputationStatus.EXECUTION_FAILED,
                input_text=input_text,
                input_sha256=input_sha256,
                error_code="PREFLIGHT_RUNTIME_FAILED",
                error_message=(
                    "Cas-OFFinder version/OpenCL preflight failed before a "
                    "compatible version banner was observed"
                ),
                exit_code=preflight.returncode,
                stdout=preflight_stdout,
                stderr=preflight_stderr,
            )
        return _failure_result(
            request=request,
            status=OffTargetComputationStatus.UNAVAILABLE,
            input_text=input_text,
            input_sha256=input_sha256,
            error_code="INCOMPATIBLE_ENGINE_VERSION",
            error_message="configured executable did not report Cas-OFFinder v2.4.1",
            exit_code=preflight.returncode,
            stdout=preflight_stdout,
            stderr=preflight_stderr,
        )
    executable_identity = CasOffinderExecutableIdentity(
        resolved_path=resolved_executable,
        sha256=executable_sha256,
        observed_banner=banner_lines[0],
    )
    with tempfile.TemporaryDirectory(prefix="ubd-cas-offinder-v241-") as temp_dir:
        input_path = Path(temp_dir) / "request.txt"
        output_path = Path(temp_dir) / "result.tsv"
        input_path.write_text(input_text, encoding="utf-8", newline="\n")
        invocation = (
            resolved_executable,
            str(input_path),
            CAS_OFFINDER_CPU_MODE,
            str(output_path),
        )
        try:
            completed = subprocess.run(
                list(invocation),
                capture_output=True,
                text=True,
                timeout=float(timeout_seconds),
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            return _failure_result(
                request=request,
                status=OffTargetComputationStatus.EXECUTION_FAILED,
                input_text=input_text,
                input_sha256=input_sha256,
                error_code="EXECUTION_TIMEOUT",
                error_message="Cas-OFFinder execution timed out",
                executable=executable_identity,
                invocation=invocation,
                stdout=_decode_process_text(error.stdout),
                stderr=_decode_process_text(error.stderr),
            )
        except OSError as error:
            return _failure_result(
                request=request,
                status=OffTargetComputationStatus.EXECUTION_FAILED,
                input_text=input_text,
                input_sha256=input_sha256,
                error_code="EXECUTION_OS_ERROR",
                error_message=str(error),
                executable=executable_identity,
                invocation=invocation,
            )
        stdout = _decode_process_text(completed.stdout)
        stderr = _decode_process_text(completed.stderr)
        if completed.returncode != 0:
            return _failure_result(
                request=request,
                status=OffTargetComputationStatus.EXECUTION_FAILED,
                input_text=input_text,
                input_sha256=input_sha256,
                error_code="NON_ZERO_EXIT",
                error_message="Cas-OFFinder returned a non-zero exit code",
                executable=executable_identity,
                invocation=invocation,
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        if not output_path.is_file():
            return _failure_result(
                request=request,
                status=OffTargetComputationStatus.EXECUTION_FAILED,
                input_text=input_text,
                input_sha256=input_sha256,
                error_code="OUTPUT_UNAVAILABLE",
                error_message="Cas-OFFinder did not create its output artifact",
                executable=executable_identity,
                invocation=invocation,
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        try:
            output_text = output_path.read_text(encoding="utf-8")
            hits = parse_cas_offinder_v241_output(
                output_text,
                request,
                executable_sha256=executable_sha256,
                input_sha256=input_sha256,
            )
            _validate_hit_reference_evidence(request.reference, hits)
        except (OSError, UnicodeError, CasOffinderContractError) as error:
            output_text = (
                output_path.read_text(encoding="utf-8", errors="replace")
                if output_path.is_file()
                else None
            )
            return _failure_result(
                request=request,
                status=OffTargetComputationStatus.PARSE_FAILED,
                input_text=input_text,
                input_sha256=input_sha256,
                output_text=output_text,
                error_code="PARSE_FAILED",
                error_message=str(error),
                executable=executable_identity,
                invocation=invocation,
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        return CasOffinderRunResult(
            request=request,
            status=OffTargetComputationStatus.COMPUTED,
            hits=hits,
            input_text=input_text,
            input_sha256=input_sha256,
            output_text=output_text,
            output_sha256=_sha256_text(output_text),
            executable=executable_identity,
            invocation=invocation,
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            error_code=None,
            error_message=None,
            temporary_paths_cleaned=True,
        )


__all__ = [
    "BULGE_POLICY",
    "CAS_OFFINDER_CPU_MODE",
    "CAS_OFFINDER_ENGINE",
    "CAS_OFFINDER_TAG_COMMIT",
    "CAS_OFFINDER_VERSION",
    "OPENCL_RUNTIME_REQUIRED",
    "SPCAS9_PATTERN",
    "CasOffinderContractError",
    "CasOffinderExecutableIdentity",
    "CasOffinderRequest",
    "CasOffinderRunResult",
    "canonical_hit_order",
    "canonical_result_sha256",
    "EnumeratedOffTargetHit",
    "OffTargetComputationStatus",
    "build_cas_offinder_input",
    "not_computed_result",
    "parse_cas_offinder_v241_output",
    "run_cas_offinder",
    "validate_installed_reference",
]
