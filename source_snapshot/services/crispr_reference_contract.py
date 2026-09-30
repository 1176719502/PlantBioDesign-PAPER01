"""Typed identity contract for a user-installed CRISPR reference.

The contract identifies reference content by assembly metadata, a normalized
local directory, a deterministic FASTA manifest, and installation provenance.
A path by itself is deliberately not a reference identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
V1_FASTA_SUFFIXES = (".fa", ".fasta", ".fna")


class CrisprReferenceContractError(ValueError):
    """Raised when an installed reference cannot enter the typed contract."""


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_text(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CrisprReferenceContractError(
            f"{field_name} must be a non-empty string"
        )
    if any(character in value for character in ("\r", "\n", "\t")):
        raise CrisprReferenceContractError(
            f"{field_name} must not contain tabs or newlines"
        )


def _require_sha256(field_name: str, value: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CrisprReferenceContractError(
            f"{field_name} must be a lowercase 64-character SHA-256"
        )


def _normalize_directory(value: str | Path) -> str:
    path = Path(value).expanduser().resolve(strict=False)
    if not path.is_absolute():
        raise CrisprReferenceContractError("fasta_directory must be absolute")
    normalized = str(path)
    if any(character in normalized for character in ("\r", "\n")):
        raise CrisprReferenceContractError(
            "fasta_directory must not contain newlines"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class ReferenceFastaFile:
    """One immutable FASTA file admitted by the installed manifest."""

    relative_path: str
    sha256: str
    contigs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text("relative_path", self.relative_path)
        path = PurePosixPath(self.relative_path.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
            raise CrisprReferenceContractError(
                "relative_path must stay inside fasta_directory"
            )
        if path.as_posix() != self.relative_path:
            raise CrisprReferenceContractError(
                "relative_path must use normalized POSIX separators"
            )
        if len(path.parts) != 1:
            raise CrisprReferenceContractError(
                "relative_path must name a top-level FASTA searched by Cas-OFFinder"
            )
        if path.suffix.lower() not in V1_FASTA_SUFFIXES:
            raise CrisprReferenceContractError(
                "relative_path must use a V1 FASTA suffix: .fa, .fasta, or .fna"
            )
        _require_sha256("sha256", self.sha256)
        if not isinstance(self.contigs, tuple) or not self.contigs:
            raise CrisprReferenceContractError(
                "contigs must be a non-empty tuple"
            )
        for contig in self.contigs:
            _require_text("contig", contig)
            if any(character.isspace() for character in contig):
                raise CrisprReferenceContractError(
                    "contig identifiers must not contain whitespace"
                )
        if len(set(self.contigs)) != len(self.contigs):
            raise CrisprReferenceContractError("contigs must be unique per FASTA")
        if tuple(sorted(self.contigs)) != self.contigs:
            raise CrisprReferenceContractError(
                "contigs must use deterministic lexical order"
            )

    @property
    def manifest_payload(self) -> dict[str, Any]:
        return {
            "contigs": list(self.contigs),
            "relative_path": self.relative_path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class InstalledReferenceIdentity:
    """Immutable identity for a user-installed reference FASTA directory."""

    organism_scientific_name: str
    taxonomy_id: str | None
    provider: str
    assembly_accession: str
    assembly_version: str
    fasta_directory: str
    fasta_files: tuple[ReferenceFastaFile, ...]
    manifest_sha256: str
    installation_provenance: str
    identity_sha256: str

    @classmethod
    def build(
        cls,
        *,
        organism_scientific_name: str,
        taxonomy_id: str | None,
        provider: str,
        assembly_accession: str,
        assembly_version: str,
        fasta_directory: str | Path,
        fasta_files: Iterable[ReferenceFastaFile],
        installation_provenance: str,
    ) -> "InstalledReferenceIdentity":
        files = tuple(sorted(fasta_files, key=lambda item: item.relative_path))
        directory = _normalize_directory(fasta_directory)
        manifest_sha256 = cls.calculate_manifest_sha256(files)
        identity_sha256 = cls.calculate_identity_sha256(
            organism_scientific_name=organism_scientific_name,
            taxonomy_id=taxonomy_id,
            provider=provider,
            assembly_accession=assembly_accession,
            assembly_version=assembly_version,
            fasta_directory=directory,
            manifest_sha256=manifest_sha256,
            installation_provenance=installation_provenance,
        )
        return cls(
            organism_scientific_name=organism_scientific_name,
            taxonomy_id=taxonomy_id,
            provider=provider,
            assembly_accession=assembly_accession,
            assembly_version=assembly_version,
            fasta_directory=directory,
            fasta_files=files,
            manifest_sha256=manifest_sha256,
            installation_provenance=installation_provenance,
            identity_sha256=identity_sha256,
        )

    @staticmethod
    def calculate_manifest_sha256(
        fasta_files: tuple[ReferenceFastaFile, ...],
    ) -> str:
        return _canonical_sha256(
            [item.manifest_payload for item in fasta_files]
        )

    @staticmethod
    def calculate_identity_sha256(
        *,
        organism_scientific_name: str,
        taxonomy_id: str | None,
        provider: str,
        assembly_accession: str,
        assembly_version: str,
        fasta_directory: str,
        manifest_sha256: str,
        installation_provenance: str,
    ) -> str:
        return _canonical_sha256(
            {
                "assembly_accession": assembly_accession,
                "assembly_version": assembly_version,
                "fasta_directory": fasta_directory,
                "installation_provenance": installation_provenance,
                "manifest_sha256": manifest_sha256,
                "organism_scientific_name": organism_scientific_name,
                "provider": provider,
                "taxonomy_id": taxonomy_id,
            }
        )

    def __post_init__(self) -> None:
        for field_name in (
            "organism_scientific_name",
            "provider",
            "assembly_accession",
            "assembly_version",
            "installation_provenance",
        ):
            _require_text(field_name, getattr(self, field_name))
        if self.taxonomy_id is not None:
            _require_text("taxonomy_id", self.taxonomy_id)
            if not self.taxonomy_id.isdecimal():
                raise CrisprReferenceContractError(
                    "taxonomy_id must contain decimal digits when supplied"
                )
        if self.fasta_directory != _normalize_directory(self.fasta_directory):
            raise CrisprReferenceContractError(
                "fasta_directory must be normalized and absolute"
            )
        if not isinstance(self.fasta_files, tuple) or not self.fasta_files:
            raise CrisprReferenceContractError(
                "fasta_files must be a non-empty tuple"
            )
        if not all(isinstance(item, ReferenceFastaFile) for item in self.fasta_files):
            raise CrisprReferenceContractError(
                "fasta_files must contain ReferenceFastaFile records"
            )
        if tuple(sorted(self.fasta_files, key=lambda item: item.relative_path)) != self.fasta_files:
            raise CrisprReferenceContractError(
                "fasta_files must use deterministic relative-path order"
            )
        paths = [item.relative_path for item in self.fasta_files]
        if len(set(paths)) != len(paths):
            raise CrisprReferenceContractError(
                "fasta_files must have unique relative paths"
            )
        contigs = [contig for item in self.fasta_files for contig in item.contigs]
        if len(set(contigs)) != len(contigs):
            raise CrisprReferenceContractError(
                "contig identifiers must be unique across the manifest"
            )
        _require_sha256("manifest_sha256", self.manifest_sha256)
        _require_sha256("identity_sha256", self.identity_sha256)
        expected_manifest = self.calculate_manifest_sha256(self.fasta_files)
        if self.manifest_sha256 != expected_manifest:
            raise CrisprReferenceContractError(
                "manifest_sha256 is inconsistent with fasta_files"
            )
        expected_identity = self.calculate_identity_sha256(
            organism_scientific_name=self.organism_scientific_name,
            taxonomy_id=self.taxonomy_id,
            provider=self.provider,
            assembly_accession=self.assembly_accession,
            assembly_version=self.assembly_version,
            fasta_directory=self.fasta_directory,
            manifest_sha256=self.manifest_sha256,
            installation_provenance=self.installation_provenance,
        )
        if self.identity_sha256 != expected_identity:
            raise CrisprReferenceContractError(
                "identity_sha256 is inconsistent with reference identity fields"
            )

    @property
    def contig_to_relative_path(self) -> dict[str, str]:
        return {
            contig: item.relative_path
            for item in self.fasta_files
            for contig in item.contigs
        }


__all__ = [
    "CrisprReferenceContractError",
    "InstalledReferenceIdentity",
    "ReferenceFastaFile",
    "V1_FASTA_SUFFIXES",
]
