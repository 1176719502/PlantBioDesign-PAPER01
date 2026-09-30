from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from services.plant_expression_candidate_ingestion.config import SCHEMA_VERSION
from services.plant_expression_candidate_ingestion.normalizers import NormalizedRecord
from services.plant_expression_candidate_ingestion.registry import QueryDefinition, SourceDefinition
from services.plant_expression_candidate_ingestion.utils import clean_text, utc_now


class CandidateRepositoryError(RuntimeError):
    """Raised when candidate database operations fail."""


class CandidateRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            conn = sqlite3.connect(f"file:{self.database_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> dict[str, Any]:
        conn = self.connect()
        try:
            _init_schema(conn)
            fts_enabled = _try_init_fts(conn)
            conn.commit()
            return {"schema_version": SCHEMA_VERSION, "fts_enabled": fts_enabled}
        finally:
            conn.close()

    def register_source(self, source: SourceDefinition) -> None:
        conn = self.connect()
        try:
            _init_schema(conn)
            conn.execute(
                """
                INSERT INTO sources (
                    source_id, source_name, adapter, base_url, endpoint_note,
                    license_note, usage_policy_note, adapter_version, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_name=excluded.source_name,
                    adapter=excluded.adapter,
                    base_url=excluded.base_url,
                    endpoint_note=excluded.endpoint_note,
                    license_note=excluded.license_note,
                    usage_policy_note=excluded.usage_policy_note,
                    adapter_version=excluded.adapter_version,
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
                """,
                (
                    source.source_id,
                    source.source_name,
                    source.adapter,
                    source.base_url,
                    source.endpoint_note,
                    source.license_note,
                    source.usage_policy_note,
                    source.adapter_version,
                    int(source.enabled),
                    utc_now(),
                    utc_now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def register_query(self, plan_id: str, source_id: str, query: QueryDefinition, request_params: dict[str, Any]) -> None:
        conn = self.connect()
        try:
            _init_schema(conn)
            conn.execute(
                """
                INSERT INTO source_queries (
                    query_id, query_plan_id, source_id, description, domain_label, enabled,
                    max_records, query_params_json, date_version, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(query_id, source_id) DO UPDATE SET
                    query_plan_id=excluded.query_plan_id,
                    description=excluded.description,
                    domain_label=excluded.domain_label,
                    enabled=excluded.enabled,
                    max_records=excluded.max_records,
                    query_params_json=excluded.query_params_json,
                    date_version=excluded.date_version,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at
                """,
                (
                    query.query_id,
                    plan_id,
                    source_id,
                    query.description,
                    query.domain_label,
                    int(query.enabled),
                    query.max_records,
                    json.dumps(request_params, ensure_ascii=False, sort_keys=True),
                    query.version_date,
                    query.notes,
                    utc_now(),
                    utc_now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def start_run(self, run: dict[str, Any]) -> None:
        conn = self.connect()
        try:
            _init_schema(conn)
            conn.execute(
                """
                INSERT INTO ingestion_runs (
                    ingestion_run_id, source_id, query_plan_id, adapter_version,
                    started_at, finished_at, completion_status, manifest_path,
                    software_git_commit, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["ingestion_run_id"],
                    run["source_id"],
                    run["query_plan_id"],
                    run["adapter_version"],
                    run["started_at"],
                    "",
                    "running",
                    "",
                    clean_text(run.get("software_git_commit")),
                    "{}",
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def finish_run(self, run_id: str, *, status: str, manifest_path: str, summary: dict[str, Any]) -> None:
        conn = self.connect()
        try:
            conn.execute(
                """
                UPDATE ingestion_runs
                SET finished_at = ?, completion_status = ?, manifest_path = ?, summary_json = ?
                WHERE ingestion_run_id = ?
                """,
                (utc_now(), status, manifest_path, json.dumps(summary, ensure_ascii=False, sort_keys=True), run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def insert_records(
        self,
        *,
        ingestion_run_id: str,
        query_id: str,
        raw_snapshot_path: str,
        raw_snapshot_hash: str,
        records: list[NormalizedRecord],
    ) -> dict[str, int]:
        inserted = 0
        duplicates = 0
        conn = self.connect()
        try:
            _init_schema(conn)
            for record in records:
                existing_id = _find_canonical_by_identifier(conn, record)
                canonical_id = existing_id or record.canonical_record_id
                now = utc_now()
                row = conn.execute(
                    "SELECT canonical_record_id FROM components_candidates WHERE canonical_record_id = ?",
                    (canonical_id,),
                ).fetchone()
                if row:
                    duplicates += 1
                    conn.execute(
                        "UPDATE components_candidates SET updated_at = ?, raw_metadata_json = ? WHERE canonical_record_id = ?",
                        (now, json.dumps(record.raw_metadata, ensure_ascii=False, sort_keys=True), canonical_id),
                    )
                else:
                    inserted += 1
                    conn.execute(
                        """
                        INSERT INTO components_candidates (
                            canonical_record_id, record_type, primary_name, description,
                            source_id, source_record_id, pmid, pmcid, doi, accession,
                            taxon_id, organism_name, publication_year, journal_or_repository,
                            abstract_or_summary, component_type_candidate,
                            expression_context_candidate, assembly_standard_candidate,
                            external_url, fetched_at, ingestion_run_id, content_hash,
                            provenance_status, evidence_status, review_status, limitations,
                            raw_metadata_json, license_note, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            canonical_id,
                            record.record_type,
                            record.primary_name,
                            record.description,
                            record.source_id,
                            record.source_record_id,
                            record.pmid,
                            record.pmcid,
                            record.doi,
                            record.accession,
                            record.taxon_id,
                            record.organism_name,
                            record.publication_year,
                            record.journal_or_repository,
                            record.abstract_or_summary,
                            record.component_type_candidate,
                            record.expression_context_candidate,
                            record.assembly_standard_candidate,
                            record.external_url,
                            now,
                            ingestion_run_id,
                            record.content_hash,
                            record.provenance_status,
                            record.evidence_status,
                            record.review_status,
                            record.limitations,
                            json.dumps(record.raw_metadata, ensure_ascii=False, sort_keys=True),
                            record.license_note,
                            now,
                            now,
                        ),
                    )
                    _insert_type_specific_rows(conn, canonical_id, record, now)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO source_records (
                        source_id, source_record_id, canonical_record_id, ingestion_run_id,
                        query_id, raw_snapshot_path, raw_snapshot_hash, content_hash, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.source_id,
                        record.source_record_id,
                        canonical_id,
                        ingestion_run_id,
                        query_id,
                        raw_snapshot_path,
                        raw_snapshot_hash,
                        record.content_hash,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO source_query_records (
                        query_id, source_id, source_record_id, canonical_record_id, ingestion_run_id, raw_snapshot_path
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (query_id, record.source_id, record.source_record_id, canonical_id, ingestion_run_id, raw_snapshot_path),
                )
                _insert_identifiers_aliases_links(conn, canonical_id, record)
                _insert_review_state(conn, canonical_id, record.review_status, now)
                _insert_inferences(conn, canonical_id, record)
            _refresh_fts(conn)
            conn.commit()
        finally:
            conn.close()
        return {"inserted_count": inserted, "duplicate_count": duplicates}

    def stats(self, *, read_only: bool = False) -> dict[str, Any]:
        conn = self.connect(read_only=read_only)
        try:
            if not read_only:
                _init_schema(conn)
            return {
                "database_path": str(self.database_path),
                "fts_enabled": _has_fts(conn),
                "total_records": _scalar(conn, "SELECT COUNT(*) FROM components_candidates"),
                "records_by_source": _group_count(conn, "SELECT source_id, COUNT(*) AS count FROM components_candidates GROUP BY source_id"),
                "records_by_type": _group_count(conn, "SELECT record_type, COUNT(*) AS count FROM components_candidates GROUP BY record_type"),
                "review_status_counts": _group_count(conn, "SELECT review_status, COUNT(*) AS count FROM components_candidates GROUP BY review_status"),
                "unique_identifier_count": _scalar(conn, "SELECT COUNT(DISTINCT identifier_type || ':' || identifier_value) FROM record_identifiers"),
                "latest_ingestion_runs": [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT ingestion_run_id, source_id, query_plan_id, started_at, finished_at, completion_status, manifest_path
                        FROM ingestion_runs
                        ORDER BY started_at DESC
                        LIMIT 10
                        """
                    ).fetchall()
                ],
                "query_coverage": _group_count(conn, "SELECT query_id, COUNT(*) AS count FROM source_query_records GROUP BY query_id"),
                "sample_records": [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT canonical_record_id, record_type, primary_name, source_id, source_record_id,
                               review_status, provenance_status, evidence_status, external_url
                        FROM components_candidates
                        ORDER BY created_at DESC
                        LIMIT 5
                        """
                    ).fetchall()
                ],
                "run_rollup": {
                    "retrieved_count": _scalar(conn, "SELECT COUNT(*) FROM source_records"),
                    "duplicate_count": max(
                        0,
                        _scalar(conn, "SELECT COUNT(*) FROM source_query_records")
                        - _scalar(conn, "SELECT COUNT(*) FROM components_candidates"),
                    ),
                },
            }
        finally:
            conn.close()

    def search(self, term: str, *, limit: int = 10, read_only: bool = False) -> list[dict[str, Any]]:
        clean = clean_text(term)
        if not clean:
            return []
        conn = self.connect(read_only=read_only)
        try:
            if not read_only:
                _init_schema(conn)
            if _has_fts(conn):
                rows = conn.execute(
                    """
                    SELECT c.canonical_record_id, c.record_type, c.primary_name, c.source_id,
                           c.source_record_id, c.review_status, c.external_url
                    FROM candidate_fts f
                    JOIN components_candidates c ON c.canonical_record_id = f.canonical_record_id
                    WHERE candidate_fts MATCH ?
                    LIMIT ?
                    """,
                    (clean, limit),
                ).fetchall()
            else:
                like = f"%{clean}%"
                rows = conn.execute(
                    """
                    SELECT canonical_record_id, record_type, primary_name, source_id,
                           source_record_id, review_status, external_url
                    FROM components_candidates
                    WHERE primary_name LIKE ? OR description LIKE ? OR abstract_or_summary LIKE ?
                    LIMIT ?
                    """,
                    (like, like, like, limit),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', 'v2.7-r225-plant-expression-candidate-db');

        CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            adapter TEXT NOT NULL,
            base_url TEXT NOT NULL,
            endpoint_note TEXT NOT NULL DEFAULT '',
            license_note TEXT NOT NULL DEFAULT '',
            usage_policy_note TEXT NOT NULL DEFAULT '',
            adapter_version TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS source_queries (
            query_id TEXT NOT NULL,
            query_plan_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            domain_label TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            max_records INTEGER NOT NULL DEFAULT 0,
            query_params_json TEXT NOT NULL DEFAULT '{}',
            date_version TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (query_id, source_id),
            FOREIGN KEY (source_id) REFERENCES sources(source_id)
        );

        CREATE TABLE IF NOT EXISTS ingestion_runs (
            ingestion_run_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            query_plan_id TEXT NOT NULL,
            adapter_version TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL DEFAULT '',
            completion_status TEXT NOT NULL,
            manifest_path TEXT NOT NULL DEFAULT '',
            software_git_commit TEXT NOT NULL DEFAULT '',
            summary_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (source_id) REFERENCES sources(source_id)
        );

        CREATE TABLE IF NOT EXISTS components_candidates (
            canonical_record_id TEXT PRIMARY KEY,
            record_type TEXT NOT NULL,
            primary_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL,
            source_record_id TEXT NOT NULL,
            pmid TEXT NOT NULL DEFAULT '',
            pmcid TEXT NOT NULL DEFAULT '',
            doi TEXT NOT NULL DEFAULT '',
            accession TEXT NOT NULL DEFAULT '',
            taxon_id TEXT NOT NULL DEFAULT '',
            organism_name TEXT NOT NULL DEFAULT '',
            publication_year TEXT NOT NULL DEFAULT '',
            journal_or_repository TEXT NOT NULL DEFAULT '',
            abstract_or_summary TEXT NOT NULL DEFAULT '',
            component_type_candidate TEXT NOT NULL DEFAULT '',
            expression_context_candidate TEXT NOT NULL DEFAULT '',
            assembly_standard_candidate TEXT NOT NULL DEFAULT '',
            external_url TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            ingestion_run_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            provenance_status TEXT NOT NULL CHECK (provenance_status IN ('candidate', 'source_metadata_preserved')),
            evidence_status TEXT NOT NULL CHECK (evidence_status IN ('metadata_candidate', 'accession_metadata_candidate')),
            review_status TEXT NOT NULL CHECK (review_status IN ('candidate', 'unreviewed', 'needs_manual_review')),
            limitations TEXT NOT NULL DEFAULT '',
            raw_metadata_json TEXT NOT NULL DEFAULT '{}',
            license_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (source_id) REFERENCES sources(source_id),
            FOREIGN KEY (ingestion_run_id) REFERENCES ingestion_runs(ingestion_run_id)
        );

        CREATE TABLE IF NOT EXISTS publications (
            canonical_record_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            pmid TEXT NOT NULL DEFAULT '',
            pmcid TEXT NOT NULL DEFAULT '',
            doi TEXT NOT NULL DEFAULT '',
            publication_year TEXT NOT NULL DEFAULT '',
            journal TEXT NOT NULL DEFAULT '',
            abstract_or_summary TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (canonical_record_id) REFERENCES components_candidates(canonical_record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS organisms (
            taxon_id TEXT PRIMARY KEY,
            organism_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sequences_or_accessions (
            canonical_record_id TEXT PRIMARY KEY,
            accession TEXT NOT NULL,
            taxon_id TEXT NOT NULL DEFAULT '',
            organism_name TEXT NOT NULL DEFAULT '',
            protein_name TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (canonical_record_id) REFERENCES components_candidates(canonical_record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS vectors_or_toolkits_candidates (
            canonical_record_id TEXT PRIMARY KEY,
            toolkit_or_standard_candidate TEXT NOT NULL DEFAULT '',
            source_note TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (canonical_record_id) REFERENCES components_candidates(canonical_record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS evidence_candidates (
            canonical_record_id TEXT PRIMARY KEY,
            evidence_status TEXT NOT NULL,
            source_note TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (canonical_record_id) REFERENCES components_candidates(canonical_record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS source_records (
            source_id TEXT NOT NULL,
            source_record_id TEXT NOT NULL,
            canonical_record_id TEXT NOT NULL,
            ingestion_run_id TEXT NOT NULL,
            query_id TEXT NOT NULL,
            raw_snapshot_path TEXT NOT NULL,
            raw_snapshot_hash TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (source_id, source_record_id),
            FOREIGN KEY (canonical_record_id) REFERENCES components_candidates(canonical_record_id)
        );

        CREATE TABLE IF NOT EXISTS source_query_records (
            query_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_record_id TEXT NOT NULL,
            canonical_record_id TEXT NOT NULL,
            ingestion_run_id TEXT NOT NULL,
            raw_snapshot_path TEXT NOT NULL,
            PRIMARY KEY (query_id, source_id, source_record_id)
        );

        CREATE TABLE IF NOT EXISTS record_identifiers (
            canonical_record_id TEXT NOT NULL,
            identifier_type TEXT NOT NULL,
            identifier_value TEXT NOT NULL,
            PRIMARY KEY (identifier_type, identifier_value),
            FOREIGN KEY (canonical_record_id) REFERENCES components_candidates(canonical_record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS record_aliases (
            canonical_record_id TEXT NOT NULL,
            alias TEXT NOT NULL,
            PRIMARY KEY (canonical_record_id, alias),
            FOREIGN KEY (canonical_record_id) REFERENCES components_candidates(canonical_record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS record_links (
            canonical_record_id TEXT NOT NULL,
            link_type TEXT NOT NULL,
            url TEXT NOT NULL,
            PRIMARY KEY (canonical_record_id, link_type, url),
            FOREIGN KEY (canonical_record_id) REFERENCES components_candidates(canonical_record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS review_states (
            canonical_record_id TEXT PRIMARY KEY,
            review_status TEXT NOT NULL CHECK (review_status IN ('candidate', 'unreviewed', 'needs_manual_review')),
            review_note TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (canonical_record_id) REFERENCES components_candidates(canonical_record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS inference_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_record_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            inferred_value TEXT NOT NULL,
            inference_method TEXT NOT NULL,
            source_field TEXT NOT NULL,
            mapping_rule_version TEXT NOT NULL,
            confidence_category TEXT NOT NULL,
            FOREIGN KEY (canonical_record_id) REFERENCES components_candidates(canonical_record_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_components_source ON components_candidates(source_id, source_record_id);
        CREATE INDEX IF NOT EXISTS idx_components_review ON components_candidates(review_status);
        CREATE INDEX IF NOT EXISTS idx_source_query_records_query ON source_query_records(query_id);
        """
    )


def _try_init_fts(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS candidate_fts USING fts5(
                canonical_record_id UNINDEXED,
                primary_name,
                aliases,
                description,
                abstract_or_summary,
                organism_name,
                identifiers
            )
            """
        )
    except sqlite3.OperationalError:
        return False
    _refresh_fts(conn)
    return True


def _has_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='candidate_fts'").fetchone()
    return row is not None


def _refresh_fts(conn: sqlite3.Connection) -> None:
    if not _has_fts(conn):
        return
    conn.execute("DELETE FROM candidate_fts")
    rows = conn.execute(
        """
        SELECT c.canonical_record_id, c.primary_name, c.description, c.abstract_or_summary, c.organism_name,
               GROUP_CONCAT(DISTINCT a.alias) AS aliases,
               GROUP_CONCAT(DISTINCT i.identifier_type || ':' || i.identifier_value) AS identifiers
        FROM components_candidates c
        LEFT JOIN record_aliases a ON a.canonical_record_id = c.canonical_record_id
        LEFT JOIN record_identifiers i ON i.canonical_record_id = c.canonical_record_id
        GROUP BY c.canonical_record_id
        """
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT INTO candidate_fts (
                canonical_record_id, primary_name, aliases, description,
                abstract_or_summary, organism_name, identifiers
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["canonical_record_id"],
                row["primary_name"],
                row["aliases"] or "",
                row["description"] or "",
                row["abstract_or_summary"] or "",
                row["organism_name"] or "",
                row["identifiers"] or "",
            ),
        )


def _find_canonical_by_identifier(conn: sqlite3.Connection, record: NormalizedRecord) -> str:
    source_row = conn.execute(
        """
        SELECT canonical_record_id FROM source_records
        WHERE source_id = ? AND source_record_id = ?
        """,
        (record.source_id, record.source_record_id),
    ).fetchone()
    if source_row:
        return str(source_row["canonical_record_id"])
    dedupe_identifier_types = {"PMID", "PMCID", "DOI", "UniProt accession", "NCBI Gene ID", "NCBI accession.version"}
    for identifier in record.identifiers:
        identifier_type = clean_text(identifier.get("identifier_type"))
        identifier_value = clean_text(identifier.get("identifier_value"))
        if not identifier_type or not identifier_value or identifier_type not in dedupe_identifier_types:
            continue
        row = conn.execute(
            """
            SELECT canonical_record_id FROM record_identifiers
            WHERE identifier_type = ? AND identifier_value = ?
            """,
            (identifier_type, identifier_value),
        ).fetchone()
        if row:
            return str(row["canonical_record_id"])
    return ""


def _insert_type_specific_rows(conn: sqlite3.Connection, canonical_id: str, record: NormalizedRecord, now: str) -> None:
    if record.record_type == "publication":
        conn.execute(
            """
            INSERT OR REPLACE INTO publications (
                canonical_record_id, title, pmid, pmcid, doi, publication_year, journal, abstract_or_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_id,
                record.primary_name,
                record.pmid,
                record.pmcid,
                record.doi,
                record.publication_year,
                record.journal_or_repository,
                record.abstract_or_summary,
            ),
        )
    if record.record_type == "sequence_or_accession":
        conn.execute(
            """
            INSERT OR REPLACE INTO sequences_or_accessions (
                canonical_record_id, accession, taxon_id, organism_name, protein_name, summary
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_id,
                record.accession,
                record.taxon_id,
                record.organism_name,
                record.primary_name,
                record.abstract_or_summary,
            ),
        )
        if record.taxon_id:
            conn.execute(
                "INSERT OR IGNORE INTO organisms (taxon_id, organism_name, created_at) VALUES (?, ?, ?)",
                (record.taxon_id, record.organism_name, now),
            )
    if "toolkit" in record.component_type_candidate.casefold() or record.assembly_standard_candidate:
        conn.execute(
            """
            INSERT OR REPLACE INTO vectors_or_toolkits_candidates (
                canonical_record_id, toolkit_or_standard_candidate, source_note
            ) VALUES (?, ?, ?)
            """,
            (canonical_id, record.assembly_standard_candidate, record.limitations),
        )
    conn.execute(
        """
        INSERT OR REPLACE INTO evidence_candidates (canonical_record_id, evidence_status, source_note)
        VALUES (?, ?, ?)
        """,
        (canonical_id, record.evidence_status, record.limitations),
    )


def _insert_identifiers_aliases_links(conn: sqlite3.Connection, canonical_id: str, record: NormalizedRecord) -> None:
    for identifier in record.identifiers:
        identifier_type = clean_text(identifier.get("identifier_type"))
        identifier_value = clean_text(identifier.get("identifier_value"))
        if identifier_type and identifier_value:
            conn.execute(
                """
                INSERT OR IGNORE INTO record_identifiers (canonical_record_id, identifier_type, identifier_value)
                VALUES (?, ?, ?)
                """,
                (canonical_id, identifier_type, identifier_value),
            )
    for alias in record.aliases:
        clean_alias = clean_text(alias)
        if clean_alias:
            conn.execute(
                "INSERT OR IGNORE INTO record_aliases (canonical_record_id, alias) VALUES (?, ?)",
                (canonical_id, clean_alias),
            )
    for link in record.links:
        link_type = clean_text(link.get("link_type"))
        url = clean_text(link.get("url"))
        if link_type and url:
            conn.execute(
                "INSERT OR IGNORE INTO record_links (canonical_record_id, link_type, url) VALUES (?, ?, ?)",
                (canonical_id, link_type, url),
            )


def _insert_review_state(conn: sqlite3.Connection, canonical_id: str, review_status: str, now: str) -> None:
    conn.execute(
        """
        INSERT INTO review_states (canonical_record_id, review_status, review_note, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(canonical_record_id) DO UPDATE SET
            review_status=excluded.review_status,
            updated_at=excluded.updated_at
        """,
        (canonical_id, review_status, "Manual source/provenance review required before any curated use.", now),
    )


def _insert_inferences(conn: sqlite3.Connection, canonical_id: str, record: NormalizedRecord) -> None:
    for inference in record.inference_records:
        conn.execute(
            """
            INSERT INTO inference_records (
                canonical_record_id, field_name, inferred_value, inference_method,
                source_field, mapping_rule_version, confidence_category
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_id,
                clean_text(inference.get("field_name")),
                clean_text(inference.get("inferred_value")),
                clean_text(inference.get("inference_method")),
                clean_text(inference.get("source_field")),
                clean_text(inference.get("mapping_rule_version")),
                clean_text(inference.get("confidence_category")),
            ),
        )


def _scalar(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0] or 0) if row else 0


def _group_count(conn: sqlite3.Connection, sql: str) -> dict[str, int]:
    return {str(row[0]): int(row["count"]) for row in conn.execute(sql).fetchall()}
