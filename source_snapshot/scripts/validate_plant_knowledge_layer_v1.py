"""Validate the Plant Knowledge Layer v1 evidence curation bundle.

The Registry is authoritative. This validator deliberately rejects sequence
content in the knowledge-layer bundle and compares every stored identity/hash
reference with the Registry and its source manifest.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "plant_knowledge_layer_v1"
BUNDLE_PATH = DATA_ROOT / "evidence_curation_v1.json"
SCHEMA_PATH = DATA_ROOT / "evidence_curation_v1.schema.json"
REGISTRY_PATH = ROOT / "data" / "plant_component_registry_v1" / "registry.batch1.json"
MANIFEST_PATH = ROOT / "data" / "plant_component_registry_v1" / "source_manifest.csv"
EXPECTED_IDS = {
    "PCLV1-PRO-35S-835",
    "PCLV1-PRO-UBQ10",
    "PCLV1-VEC-PBIN19",
    "PCLV1-PRO-UBI1",
    "PCLV1-PRO-FMVT",
    "PCLV1-CDS-NPTII",
    "PCLV1-CDS-GUSA",
    "PCLV1-CDS-CYP76AD1",
    "PCLV1-CDS-DODA1",
    "PCLV1-CDS-CDOPA5GT",
    "PCLV1-3REG-NOS-256",
    "PCLV1-3REG-NOS-253",
    "PCLV1-TER-OCS",
    "PCLV1-PRO-35S2-758",
    "PCLV1-5UTR-TEV-136",
    "PCLV1-CDS-SGFP",
    "PCLV1-3REG-CAMV35S-212",
    "PCLV1-VEC-PCSGFPBT",
    "PCLV1-TER-HSP18-2-250",
    "PCLV1-TER-RBCS-E9-295",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TOP_LEVEL_FIELDS = {"schema_version", "dataset_version", "registry_source", "records"}
REGISTRY_SOURCE_FIELDS = {"registry_path", "registry_version", "source_manifest_path"}
RECORD_FIELDS = {
    "evidence_object_id", "component_id", "display_name", "component_type",
    "registry_reference", "literature_references", "biological_context",
    "evidence_claims", "engineering_context_notes", "limitations", "review",
}
REGISTRY_REFERENCE_FIELDS = {
    "component_id", "accession", "accession_version", "sequence_length", "sequence_sha256",
    "source_record", "source_record_sha256",
}
LITERATURE_FIELDS = {"reference_id", "status", "citation", "provenance_note"}
LITERATURE_FIELDS |= {"source_database", "doi", "pmid"}
CLAIM_FIELDS = {
    "claim_id", "claim_type", "statement", "fact_status", "provenance",
    "review_status", "unknown_reason", "evidence_level",
}
REVIEW_FIELDS = {
    "record_status", "human_review_status", "reviewer", "reviewed_at_utc",
    "review_notes",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_keys(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for name, child in value.items():
            if name == key:
                found.append(child)
            found.extend(_walk_keys(child, key))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_keys(child, key))
    return found


def _check_object_shape(value: Any, allowed: set[str], required: set[str], path: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{path} must be an object"]
    errors: list[str] = []
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        errors.append(f"{path} contains unknown fields: {unknown!r}")
    if missing:
        errors.append(f"{path} is missing fields: {missing!r}")
    return errors


def _validate_schema_shape(bundle: Any) -> list[str]:
    errors = _check_object_shape(bundle, TOP_LEVEL_FIELDS, TOP_LEVEL_FIELDS, "bundle")
    if not isinstance(bundle, dict):
        return errors
    errors.extend(_check_object_shape(bundle.get("registry_source"), REGISTRY_SOURCE_FIELDS, REGISTRY_SOURCE_FIELDS, "bundle.registry_source"))
    records = bundle.get("records")
    if not isinstance(records, list):
        return errors + ["bundle.records must be an array"]
    for index, record in enumerate(records):
        path = f"bundle.records[{index}]"
        errors.extend(_check_object_shape(record, RECORD_FIELDS, RECORD_FIELDS, path))
        if not isinstance(record, dict):
            continue
        errors.extend(_check_object_shape(record.get("registry_reference"), REGISTRY_REFERENCE_FIELDS, REGISTRY_REFERENCE_FIELDS, f"{path}.registry_reference"))
        errors.extend(_check_object_shape(record.get("review"), REVIEW_FIELDS, REVIEW_FIELDS, f"{path}.review"))
        for child_index, literature in enumerate(record.get("literature_references", [])):
            errors.extend(_check_object_shape(literature, LITERATURE_FIELDS, LITERATURE_FIELDS, f"{path}.literature_references[{child_index}]"))
        for child_index, claim in enumerate(record.get("evidence_claims", [])):
            errors.extend(_check_object_shape(claim, CLAIM_FIELDS, CLAIM_FIELDS, f"{path}.evidence_claims[{child_index}]"))
    return errors


def validate() -> list[str]:
    errors: list[str] = []
    try:
        bundle = _load(BUNDLE_PATH)
        schema = _load(SCHEMA_PATH)
        registry = _load(REGISTRY_PATH)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"input read failed: {exc}"]

    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("schema must declare JSON Schema 2020-12")
    errors.extend(_validate_schema_shape(bundle))
    if bundle.get("schema_version") != "plant-knowledge-layer-evidence-v1":
        errors.append("bundle schema_version is invalid")
    if bundle.get("dataset_version") != "pkl-v1-publication-minimum-expansion-20260824-draft":
        errors.append("bundle dataset_version is invalid")
    source = bundle.get("registry_source", {})
    if source.get("registry_path") != "data/plant_component_registry_v1/registry.batch1.json":
        errors.append("Registry path does not identify the authoritative Registry batch")
    if source.get("source_manifest_path") != "data/plant_component_registry_v1/source_manifest.csv":
        errors.append("source manifest path does not identify the authoritative Registry manifest")
    if source.get("registry_version") != registry.get("registry_version"):
        errors.append("Registry version reference mismatch")

    # Exact key check prevents silently creating a second component registry or
    # omitting a Registry component from this expanded curation batch.
    if _walk_keys(bundle, "sequence"):
        errors.append("knowledge-layer bundle must not contain sequence data")
    records = bundle.get("records")
    if not isinstance(records, list):
        return errors + ["records must be a list"]
    ids = {record.get("component_id") for record in records if isinstance(record, dict)}
    if ids != EXPECTED_IDS:
        errors.append(f"curated component IDs differ from expected set: {sorted(ids)!r}")
    if len(records) != len(EXPECTED_IDS):
        errors.append(f"expanded dataset must contain exactly {len(EXPECTED_IDS)} records")

    registry_by_id = {
        record.get("component_id"): record
        for record in registry.get("records", [])
        if isinstance(record, dict)
    }
    manifest_by_id: dict[str, dict[str, str]] = {}
    try:
        with MANIFEST_PATH.open(encoding="utf-8", newline="") as handle:
            manifest_by_id = {row["component_id"]: row for row in csv.DictReader(handle)}
    except (OSError, KeyError, csv.Error) as exc:
        errors.append(f"source manifest read failed: {exc}")

    evidence_ids: set[str] = set()
    for index, record in enumerate(records):
        prefix = f"records[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        evidence_id = record.get("evidence_object_id")
        if evidence_id in evidence_ids:
            errors.append(f"duplicate evidence_object_id: {evidence_id}")
        evidence_ids.add(evidence_id)
        component_id = record.get("component_id")
        registry_record = registry_by_id.get(component_id)
        if registry_record is None:
            errors.append(f"{prefix} references missing Registry component: {component_id}")
            continue
        if record.get("component_type") != registry_record.get("component_type"):
            errors.append(f"{prefix} component_type does not match Registry")
        reference = record.get("registry_reference", {})
        for field in ("accession", "accession_version", "sequence_length", "sequence_sha256", "source_record", "source_record_sha256"):
            if reference.get(field) != registry_record.get(field):
                errors.append(f"{prefix} {field} does not match Registry")
        if reference.get("component_id") != component_id:
            errors.append(f"{prefix} registry_reference.component_id mismatch")
        context = record.get("biological_context", {})
        for field in ("source_organism", "target_host_species", "host_group"):
            if context.get(field) != registry_record.get(field):
                errors.append(f"{prefix} biological_context.{field} does not match Registry")
        if context.get("registry_component_role") != registry_record.get("component_role"):
            errors.append(f"{prefix} biological_context.registry_component_role does not match Registry")
        if context.get("registry_evidence_level") != registry_record.get("evidence_level"):
            errors.append(f"{prefix} biological_context.registry_evidence_level does not match Registry")
        if not SHA256.fullmatch(str(reference.get("sequence_sha256", ""))):
            errors.append(f"{prefix} sequence_sha256 is invalid")
        if not SHA256.fullmatch(str(reference.get("source_record_sha256", ""))):
            errors.append(f"{prefix} source_record_sha256 is invalid")
        manifest = manifest_by_id.get(component_id)
        if manifest is None:
            errors.append(f"{prefix} is absent from source manifest")
        else:
            for field in ("accession_version", "source_record", "source_record_sha256"):
                if reference.get(field) != manifest.get(field):
                    errors.append(f"{prefix} {field} does not match source manifest")
        source_path = ROOT / str(reference.get("source_record", ""))
        if not source_path.is_file():
            errors.append(f"{prefix} source record is missing: {source_path}")
        elif hashlib.sha256(source_path.read_bytes()).hexdigest() != reference.get("source_record_sha256"):
            errors.append(f"{prefix} source record SHA-256 mismatch")

        review = record.get("review", {})
        if review.get("record_status") != "DRAFT":
            errors.append(f"{prefix} must remain DRAFT")
        if review.get("human_review_status") != "PENDING_HUMAN_REVIEW":
            errors.append(f"{prefix} must remain pending human review")
        if review.get("reviewer") is not None or review.get("reviewed_at_utc") is not None:
            errors.append(f"{prefix} cannot contain completed review identity")
        for claim in record.get("evidence_claims", []):
            if not claim.get("unknown_reason", "").strip():
                errors.append(f"{prefix} claim lacks explicit unknown_reason")
            if claim.get("review_status") not in {"DRAFT", "PENDING_HUMAN_REVIEW"}:
                errors.append(f"{prefix} claim has an invalid review status")
            if claim.get("evidence_level") not in {"E1", "E2", "UNKNOWN"}:
                errors.append(f"{prefix} claim has an invalid evidence level")
        for literature in record.get("literature_references", []):
            if not literature.get("source_database", "").strip():
                errors.append(f"{prefix} literature reference lacks source database")
            if literature.get("status") == "RECORDED" and not literature.get("citation"):
                errors.append(f"{prefix} recorded literature reference lacks citation")
            if literature.get("status") == "UNKNOWN" and literature.get("citation") is not None:
                errors.append(f"{prefix} UNKNOWN literature reference must have null citation")

    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        print("Plant Knowledge Layer v1 validation failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        raise SystemExit(1)
    print(f"Plant Knowledge Layer v1 validation passed: {len(EXPECTED_IDS)} Registry-linked draft evidence objects.")
