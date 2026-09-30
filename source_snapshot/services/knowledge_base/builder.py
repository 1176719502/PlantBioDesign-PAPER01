from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from services.knowledge_base.constants import (
    APPLICATION_ID,
    BUILD_TOOL_VERSION,
    BUILD_PROVENANCE_FILENAME,
    BUILD_PROVENANCE_RELATIVE_PATH,
    CONTRACT_VERSION,
    DATABASE_FILENAME,
    DATABASE_RELATIVE_PATH,
    ENTITY_TYPES,
    MANIFEST_FILENAME,
    REQUIRED_SQLITE_COMPILE_OPTIONS_SHA256,
    REQUIRED_SQLITE_SOURCE_ID,
    REQUIRED_SQLITE_VERSION,
    SCHEMA_VERSION,
    WRITER_CONTRACT_VERSION,
)
from services.knowledge_base.errors import KnowledgeBuildError
from services.knowledge_base.validation import (
    KEY_FIELDS,
    LABEL_FIELDS,
    ValidatedBundle,
    canonical_json_bytes,
    sha256_hex,
    validate_import_bundle,
)


SCHEMA_PATH = Path(__file__).with_name("schema_v1.sql")


@dataclass(frozen=True)
class BuildResult:
    database_path: Path
    manifest_path: Path
    database_sha256: str
    logical_dump_sha256: str
    build_manifest_sha256: str
    source_bundle_sha256: str
    provenance_path: Path


def _json_text(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _sqlite_source_id(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT sqlite_source_id()").fetchone()
    if row is None or not isinstance(row[0], str) or not row[0]:
        raise KnowledgeBuildError("KB00 writer environment did not expose sqlite_source_id()")
    return row[0]


def _writer_environment() -> dict[str, Any]:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(":memory:")
        source_id = _sqlite_source_id(connection)
        compile_options = sorted(
            str(row[0])
            for row in connection.execute("PRAGMA compile_options").fetchall()
        )
    except (sqlite3.Error, TypeError, ValueError) as exc:
        raise KnowledgeBuildError(
            f"KB00 writer environment metadata could not be read: {exc}"
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "architecture_bits": struct.calcsize("P") * 8,
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_version_info": list(sqlite3.sqlite_version_info),
        "sqlite_source_id": source_id,
        "sqlite_compile_options": compile_options,
        "sqlite_compile_options_sha256": hashlib.sha256(
            ("\n".join(compile_options) + "\n").encode("utf-8")
        ).hexdigest(),
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
    }


def require_pinned_writer() -> dict[str, Any]:
    """Fail closed unless the release build uses the audited SQLite writer."""

    environment = _writer_environment()
    required_version = ".".join(str(part) for part in REQUIRED_SQLITE_VERSION)
    mismatches: list[str] = []
    if tuple(environment["sqlite_version_info"]) != REQUIRED_SQLITE_VERSION:
        mismatches.append(
            f"SQLite version required {required_version}, found {environment['sqlite_version']}"
        )
    if environment["sqlite_source_id"] != REQUIRED_SQLITE_SOURCE_ID:
        mismatches.append("SQLite source ID differs from the audited writer")
    if (
        environment["sqlite_compile_options_sha256"]
        != REQUIRED_SQLITE_COMPILE_OPTIONS_SHA256
    ):
        mismatches.append("SQLite compile identity differs from the audited writer")
    if mismatches:
        raise KnowledgeBuildError(
            "KB00_PINNED_WRITER_ENVIRONMENT_MISMATCH: "
            + "; ".join(mismatches)
        )
    return environment


def _builder_source_sha256() -> str:
    try:
        source = Path(__file__).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise KnowledgeBuildError(
            f"KB00 builder source identity could not be read: {exc}"
        ) from exc
    canonical = source.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return sha256_hex(canonical)


def _bool(value: bool) -> int:
    return 1 if value else 0


def _record_counts(bundle: Mapping[str, Any]) -> dict[str, Any]:
    records = bundle["records"]
    claims = records["evidence_claim"]
    return {
        "entities": sum(len(records[name]) for name in ENTITY_TYPES),
        "by_entity_type": {name: len(records[name]) for name in ENTITY_TYPES},
        "claims": len(claims),
        "by_fact_class": {
            name: sum(claim["fact_class"] == name for claim in claims)
            for name in ("FACT", "DERIVATION", "INFERENCE", "UNKNOWN")
        },
        "by_review_status": {
            name: sum(claim["review"]["status"] == name for claim in claims)
            for name in sorted({claim["review"]["status"] for claim in claims})
        },
        "runtime_eligible": sum(claim["eligibility"]["runtime_eligible"] for claim in claims),
        "registry_eligible": sum(claim["eligibility"]["registry_eligible"] for claim in claims),
        "conflict_rows": len(bundle["relationships"]["claim_conflict"]),
        "unknown_claims": sum(claim["fact_class"] == "UNKNOWN" for claim in claims),
        "limitations": len(records["limitation"]),
    }


def _build_manifest_basis(validated: ValidatedBundle, schema_sha256: str) -> dict[str, Any]:
    payload = validated.payload
    release = payload["release"]
    return {
        "manifest_version": 1,
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "dataset_version": payload["dataset_version"],
        "release_id": release["release_id"],
        "release_status": release["release_status"],
        "approved_by": release["approved_by"],
        "approved_at_utc": release["approved_at_utc"],
        "built_at_utc": release["built_at_utc"],
        "build_tool_version": BUILD_TOOL_VERSION,
        "schema_sha256": schema_sha256,
        "source_bundle_sha256": validated.source_bundle_sha256,
        "record_counts": _record_counts(payload),
    }


def _canonical_schema_bytes(path: Path | None = None) -> bytes:
    schema_path = SCHEMA_PATH if path is None else path
    try:
        schema_text = schema_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise KnowledgeBuildError(
            f"knowledge schema could not be read: {schema_path}: {exc}"
        ) from exc
    return schema_text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _sorted_records(validated: ValidatedBundle, record_type: str) -> list[dict[str, Any]]:
    key_field = KEY_FIELDS[record_type]
    return sorted(validated.payload["records"][record_type], key=lambda row: row[key_field])


def _insert_release(
    connection: sqlite3.Connection,
    validated: ValidatedBundle,
    build_manifest_sha256: str,
) -> None:
    release = validated.payload["release"]
    connection.execute(
        "INSERT INTO kb_release VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            release["release_id"],
            SCHEMA_VERSION,
            CONTRACT_VERSION,
            validated.payload["dataset_version"],
            build_manifest_sha256,
            validated.source_bundle_sha256,
            release["release_status"],
            release["approved_by"],
            release["approved_at_utc"],
            release["built_at_utc"],
            release["built_at_utc"],
        ),
    )


def _insert_entities(connection: sqlite3.Connection, validated: ValidatedBundle) -> None:
    release_id = validated.payload["release"]["release_id"]
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for record_type in ENTITY_TYPES:
        for record in _sorted_records(validated, record_type):
            rows.append((record[KEY_FIELDS[record_type]], record_type, record))
    for entity_key, record_type, record in sorted(rows, key=lambda item: item[0]):
        metadata = record["metadata"]
        label = record[LABEL_FIELDS[record_type]] or entity_key
        connection.execute(
            "INSERT INTO kb_entity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entity_key,
                record_type,
                label,
                metadata["lifecycle_status"],
                metadata["revision"],
                metadata["created_by"],
                metadata["created_by_actor_type"],
                metadata["created_at_utc"],
                metadata["created_by"],
                metadata["created_at_utc"],
            ),
        )
        payload = {key: value for key, value in record.items() if key != "metadata"}
        payload_json = _json_text(payload)
        connection.execute(
            "INSERT INTO kb_entity_revision VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entity_key,
                metadata["revision"],
                release_id,
                payload_json,
                sha256_hex(payload_json.encode("utf-8")),
                metadata["change_reason"],
                metadata.get("supersedes_revision"),
                metadata["created_by"],
                metadata["created_by_actor_type"],
                metadata["created_at_utc"],
            ),
        )


def _execute_many(
    connection: sqlite3.Connection,
    sql: str,
    values: Iterable[tuple[Any, ...]],
) -> None:
    connection.executemany(sql, values)


def _insert_subtypes(connection: sqlite3.Connection, validated: ValidatedBundle) -> None:
    records = validated.payload["records"]
    _execute_many(
        connection,
        "INSERT INTO kb_paper VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            (r["paper_key"], r["title"], r["publication_year"], r["journal_or_repository"], r["doi_normalized"], r["pmid"], r["pmcid"], r["publication_status"])
            for r in _sorted_records(validated, "paper")
        ),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_source_reference VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            (r["source_reference_key"], r["source_kind"], r["provider"], r["source_record_id"], r["source_version"], r["source_uri"], r["source_title"], r["content_sha256"], r["license_or_access_status"], r["acquired_at_utc"], r["immutable_identity_sha256"], r["paper_key"])
            for r in _sorted_records(validated, "source_reference")
        ),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_organism VALUES (?, ?, ?, ?, ?)",
        ((r["organism_key"], r["scientific_name"], r["taxonomy_id"], r["strain_cultivar_ecotype"], r["common_name"]) for r in _sorted_records(validated, "organism")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_tissue VALUES (?, ?, ?, ?, ?)",
        ((r["tissue_key"], r["organism_key"], r["tissue_name"], r["ontology_id"], r["developmental_stage"]) for r in _sorted_records(validated, "tissue")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_experiment VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            (r["experiment_key"], r["paper_key"], r["experiment_label"], r["experiment_type"], r["organism_key"], r["tissue_key"], r["developmental_stage"], r["genotype_or_background"], r["treatment_context"], r["assay_context"], _json_text(r["condition"]), r["context_completeness"])
            for r in _sorted_records(validated, "experiment")
        ),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_design_case VALUES (?, ?, ?, ?, ?)",
        ((r["design_case_key"], r["case_label"], r["case_type"], r["case_summary"], r["review_boundary"]) for r in _sorted_records(validated, "design_case")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_construct VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ((r["construct_key"], r["construct_label"], r["construct_type"], r["topology"], r["sequence_availability"], r["sequence_sha256"], r["sequence_length"], r["source_reference_key"]) for r in _sorted_records(validated, "construct")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_transcription_unit VALUES (?, ?, ?, ?, ?, ?, ?)",
        ((r["transcription_unit_key"], r["construct_key"], r["unit_label"], r["unit_order"], r["orientation"], r["sequence_sha256"], r["sequence_length"]) for r in _sorted_records(validated, "transcription_unit")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_component VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ((r["component_key"], r["component_name"], r["component_type"], r["source_organism_key"], r["sequence_availability"], r["sequence_sha256"], r["sequence_length"], r["source_reference_key"]) for r in _sorted_records(validated, "component")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_metabolite VALUES (?, ?, ?, ?, ?)",
        ((r["metabolite_key"], r["preferred_name"], r["chebi_id"], r["inchikey"], r["formula"]) for r in _sorted_records(validated, "metabolite")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_measurement VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ((r["measurement_key"], r["experiment_key"], r["metabolite_key"], r["measured_entity_key"], r["measurement_type"], r["value_numeric"], r["value_text"], r["unit"], r["uncertainty_numeric"], r["replicate_count"], r["normalization_basis"], r["timepoint"], r["source_reference_key"]) for r in _sorted_records(validated, "measurement")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_accession VALUES (?, ?, ?, ?, ?, ?, ?)",
        ((r["accession_key"], r["accession_system"], r["accession_value"], r["accession_version"], r["record_type"], r["source_reference_key"], r["referenced_entity_key"]) for r in _sorted_records(validated, "accession")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_evidence_level VALUES (?, ?, ?, ?, ?, ?, ?)",
        ((r["evidence_level_key"], r["level_code"], r["rank_ordinal"], r["definition"], r["minimum_source_requirements"], _bool(r["permits_runtime_use"]), _bool(r["permits_registry_consideration"])) for r in _sorted_records(validated, "evidence_level")),
    )
    claim_rows = []
    for r in _sorted_records(validated, "evidence_claim"):
        obj, context, review, eligibility, metadata = r["object"], r["context"], r["review"], r["eligibility"], r["metadata"]
        claim_rows.append(
            (
                r["evidence_claim_key"], r["subject_entity_key"], r["predicate"], obj["entity_key"], obj["value_text"], None if obj["value_json"] is None else _json_text(obj["value_json"]), obj["unit"], r["fact_class"], r["provenance_method"], r["evidence_type"], r["evidence_level_key"], context["organism_status"], context["organism_key"], context["tissue_status"], context["tissue_key"], context["experiment_status"], context["experiment_key"], r["unknown_reason"], review["status"], review["reviewed_by"], review["reviewed_at_utc"], _bool(eligibility["runtime_eligible"]), _bool(eligibility["registry_eligible"]), eligibility["actor_type"], eligibility["decided_by"], eligibility["decided_at_utc"], eligibility["registry_candidate_reason"], metadata["created_by"], metadata["created_by_actor_type"], metadata["created_at_utc"], metadata["created_by"], metadata["created_at_utc"],
            )
        )
    _execute_many(connection, "INSERT INTO kb_evidence_claim VALUES (" + ",".join("?" for _ in range(32)) + ")", claim_rows)
    _execute_many(
        connection,
        "INSERT INTO kb_component_evidence VALUES (?, ?, ?, ?, ?)",
        ((r["component_evidence_key"], r["component_key"], r["evidence_claim_key"], r["evidence_role"], r["metadata"]["created_at_utc"]) for r in _sorted_records(validated, "component_evidence")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_applicability_scope VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ((r["applicability_scope_key"], r["scope_mode"], r["organism_key"], r["tissue_key"], r["experiment_key"], r["developmental_stage"], _json_text(r["condition"]), r["scope_note"]) for r in _sorted_records(validated, "applicability_scope")),
    )
    _execute_many(
        connection,
        "INSERT INTO kb_limitation VALUES (?, ?, ?, ?, ?)",
        ((r["limitation_key"], r["limitation_type"], r["limitation_text"], r["severity"], r["resolution_status"]) for r in _sorted_records(validated, "limitation")),
    )


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: _json_text(row))


def _insert_relationships(connection: sqlite3.Connection, validated: ValidatedBundle) -> None:
    rel = validated.payload["relationships"]
    _execute_many(connection, "INSERT INTO kb_design_case_paper VALUES (?, ?, ?)", ((r["design_case_key"], r["paper_key"], r["relationship_type"]) for r in _sort_rows(rel["design_case_paper"])))
    _execute_many(connection, "INSERT INTO kb_design_case_experiment VALUES (?, ?, ?)", ((r["design_case_key"], r["experiment_key"], r["relationship_type"]) for r in _sort_rows(rel["design_case_experiment"])))
    _execute_many(connection, "INSERT INTO kb_design_case_construct VALUES (?, ?, ?)", ((r["design_case_key"], r["construct_key"], r["relationship_type"]) for r in _sort_rows(rel["design_case_construct"])))
    _execute_many(connection, "INSERT INTO kb_transcription_unit_component VALUES (?, ?, ?, ?, ?, ?, ?)", ((r["transcription_unit_key"], r["component_key"], r["component_order"], r["biological_role"], r["orientation"], r["start_zero_based"], r["end_zero_based_exclusive"]) for r in _sort_rows(rel["transcription_unit_component"])))
    _execute_many(connection, "INSERT INTO kb_claim_source VALUES (?, ?, ?, ?, ?, ?)", ((r["evidence_claim_key"], r["source_reference_key"], r["source_role"], r["location_type"], r["location_value"], r["source_excerpt_sha256"]) for r in _sort_rows(rel["claim_source"])))
    _execute_many(connection, "INSERT INTO kb_claim_applicability_scope VALUES (?, ?)", ((r["evidence_claim_key"], r["applicability_scope_key"]) for r in _sort_rows(rel["claim_applicability_scope"])))
    _execute_many(connection, "INSERT INTO kb_claim_limitation VALUES (?, ?)", ((r["evidence_claim_key"], r["limitation_key"]) for r in _sort_rows(rel["claim_limitation"])))
    _execute_many(connection, "INSERT INTO kb_claim_conflict VALUES (?, ?, ?, ?, ?, ?)", ((r["conflict_key"], r["evidence_claim_key"], r["conflict_role"], r["conflict_type"], r["resolution_status"], r["resolution_note"]) for r in _sort_rows(rel["claim_conflict"])))
    _execute_many(
        connection,
        "INSERT INTO kb_review_event VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ((r["review_event_key"], r["entity_key"], r["prior_status"], r["new_status"], r["actor_id"], r["actor_type"], r["reason"], r["occurred_at_utc"]) for r in sorted(validated.payload["review_events"], key=lambda row: row["review_event_key"])),
    )


def _single_value(connection: sqlite3.Connection, sql: str) -> Any:
    row = connection.execute(sql).fetchone()
    return None if row is None else row[0]


def validate_database_connection(
    connection: sqlite3.Connection,
    *,
    expected_dataset_version: str | None = None,
    expected_build_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    if _single_value(connection, "PRAGMA application_id") != APPLICATION_ID:
        raise KnowledgeBuildError("database application_id does not match the KB contract")
    if _single_value(connection, "PRAGMA user_version") != SCHEMA_VERSION:
        raise KnowledgeBuildError("database user_version does not match the KB schema")
    integrity_rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    if integrity_rows != ["ok"]:
        raise KnowledgeBuildError(f"database integrity_check failed: {integrity_rows!r}")
    foreign_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_rows:
        raise KnowledgeBuildError(f"database foreign_key_check failed: {foreign_rows!r}")
    releases = connection.execute(
        "SELECT dataset_version, build_manifest_sha256, release_status, approved_by, approved_at_utc FROM kb_release"
    ).fetchall()
    if len(releases) != 1 or releases[0][2] != "HUMAN_APPROVED" or not releases[0][3] or not releases[0][4]:
        raise KnowledgeBuildError("database must contain exactly one human-approved release")
    if expected_dataset_version is not None and releases[0][0] != expected_dataset_version:
        raise KnowledgeBuildError("database dataset_version does not match the build request")
    if expected_build_manifest_sha256 is not None and releases[0][1] != expected_build_manifest_sha256:
        raise KnowledgeBuildError("database build manifest hash does not match")

    subtype_tables = {name: f"kb_{name}" for name in ENTITY_TYPES}
    mismatches: list[str] = []
    for entity_type, table in subtype_tables.items():
        key_field = KEY_FIELDS[entity_type]
        missing = connection.execute(
            f"SELECT e.entity_key FROM kb_entity AS e LEFT JOIN {table} AS s ON s.{key_field} = e.entity_key "
            "WHERE e.entity_type = ? AND s." + key_field + " IS NULL",
            (entity_type,),
        ).fetchall()
        extra = connection.execute(
            f"SELECT s.{key_field} FROM {table} AS s JOIN kb_entity AS e ON e.entity_key = s.{key_field} "
            "WHERE e.entity_type <> ?",
            (entity_type,),
        ).fetchall()
        mismatches.extend(str(row[0]) for row in missing + extra)
    if mismatches:
        raise KnowledgeBuildError(f"entity subtype mismatch: {sorted(mismatches)!r}")
    missing_revisions = connection.execute(
        "SELECT e.entity_key FROM kb_entity AS e LEFT JOIN kb_entity_revision AS r "
        "ON r.entity_key = e.entity_key AND r.revision = e.current_revision WHERE r.entity_key IS NULL"
    ).fetchall()
    if missing_revisions:
        raise KnowledgeBuildError("one or more entities lack their current revision")
    missing_sources = connection.execute(
        "SELECT c.evidence_claim_key FROM kb_evidence_claim AS c LEFT JOIN kb_claim_source AS s "
        "ON s.evidence_claim_key = c.evidence_claim_key GROUP BY c.evidence_claim_key HAVING count(s.source_reference_key) = 0"
    ).fetchall()
    if missing_sources:
        raise KnowledgeBuildError("one or more claims lack source locations")
    invalid_runtime = connection.execute(
        "SELECT c.evidence_claim_key FROM kb_evidence_claim AS c "
        "JOIN kb_evidence_level AS level ON level.evidence_level_key = c.evidence_level_key "
        "WHERE c.runtime_eligible = 1 AND (c.fact_class <> 'FACT' OR c.review_status <> 'HUMAN_APPROVED' OR level.permits_runtime_use <> 1)"
    ).fetchall()
    if invalid_runtime:
        raise KnowledgeBuildError("runtime eligibility audit failed")
    return {
        "application_id": APPLICATION_ID,
        "user_version": SCHEMA_VERSION,
        "integrity_check": "ok",
        "foreign_key_violations": 0,
        "release_rows": 1,
        "entity_rows": _single_value(connection, "SELECT count(*) FROM kb_entity"),
        "claim_rows": _single_value(connection, "SELECT count(*) FROM kb_evidence_claim"),
    }


def logical_dump_sha256(database_path: Path) -> str:
    uri = database_path.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        dump = "\n".join(connection.iterdump()) + "\n"
    finally:
        connection.close()
    return hashlib.sha256(dump.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.building")
    try:
        with temporary.open("wb") as handle:
            handle.write(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode(
                    "utf-8"
                )
            )
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_knowledge_release(
    bundle: Mapping[str, Any],
    output_directory: str | os.PathLike[str],
    *,
    fault_after_database_validation: bool = False,
) -> BuildResult:
    writer_environment = require_pinned_writer()
    validated = validate_import_bundle(bundle)
    schema_bytes = _canonical_schema_bytes()
    schema_sha256 = sha256_hex(schema_bytes)
    manifest_basis = _build_manifest_basis(validated, schema_sha256)
    build_manifest_sha256 = sha256_hex(canonical_json_bytes(manifest_basis))

    output = Path(output_directory).resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    database_path = output / DATABASE_FILENAME
    manifest_path = output / MANIFEST_FILENAME
    provenance_path = output / BUILD_PROVENANCE_FILENAME
    temporary = output / f".{DATABASE_FILENAME}.building"
    quarantine = output / f".{DATABASE_FILENAME}.failed"
    if temporary.exists():
        raise KnowledgeBuildError(f"build temporary path already exists: {temporary}")

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(temporary))
        connection.execute("PRAGMA page_size = 4096")
        connection.execute("PRAGMA auto_vacuum = NONE")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.executescript(schema_bytes.decode("utf-8"))
        connection.execute("BEGIN IMMEDIATE")
        _insert_release(connection, validated, build_manifest_sha256)
        _insert_entities(connection, validated)
        _insert_subtypes(connection, validated)
        _insert_relationships(connection, validated)
        connection.commit()
        validate_database_connection(
            connection,
            expected_dataset_version=validated.payload["dataset_version"],
            expected_build_manifest_sha256=build_manifest_sha256,
        )
        connection.execute("VACUUM")
        connection.close()
        connection = None

        readonly = sqlite3.connect(temporary.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            validation_evidence = validate_database_connection(
                readonly,
                expected_dataset_version=validated.payload["dataset_version"],
                expected_build_manifest_sha256=build_manifest_sha256,
            )
        finally:
            readonly.close()
        if fault_after_database_validation:
            raise KnowledgeBuildError("injected fault after database validation")

        database_sha256 = sha256_hex(temporary.read_bytes())
        logical_sha256 = logical_dump_sha256(temporary)
        manifest = {
            **manifest_basis,
            "build_manifest_sha256": build_manifest_sha256,
            "database": {
                "relative_path": DATABASE_RELATIVE_PATH,
                "filename": DATABASE_FILENAME,
                "sha256": database_sha256,
                "size_bytes": temporary.stat().st_size,
                "application_id": APPLICATION_ID,
                "user_version": SCHEMA_VERSION,
                "logical_dump_sha256": logical_sha256,
            },
            "validation": validation_evidence,
            "copy_inventory": [
                {
                    "classification": "synthetic_infrastructure_fixture",
                    "license_or_access_status": "INTERNAL_SYNTHETIC",
                    "contains_real_literature": False,
                    "contains_real_accessions": False,
                    "contains_real_sequences": False,
                    "runtime_boundary": "documentation and review retrieval only",
                }
            ],
        }
        provenance = {
            "provenance_version": 1,
            "relative_path": BUILD_PROVENANCE_RELATIVE_PATH,
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "required_sqlite_version": ".".join(
                str(part) for part in REQUIRED_SQLITE_VERSION
            ),
            "writer_environment": writer_environment,
            "builder": {
                "build_tool_version": BUILD_TOOL_VERSION,
                "builder_source_sha256": _builder_source_sha256(),
                "schema_sha256": schema_sha256,
                "source_bundle_sha256": validated.source_bundle_sha256,
                "build_manifest_sha256": build_manifest_sha256,
            },
            "database": {
                "relative_path": DATABASE_RELATIVE_PATH,
                "sha256": database_sha256,
                "logical_dump_sha256": logical_sha256,
            },
        }
        os.replace(temporary, database_path)
        _write_json(manifest_path, manifest)
        _write_json(provenance_path, provenance)
        return BuildResult(
            database_path=database_path,
            manifest_path=manifest_path,
            database_sha256=database_sha256,
            logical_dump_sha256=logical_sha256,
            build_manifest_sha256=build_manifest_sha256,
            source_bundle_sha256=validated.source_bundle_sha256,
            provenance_path=provenance_path,
        )
    except Exception as exc:
        if connection is not None:
            connection.close()
        if temporary.exists():
            if quarantine.exists():
                quarantine.unlink()
            os.replace(temporary, quarantine)
        if isinstance(exc, KnowledgeBuildError):
            raise
        if isinstance(exc, (sqlite3.Error, OSError, UnicodeError, ValueError, TypeError)):
            raise KnowledgeBuildError(f"knowledge release build failed: {exc}") from exc
        raise


def build_knowledge_release_from_file(
    bundle_path: str | os.PathLike[str],
    output_directory: str | os.PathLike[str],
    *,
    fault_after_database_validation: bool = False,
) -> BuildResult:
    source = Path(bundle_path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise KnowledgeBuildError(f"import bundle could not be read: {source}: {exc}") from exc
    return build_knowledge_release(
        payload,
        output_directory,
        fault_after_database_validation=fault_after_database_validation,
    )
