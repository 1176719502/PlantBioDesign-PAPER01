from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from services.knowledge_base.constants import (
    APPLICATION_ID,
    CONTRACT_VERSION,
    DATABASE_FILENAME,
    DATABASE_RELATIVE_PATH,
    MANIFEST_FILENAME,
    QUERY_CONTRACT_VERSION,
    RESOURCE_DIRECTORY,
    SCHEMA_VERSION,
)
from services.knowledge_base.errors import KnowledgeResourceError
from services.knowledge_base.snapshot import KnowledgeReferenceSnapshot


@dataclass(frozen=True)
class EntityRecord:
    entity_key: str
    entity_type: str
    canonical_label: str
    lifecycle_status: str
    revision: int
    payload_sha256: str
    payload: Any
    dataset_version: str


@dataclass(frozen=True)
class SourceLocation:
    source_reference_key: str
    source_role: str
    location_type: str
    location_value: str
    source_excerpt_sha256: str | None


@dataclass(frozen=True)
class ApplicabilityScope:
    applicability_scope_key: str
    scope_mode: str
    organism_key: str | None
    tissue_key: str | None
    experiment_key: str | None
    developmental_stage: str
    condition: Any
    scope_note: str


@dataclass(frozen=True)
class ClaimLimitation:
    limitation_key: str
    limitation_type: str
    limitation_text: str
    severity: str
    resolution_status: str


@dataclass(frozen=True)
class ClaimConflict:
    conflict_key: str
    conflict_role: str
    conflict_type: str
    resolution_status: str
    resolution_note: str


@dataclass(frozen=True)
class KnowledgeClaim:
    evidence_claim_key: str
    subject_entity_key: str
    predicate: str
    object_entity_key: str | None
    object_value_text: str | None
    object_value_json: Any
    value_unit: str
    fact_class: str
    provenance_method: str
    evidence_type: str
    evidence_level_key: str
    organism_context_status: str
    organism_key: str | None
    tissue_context_status: str
    tissue_key: str | None
    experiment_context_status: str
    experiment_key: str | None
    unknown_reason: str
    review_status: str
    runtime_eligible: bool
    registry_eligible: bool
    sources: tuple[SourceLocation, ...]
    scopes: tuple[ApplicabilityScope, ...]
    limitations: tuple[ClaimLimitation, ...]
    conflicts: tuple[ClaimConflict, ...]
    dataset_version: str
    entity_revision: int
    entity_payload_sha256: str


@dataclass(frozen=True)
class DesignCaseGraph:
    design_case: EntityRecord
    paper_keys: tuple[str, ...]
    experiment_keys: tuple[str, ...]
    construct_keys: tuple[str, ...]
    transcription_unit_keys: tuple[str, ...]
    component_keys: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotComparison:
    status: str
    saved_dataset_version: str
    current_dataset_version: str
    entity_key: str
    saved_revision: int
    current_revision: int | None
    saved_payload_sha256: str
    current_payload_sha256: str | None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KnowledgeResourceError(f"knowledge manifest is missing: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise KnowledgeResourceError(f"knowledge manifest is unreadable: {path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != 1:
        raise KnowledgeResourceError("knowledge manifest version is unsupported")
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise KnowledgeResourceError("knowledge manifest contract version is unsupported")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise KnowledgeResourceError("knowledge manifest schema version is unsupported")
    database = manifest.get("database")
    if not isinstance(database, dict):
        raise KnowledgeResourceError("knowledge manifest lacks database metadata")
    required = {
        "relative_path",
        "filename",
        "sha256",
        "size_bytes",
        "application_id",
        "user_version",
        "logical_dump_sha256",
    }
    if not required <= set(database):
        raise KnowledgeResourceError("knowledge manifest database metadata is incomplete")
    if database["relative_path"] != DATABASE_RELATIVE_PATH or database["filename"] != DATABASE_FILENAME:
        raise KnowledgeResourceError("knowledge manifest names an unexpected database path")
    if database["application_id"] != APPLICATION_ID or database["user_version"] != SCHEMA_VERSION:
        raise KnowledgeResourceError("knowledge manifest database identity is unsupported")
    return manifest


def _read_only_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro&immutable=1"


def _scalar(connection: sqlite3.Connection, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
    row = connection.execute(sql, parameters).fetchone()
    return None if row is None else row[0]


def _verify_connection(connection: sqlite3.Connection, manifest: dict[str, Any]) -> dict[str, Any]:
    if _scalar(connection, "PRAGMA application_id") != APPLICATION_ID:
        raise KnowledgeResourceError("knowledge database application_id mismatch")
    user_version = _scalar(connection, "PRAGMA user_version")
    if user_version != SCHEMA_VERSION:
        relation = "future" if isinstance(user_version, int) and user_version > SCHEMA_VERSION else "unsupported"
        raise KnowledgeResourceError(f"knowledge database has {relation} user_version {user_version}")
    integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise KnowledgeResourceError(f"knowledge database integrity_check failed: {integrity!r}")
    foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_keys:
        raise KnowledgeResourceError("knowledge database foreign_key_check failed")
    releases = connection.execute(
        "SELECT release_id, contract_version, dataset_version, build_manifest_sha256, "
        "source_bundle_sha256, release_status, approved_by, approved_at_utc "
        "FROM kb_release"
    ).fetchall()
    if len(releases) != 1:
        raise KnowledgeResourceError("knowledge database must contain exactly one release")
    release = releases[0]
    if release[1] != CONTRACT_VERSION or release[5] != "HUMAN_APPROVED" or not release[6] or not release[7]:
        raise KnowledgeResourceError("knowledge database release is not human approved")
    expected = (
        manifest.get("release_id"),
        manifest.get("contract_version"),
        manifest.get("dataset_version"),
        manifest.get("build_manifest_sha256"),
        manifest.get("source_bundle_sha256"),
        manifest.get("release_status"),
        manifest.get("approved_by"),
        manifest.get("approved_at_utc"),
    )
    if tuple(release) != expected:
        raise KnowledgeResourceError("knowledge database release metadata differs from manifest")
    return manifest


class KnowledgeQueryV0:
    """Versioned read-only query surface; no connection or write operation is exposed."""

    contract_version = QUERY_CONTRACT_VERSION

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        manifest: dict[str, Any],
        database_path: Path,
    ) -> None:
        self._connection = connection
        self._manifest = manifest
        self._database_path = database_path
        self._closed = False

    @property
    def dataset_version(self) -> str:
        return str(self._manifest["dataset_version"])

    @property
    def database_path(self) -> Path:
        return self._database_path

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "KnowledgeQueryV0":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise KnowledgeResourceError("knowledge query service is closed")

    def get_entity(
        self,
        entity_key: str,
        dataset_version: str | None = None,
    ) -> EntityRecord | None:
        self._ensure_open()
        if dataset_version is not None and dataset_version != self.dataset_version:
            return None
        row = self._connection.execute(
            "SELECT e.entity_key, e.entity_type, e.canonical_label, e.lifecycle_status, "
            "e.current_revision, r.payload_sha256, r.payload_json "
            "FROM kb_entity AS e JOIN kb_entity_revision AS r "
            "ON r.entity_key = e.entity_key AND r.revision = e.current_revision "
            "WHERE e.entity_key = ?",
            (entity_key,),
        ).fetchone()
        if row is None:
            return None
        return EntityRecord(
            entity_key=row[0],
            entity_type=row[1],
            canonical_label=row[2],
            lifecycle_status=row[3],
            revision=int(row[4]),
            payload_sha256=row[5],
            payload=json.loads(row[6]),
            dataset_version=self.dataset_version,
        )

    def _source_locations(self, claim_key: str) -> tuple[SourceLocation, ...]:
        rows = self._connection.execute(
            "SELECT source_reference_key, source_role, location_type, location_value, source_excerpt_sha256 "
            "FROM kb_claim_source WHERE evidence_claim_key = ? "
            "ORDER BY source_reference_key, source_role, location_type, location_value",
            (claim_key,),
        ).fetchall()
        return tuple(SourceLocation(*row) for row in rows)

    def _scopes(self, claim_key: str) -> tuple[ApplicabilityScope, ...]:
        rows = self._connection.execute(
            "SELECT s.applicability_scope_key, s.scope_mode, s.organism_key, s.tissue_key, "
            "s.experiment_key, s.developmental_stage, s.condition_json, s.scope_note "
            "FROM kb_claim_applicability_scope AS link JOIN kb_applicability_scope AS s "
            "ON s.applicability_scope_key = link.applicability_scope_key "
            "WHERE link.evidence_claim_key = ? ORDER BY s.applicability_scope_key",
            (claim_key,),
        ).fetchall()
        return tuple(
            ApplicabilityScope(row[0], row[1], row[2], row[3], row[4], row[5], json.loads(row[6]), row[7])
            for row in rows
        )

    def _limitations(self, claim_key: str) -> tuple[ClaimLimitation, ...]:
        rows = self._connection.execute(
            "SELECT l.limitation_key, l.limitation_type, l.limitation_text, l.severity, l.resolution_status "
            "FROM kb_claim_limitation AS link JOIN kb_limitation AS l ON l.limitation_key = link.limitation_key "
            "WHERE link.evidence_claim_key = ? ORDER BY l.limitation_key",
            (claim_key,),
        ).fetchall()
        return tuple(ClaimLimitation(*row) for row in rows)

    def _conflicts(self, claim_key: str) -> tuple[ClaimConflict, ...]:
        rows = self._connection.execute(
            "SELECT conflict_key, conflict_role, conflict_type, resolution_status, resolution_note "
            "FROM kb_claim_conflict WHERE evidence_claim_key = ? ORDER BY conflict_key, conflict_role",
            (claim_key,),
        ).fetchall()
        return tuple(ClaimConflict(*row) for row in rows)

    def get_claim(self, claim_key: str) -> KnowledgeClaim | None:
        self._ensure_open()
        row = self._connection.execute(
            "SELECT c.evidence_claim_key, c.subject_entity_key, c.predicate, c.object_entity_key, "
            "c.object_value_text, c.object_value_json, c.value_unit, c.fact_class, c.provenance_method, "
            "c.evidence_type, c.evidence_level_key, c.organism_context_status, c.organism_key, "
            "c.tissue_context_status, c.tissue_key, c.experiment_context_status, c.experiment_key, "
            "c.unknown_reason, c.review_status, c.runtime_eligible, c.registry_eligible, "
            "e.current_revision, r.payload_sha256 "
            "FROM kb_evidence_claim AS c JOIN kb_entity AS e ON e.entity_key = c.evidence_claim_key "
            "JOIN kb_entity_revision AS r ON r.entity_key = e.entity_key AND r.revision = e.current_revision "
            "WHERE c.evidence_claim_key = ?",
            (claim_key,),
        ).fetchone()
        if row is None:
            return None
        return KnowledgeClaim(
            evidence_claim_key=row[0],
            subject_entity_key=row[1],
            predicate=row[2],
            object_entity_key=row[3],
            object_value_text=row[4],
            object_value_json=None if row[5] is None else json.loads(row[5]),
            value_unit=row[6],
            fact_class=row[7],
            provenance_method=row[8],
            evidence_type=row[9],
            evidence_level_key=row[10],
            organism_context_status=row[11],
            organism_key=row[12],
            tissue_context_status=row[13],
            tissue_key=row[14],
            experiment_context_status=row[15],
            experiment_key=row[16],
            unknown_reason=row[17],
            review_status=row[18],
            runtime_eligible=bool(row[19]),
            registry_eligible=bool(row[20]),
            sources=self._source_locations(claim_key),
            scopes=self._scopes(claim_key),
            limitations=self._limitations(claim_key),
            conflicts=self._conflicts(claim_key),
            dataset_version=self.dataset_version,
            entity_revision=int(row[21]),
            entity_payload_sha256=row[22],
        )

    def search_claims(
        self,
        text: str,
        organism_key: str | None = None,
        tissue_key: str | None = None,
        experiment_key: str | None = None,
        limit: int = 20,
    ) -> tuple[KnowledgeClaim, ...]:
        self._ensure_open()
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 100:
            raise ValueError("limit must be an integer from 1 through 100")
        escaped = str(text or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        clauses = [
            "(c.predicate LIKE ? ESCAPE '\\' OR coalesce(c.object_value_text, '') LIKE ? ESCAPE '\\' OR e.canonical_label LIKE ? ESCAPE '\\')"
        ]
        parameters: list[Any] = [pattern, pattern, pattern]
        for column, value in (
            ("organism_key", organism_key),
            ("tissue_key", tissue_key),
            ("experiment_key", experiment_key),
        ):
            if value is not None:
                clauses.append(f"c.{column} = ?")
                parameters.append(value)
        parameters.append(limit)
        keys = self._connection.execute(
            "SELECT c.evidence_claim_key FROM kb_runtime_claim_v0 AS c "
            "JOIN kb_entity AS e ON e.entity_key = c.subject_entity_key WHERE "
            + " AND ".join(clauses)
            + " ORDER BY c.evidence_claim_key LIMIT ?",
            tuple(parameters),
        ).fetchall()
        claims = [self.get_claim(row[0]) for row in keys]
        return tuple(claim for claim in claims if claim is not None)

    def list_component_evidence(
        self,
        component_key: str,
        include_ineligible: bool = False,
    ) -> tuple[KnowledgeClaim, ...]:
        self._ensure_open()
        table = "kb_evidence_claim" if include_ineligible else "kb_runtime_claim_v0"
        keys = self._connection.execute(
            f"SELECT c.evidence_claim_key FROM kb_component_evidence AS link JOIN {table} AS c "
            "ON c.evidence_claim_key = link.evidence_claim_key WHERE link.component_key = ? "
            "ORDER BY c.evidence_claim_key",
            (component_key,),
        ).fetchall()
        return tuple(claim for row in keys if (claim := self.get_claim(row[0])) is not None)

    def get_design_case_graph(self, design_case_key: str) -> DesignCaseGraph | None:
        self._ensure_open()
        case = self.get_entity(design_case_key)
        if case is None or case.entity_type != "design_case":
            return None
        paper_keys = tuple(row[0] for row in self._connection.execute("SELECT paper_key FROM kb_design_case_paper WHERE design_case_key = ? ORDER BY paper_key", (design_case_key,)))
        experiment_keys = tuple(row[0] for row in self._connection.execute("SELECT experiment_key FROM kb_design_case_experiment WHERE design_case_key = ? ORDER BY experiment_key", (design_case_key,)))
        construct_keys = tuple(row[0] for row in self._connection.execute("SELECT construct_key FROM kb_design_case_construct WHERE design_case_key = ? ORDER BY construct_key", (design_case_key,)))
        if construct_keys:
            placeholders = ",".join("?" for _ in construct_keys)
            transcription_unit_keys = tuple(row[0] for row in self._connection.execute(f"SELECT transcription_unit_key FROM kb_transcription_unit WHERE construct_key IN ({placeholders}) ORDER BY construct_key, unit_order", construct_keys))
        else:
            transcription_unit_keys = ()
        if transcription_unit_keys:
            placeholders = ",".join("?" for _ in transcription_unit_keys)
            component_keys = tuple(row[0] for row in self._connection.execute(f"SELECT DISTINCT component_key FROM kb_transcription_unit_component WHERE transcription_unit_key IN ({placeholders}) ORDER BY component_key", transcription_unit_keys))
        else:
            component_keys = ()
        return DesignCaseGraph(case, paper_keys, experiment_keys, construct_keys, transcription_unit_keys, component_keys)

    def list_conflicts(self, subject_entity_key: str | None = None) -> tuple[KnowledgeClaim, ...]:
        self._ensure_open()
        sql = "SELECT DISTINCT conflict.evidence_claim_key FROM kb_claim_conflict AS conflict JOIN kb_evidence_claim AS claim ON claim.evidence_claim_key = conflict.evidence_claim_key"
        parameters: tuple[Any, ...] = ()
        if subject_entity_key is not None:
            sql += " WHERE claim.subject_entity_key = ?"
            parameters = (subject_entity_key,)
        sql += " ORDER BY conflict.evidence_claim_key"
        return tuple(claim for row in self._connection.execute(sql, parameters) if (claim := self.get_claim(row[0])) is not None)

    def list_unknowns(self, subject_entity_key: str | None = None) -> tuple[KnowledgeClaim, ...]:
        self._ensure_open()
        sql = "SELECT evidence_claim_key FROM kb_evidence_claim WHERE fact_class = 'UNKNOWN'"
        parameters: tuple[Any, ...] = ()
        if subject_entity_key is not None:
            sql += " AND subject_entity_key = ?"
            parameters = (subject_entity_key,)
        sql += " ORDER BY evidence_claim_key"
        return tuple(claim for row in self._connection.execute(sql, parameters) if (claim := self.get_claim(row[0])) is not None)

    def compare_project_snapshot(
        self,
        snapshot: KnowledgeReferenceSnapshot | dict[str, Any],
    ) -> SnapshotComparison:
        resolved = snapshot if isinstance(snapshot, KnowledgeReferenceSnapshot) else KnowledgeReferenceSnapshot.from_mapping(snapshot)
        current = self.get_entity(resolved.entity_key)
        if current is None:
            status, revision, payload_hash = "missing", None, None
        elif current.lifecycle_status in {"RETIRED", "WITHDRAWN"}:
            status, revision, payload_hash = "retired", current.revision, current.payload_sha256
        elif current.revision != resolved.entity_revision or current.payload_sha256 != resolved.entity_payload_sha256:
            status, revision, payload_hash = "changed", current.revision, current.payload_sha256
        elif resolved.kb_dataset_version != self.dataset_version:
            status, revision, payload_hash = "current", current.revision, current.payload_sha256
        else:
            status, revision, payload_hash = "current", current.revision, current.payload_sha256
        return SnapshotComparison(
            status=status,
            saved_dataset_version=resolved.kb_dataset_version,
            current_dataset_version=self.dataset_version,
            entity_key=resolved.entity_key,
            saved_revision=resolved.entity_revision,
            current_revision=revision,
            saved_payload_sha256=resolved.entity_payload_sha256,
            current_payload_sha256=payload_hash,
        )


def open_knowledge_base(
    database_path: str | Path,
    manifest_path: str | Path,
) -> KnowledgeQueryV0:
    database = Path(database_path)
    manifest_file = Path(manifest_path)
    if not database.is_file():
        raise KnowledgeResourceError(f"knowledge database is missing: {database}")
    manifest = _load_manifest(manifest_file)
    metadata = manifest["database"]
    try:
        size = database.stat().st_size
        digest = _sha256_file(database)
    except OSError as exc:
        raise KnowledgeResourceError(f"knowledge database could not be hashed: {database}: {exc}") from exc
    if size != metadata["size_bytes"]:
        raise KnowledgeResourceError("knowledge database size differs from manifest")
    if digest != metadata["sha256"]:
        raise KnowledgeResourceError("knowledge database SHA-256 differs from manifest")

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(_read_only_uri(database), uri=True)
        connection.execute("PRAGMA query_only = ON")
        _verify_connection(connection, manifest)
        return KnowledgeQueryV0(connection, manifest=manifest, database_path=database.resolve())
    except sqlite3.Error as exc:
        if connection is not None:
            connection.close()
        raise KnowledgeResourceError(f"knowledge database read-only open failed: {exc}") from exc
    except Exception:
        if connection is not None:
            connection.close()
        raise


def _default_runtime_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[2]


def open_packaged_knowledge_base(resource_root: str | Path | None = None) -> KnowledgeQueryV0:
    root = Path(resource_root) if resource_root is not None else _default_runtime_root()
    resource_directory = root / RESOURCE_DIRECTORY
    return open_knowledge_base(
        resource_directory / DATABASE_FILENAME,
        resource_directory / MANIFEST_FILENAME,
    )
