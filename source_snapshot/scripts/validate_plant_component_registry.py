"""Offline integrity checks for the versioned plant component registry."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ROOT = ROOT / "data" / "plant_component_registry_v1"
DNA = re.compile(r"^[ACGTN]+$")
ACCESSION = re.compile(r"^[A-Z]{1,4}[0-9]{5,8}(?:\.[0-9]+)$")
REQUIRED_FIELDS = {
    "schema_version",
    "component_id",
    "display_name",
    "component_type",
    "component_role",
    "sequence",
    "sequence_length",
    "sequence_sha256",
    "source_organism",
    "target_host_species",
    "host_group",
    "accession",
    "accession_version",
    "plasmid_id",
    "primary_reference",
    "evidence_level",
    "evidence_context",
    "feature_boundary_method",
    "source_record",
    "source_record_sha256",
    "redistribution_status",
    "workflow_fit",
    "aliases",
    "limitations",
    "review_status",
    "notes",
}
REVIEW_STATUSES = {
    "source_and_boundary_reviewed",
    "source_sequence_reviewed_context_limited",
    "manual_context_review_required",
}
NOS_RELATED_IDS = {
    "PCLV1-3REG-NOS-256": "PCLV1-3REG-NOS-253",
    "PCLV1-3REG-NOS-253": "PCLV1-3REG-NOS-256",
}


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def fasta_sequence(path: Path) -> str:
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines or not lines[0].startswith(">"):
        raise ValueError(f"{path.relative_to(ROOT)} is not a one-record FASTA")
    sequence = "".join(lines[1:])
    if any(line.startswith(">") for line in lines[1:]):
        raise ValueError(f"{path.relative_to(ROOT)} contains multiple FASTA records")
    return sequence


def source_feature_sequence(source_path: Path, boundary: dict[str, object]) -> str:
    record = SeqIO.read(source_path, "genbank")
    start = int(boundary["start_one_based"])
    end = int(boundary["end_one_based_inclusive"])
    if start < 1 or end < 1 or start > len(record.seq) or end > len(record.seq):
        raise ValueError(f"{source_path.relative_to(ROOT)} boundary is outside source record")
    if boundary.get("crosses_origin"):
        extracted = record.seq[start - 1 :] + record.seq[:end]
    elif start <= end:
        extracted = record.seq[start - 1 : end]
    else:
        raise ValueError(f"{source_path.relative_to(ROOT)} non-crossing boundary is reversed")
    if boundary.get("reverse_complemented"):
        extracted = extracted.reverse_complement()
    return str(extracted).upper()


def validate() -> list[str]:
    errors: list[str] = []
    registry_path = REGISTRY_ROOT / "registry.batch1.json"
    schema_path = REGISTRY_ROOT / "registry.schema.json"
    manifest_path = REGISTRY_ROOT / "source_manifest.csv"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [str(exc)]

    if schema.get("required") != ["registry_version", "records"]:
        errors.append("schema must require registry_version and records")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        return errors + ["registry records must be a non-empty list"]

    ids: set[str] = set()
    hashes: set[str] = set()
    canonical_sequences: dict[str, str] = {}
    manifest_rows: dict[str, dict[str, str]] = {}
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            manifest_rows[row["component_id"]] = row

    for record in records:
        component_id = record.get("component_id", "<missing>")
        missing = REQUIRED_FIELDS - set(record)
        if missing:
            errors.append(f"{component_id}: missing fields {sorted(missing)}")
            continue
        if component_id in ids:
            errors.append(f"duplicate component_id: {component_id}")
        ids.add(component_id)
        sequence = record["sequence"]
        if not isinstance(sequence, str) or sequence != sequence.upper() or not DNA.fullmatch(sequence):
            errors.append(f"{component_id}: sequence is not normalized DNA")
        if record["sequence_length"] != len(sequence):
            errors.append(f"{component_id}: sequence length mismatch")
        observed_hash = digest_text(sequence)
        if record["sequence_sha256"] != observed_hash:
            errors.append(f"{component_id}: sequence SHA-256 mismatch")
        if observed_hash in hashes:
            errors.append(f"duplicate sequence SHA-256: {observed_hash}")
        hashes.add(observed_hash)
        canonical_sequence = min(sequence, str(Seq(sequence).reverse_complement()))
        if canonical_sequence in canonical_sequences:
            errors.append(
                f"duplicate sequence including reverse complement: "
                f"{canonical_sequences[canonical_sequence]} and {component_id}"
            )
        canonical_sequences[canonical_sequence] = component_id
        if record["evidence_level"] not in {"E1", "E2"}:
            errors.append(f"{component_id}: non-E1/E2 record in registry")
        if record["review_status"] not in REVIEW_STATUSES:
            errors.append(f"{component_id}: unsupported review status")
        for text_field in ("primary_reference", "evidence_context", "limitations"):
            if not isinstance(record[text_field], str) or not record[text_field].strip():
                errors.append(f"{component_id}: {text_field} must be non-empty")
        if not ACCESSION.fullmatch(record["accession_version"]):
            errors.append(f"{component_id}: accession_version is invalid")
        if not record["source_organism"] or not isinstance(record["target_host_species"], list):
            errors.append(f"{component_id}: source organism or target hosts missing")
        if not isinstance(record["host_group"], list) or any(
            value in record["target_host_species"] for value in record["host_group"]
        ):
            errors.append(f"{component_id}: host_group must be separate from species")
        elif not record["target_host_species"] and not record["host_group"]:
            errors.append(f"{component_id}: host/species relevance is missing")
        source_path = ROOT / record["source_record"]
        if source_path.resolve().is_relative_to(ROOT.resolve()) is False or not source_path.is_file():
            errors.append(f"{component_id}: source record is missing or outside repository")
        elif hashlib.sha256(source_path.read_bytes()).hexdigest() != record["source_record_sha256"]:
            errors.append(f"{component_id}: source record SHA-256 mismatch")
        else:
            boundary = record["feature_boundary_method"]
            required_boundary_fields = {
                "method",
                "feature_type",
                "feature_label",
                "strand",
                "start_one_based",
                "end_one_based_inclusive",
                "crosses_origin",
                "reverse_complemented",
                "extraction",
            }
            if not isinstance(boundary, dict) or required_boundary_fields - set(boundary):
                errors.append(f"{component_id}: incomplete feature boundary metadata")
            elif boundary["strand"] not in {"+", "-"}:
                errors.append(f"{component_id}: feature strand must be + or -")
            else:
                try:
                    if source_feature_sequence(source_path, boundary) != sequence:
                        errors.append(f"{component_id}: source boundary extraction mismatch")
                except (OSError, ValueError) as exc:
                    errors.append(str(exc))
        fasta_path = REGISTRY_ROOT / "sequences" / f"{component_id}.fasta"
        try:
            if fasta_sequence(fasta_path) != sequence:
                errors.append(f"{component_id}: FASTA sequence mismatch")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            errors.append(str(exc))
        if component_id not in manifest_rows:
            errors.append(f"{component_id}: source manifest entry missing")
        else:
            manifest_row = manifest_rows[component_id]
            for field in (
                "accession_version",
                "source_record",
                "source_record_sha256",
                "evidence_level",
                "redistribution_status",
            ):
                if manifest_row.get(field) != str(record[field]):
                    errors.append(f"{component_id}: source manifest {field} mismatch")

        if component_id in NOS_RELATED_IDS:
            related = record.get("related_records")
            expected_related_id = NOS_RELATED_IDS[component_id]
            if not isinstance(related, list) or len(related) != 1:
                errors.append(f"{component_id}: NOS relationship metadata must contain one record")
            else:
                relationship = related[0]
                if relationship.get("component_id") != expected_related_id:
                    errors.append(f"{component_id}: NOS related component ID mismatch")
                if relationship.get("relationship_type") != "related_locus_source_variant":
                    errors.append(f"{component_id}: NOS relationship type mismatch")
                if relationship.get("shared_accession_version") != "AF485783.1":
                    errors.append(f"{component_id}: NOS shared accession mismatch")
                if "not as independent biological diversity" not in str(
                    relationship.get("diversity_interpretation", "")
                ):
                    errors.append(f"{component_id}: NOS diversity interpretation is missing")

        if component_id == "PCLV1-VEC-PBIN19":
            context = record.get("vector_context", {})
            if record["sequence_length"] != 11777:
                errors.append("PCLV1-VEC-PBIN19: complete vector source must be 11777 bp")
            if context.get("t_dna_region") != {
                "start_one_based": 6043,
                "end_one_based_inclusive": 9421,
                "length": 3379,
                "crosses_origin": False,
            }:
                errors.append("PCLV1-VEC-PBIN19: T-DNA region metadata mismatch")
            non_t_dna = context.get("non_t_dna_backbone", {})
            if non_t_dna.get("length") != 8398 or non_t_dna.get("crosses_origin") is not True:
                errors.append("PCLV1-VEC-PBIN19: non-T-DNA backbone metadata mismatch")
            cassette = context.get("plant_selectable_cassette", {})
            if cassette.get("start_one_based") != 7501 or cassette.get("end_one_based_inclusive") != 9259:
                errors.append("PCLV1-VEC-PBIN19: plant selectable cassette metadata mismatch")

    if set(manifest_rows) != ids:
        errors.append("source manifest does not cover exactly the registry records")
    registry_by_id = {
        str(record.get("component_id")): record
        for record in records
        if isinstance(record, dict)
    }
    nos_256 = str(registry_by_id.get("PCLV1-3REG-NOS-256", {}).get("sequence", ""))
    nos_253 = str(registry_by_id.get("PCLV1-3REG-NOS-253", {}).get("sequence", ""))
    if not nos_256.startswith(nos_253) or len(nos_256) - len(nos_253) != 3:
        errors.append("NOS 253/256 sequence relationship is not the documented three-base suffix difference")
    denylist_names = {".git", "restricted", "paper.pdf", "web_snapshot"}
    for path in REGISTRY_ROOT.rglob("*"):
        if path.name.lower() in denylist_names:
            errors.append(f"denylisted file or directory: {path.relative_to(ROOT)}")
    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        print("Registry validation failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        raise SystemExit(1)
    print("Plant component registry validation passed.")
