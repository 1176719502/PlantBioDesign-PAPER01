from __future__ import annotations

from dataclasses import fields, replace
import hashlib
from pathlib import Path
import subprocess

import pytest

import services.cas_offinder_adapter as adapter
from services.cas_offinder_adapter import (
    BULGE_POLICY,
    CAS_OFFINDER_CPU_MODE,
    CAS_OFFINDER_ENGINE,
    CAS_OFFINDER_TAG_COMMIT,
    CAS_OFFINDER_VERSION,
    OPENCL_RUNTIME_REQUIRED,
    SPCAS9_PATTERN,
    CasOffinderContractError,
    CasOffinderRequest,
    EnumeratedOffTargetHit,
    OffTargetComputationStatus,
    build_cas_offinder_input,
    canonical_hit_order,
    canonical_result_sha256,
    not_computed_result,
    parse_cas_offinder_v241_output,
    run_cas_offinder,
    validate_installed_reference,
)
from services.crispr_reference_contract import (
    InstalledReferenceIdentity,
    ReferenceFastaFile,
)
from services.crispr_v1_contract import CrisprStrand


SPACER = "ACGTACGTACGTACGTACGT"
QUERY = f"{SPACER}NNN"
PLUS_CONTEXT = f"{SPACER}TGG"
REVERSE_FORWARD_CONTEXT = "CCAAGTCAGTCAGTCAGTCAGTC"
REVERSE_MATCHED = "GACTGACTGACTGACTGACTTGG"


def _reference(tmp_path: Path, *, create: bool = True) -> InstalledReferenceIdentity:
    directory = tmp_path / "reference"
    fasta_bytes = (
        f">chr1 fixture\nAA{PLUS_CONTEXT}AAAA{REVERSE_FORWARD_CONTEXT}TT\n"
    ).encode("utf-8")
    if create:
        directory.mkdir()
        (directory / "assembly.fa").write_bytes(fasta_bytes)
    return InstalledReferenceIdentity.build(
        organism_scientific_name="Arabidopsis thaliana",
        taxonomy_id="3702",
        provider="fixture-provider",
        assembly_accession="GCF_000001735.4",
        assembly_version="TAIR10.1",
        fasta_directory=directory,
        fasta_files=(
            ReferenceFastaFile(
                relative_path="assembly.fa",
                sha256=hashlib.sha256(fasta_bytes).hexdigest(),
                contigs=("chr1",),
            ),
        ),
        installation_provenance="user-installed deterministic fixture",
    )


def _request(tmp_path: Path, *, create_reference: bool = True) -> CasOffinderRequest:
    return CasOffinderRequest(
        guide_id="guide-001",
        spacer=SPACER,
        maximum_mismatches=4,
        reference=_reference(tmp_path, create=create_reference),
    )


def _executable(tmp_path: Path) -> Path:
    path = tmp_path / "cas-offinder.exe"
    path.write_bytes(b"fixture executable")
    return path


def _row(
    *,
    contig: str = "chr1",
    position: int = 2,
    matched: str = PLUS_CONTEXT,
    strand: str = "+",
    mismatches: str = "0",
) -> str:
    return f"{QUERY}\t{contig}\t{position}\t{matched}\t{strand}\t{mismatches}"


def _reference_from_fasta(
    tmp_path: Path,
    fasta_text: str,
    *,
    contigs: tuple[str, ...],
    filename: str = "assembly.fa",
) -> InstalledReferenceIdentity:
    directory = tmp_path / "reference"
    directory.mkdir()
    fasta_bytes = fasta_text.encode("utf-8")
    (directory / filename).write_bytes(fasta_bytes)
    return InstalledReferenceIdentity.build(
        organism_scientific_name="Arabidopsis thaliana",
        taxonomy_id="3702",
        provider="fixture-provider",
        assembly_accession="GCF_000001735.4",
        assembly_version="TAIR10.1",
        fasta_directory=directory,
        fasta_files=(
            ReferenceFastaFile(
                relative_path=filename,
                sha256=hashlib.sha256(fasta_bytes).hexdigest(),
                contigs=contigs,
            ),
        ),
        installation_provenance="user-installed deterministic fixture",
    )


def _request_for_reference(reference: InstalledReferenceIdentity) -> CasOffinderRequest:
    return CasOffinderRequest(
        guide_id="guide-001",
        spacer=SPACER,
        maximum_mismatches=4,
        reference=reference,
    )


def _fake_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    output_text: str = "",
    execution_returncode: int = 0,
    execution_stdout: str = "",
    execution_stderr: str = "",
    execution_timeout: bool = False,
    banner: str | None = "Cas-OFFinder v2.4.1 (fixture)",
    preflight_returncode: int = 0,
    preflight_stderr: str = "",
) -> list[tuple[list[str], dict[str, object]]]:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(arguments, **kwargs):
        args = list(arguments)
        calls.append((args, kwargs))
        if len(args) == 1:
            banner_text = "" if banner is None else f"{banner}\n"
            return subprocess.CompletedProcess(
                args,
                preflight_returncode,
                stdout=banner_text,
                stderr=preflight_stderr,
            )
        if execution_timeout:
            raise subprocess.TimeoutExpired(
                args,
                kwargs["timeout"],
                output="partial stdout",
                stderr="OpenCL device pending",
            )
        if execution_returncode == 0:
            Path(args[3]).write_text(output_text, encoding="utf-8", newline="")
        return subprocess.CompletedProcess(
            args,
            execution_returncode,
            stdout=execution_stdout,
            stderr=execution_stderr,
        )

    monkeypatch.setattr(adapter.subprocess, "run", fake_run)
    return calls


def test_frozen_engine_and_input_contract_are_exact(tmp_path: Path) -> None:
    request = _request(tmp_path)
    text, input_sha256 = build_cas_offinder_input(request)

    assert CAS_OFFINDER_ENGINE == "Cas-OFFinder"
    assert CAS_OFFINDER_VERSION == "2.4.1"
    assert CAS_OFFINDER_TAG_COMMIT == "9816b94c20c4cba2e79b039e1e2a6dee684b7b66"
    assert CAS_OFFINDER_CPU_MODE == "C"
    assert OPENCL_RUNTIME_REQUIRED is True
    assert SPCAS9_PATTERN == "N" * 21 + "GG"
    assert BULGE_POLICY == "excluded_v1"
    assert text == (
        f"{request.reference.fasta_directory}\n"
        f"{'N' * 21}GG\n"
        f"{QUERY} 4\n"
    )
    assert input_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert "guide-001" not in text


@pytest.mark.parametrize("maximum", [-1, 21, True, 1.5])
def test_request_rejects_invalid_mismatch_limits(
    tmp_path: Path,
    maximum: object,
) -> None:
    with pytest.raises(CasOffinderContractError, match="0..20"):
        CasOffinderRequest(
            guide_id="guide-001",
            spacer=SPACER,
            maximum_mismatches=maximum,  # type: ignore[arg-type]
            reference=_reference(tmp_path),
        )


def test_valid_forward_and_reverse_rows_use_forward_reference_coordinates(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    output = _row() + "\n" + _row(
        position=29,
        matched=REVERSE_MATCHED,
        strand="-",
        mismatches="2",
    ) + "\n"
    hits = parse_cas_offinder_v241_output(
        output,
        request,
        executable_sha256="a" * 64,
    )

    assert len(hits) == 2
    assert (hits[0].start, hits[0].end, hits[0].strand) == (
        2,
        25,
        CrisprStrand.PLUS,
    )
    assert (hits[1].start, hits[1].end, hits[1].strand) == (
        29,
        52,
        CrisprStrand.MINUS,
    )
    assert hits[1].raw_engine_position == 29
    assert hits[1].raw_strand == "-"


def test_multiple_rows_preserve_raw_evidence_while_using_deterministic_order(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    later = _row(position=29, matched=REVERSE_MATCHED, strand="-", mismatches="1")
    earlier = _row(matched="AcGTACGTACGTACGTACGTTGG", mismatches="1")
    hits = parse_cas_offinder_v241_output(
        later + "\n" + earlier + "\n",
        request,
        executable_sha256="b" * 64,
    )

    assert [hit.start for hit in hits] == [2, 29]
    assert hits[0].raw_row == earlier
    assert hits[0].raw_row_number == 2
    assert hits[0].matched_sequence.startswith("Ac")
    assert hits[0].guide_oriented_sequence == PLUS_CONTEXT


def test_native_permutations_share_normalized_identity_but_keep_raw_identity_distinct(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    rows = (
        _row(position=2, matched=PLUS_CONTEXT, mismatches="0"),
        _row(position=29, matched=REVERSE_MATCHED, strand="-", mismatches="1"),
        _row(position=2, matched=PLUS_CONTEXT, mismatches="2"),
        _row(position=29, matched=REVERSE_MATCHED, strand="-", mismatches="3"),
    )
    outputs = (
        "\n".join(rows) + "\n",
        "\n".join(reversed(rows)) + "\n",
        "\n".join((rows[2], rows[0], rows[3], rows[1])) + "\n",
    )
    parsed = tuple(
        parse_cas_offinder_v241_output(
            output,
            request,
            executable_sha256="e" * 64,
        )
        for output in outputs
    )

    assert len({hashlib.sha256(output.encode()).hexdigest() for output in outputs}) == 3
    assert len({canonical_result_sha256(request, hits) for hits in parsed}) == 1
    assert len({tuple(hit.result_sha256 for hit in hits) for hits in parsed}) == 1
    scientific_rows = {
        tuple(
            (hit.contig, hit.start, hit.end, hit.strand, hit.mismatch_count)
            for hit in hits
        )
        for hits in parsed
    }
    assert len(scientific_rows) == 1
    assert len({tuple(hit.raw_row_number for hit in hits) for hits in parsed}) == 3


def test_normalized_identity_excludes_machine_specific_input_evidence(tmp_path: Path) -> None:
    request = _request(tmp_path)
    hits = parse_cas_offinder_v241_output(
        _row() + "\n",
        request,
        executable_sha256="e" * 64,
    )
    different_input_evidence = tuple(
        replace(hit, input_sha256="f" * 64) for hit in hits
    )

    assert canonical_hit_order(hits) != canonical_hit_order(different_input_evidence)
    assert canonical_result_sha256(request, hits) == canonical_result_sha256(
        request, different_input_evidence
    )


def test_zero_hit_normalized_identity_is_request_bound_and_deterministic(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    assert canonical_result_sha256(request, ()) == canonical_result_sha256(request, ())


def test_zero_hit_output_parses_as_an_empty_computed_payload(tmp_path: Path) -> None:
    assert parse_cas_offinder_v241_output(
        "",
        _request(tmp_path),
        executable_sha256="c" * 64,
    ) == ()


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("\t".join([QUERY, "chr1", "2", PLUS_CONTEXT, "+"]), "six"),
        ("\t".join([QUERY, "chr1", "2", PLUS_CONTEXT, "+", "0", "id"]), "six"),
        ("\t".join(["X", QUERY, "chr1", "2", PLUS_CONTEXT, "+", "0", "0", "0"]), "six"),
        (_row(position=-1), "raw position"),
        (_row(strand="?"), "strand"),
        (_row(mismatches="x"), "mismatch count"),
        (_row(mismatches="5"), "exceeds"),
        (_row(matched="N" * 23), "matched sequence"),
        (f"{'A' * 20}NGN\tchr1\t2\t{PLUS_CONTEXT}\t+\t0", "query"),
    ],
)
def test_strict_parser_rejects_malformed_v2_id_and_v3_rows(
    tmp_path: Path,
    output: str,
    message: str,
) -> None:
    with pytest.raises(CasOffinderContractError, match=message):
        parse_cas_offinder_v241_output(
            output,
            _request(tmp_path),
            executable_sha256="d" * 64,
        )


def test_executable_missing_is_unavailable(tmp_path: Path) -> None:
    result = run_cas_offinder(
        _request(tmp_path),
        executable_path=tmp_path / "missing.exe",
    )

    assert result.status is OffTargetComputationStatus.UNAVAILABLE
    assert result.error_code == "EXECUTABLE_UNAVAILABLE"
    assert result.hit_count is None


def test_reference_missing_is_unavailable(tmp_path: Path) -> None:
    result = run_cas_offinder(
        _request(tmp_path, create_reference=False),
        executable_path=_executable(tmp_path),
    )

    assert result.status is OffTargetComputationStatus.UNAVAILABLE
    assert result.error_code == "REFERENCE_UNAVAILABLE"


def test_closed_reference_directory_accepts_only_manifested_searchable_fasta(
    tmp_path: Path,
) -> None:
    reference = _reference(tmp_path)

    validate_installed_reference(reference)


@pytest.mark.parametrize(
    "filename",
    ["unexpected.fa", "unexpected.fasta", "unexpected.fna"],
)
def test_closed_reference_directory_rejects_unmanifested_searchable_fasta(
    tmp_path: Path,
    filename: str,
) -> None:
    reference = _reference(tmp_path)
    directory = Path(reference.fasta_directory)
    (directory / filename).write_text(">extra\nACGT\n", encoding="utf-8")

    with pytest.raises(CasOffinderContractError, match="unmanifested searchable"):
        validate_installed_reference(reference)


def test_closed_reference_directory_rejects_searchable_fasta_with_other_suffix(
    tmp_path: Path,
) -> None:
    reference = _reference(tmp_path)
    directory = Path(reference.fasta_directory)
    (directory / "unexpected.data").write_text(">extra\nACGT\n", encoding="utf-8")

    with pytest.raises(CasOffinderContractError, match="unmanifested searchable"):
        validate_installed_reference(reference)


def test_closed_reference_directory_rejects_missing_or_mutated_manifest_file(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    missing_reference = _reference(missing_root)
    Path(missing_reference.fasta_directory, "assembly.fa").unlink()

    with pytest.raises(FileNotFoundError, match="unavailable or not searchable"):
        validate_installed_reference(missing_reference)

    mutated_root = tmp_path / "mutated"
    mutated_root.mkdir()
    mutated_reference = _reference(mutated_root)
    Path(mutated_reference.fasta_directory, "assembly.fa").write_text(
        ">chr1 fixture\n" + "A" * 60 + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CasOffinderContractError, match="hash mismatch"):
        validate_installed_reference(mutated_reference)


def test_non_fasta_file_does_not_change_closed_reference_identity(
    tmp_path: Path,
) -> None:
    reference = _reference(tmp_path)
    identity_before = reference.identity_sha256
    Path(reference.fasta_directory, "notes.txt").write_text(
        "local installation note\n",
        encoding="utf-8",
    )

    validate_installed_reference(reference)
    assert reference.identity_sha256 == identity_before


def test_closed_reference_validation_is_independent_of_directory_listing_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference(tmp_path)
    directory = Path(reference.fasta_directory)
    identity_before = reference.identity_sha256
    Path(directory, "notes.txt").write_text("local note\n", encoding="utf-8")
    original_iterdir = Path.iterdir

    def reversed_iterdir(path: Path):
        entries = tuple(original_iterdir(path))
        if path.resolve() == directory.resolve():
            return iter(reversed(entries))
        return iter(entries)

    monkeypatch.setattr(Path, "iterdir", reversed_iterdir)

    validate_installed_reference(reference)
    assert reference.identity_sha256 == identity_before


def test_successful_cpu_invocation_preserves_provenance_and_cleans_temp_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_runner(
        monkeypatch,
        output_text=_row() + "\n",
        execution_stdout="search complete",
        execution_stderr="fixture diagnostic",
    )
    executable = _executable(tmp_path)
    result = run_cas_offinder(
        _request(tmp_path),
        executable_path=executable,
        timeout_seconds=7,
    )

    assert result.status is OffTargetComputationStatus.COMPUTED
    assert result.hit_count == 1
    assert result.stderr == "fixture diagnostic"
    assert calls[0][0] == [str(executable.resolve())]
    assert calls[1][0] == list(result.invocation)
    assert calls[1][0][0] == str(executable.resolve())
    assert calls[1][0][2] == "C"
    assert calls[1][1]["shell"] is False
    assert not Path(calls[1][0][1]).exists()
    assert not Path(calls[1][0][3]).exists()
    assert result.temporary_paths_cleaned is True
    hit = result.hits[0]
    assert hit.reference.identity_sha256 == result.request.reference.identity_sha256
    assert hit.parameter_identity_sha256 == result.request.parameter_identity_sha256
    assert hit.input_sha256 == result.input_sha256
    assert hit.result_sha256 == result.result_sha256
    assert result.output_sha256 == hashlib.sha256(result.output_text.encode()).hexdigest()
    assert hit.result_sha256 != result.output_sha256


def test_successful_reverse_hit_is_reconstructed_from_forward_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_runner(
        monkeypatch,
        output_text=_row(
            position=29,
            matched=REVERSE_MATCHED,
            strand="-",
            mismatches="2",
        ) + "\n",
    )
    result = run_cas_offinder(
        _request(tmp_path),
        executable_path=_executable(tmp_path),
    )

    assert result.status is OffTargetComputationStatus.COMPUTED
    assert result.hits[0].strand is CrisprStrand.MINUS
    assert (result.hits[0].start, result.hits[0].end) == (29, 52)


@pytest.mark.parametrize(
    ("position", "matched", "strand"),
    [
        (2, PLUS_CONTEXT, "+"),
        (29, REVERSE_MATCHED, "-"),
    ],
)
def test_repeated_identical_rows_remain_distinct_and_parse_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    position: int,
    matched: str,
    strand: str,
) -> None:
    repeated_row = _row(position=position, matched=matched, strand=strand)
    _fake_runner(monkeypatch, output_text=repeated_row + "\n" + repeated_row + "\n")

    result = run_cas_offinder(
        _request(tmp_path),
        executable_path=_executable(tmp_path),
    )

    assert result.status is OffTargetComputationStatus.COMPUTED
    assert result.hit_count == 2
    assert [hit.raw_row_number for hit in result.hits] == [1, 2]
    assert len(
        {(hit.contig, hit.start, hit.end, hit.strand) for hit in result.hits}
    ) == 1


def test_same_sequence_at_distinct_loci_is_not_deduplicated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference_from_fasta(
        tmp_path,
        f">chr1\n{PLUS_CONTEXT}AAAA{PLUS_CONTEXT}\n",
        contigs=("chr1",),
    )
    _fake_runner(
        monkeypatch,
        output_text=_row(position=0) + "\n" + _row(position=27) + "\n",
    )

    result = run_cas_offinder(
        _request_for_reference(reference),
        executable_path=_executable(tmp_path),
    )

    assert result.status is OffTargetComputationStatus.COMPUTED
    assert [(hit.contig, hit.start) for hit in result.hits] == [
        ("chr1", 0),
        ("chr1", 27),
    ]


def test_same_start_on_distinct_contigs_is_not_deduplicated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _reference_from_fasta(
        tmp_path,
        f">chr1\n{PLUS_CONTEXT}\n>chr2\n{PLUS_CONTEXT}\n",
        contigs=("chr1", "chr2"),
    )
    _fake_runner(
        monkeypatch,
        output_text=_row(contig="chr2", position=0)
        + "\n"
        + _row(contig="chr1", position=0)
        + "\n",
    )

    result = run_cas_offinder(
        _request_for_reference(reference),
        executable_path=_executable(tmp_path),
    )

    assert result.status is OffTargetComputationStatus.COMPUTED
    assert [(hit.contig, hit.start) for hit in result.hits] == [
        ("chr1", 0),
        ("chr2", 0),
    ]


def test_zero_hits_after_success_are_computed_not_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_runner(monkeypatch, output_text="")
    result = run_cas_offinder(
        _request(tmp_path),
        executable_path=_executable(tmp_path),
    )

    assert result.status is OffTargetComputationStatus.COMPUTED
    assert result.hits == ()
    assert result.hit_count == 0


def test_opencl_runtime_failure_is_execution_failed_with_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_runner(
        monkeypatch,
        execution_returncode=2,
        execution_stderr="No OpenCL CPU device found",
    )
    result = run_cas_offinder(
        _request(tmp_path),
        executable_path=_executable(tmp_path),
    )

    assert result.status is OffTargetComputationStatus.EXECUTION_FAILED
    assert result.exit_code == 2
    assert result.stderr == "No OpenCL CPU device found"
    assert result.hit_count is None


def test_opencl_preflight_failure_is_execution_failed_not_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_runner(
        monkeypatch,
        banner=None,
        preflight_returncode=3,
        preflight_stderr="CL_PLATFORM_NOT_FOUND_KHR",
    )
    result = run_cas_offinder(
        _request(tmp_path),
        executable_path=_executable(tmp_path),
    )

    assert result.status is OffTargetComputationStatus.EXECUTION_FAILED
    assert result.error_code == "PREFLIGHT_RUNTIME_FAILED"
    assert result.stderr == "CL_PLATFORM_NOT_FOUND_KHR"


def test_timeout_is_execution_failed_and_captures_partial_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_runner(monkeypatch, execution_timeout=True)
    result = run_cas_offinder(
        _request(tmp_path),
        executable_path=_executable(tmp_path),
        timeout_seconds=0.25,
    )

    assert result.status is OffTargetComputationStatus.EXECUTION_FAILED
    assert result.error_code == "EXECUTION_TIMEOUT"
    assert result.stdout == "partial stdout"
    assert result.stderr == "OpenCL device pending"
    assert not Path(calls[1][0][1]).exists()
    assert not Path(calls[1][0][3]).exists()


def test_nonzero_exit_and_stderr_are_not_computed_zero_hits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_runner(
        monkeypatch,
        execution_returncode=9,
        execution_stdout="partial",
        execution_stderr="engine failed",
    )
    result = run_cas_offinder(
        _request(tmp_path),
        executable_path=_executable(tmp_path),
    )

    assert result.status is OffTargetComputationStatus.EXECUTION_FAILED
    assert result.exit_code == 9
    assert result.stdout == "partial"
    assert result.stderr == "engine failed"
    assert result.hit_count is None


def test_malformed_output_and_reference_inconsistency_are_parse_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_runner(monkeypatch, output_text="not\tsix\tcolumns\n")
    malformed = run_cas_offinder(
        _request(tmp_path),
        executable_path=_executable(tmp_path),
    )

    assert malformed.status is OffTargetComputationStatus.PARSE_FAILED
    assert malformed.hit_count is None

    second_root = tmp_path / "second"
    second_root.mkdir()
    _fake_runner(
        monkeypatch,
        output_text=_row(matched="T" * 23) + "\n",
    )
    inconsistent = run_cas_offinder(
        _request(second_root),
        executable_path=_executable(second_root),
    )
    assert inconsistent.status is OffTargetComputationStatus.PARSE_FAILED
    assert "reference bytes" in inconsistent.error_message


def test_wrong_engine_version_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_runner(monkeypatch, banner="Cas-OFFinder v3.0.0 (fixture)")
    result = run_cas_offinder(
        _request(tmp_path),
        executable_path=_executable(tmp_path),
    )

    assert result.status is OffTargetComputationStatus.UNAVAILABLE
    assert result.error_code == "INCOMPATIBLE_ENGINE_VERSION"


def test_not_computed_is_distinct_from_failed_computed_and_unavailable(
    tmp_path: Path,
) -> None:
    result = not_computed_result(_request(tmp_path))

    assert result.status is OffTargetComputationStatus.NOT_COMPUTED
    assert result.hit_count is None
    assert result.hits == ()
    assert set(OffTargetComputationStatus) == {
        OffTargetComputationStatus.COMPUTED,
        OffTargetComputationStatus.UNAVAILABLE,
        OffTargetComputationStatus.EXECUTION_FAILED,
        OffTargetComputationStatus.PARSE_FAILED,
        OffTargetComputationStatus.NOT_COMPUTED,
    }


def test_off_target_contract_has_no_score_rank_or_recommendation_fields() -> None:
    field_names = {field.name for field in fields(EnumeratedOffTargetHit)}

    assert not field_names.intersection(
        {
            "specificity_score",
            "risk_score",
            "overall_score",
            "rank",
            "ranking",
            "recommended",
            "recommendation",
        }
    )
