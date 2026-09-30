from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path

import pytest

from services.crispr_reference_contract import (
    CrisprReferenceContractError,
    InstalledReferenceIdentity,
    ReferenceFastaFile,
    V1_FASTA_SUFFIXES,
)


def _manifest_file() -> ReferenceFastaFile:
    return ReferenceFastaFile(
        relative_path="assembly.fa",
        sha256=hashlib.sha256(b">chr1\nACGT\n").hexdigest(),
        contigs=("chr1",),
    )


def _reference(tmp_path: Path) -> InstalledReferenceIdentity:
    return InstalledReferenceIdentity.build(
        organism_scientific_name="Arabidopsis thaliana",
        taxonomy_id="3702",
        provider="fixture-provider",
        assembly_accession="GCF_000001735.4",
        assembly_version="TAIR10.1",
        fasta_directory=tmp_path / "reference",
        fasta_files=(_manifest_file(),),
        installation_provenance="user-installed fixture manifest",
    )


def test_valid_reference_identity_is_typed_and_deterministic(tmp_path: Path) -> None:
    first = _reference(tmp_path)
    second = _reference(tmp_path)

    assert first == second
    assert Path(first.fasta_directory).is_absolute()
    assert len(first.manifest_sha256) == 64
    assert len(first.identity_sha256) == 64
    assert first.contig_to_relative_path == {"chr1": "assembly.fa"}
    assert V1_FASTA_SUFFIXES == (".fa", ".fasta", ".fna")


def test_reference_identity_is_independent_of_manifest_input_order(
    tmp_path: Path,
) -> None:
    first_file = ReferenceFastaFile(
        relative_path="a.fa",
        sha256=hashlib.sha256(b">chrA\nAAAA\n").hexdigest(),
        contigs=("chrA",),
    )
    second_file = ReferenceFastaFile(
        relative_path="b.fna",
        sha256=hashlib.sha256(b">chrB\nCCCC\n").hexdigest(),
        contigs=("chrB",),
    )
    values = {
        "organism_scientific_name": "Arabidopsis thaliana",
        "taxonomy_id": "3702",
        "provider": "fixture-provider",
        "assembly_accession": "GCF_000001735.4",
        "assembly_version": "TAIR10.1",
        "fasta_directory": tmp_path / "reference",
        "installation_provenance": "user-installed fixture manifest",
    }

    forward = InstalledReferenceIdentity.build(
        **values, fasta_files=(first_file, second_file)
    )
    reversed_input = InstalledReferenceIdentity.build(
        **values, fasta_files=(second_file, first_file)
    )

    assert forward.fasta_files == reversed_input.fasta_files
    assert forward.manifest_sha256 == reversed_input.manifest_sha256
    assert forward.identity_sha256 == reversed_input.identity_sha256


def test_reference_content_hash_change_creates_a_new_governed_identity(
    tmp_path: Path,
) -> None:
    original = _reference(tmp_path)
    changed_file = replace(
        original.fasta_files[0],
        sha256=hashlib.sha256(b">chr1\nTGCA\n").hexdigest(),
    )
    changed = InstalledReferenceIdentity.build(
        organism_scientific_name=original.organism_scientific_name,
        taxonomy_id=original.taxonomy_id,
        provider=original.provider,
        assembly_accession=original.assembly_accession,
        assembly_version=original.assembly_version,
        fasta_directory=original.fasta_directory,
        fasta_files=(changed_file,),
        installation_provenance=original.installation_provenance,
    )

    assert changed.manifest_sha256 != original.manifest_sha256
    assert changed.identity_sha256 != original.identity_sha256


@pytest.mark.parametrize("field_name", ["assembly_accession", "assembly_version"])
def test_missing_accession_or_version_is_rejected(
    tmp_path: Path,
    field_name: str,
) -> None:
    values = {
        "organism_scientific_name": "Arabidopsis thaliana",
        "taxonomy_id": "3702",
        "provider": "fixture-provider",
        "assembly_accession": "GCF_000001735.4",
        "assembly_version": "TAIR10.1",
        "fasta_directory": tmp_path / "reference",
        "fasta_files": (_manifest_file(),),
        "installation_provenance": "user-installed fixture manifest",
    }
    values[field_name] = ""

    with pytest.raises(CrisprReferenceContractError, match=field_name):
        InstalledReferenceIdentity.build(**values)


@pytest.mark.parametrize("invalid_hash", ["", "A" * 64, "0" * 63, "z" * 64])
def test_invalid_fasta_hash_is_rejected(invalid_hash: str) -> None:
    with pytest.raises(CrisprReferenceContractError, match="SHA-256"):
        ReferenceFastaFile(
            relative_path="assembly.fa",
            sha256=invalid_hash,
            contigs=("chr1",),
        )


def test_inconsistent_manifest_hash_is_rejected(tmp_path: Path) -> None:
    reference = _reference(tmp_path)

    with pytest.raises(CrisprReferenceContractError, match="manifest_sha256"):
        replace(reference, manifest_sha256="0" * 64)


def test_inconsistent_reference_identity_is_rejected(tmp_path: Path) -> None:
    reference = _reference(tmp_path)

    with pytest.raises(CrisprReferenceContractError, match="identity_sha256"):
        replace(reference, assembly_version="unexpected-version")


def test_path_alone_cannot_form_a_reference_identity(tmp_path: Path) -> None:
    with pytest.raises(CrisprReferenceContractError, match="assembly_accession"):
        InstalledReferenceIdentity.build(
            organism_scientific_name="Arabidopsis thaliana",
            taxonomy_id="3702",
            provider="fixture-provider",
            assembly_accession="",
            assembly_version="",
            fasta_directory=tmp_path / "reference",
            fasta_files=(_manifest_file(),),
            installation_provenance="user-installed fixture manifest",
        )


def test_unsafe_or_inconsistent_manifest_paths_and_contigs_are_rejected() -> None:
    with pytest.raises(CrisprReferenceContractError, match="stay inside"):
        ReferenceFastaFile(
            relative_path="../assembly.fa",
            sha256="0" * 64,
            contigs=("chr1",),
        )
    with pytest.raises(CrisprReferenceContractError, match="lexical order"):
        ReferenceFastaFile(
            relative_path="assembly.fa",
            sha256="0" * 64,
            contigs=("chr2", "chr1"),
        )


@pytest.mark.parametrize("relative_path", ["assembly.txt", "nested/assembly.fa"])
def test_manifest_rejects_files_outside_the_v1_searchable_name_contract(
    relative_path: str,
) -> None:
    with pytest.raises(CrisprReferenceContractError, match="top-level|V1 FASTA suffix"):
        ReferenceFastaFile(
            relative_path=relative_path,
            sha256="0" * 64,
            contigs=("chr1",),
        )
