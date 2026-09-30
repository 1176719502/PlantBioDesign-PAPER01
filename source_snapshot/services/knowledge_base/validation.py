from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from services.knowledge_base.constants import (
    ACTOR_TYPES,
    CONTEXT_STATES,
    CONTRACT_VERSION,
    ENTITY_TYPES,
    FACT_CLASSES,
    IMPORT_SCHEMA_VERSION,
    LIFECYCLE_STATES,
    REVIEW_STATES,
)
from services.knowledge_base.errors import KnowledgeBuildError


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_KEY_RE = re.compile(r"^kb:[a-z][a-z0-9-]*:[a-z0-9][a-z0-9._-]*$")

ROOT_FIELDS = {
    "schema_version",
    "contract_version",
    "dataset_version",
    "release",
    "template_notice",
    "records",
    "relationships",
    "review_events",
    "builder_requirements",
}
RELEASE_FIELDS = {
    "release_id",
    "release_status",
    "source_bundle_sha256",
    "built_at_utc",
    "approved_by",
    "approved_at_utc",
}
METADATA_FIELDS = {
    "revision",
    "lifecycle_status",
    "created_by",
    "created_by_actor_type",
    "created_at_utc",
    "change_reason",
    "supersedes_revision",
}
METADATA_REQUIRED = METADATA_FIELDS - {"supersedes_revision"}

RECORD_FIELDS: dict[str, set[str]] = {
    "paper": {"paper_key", "title", "publication_year", "journal_or_repository", "doi_normalized", "pmid", "pmcid", "publication_status", "metadata"},
    "source_reference": {"source_reference_key", "source_kind", "provider", "source_record_id", "source_version", "source_uri", "source_title", "content_sha256", "license_or_access_status", "acquired_at_utc", "immutable_identity_sha256", "paper_key", "metadata"},
    "organism": {"organism_key", "scientific_name", "taxonomy_id", "strain_cultivar_ecotype", "common_name", "metadata"},
    "tissue": {"tissue_key", "organism_key", "tissue_name", "ontology_id", "developmental_stage", "metadata"},
    "experiment": {"experiment_key", "paper_key", "experiment_label", "experiment_type", "organism_key", "tissue_key", "developmental_stage", "genotype_or_background", "treatment_context", "assay_context", "condition", "context_completeness", "metadata"},
    "design_case": {"design_case_key", "case_label", "case_type", "case_summary", "review_boundary", "metadata"},
    "construct": {"construct_key", "construct_label", "construct_type", "topology", "sequence_availability", "sequence_sha256", "sequence_length", "source_reference_key", "metadata"},
    "transcription_unit": {"transcription_unit_key", "construct_key", "unit_label", "unit_order", "orientation", "sequence_sha256", "sequence_length", "metadata"},
    "component": {"component_key", "component_name", "component_type", "source_organism_key", "sequence_availability", "sequence_sha256", "sequence_length", "source_reference_key", "metadata"},
    "component_evidence": {"component_evidence_key", "component_key", "evidence_claim_key", "evidence_role", "metadata"},
    "metabolite": {"metabolite_key", "preferred_name", "chebi_id", "inchikey", "formula", "metadata"},
    "measurement": {"measurement_key", "experiment_key", "metabolite_key", "measured_entity_key", "measurement_type", "value_numeric", "value_text", "unit", "uncertainty_numeric", "replicate_count", "normalization_basis", "timepoint", "source_reference_key", "metadata"},
    "accession": {"accession_key", "accession_system", "accession_value", "accession_version", "record_type", "source_reference_key", "referenced_entity_key", "metadata"},
    "evidence_level": {"evidence_level_key", "level_code", "rank_ordinal", "definition", "minimum_source_requirements", "permits_runtime_use", "permits_registry_consideration", "metadata"},
    "evidence_claim": {"evidence_claim_key", "subject_entity_key", "predicate", "object", "fact_class", "unknown_reason", "provenance_method", "evidence_type", "evidence_level_key", "context", "review", "eligibility", "metadata"},
    "applicability_scope": {"applicability_scope_key", "scope_mode", "organism_key", "tissue_key", "experiment_key", "developmental_stage", "condition", "scope_note", "metadata"},
    "limitation": {"limitation_key", "limitation_type", "limitation_text", "severity", "resolution_status", "metadata"},
}

KEY_FIELDS = {
    "paper": "paper_key",
    "source_reference": "source_reference_key",
    "organism": "organism_key",
    "tissue": "tissue_key",
    "experiment": "experiment_key",
    "design_case": "design_case_key",
    "construct": "construct_key",
    "transcription_unit": "transcription_unit_key",
    "component": "component_key",
    "component_evidence": "component_evidence_key",
    "metabolite": "metabolite_key",
    "measurement": "measurement_key",
    "accession": "accession_key",
    "evidence_claim": "evidence_claim_key",
    "evidence_level": "evidence_level_key",
    "applicability_scope": "applicability_scope_key",
    "limitation": "limitation_key",
}

LABEL_FIELDS = {
    "paper": "title",
    "source_reference": "source_title",
    "organism": "scientific_name",
    "tissue": "tissue_name",
    "experiment": "experiment_label",
    "design_case": "case_label",
    "construct": "construct_label",
    "transcription_unit": "unit_label",
    "component": "component_name",
    "component_evidence": "evidence_role",
    "metabolite": "preferred_name",
    "measurement": "measurement_type",
    "accession": "accession_value",
    "evidence_claim": "predicate",
    "evidence_level": "level_code",
    "applicability_scope": "scope_note",
    "limitation": "limitation_text",
}

RELATIONSHIP_FIELDS: dict[str, set[str]] = {
    "design_case_paper": {"design_case_key", "paper_key", "relationship_type"},
    "design_case_experiment": {"design_case_key", "experiment_key", "relationship_type"},
    "design_case_construct": {"design_case_key", "construct_key", "relationship_type"},
    "transcription_unit_component": {"transcription_unit_key", "component_key", "component_order", "biological_role", "orientation", "start_zero_based", "end_zero_based_exclusive"},
    "claim_source": {"evidence_claim_key", "source_reference_key", "source_role", "location_type", "location_value", "source_excerpt_sha256"},
    "claim_applicability_scope": {"evidence_claim_key", "applicability_scope_key"},
    "claim_limitation": {"evidence_claim_key", "limitation_key"},
    "claim_conflict": {"conflict_key", "evidence_claim_key", "conflict_role", "conflict_type", "resolution_status", "resolution_note"},
}

REFERENCE_FIELDS: dict[str, dict[str, str | None]] = {
    "source_reference": {"paper_key": "paper"},
    "tissue": {"organism_key": "organism"},
    "experiment": {"paper_key": "paper", "organism_key": "organism", "tissue_key": "tissue"},
    "construct": {"source_reference_key": "source_reference"},
    "transcription_unit": {"construct_key": "construct"},
    "component": {"source_organism_key": "organism", "source_reference_key": "source_reference"},
    "component_evidence": {"component_key": "component", "evidence_claim_key": "evidence_claim"},
    "measurement": {"experiment_key": "experiment", "metabolite_key": "metabolite", "measured_entity_key": None, "source_reference_key": "source_reference"},
    "accession": {"source_reference_key": "source_reference", "referenced_entity_key": None},
    "evidence_claim": {"subject_entity_key": None, "evidence_level_key": "evidence_level"},
    "applicability_scope": {"organism_key": "organism", "tissue_key": "tissue", "experiment_key": "experiment"},
}

RELATIONSHIP_REFERENCES: dict[str, dict[str, str]] = {
    "design_case_paper": {"design_case_key": "design_case", "paper_key": "paper"},
    "design_case_experiment": {"design_case_key": "design_case", "experiment_key": "experiment"},
    "design_case_construct": {"design_case_key": "design_case", "construct_key": "construct"},
    "transcription_unit_component": {"transcription_unit_key": "transcription_unit", "component_key": "component"},
    "claim_source": {"evidence_claim_key": "evidence_claim", "source_reference_key": "source_reference"},
    "claim_applicability_scope": {"evidence_claim_key": "evidence_claim", "applicability_scope_key": "applicability_scope"},
    "claim_limitation": {"evidence_claim_key": "evidence_claim", "limitation_key": "limitation"},
    "claim_conflict": {"evidence_claim_key": "evidence_claim"},
}

RELATIONSHIP_VALUE_SETS: dict[str, dict[str, set[str]]] = {
    "design_case_paper": {
        "relationship_type": {"PRIMARY_REPORT", "SUPPORTING_REPORT", "REVIEW", "CONFLICTING_REPORT"}
    },
    "design_case_experiment": {
        "relationship_type": {"PRIMARY", "SUPPORTING", "COMPARATOR", "CONFLICTING"}
    },
    "design_case_construct": {
        "relationship_type": {"TESTED", "RECONSTRUCTED", "REFERENCE", "COMPARATOR"}
    },
    "transcription_unit_component": {"orientation": {"FORWARD", "REVERSE", "UNKNOWN"}},
    "claim_source": {
        "source_role": {"PRIMARY", "SUPPORTING", "CONFLICTING", "DERIVATION_INPUT"},
        "location_type": {"PAGE", "SECTION", "FIGURE", "TABLE", "SUPPLEMENT", "ACCESSION_FEATURE", "COORDINATE", "JSON_POINTER", "FILE_OFFSET", "WHOLE_RECORD", "UNKNOWN"},
    },
    "claim_conflict": {
        "conflict_role": {"CLAIM_A", "CLAIM_B", "ADDITIONAL"},
        "conflict_type": {"DIRECT_CONTRADICTION", "CONTEXT_MISMATCH", "MEASUREMENT_DISAGREEMENT", "SOURCE_VERSION_MISMATCH", "DUPLICATE_INTERPRETATION"},
        "resolution_status": {"OPEN", "HUMAN_RESOLVED", "UNRESOLVED"},
    },
}


@dataclass(frozen=True)
class ValidatedBundle:
    payload: dict[str, Any]
    source_bundle_sha256: str
    entity_types: dict[str, str]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise KnowledgeBuildError(f"{path} must be an object")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise KnowledgeBuildError(f"{path} must be an array")
    return value


def _fields(
    value: Mapping[str, Any],
    *,
    allowed: set[str],
    required: set[str] | None = None,
    path: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise KnowledgeBuildError(f"{path} contains unknown fields: {', '.join(unknown)}")
    missing = sorted((required if required is not None else allowed) - set(value))
    if missing:
        raise KnowledgeBuildError(f"{path} is missing fields: {', '.join(missing)}")


def _text(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        qualifier = "text" if allow_empty else "non-empty text"
        raise KnowledgeBuildError(f"{path} must be {qualifier}")
    return value


def _sha256(value: Any, path: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise KnowledgeBuildError(f"{path} must be a lowercase SHA-256 value")


def _utc(value: Any, path: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    text = _text(value, path)
    if not text.endswith("Z"):
        raise KnowledgeBuildError(f"{path} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise KnowledgeBuildError(f"{path} must be an RFC3339 UTC timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise KnowledgeBuildError(f"{path} must be an RFC3339 UTC timestamp")


def _metadata(value: Any, path: str) -> dict[str, Any]:
    metadata = _mapping(value, path)
    _fields(metadata, allowed=METADATA_FIELDS, required=METADATA_REQUIRED, path=path)
    revision = metadata["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise KnowledgeBuildError(f"{path}.revision must be a positive integer")
    supersedes = metadata.get("supersedes_revision")
    if (revision == 1 and supersedes is not None) or (
        revision > 1 and supersedes != revision - 1
    ):
        raise KnowledgeBuildError(f"{path}.supersedes_revision must identify the prior revision")
    if metadata["lifecycle_status"] not in LIFECYCLE_STATES:
        raise KnowledgeBuildError(f"{path}.lifecycle_status is invalid")
    _text(metadata["created_by"], f"{path}.created_by")
    if metadata["created_by_actor_type"] not in ACTOR_TYPES:
        raise KnowledgeBuildError(f"{path}.created_by_actor_type is invalid")
    _utc(metadata["created_at_utc"], f"{path}.created_at_utc")
    _text(metadata["change_reason"], f"{path}.change_reason")
    return metadata


def _entity_key(value: Any, path: str) -> str:
    text = _text(value, path)
    if _KEY_RE.fullmatch(text) is None:
        raise KnowledgeBuildError(f"{path} must be a stable kb: namespace key")
    return text


def _validate_claim(record: dict[str, Any], path: str) -> None:
    object_value = _mapping(record["object"], f"{path}.object")
    _fields(
        object_value,
        allowed={"entity_key", "value_text", "value_json", "unit"},
        path=f"{path}.object",
    )
    context = _mapping(record["context"], f"{path}.context")
    _fields(
        context,
        allowed={"organism_status", "organism_key", "tissue_status", "tissue_key", "experiment_status", "experiment_key"},
        path=f"{path}.context",
    )
    for name, entity_type in (
        ("organism", "organism"),
        ("tissue", "tissue"),
        ("experiment", "experiment"),
    ):
        status = context[f"{name}_status"]
        key = context[f"{name}_key"]
        if status not in CONTEXT_STATES:
            raise KnowledgeBuildError(f"{path}.context.{name}_status is invalid")
        if (status == "KNOWN") != (key is not None):
            raise KnowledgeBuildError(f"{path}.context.{name}_key does not match its status")
        if key is not None:
            _entity_key(key, f"{path}.context.{name}_key")

    fact_class = record["fact_class"]
    if fact_class not in FACT_CLASSES:
        raise KnowledgeBuildError(f"{path}.fact_class is invalid")
    objects = [object_value["entity_key"], object_value["value_text"], object_value["value_json"]]
    populated = sum(value is not None for value in objects)
    if fact_class == "UNKNOWN":
        if populated or not isinstance(record["unknown_reason"], str) or not record["unknown_reason"].strip():
            raise KnowledgeBuildError(f"{path} UNKNOWN claim requires a reason and no object")
    elif populated != 1:
        raise KnowledgeBuildError(f"{path} non-UNKNOWN claim requires exactly one object")
    if object_value["entity_key"] is not None:
        _entity_key(object_value["entity_key"], f"{path}.object.entity_key")
    if object_value["value_text"] == "":
        raise KnowledgeBuildError(f"{path}.object.value_text cannot silently represent unknown")

    review = _mapping(record["review"], f"{path}.review")
    _fields(review, allowed={"status", "reviewed_by", "reviewed_at_utc"}, path=f"{path}.review")
    if review["status"] not in REVIEW_STATES:
        raise KnowledgeBuildError(f"{path}.review.status is invalid")
    if review["status"] == "HUMAN_APPROVED":
        _text(review["reviewed_by"], f"{path}.review.reviewed_by")
        _utc(review["reviewed_at_utc"], f"{path}.review.reviewed_at_utc")
    elif review["reviewed_by"] is not None or review["reviewed_at_utc"] is not None:
        raise KnowledgeBuildError(f"{path}.review identity is only valid for HUMAN_APPROVED")

    eligibility = _mapping(record["eligibility"], f"{path}.eligibility")
    _fields(
        eligibility,
        allowed={"runtime_eligible", "registry_eligible", "actor_type", "decided_by", "decided_at_utc", "registry_candidate_reason"},
        path=f"{path}.eligibility",
    )
    for field_name in ("runtime_eligible", "registry_eligible"):
        if not isinstance(eligibility[field_name], bool):
            raise KnowledgeBuildError(f"{path}.eligibility.{field_name} must be Boolean")
    if eligibility["actor_type"] not in {"NONE", "HUMAN"}:
        raise KnowledgeBuildError(f"{path}.eligibility.actor_type cannot be AI or IMPORT")
    if eligibility["runtime_eligible"]:
        if fact_class != "FACT" or review["status"] != "HUMAN_APPROVED" or eligibility["actor_type"] != "HUMAN":
            raise KnowledgeBuildError(f"{path} runtime eligibility requires a human-approved FACT")
        _text(eligibility["decided_by"], f"{path}.eligibility.decided_by")
        _utc(eligibility["decided_at_utc"], f"{path}.eligibility.decided_at_utc")
    elif eligibility["actor_type"] == "NONE":
        if eligibility["decided_by"] is not None or eligibility["decided_at_utc"] is not None:
            raise KnowledgeBuildError(f"{path} eligibility decision identity is inconsistent")
    if eligibility["registry_eligible"]:
        if not eligibility["runtime_eligible"] or not str(eligibility["registry_candidate_reason"]).strip():
            raise KnowledgeBuildError(f"{path} Registry eligibility requires runtime eligibility and a human reason")


def _validate_record_values(record_type: str, record: dict[str, Any], path: str) -> None:
    if record_type == "paper" and record["publication_status"] not in {"PUBLISHED", "PREPRINT", "THESIS", "DATASET", "UNKNOWN"}:
        raise KnowledgeBuildError(f"{path}.publication_status is invalid")
    if record_type == "paper":
        year = record["publication_year"]
        if year is not None and (
            isinstance(year, bool) or not isinstance(year, int) or not 1600 <= year <= 3000
        ):
            raise KnowledgeBuildError(f"{path}.publication_year is invalid")
    if record_type == "source_reference":
        if record["source_kind"] not in {"PAPER", "DATABASE_RECORD", "DATASET", "FILE", "WEB_SNAPSHOT", "INTERNAL_REVIEW_NOTE", "USER_PROVIDED"}:
            raise KnowledgeBuildError(f"{path}.source_kind is invalid")
        _sha256(record["content_sha256"], f"{path}.content_sha256", nullable=True)
        _sha256(record["immutable_identity_sha256"], f"{path}.immutable_identity_sha256")
        _utc(record["acquired_at_utc"], f"{path}.acquired_at_utc", nullable=True)
    if record_type == "experiment":
        if record["context_completeness"] not in {"COMPLETE", "PARTIAL", "UNKNOWN"}:
            raise KnowledgeBuildError(f"{path}.context_completeness is invalid")
        _mapping(record["condition"], f"{path}.condition")
    if record_type == "design_case" and record["case_type"] not in {"PUBLISHED_CASE", "RECONSTRUCTED_CASE", "INTERNAL_REVIEW_CASE", "UNKNOWN"}:
        raise KnowledgeBuildError(f"{path}.case_type is invalid")
    if record_type in {"construct", "component"}:
        if record["sequence_availability"] not in {"COMPLETE", "PARTIAL", "ACCESSION_ONLY", "NOT_AVAILABLE", "UNKNOWN"}:
            raise KnowledgeBuildError(f"{path}.sequence_availability is invalid")
        _sha256(record["sequence_sha256"], f"{path}.sequence_sha256", nullable=True)
        if record["sequence_availability"] == "COMPLETE" and (record["sequence_sha256"] is None or record["sequence_length"] is None):
            raise KnowledgeBuildError(f"{path} complete sequence requires hash and length")
        sequence_length = record["sequence_length"]
        if sequence_length is not None and (
            isinstance(sequence_length, bool)
            or not isinstance(sequence_length, int)
            or sequence_length < 0
        ):
            raise KnowledgeBuildError(f"{path}.sequence_length must be a non-negative integer")
    if record_type == "construct" and record["topology"] not in {"LINEAR", "CIRCULAR", "UNKNOWN"}:
        raise KnowledgeBuildError(f"{path}.topology is invalid")
    if record_type == "transcription_unit":
        if record["orientation"] not in {"FORWARD", "REVERSE", "UNKNOWN"}:
            raise KnowledgeBuildError(f"{path}.orientation is invalid")
        _sha256(record["sequence_sha256"], f"{path}.sequence_sha256", nullable=True)
        if isinstance(record["unit_order"], bool) or not isinstance(record["unit_order"], int) or record["unit_order"] < 1:
            raise KnowledgeBuildError(f"{path}.unit_order must be a positive integer")
        sequence_length = record["sequence_length"]
        if sequence_length is not None and (
            isinstance(sequence_length, bool)
            or not isinstance(sequence_length, int)
            or sequence_length < 0
        ):
            raise KnowledgeBuildError(f"{path}.sequence_length must be a non-negative integer")
    if record_type == "component" and record["component_type"] not in {"PROMOTER", "FIVE_PRIME_UTR", "CDS", "THREE_PRIME_REGULATORY_REGION", "TERMINATOR", "SIGNAL_PEPTIDE", "TRANSIT_PEPTIDE", "TAG", "LINKER", "MARKER", "REPORTER", "VECTOR_BACKBONE", "ORIGIN", "BORDER", "OTHER", "UNKNOWN"}:
        raise KnowledgeBuildError(f"{path}.component_type is invalid")
    if record_type == "component_evidence" and record["evidence_role"] not in {"IDENTITY", "BOUNDARY", "FUNCTION", "EXPERIMENTAL_CONTEXT", "LIMITATION"}:
        raise KnowledgeBuildError(f"{path}.evidence_role is invalid")
    if record_type == "evidence_level":
        if not isinstance(record["permits_runtime_use"], bool) or not isinstance(record["permits_registry_consideration"], bool):
            raise KnowledgeBuildError(f"{path} evidence-level permissions must be Boolean")
        if record["permits_registry_consideration"] and not record["permits_runtime_use"]:
            raise KnowledgeBuildError(f"{path} Registry consideration requires runtime permission")
        if isinstance(record["rank_ordinal"], bool) or not isinstance(record["rank_ordinal"], int) or record["rank_ordinal"] < 0:
            raise KnowledgeBuildError(f"{path}.rank_ordinal must be a non-negative integer")
    if record_type == "evidence_claim":
        _validate_claim(record, path)
    if record_type == "applicability_scope":
        if record["scope_mode"] not in {"INCLUDE", "EXCLUDE"}:
            raise KnowledgeBuildError(f"{path}.scope_mode is invalid")
        if not any((record["organism_key"], record["tissue_key"], record["experiment_key"], record["developmental_stage"], record["condition"])):
            raise KnowledgeBuildError(f"{path} must define at least one scope constraint")
        _mapping(record["condition"], f"{path}.condition")
    if record_type == "limitation":
        if record["limitation_type"] not in {"MISSING_CONTEXT", "SOURCE_QUALITY", "CONFLICT", "GENERALIZABILITY", "SEQUENCE_BOUNDARY", "MEASUREMENT", "LICENSE", "OTHER"}:
            raise KnowledgeBuildError(f"{path}.limitation_type is invalid")
        if record["severity"] not in {"INFO", "CAUTION", "BLOCKING"} or record["resolution_status"] not in {"OPEN", "RESOLVED", "ACCEPTED", "NOT_RESOLVABLE"}:
            raise KnowledgeBuildError(f"{path} limitation status is invalid")
    if record_type == "measurement":
        if record["value_numeric"] is None and record["value_text"] is None:
            raise KnowledgeBuildError(f"{path} requires a numeric or reported text value")
        if isinstance(record["value_numeric"], bool):
            raise KnowledgeBuildError(f"{path}.value_numeric cannot be Boolean")
        replicate_count = record["replicate_count"]
        if replicate_count is not None and (
            isinstance(replicate_count, bool)
            or not isinstance(replicate_count, int)
            or replicate_count < 0
        ):
            raise KnowledgeBuildError(f"{path}.replicate_count must be a non-negative integer")


def _validate_reference(
    key: Any,
    *,
    expected_type: str | None,
    entity_types: Mapping[str, str],
    path: str,
    nullable: bool = True,
) -> None:
    if key is None and nullable:
        return
    key_text = _entity_key(key, path)
    actual = entity_types.get(key_text)
    if actual is None:
        raise KnowledgeBuildError(f"{path} references missing entity {key_text}")
    if expected_type is not None and actual != expected_type:
        raise KnowledgeBuildError(f"{path} references {actual}, expected {expected_type}")


def _validate_semantic_duplicates(records: dict[str, list[dict[str, Any]]]) -> None:
    checks = (
        ("paper", ("doi_normalized",), "doi_normalized"),
        ("paper", ("pmid",), "pmid"),
        ("source_reference", ("provider", "source_record_id", "source_version"), "source identity"),
        ("accession", ("accession_system", "accession_value", "accession_version"), "accession identity"),
        ("metabolite", ("chebi_id",), "chebi_id"),
        ("metabolite", ("inchikey",), "inchikey"),
        ("evidence_level", ("level_code",), "level_code"),
        ("transcription_unit", ("construct_key", "unit_order"), "construct unit order"),
        ("transcription_unit", ("construct_key", "unit_label"), "construct unit label"),
        ("component_evidence", ("component_key", "evidence_claim_key", "evidence_role"), "component evidence identity"),
    )
    for record_type, fields, label in checks:
        seen: set[tuple[Any, ...]] = set()
        for record in records[record_type]:
            identity = tuple(record[field] for field in fields)
            if any(value is None for value in identity):
                continue
            if identity in seen:
                raise KnowledgeBuildError(f"semantic duplicate in {record_type}.{label}: {identity!r}")
            seen.add(identity)


def validate_import_bundle(bundle: Mapping[str, Any]) -> ValidatedBundle:
    if not isinstance(bundle, Mapping):
        raise KnowledgeBuildError("import bundle must be an object")
    payload = copy.deepcopy(dict(bundle))
    _fields(payload, allowed=ROOT_FIELDS, required=ROOT_FIELDS - {"template_notice"}, path="bundle")
    if payload["schema_version"] != IMPORT_SCHEMA_VERSION:
        raise KnowledgeBuildError(f"unsupported import schema_version: {payload['schema_version']!r}")
    if payload["contract_version"] != CONTRACT_VERSION:
        raise KnowledgeBuildError(f"unsupported contract_version: {payload['contract_version']!r}")
    _text(payload["dataset_version"], "bundle.dataset_version")

    release = _mapping(payload["release"], "bundle.release")
    _fields(release, allowed=RELEASE_FIELDS, required=RELEASE_FIELDS, path="bundle.release")
    _entity_key(release["release_id"], "bundle.release.release_id")
    if release["release_status"] != "HUMAN_APPROVED":
        raise KnowledgeBuildError("bundle.release.release_status must be HUMAN_APPROVED")
    _text(release["approved_by"], "bundle.release.approved_by")
    _utc(release["approved_at_utc"], "bundle.release.approved_at_utc")
    _utc(release["built_at_utc"], "bundle.release.built_at_utc")
    if release["source_bundle_sha256"] is not None:
        _sha256(release["source_bundle_sha256"], "bundle.release.source_bundle_sha256")

    records_obj = _mapping(payload["records"], "bundle.records")
    expected_record_names = set(ENTITY_TYPES)
    _fields(records_obj, allowed=expected_record_names, required=expected_record_names, path="bundle.records")
    records: dict[str, list[dict[str, Any]]] = {}
    entity_types: dict[str, str] = {}
    for record_type in ENTITY_TYPES:
        values = _array(records_obj[record_type], f"bundle.records.{record_type}")
        if not values:
            raise KnowledgeBuildError(f"bundle.records.{record_type} must contain at least one record")
        records[record_type] = []
        for index, raw_record in enumerate(values):
            path = f"bundle.records.{record_type}[{index}]"
            record = _mapping(raw_record, path)
            _fields(record, allowed=RECORD_FIELDS[record_type], path=path)
            key = _entity_key(record[KEY_FIELDS[record_type]], f"{path}.{KEY_FIELDS[record_type]}")
            if key in entity_types:
                raise KnowledgeBuildError(f"duplicate business key: {key}")
            entity_types[key] = record_type
            _text(record[LABEL_FIELDS[record_type]], f"{path}.{LABEL_FIELDS[record_type]}")
            _metadata(record["metadata"], f"{path}.metadata")
            _validate_record_values(record_type, record, path)
            records[record_type].append(record)

    _validate_semantic_duplicates(records)
    for record_type, type_records in records.items():
        for index, record in enumerate(type_records):
            path = f"bundle.records.{record_type}[{index}]"
            for field_name, expected_type in REFERENCE_FIELDS.get(record_type, {}).items():
                _validate_reference(
                    record[field_name],
                    expected_type=expected_type,
                    entity_types=entity_types,
                    path=f"{path}.{field_name}",
                )
            if record_type == "evidence_claim":
                context = record["context"]
                for field_name, expected_type in (
                    ("organism_key", "organism"),
                    ("tissue_key", "tissue"),
                    ("experiment_key", "experiment"),
                ):
                    _validate_reference(context[field_name], expected_type=expected_type, entity_types=entity_types, path=f"{path}.context.{field_name}")
                _validate_reference(record["object"]["entity_key"], expected_type=None, entity_types=entity_types, path=f"{path}.object.entity_key")

    relationships_obj = _mapping(payload["relationships"], "bundle.relationships")
    _fields(relationships_obj, allowed=set(RELATIONSHIP_FIELDS), path="bundle.relationships")
    relationships: dict[str, list[dict[str, Any]]] = {}
    for relationship_type, allowed_fields in RELATIONSHIP_FIELDS.items():
        rows = _array(relationships_obj[relationship_type], f"bundle.relationships.{relationship_type}")
        relationships[relationship_type] = []
        seen_rows: set[bytes] = set()
        for index, raw_row in enumerate(rows):
            path = f"bundle.relationships.{relationship_type}[{index}]"
            row = _mapping(raw_row, path)
            _fields(row, allowed=allowed_fields, path=path)
            encoded_row = canonical_json_bytes(row)
            if encoded_row in seen_rows:
                raise KnowledgeBuildError(f"{path} duplicates an earlier relationship row")
            seen_rows.add(encoded_row)
            for field_name, expected_type in RELATIONSHIP_REFERENCES[relationship_type].items():
                _validate_reference(row[field_name], expected_type=expected_type, entity_types=entity_types, path=f"{path}.{field_name}", nullable=False)
            for field_name, allowed_values in RELATIONSHIP_VALUE_SETS.get(relationship_type, {}).items():
                if row[field_name] not in allowed_values:
                    raise KnowledgeBuildError(f"{path}.{field_name} is invalid")
            if relationship_type == "transcription_unit_component":
                order = row["component_order"]
                if isinstance(order, bool) or not isinstance(order, int) or order < 1:
                    raise KnowledgeBuildError(f"{path}.component_order must be a positive integer")
                start, end = row["start_zero_based"], row["end_zero_based_exclusive"]
                valid_coordinates = (start is None and end is None) or (
                    isinstance(start, int)
                    and not isinstance(start, bool)
                    and start >= 0
                    and isinstance(end, int)
                    and not isinstance(end, bool)
                    and end > start
                )
                if not valid_coordinates:
                    raise KnowledgeBuildError(f"{path} component coordinates are invalid")
            if relationship_type == "claim_source":
                _sha256(row["source_excerpt_sha256"], f"{path}.source_excerpt_sha256", nullable=True)
                if row["location_type"] == "UNKNOWN" and not str(row["location_value"]).strip():
                    raise KnowledgeBuildError(f"{path} UNKNOWN location requires an explanation")
            if relationship_type == "claim_conflict":
                if not isinstance(row["conflict_key"], str) or not row["conflict_key"].startswith("kbc:"):
                    raise KnowledgeBuildError(f"{path}.conflict_key must use the kbc: namespace")
            relationships[relationship_type].append(row)

    claims = {record["evidence_claim_key"]: record for record in records["evidence_claim"]}
    claim_sources = {row["evidence_claim_key"] for row in relationships["claim_source"]}
    missing_sources = sorted(set(claims) - claim_sources)
    if missing_sources:
        raise KnowledgeBuildError(f"claims lack source locations: {', '.join(missing_sources)}")

    level_by_key = {record["evidence_level_key"]: record for record in records["evidence_level"]}
    limitations = {record["limitation_key"]: record for record in records["limitation"]}
    blocked_claims = {
        row["evidence_claim_key"]
        for row in relationships["claim_limitation"]
        if limitations[row["limitation_key"]]["severity"] == "BLOCKING"
        and limitations[row["limitation_key"]]["resolution_status"] == "OPEN"
    }
    conflicted_claims = {
        row["evidence_claim_key"]
        for row in relationships["claim_conflict"]
        if row["conflict_type"] == "DIRECT_CONTRADICTION"
        and row["resolution_status"] in {"OPEN", "UNRESOLVED"}
    }
    conflict_group_counts: dict[str, int] = {}
    for row in relationships["claim_conflict"]:
        conflict_group_counts[row["conflict_key"]] = conflict_group_counts.get(row["conflict_key"], 0) + 1
    incomplete_conflicts = sorted(key for key, count in conflict_group_counts.items() if count < 2)
    if incomplete_conflicts:
        raise KnowledgeBuildError(
            f"conflict groups must retain at least two claims: {', '.join(incomplete_conflicts)}"
        )
    for key, claim in claims.items():
        if claim["eligibility"]["runtime_eligible"]:
            if not level_by_key[claim["evidence_level_key"]]["permits_runtime_use"]:
                raise KnowledgeBuildError(f"claim {key} uses an evidence level that forbids runtime use")
            if key in blocked_claims:
                raise KnowledgeBuildError(f"claim {key} has an open blocking limitation")
            if key in conflicted_claims:
                raise KnowledgeBuildError(f"claim {key} has an open direct conflict")
        if claim["eligibility"]["registry_eligible"] and not level_by_key[claim["evidence_level_key"]]["permits_registry_consideration"]:
            raise KnowledgeBuildError(f"claim {key} uses an evidence level that forbids Registry consideration")

    component_by_key = {record["component_key"]: record for record in records["component"]}
    accessions_by_entity = {
        record["referenced_entity_key"]
        for record in records["accession"]
        if record["referenced_entity_key"] is not None
    }
    component_evidence_claims = {
        record["evidence_claim_key"]: record for record in records["component_evidence"]
    }
    for key, claim in claims.items():
        if not claim["eligibility"]["registry_eligible"]:
            continue
        component = component_by_key.get(claim["subject_entity_key"])
        evidence_link = component_evidence_claims.get(key)
        if component is None or component["sequence_availability"] != "COMPLETE":
            raise KnowledgeBuildError(f"claim {key} Registry eligibility requires a complete component sequence")
        if component["source_reference_key"] is None or component["component_key"] not in accessions_by_entity:
            raise KnowledgeBuildError(f"claim {key} Registry eligibility requires component source and accession review")
        if evidence_link is None or evidence_link["evidence_role"] not in {"IDENTITY", "BOUNDARY", "FUNCTION"}:
            raise KnowledgeBuildError(f"claim {key} Registry eligibility requires typed component evidence")

    events = _array(payload["review_events"], "bundle.review_events")
    event_fields = {"review_event_key", "entity_key", "prior_status", "new_status", "actor_id", "actor_type", "reason", "occurred_at_utc"}
    event_transitions: set[tuple[str, str]] = set()
    event_keys: set[str] = set()
    for index, raw_event in enumerate(events):
        path = f"bundle.review_events[{index}]"
        event = _mapping(raw_event, path)
        _fields(event, allowed=event_fields, path=path)
        key = _text(event["review_event_key"], f"{path}.review_event_key")
        if not key.startswith("kbr:") or key in event_keys:
            raise KnowledgeBuildError(f"{path}.review_event_key must be unique and use kbr:")
        event_keys.add(key)
        _validate_reference(event["entity_key"], expected_type=None, entity_types=entity_types, path=f"{path}.entity_key", nullable=False)
        if event["actor_type"] not in ACTOR_TYPES:
            raise KnowledgeBuildError(f"{path}.actor_type is invalid")
        if event["new_status"] in {"HUMAN_APPROVED", "RUNTIME_ELIGIBLE", "REGISTRY_ELIGIBLE"} and event["actor_type"] != "HUMAN":
            raise KnowledgeBuildError(f"{path} AI or import actor cannot create an approval or eligibility transition")
        _text(event["actor_id"], f"{path}.actor_id")
        _text(event["reason"], f"{path}.reason")
        _utc(event["occurred_at_utc"], f"{path}.occurred_at_utc")
        event_transitions.add((event["entity_key"], event["new_status"]))

    for key, claim in claims.items():
        if claim["review"]["status"] == "HUMAN_APPROVED" and (key, "HUMAN_APPROVED") not in event_transitions:
            raise KnowledgeBuildError(f"claim {key} lacks a HUMAN_APPROVED review event")
        if claim["eligibility"]["runtime_eligible"] and (key, "RUNTIME_ELIGIBLE") not in event_transitions:
            raise KnowledgeBuildError(f"claim {key} lacks a RUNTIME_ELIGIBLE review event")
        if claim["eligibility"]["registry_eligible"] and (key, "REGISTRY_ELIGIBLE") not in event_transitions:
            raise KnowledgeBuildError(f"claim {key} lacks a REGISTRY_ELIGIBLE review event")

    requirements = _mapping(payload["builder_requirements"], "bundle.builder_requirements")
    expected_requirements = {
        "reject_unknown_fields": True,
        "reject_dangling_keys": True,
        "reject_semantic_duplicates": True,
        "reject_ai_approval_or_eligibility": True,
        "require_claim_source_location": True,
        "require_utc_timestamps": True,
        "atomic_build_staging_only": True,
        "formal_runtime_import_allowed": False,
    }
    _fields(requirements, allowed=set(expected_requirements), path="bundle.builder_requirements")
    if requirements != expected_requirements:
        raise KnowledgeBuildError("bundle.builder_requirements does not match the V0 safety contract")

    hash_payload = copy.deepcopy(payload)
    hash_payload["release"]["source_bundle_sha256"] = None
    source_hash = sha256_hex(canonical_json_bytes(hash_payload))
    declared_hash = release["source_bundle_sha256"]
    if declared_hash is not None and declared_hash != source_hash:
        raise KnowledgeBuildError("bundle.release.source_bundle_sha256 does not match canonical bundle content")
    return ValidatedBundle(payload=payload, source_bundle_sha256=source_hash, entity_types=entity_types)
