from __future__ import annotations

import os
import sqlite3
from datetime import datetime, UTC
from typing import Any
from uuid import uuid4

from core.config import DB_PATH


PART_ROLE_TERMS = (
    "promoter",
    "5'UTR",
    "rbs",
    "cds",
    "terminator",
    "other",
)


def _connect() -> sqlite3.Connection:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _clean_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _make_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _optional_text(value: Any) -> str:
    return _clean_text(value)


EXPRESSION_CONSTRUCT_PROFILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS expression_construct_profiles (
    construct_id TEXT PRIMARY KEY,
    construct_label TEXT NOT NULL,
    construct_type TEXT NOT NULL DEFAULT '',
    plasmid_backbone TEXT NOT NULL DEFAULT '',
    host_context_note TEXT NOT NULL DEFAULT '',
    source_reference TEXT NOT NULL DEFAULT '',
    provenance_note TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT '',
    documentation_scope_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

EXPRESSION_CONSTRUCT_CASSETTES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS expression_construct_cassettes (
    cassette_id TEXT PRIMARY KEY,
    construct_id TEXT NOT NULL,
    cassette_label TEXT NOT NULL,
    cassette_role TEXT NOT NULL DEFAULT '',
    cassette_order INTEGER NOT NULL DEFAULT 0,
    promoter_label TEXT NOT NULL DEFAULT '',
    gene_label TEXT NOT NULL DEFAULT '',
    terminator_label TEXT NOT NULL DEFAULT '',
    source_reference TEXT NOT NULL DEFAULT '',
    provenance_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (construct_id) REFERENCES expression_construct_profiles(construct_id) ON DELETE CASCADE
)
"""

EXPRESSION_CONSTRUCT_CASSETTE_PARTS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS expression_construct_cassette_parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cassette_id TEXT NOT NULL,
    part_order INTEGER NOT NULL DEFAULT 0,
    part_role TEXT NOT NULL CHECK (part_role IN ({", ".join(repr(v) for v in PART_ROLE_TERMS)})),
    part_label TEXT NOT NULL DEFAULT '',
    part_reference TEXT NOT NULL DEFAULT '',
    source_reference TEXT NOT NULL DEFAULT '',
    source_catalog TEXT NOT NULL DEFAULT '',
    source_record_id TEXT NOT NULL DEFAULT '',
    source_record_label TEXT NOT NULL DEFAULT '',
    evidence_context_note TEXT NOT NULL DEFAULT '',
    provenance_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (cassette_id) REFERENCES expression_construct_cassettes(cassette_id) ON DELETE CASCADE
)
"""

EXPRESSION_CONSTRUCT_GENE_LINKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS expression_construct_gene_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    construct_id TEXT NOT NULL,
    gene_label TEXT NOT NULL DEFAULT '',
    gene_reference TEXT NOT NULL DEFAULT '',
    source_reference TEXT NOT NULL DEFAULT '',
    provenance_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (construct_id) REFERENCES expression_construct_profiles(construct_id) ON DELETE CASCADE
)
"""

EXPRESSION_CONSTRUCT_PATHWAY_STEP_LINKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS expression_construct_pathway_step_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    construct_id TEXT NOT NULL,
    pathway_step_id TEXT NOT NULL DEFAULT '',
    pathway_step_label TEXT NOT NULL DEFAULT '',
    source_reference TEXT NOT NULL DEFAULT '',
    provenance_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (construct_id) REFERENCES expression_construct_profiles(construct_id) ON DELETE CASCADE
)
"""

EXPRESSION_CONSTRUCT_PROJECT_LINKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS expression_construct_project_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL DEFAULT '',
    construct_id TEXT NOT NULL,
    link_label TEXT NOT NULL DEFAULT '',
    link_note TEXT NOT NULL DEFAULT '',
    source_context TEXT NOT NULL DEFAULT '',
    curation_status TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (construct_id) REFERENCES expression_construct_profiles(construct_id) ON DELETE CASCADE
)
"""


CASSETTE_PART_LINKAGE_COLUMNS = {
    "source_catalog": "TEXT NOT NULL DEFAULT ''",
    "source_record_id": "TEXT NOT NULL DEFAULT ''",
    "source_record_label": "TEXT NOT NULL DEFAULT ''",
    "evidence_context_note": "TEXT NOT NULL DEFAULT ''",
}


def _ensure_cassette_part_linkage_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(expression_construct_cassette_parts)").fetchall()
    }
    for column_name, ddl in CASSETTE_PART_LINKAGE_COLUMNS.items():
        if column_name not in existing_columns:
            conn.execute(
                f"ALTER TABLE expression_construct_cassette_parts ADD COLUMN {column_name} {ddl}"
            )


def init_expression_construct_tables() -> None:
    conn = _connect()
    try:
        conn.execute(EXPRESSION_CONSTRUCT_PROFILES_TABLE_SQL)
        conn.execute(EXPRESSION_CONSTRUCT_CASSETTES_TABLE_SQL)
        conn.execute(EXPRESSION_CONSTRUCT_CASSETTE_PARTS_TABLE_SQL)
        _ensure_cassette_part_linkage_columns(conn)
        conn.execute(EXPRESSION_CONSTRUCT_GENE_LINKS_TABLE_SQL)
        conn.execute(EXPRESSION_CONSTRUCT_PATHWAY_STEP_LINKS_TABLE_SQL)
        conn.execute(EXPRESSION_CONSTRUCT_PROJECT_LINKS_TABLE_SQL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expression_construct_cassettes_construct "
            "ON expression_construct_cassettes (construct_id, cassette_order, cassette_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expression_construct_parts_cassette "
            "ON expression_construct_cassette_parts (cassette_id, part_order, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expression_construct_gene_links_construct "
            "ON expression_construct_gene_links (construct_id, created_at, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expression_construct_pathway_links_construct "
            "ON expression_construct_pathway_step_links (construct_id, created_at, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expression_construct_project_links_project "
            "ON expression_construct_project_links (project_id, created_at, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expression_construct_project_links_construct "
            "ON expression_construct_project_links (construct_id, created_at, id)"
        )
        conn.commit()
    finally:
        conn.close()


def list_construct_profiles() -> list[dict[str, Any]]:
    init_expression_construct_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                construct_id,
                construct_label,
                construct_type,
                plasmid_backbone,
                host_context_note,
                source_reference,
                provenance_note,
                review_status,
                documentation_scope_note,
                created_at,
                updated_at
            FROM expression_construct_profiles
            ORDER BY construct_label COLLATE NOCASE, construct_id
            """
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_construct_profile(construct_id: str) -> dict[str, Any]:
    clean_id = _clean_text(construct_id)
    if not clean_id:
        return {}
    init_expression_construct_tables()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT
                construct_id,
                construct_label,
                construct_type,
                plasmid_backbone,
                host_context_note,
                source_reference,
                provenance_note,
                review_status,
                documentation_scope_note,
                created_at,
                updated_at
            FROM expression_construct_profiles
            WHERE construct_id = ?
            """,
            (clean_id,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_construct_cassettes(construct_id: str) -> list[dict[str, Any]]:
    clean_id = _clean_text(construct_id)
    if not clean_id:
        return []
    init_expression_construct_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                cassette_id,
                construct_id,
                cassette_label,
                cassette_role,
                cassette_order,
                promoter_label,
                gene_label,
                terminator_label,
                source_reference,
                provenance_note,
                created_at,
                updated_at
            FROM expression_construct_cassettes
            WHERE construct_id = ?
            ORDER BY cassette_order, cassette_label COLLATE NOCASE, cassette_id
            """,
            (clean_id,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_construct_cassette_parts(cassette_id: str) -> list[dict[str, Any]]:
    clean_id = _clean_text(cassette_id)
    if not clean_id:
        return []
    init_expression_construct_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                cassette_id,
                part_order,
                part_role,
                part_label,
                part_reference,
                source_reference,
                source_catalog,
                source_record_id,
                source_record_label,
                evidence_context_note,
                provenance_note,
                created_at,
                updated_at
            FROM expression_construct_cassette_parts
            WHERE cassette_id = ?
            ORDER BY part_order, id
            """,
            (clean_id,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_construct_gene_links(construct_id: str) -> list[dict[str, Any]]:
    clean_id = _clean_text(construct_id)
    if not clean_id:
        return []
    init_expression_construct_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                construct_id,
                gene_label,
                gene_reference,
                source_reference,
                provenance_note,
                created_at
            FROM expression_construct_gene_links
            WHERE construct_id = ?
            ORDER BY gene_label COLLATE NOCASE, id
            """,
            (clean_id,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_construct_pathway_step_links(construct_id: str) -> list[dict[str, Any]]:
    clean_id = _clean_text(construct_id)
    if not clean_id:
        return []
    init_expression_construct_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                construct_id,
                pathway_step_id,
                pathway_step_label,
                source_reference,
                provenance_note,
                created_at
            FROM expression_construct_pathway_step_links
            WHERE construct_id = ?
            ORDER BY pathway_step_label COLLATE NOCASE, id
            """
            ,
            (clean_id,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_construct_project_link(link_id: int | str | None) -> dict[str, Any]:
    try:
        resolved_id = int(link_id) if link_id is not None else 0
    except (TypeError, ValueError):
        return {}
    if resolved_id <= 0:
        return {}
    init_expression_construct_tables()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT
                id,
                project_id,
                construct_id,
                link_label,
                link_note,
                source_context,
                curation_status,
                review_note,
                created_at,
                updated_at
            FROM expression_construct_project_links
            WHERE id = ?
            """,
            (resolved_id,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_construct_project_links(
    *,
    project_id: int | str | None = None,
    construct_id: str | None = None,
) -> list[dict[str, Any]]:
    clean_project_id = _clean_text(project_id)
    clean_construct_id = _clean_text(construct_id)
    if not clean_project_id and not clean_construct_id:
        return []
    init_expression_construct_tables()
    clauses: list[str] = []
    params: list[str] = []
    if clean_project_id:
        clauses.append("links.project_id = ?")
        params.append(clean_project_id)
    if clean_construct_id:
        clauses.append("links.construct_id = ?")
        params.append(clean_construct_id)
    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            SELECT
                links.id,
                links.project_id,
                links.construct_id,
                links.link_label,
                links.link_note,
                links.source_context,
                links.curation_status,
                links.review_note,
                links.created_at,
                links.updated_at,
                profiles.construct_label,
                profiles.construct_type,
                profiles.review_status AS construct_review_status
            FROM expression_construct_project_links AS links
            LEFT JOIN expression_construct_profiles AS profiles
                ON profiles.construct_id = links.construct_id
            WHERE {" AND ".join(clauses)}
            ORDER BY
                links.project_id COLLATE NOCASE,
                COALESCE(profiles.construct_label, links.construct_id) COLLATE NOCASE,
                links.created_at,
                links.id
            """,
            tuple(params),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_construct_profiles_for_project(project_id: int | str | None) -> list[dict[str, Any]]:
    clean_project_id = _clean_text(project_id)
    if not clean_project_id:
        return []
    init_expression_construct_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                profiles.construct_id,
                profiles.construct_label,
                profiles.construct_type,
                profiles.plasmid_backbone,
                profiles.host_context_note,
                profiles.source_reference,
                profiles.provenance_note,
                profiles.review_status,
                profiles.documentation_scope_note,
                profiles.created_at,
                profiles.updated_at,
                links.id AS project_link_id,
                links.project_id AS linked_project_id,
                links.link_label AS project_link_label,
                links.link_note AS project_link_note,
                links.source_context AS project_link_source_context,
                links.curation_status AS project_link_curation_status,
                links.review_note AS project_link_review_note
            FROM expression_construct_project_links AS links
            INNER JOIN expression_construct_profiles AS profiles
                ON profiles.construct_id = links.construct_id
            WHERE links.project_id = ?
            ORDER BY
                profiles.construct_label COLLATE NOCASE,
                profiles.construct_id,
                links.id
            """,
            (clean_project_id,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def create_construct_profile(
    *,
    construct_label: str,
    construct_type: str = "",
    plasmid_backbone: str = "",
    host_context_note: str = "",
    source_reference: str = "",
    provenance_note: str = "",
    review_status: str = "",
    documentation_scope_note: str = "",
    construct_id: str | None = None,
) -> dict[str, Any]:
    init_expression_construct_tables()
    clean_label = _clean_text(construct_label) or "Untitled construct draft"
    clean_construct_id = _clean_text(construct_id) or _make_id("construct")
    timestamp = _utc_now()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO expression_construct_profiles (
                construct_id,
                construct_label,
                construct_type,
                plasmid_backbone,
                host_context_note,
                source_reference,
                provenance_note,
                review_status,
                documentation_scope_note,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_construct_id,
                clean_label,
                _optional_text(construct_type),
                _optional_text(plasmid_backbone),
                _optional_text(host_context_note),
                _optional_text(source_reference),
                _optional_text(provenance_note),
                _optional_text(review_status),
                _optional_text(documentation_scope_note),
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_construct_profile(clean_construct_id)


def update_construct_profile(
    construct_id: str,
    *,
    construct_label: str | None = None,
    construct_type: str | None = None,
    plasmid_backbone: str | None = None,
    host_context_note: str | None = None,
    source_reference: str | None = None,
    provenance_note: str | None = None,
    review_status: str | None = None,
    documentation_scope_note: str | None = None,
) -> dict[str, Any]:
    clean_id = _clean_text(construct_id)
    existing = get_construct_profile(clean_id)
    if not existing:
        return {}
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE expression_construct_profiles
            SET construct_label = ?,
                construct_type = ?,
                plasmid_backbone = ?,
                host_context_note = ?,
                source_reference = ?,
                provenance_note = ?,
                review_status = ?,
                documentation_scope_note = ?,
                updated_at = ?
            WHERE construct_id = ?
            """,
            (
                _clean_text(construct_label) or _clean_text(existing.get("construct_label")) or "Untitled construct draft",
                _optional_text(existing.get("construct_type") if construct_type is None else construct_type),
                _optional_text(existing.get("plasmid_backbone") if plasmid_backbone is None else plasmid_backbone),
                _optional_text(existing.get("host_context_note") if host_context_note is None else host_context_note),
                _optional_text(existing.get("source_reference") if source_reference is None else source_reference),
                _optional_text(existing.get("provenance_note") if provenance_note is None else provenance_note),
                _optional_text(existing.get("review_status") if review_status is None else review_status),
                _optional_text(existing.get("documentation_scope_note") if documentation_scope_note is None else documentation_scope_note),
                _utc_now(),
                clean_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_construct_profile(clean_id)


def create_construct_cassette(
    construct_id: str,
    *,
    cassette_label: str,
    cassette_role: str = "",
    cassette_order: int = 0,
    promoter_label: str = "",
    gene_label: str = "",
    terminator_label: str = "",
    source_reference: str = "",
    provenance_note: str = "",
    cassette_id: str | None = None,
) -> dict[str, Any]:
    clean_construct_id = _clean_text(construct_id)
    if not get_construct_profile(clean_construct_id):
        return {}
    clean_cassette_id = _clean_text(cassette_id) or _make_id("cassette")
    timestamp = _utc_now()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO expression_construct_cassettes (
                cassette_id,
                construct_id,
                cassette_label,
                cassette_role,
                cassette_order,
                promoter_label,
                gene_label,
                terminator_label,
                source_reference,
                provenance_note,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_cassette_id,
                clean_construct_id,
                _clean_text(cassette_label) or "Untitled cassette draft",
                _optional_text(cassette_role),
                _clean_int(cassette_order),
                _optional_text(promoter_label),
                _optional_text(gene_label),
                _optional_text(terminator_label),
                _optional_text(source_reference),
                _optional_text(provenance_note),
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    rows = list_construct_cassettes(clean_construct_id)
    return next((row for row in rows if row.get("cassette_id") == clean_cassette_id), {})


def update_construct_cassette(
    cassette_id: str,
    *,
    cassette_label: str | None = None,
    cassette_role: str | None = None,
    cassette_order: int | None = None,
    promoter_label: str | None = None,
    gene_label: str | None = None,
    terminator_label: str | None = None,
    source_reference: str | None = None,
    provenance_note: str | None = None,
) -> dict[str, Any]:
    clean_id = _clean_text(cassette_id)
    if not clean_id:
        return {}
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM expression_construct_cassettes WHERE cassette_id = ?",
            (clean_id,),
        ).fetchone()
        existing = _row_to_dict(row)
        if not existing:
            return {}
        conn.execute(
            """
            UPDATE expression_construct_cassettes
            SET cassette_label = ?,
                cassette_role = ?,
                cassette_order = ?,
                promoter_label = ?,
                gene_label = ?,
                terminator_label = ?,
                source_reference = ?,
                provenance_note = ?,
                updated_at = ?
            WHERE cassette_id = ?
            """,
            (
                _clean_text(cassette_label) or _clean_text(existing.get("cassette_label")) or "Untitled cassette draft",
                _optional_text(existing.get("cassette_role") if cassette_role is None else cassette_role),
                _clean_int(existing.get("cassette_order") if cassette_order is None else cassette_order),
                _optional_text(existing.get("promoter_label") if promoter_label is None else promoter_label),
                _optional_text(existing.get("gene_label") if gene_label is None else gene_label),
                _optional_text(existing.get("terminator_label") if terminator_label is None else terminator_label),
                _optional_text(existing.get("source_reference") if source_reference is None else source_reference),
                _optional_text(existing.get("provenance_note") if provenance_note is None else provenance_note),
                _utc_now(),
                clean_id,
            ),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM expression_construct_cassettes WHERE cassette_id = ?",
            (clean_id,),
        ).fetchone()
        return _row_to_dict(updated)
    finally:
        conn.close()


def add_construct_cassette_part(
    cassette_id: str,
    *,
    part_order: int = 0,
    part_role: str = "other",
    part_label: str = "",
    part_reference: str = "",
    source_reference: str = "",
    source_catalog: str = "",
    source_record_id: str = "",
    source_record_label: str = "",
    evidence_context_note: str = "",
    provenance_note: str = "",
) -> dict[str, Any]:
    clean_cassette_id = _clean_text(cassette_id)
    if not clean_cassette_id:
        return {}
    if not _get_construct_id_for_cassette(clean_cassette_id):
        return {}
    clean_role = _clean_text(part_role) or "other"
    if clean_role not in PART_ROLE_TERMS:
        clean_role = "other"
    timestamp = _utc_now()
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO expression_construct_cassette_parts (
                cassette_id,
                part_order,
                part_role,
                part_label,
                part_reference,
                source_reference,
                source_catalog,
                source_record_id,
                source_record_label,
                evidence_context_note,
                provenance_note,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_cassette_id,
                _clean_int(part_order),
                clean_role,
                _optional_text(part_label),
                _optional_text(part_reference),
                _optional_text(source_reference),
                _optional_text(source_catalog),
                _optional_text(source_record_id),
                _optional_text(source_record_label),
                _optional_text(evidence_context_note),
                _optional_text(provenance_note),
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        part_id = int(cursor.lastrowid)
        row = conn.execute(
            "SELECT * FROM expression_construct_cassette_parts WHERE id = ?",
            (part_id,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_construct_cassette_part(
    part_id: int,
    *,
    part_order: int | None = None,
    part_role: str | None = None,
    part_label: str | None = None,
    part_reference: str | None = None,
    source_reference: str | None = None,
    source_catalog: str | None = None,
    source_record_id: str | None = None,
    source_record_label: str | None = None,
    evidence_context_note: str | None = None,
    provenance_note: str | None = None,
) -> dict[str, Any]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM expression_construct_cassette_parts WHERE id = ?",
            (part_id,),
        ).fetchone()
        existing = _row_to_dict(row)
        if not existing:
            return {}
        clean_role = _optional_text(existing.get("part_role") if part_role is None else part_role) or "other"
        if clean_role not in PART_ROLE_TERMS:
            clean_role = "other"
        conn.execute(
            """
            UPDATE expression_construct_cassette_parts
            SET part_order = ?,
                part_role = ?,
                part_label = ?,
                part_reference = ?,
                source_reference = ?,
                source_catalog = ?,
                source_record_id = ?,
                source_record_label = ?,
                evidence_context_note = ?,
                provenance_note = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                _clean_int(existing.get("part_order") if part_order is None else part_order),
                clean_role,
                _optional_text(existing.get("part_label") if part_label is None else part_label),
                _optional_text(existing.get("part_reference") if part_reference is None else part_reference),
                _optional_text(existing.get("source_reference") if source_reference is None else source_reference),
                _optional_text(existing.get("source_catalog") if source_catalog is None else source_catalog),
                _optional_text(existing.get("source_record_id") if source_record_id is None else source_record_id),
                _optional_text(existing.get("source_record_label") if source_record_label is None else source_record_label),
                _optional_text(existing.get("evidence_context_note") if evidence_context_note is None else evidence_context_note),
                _optional_text(existing.get("provenance_note") if provenance_note is None else provenance_note),
                _utc_now(),
                part_id,
            ),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM expression_construct_cassette_parts WHERE id = ?",
            (part_id,),
        ).fetchone()
        return _row_to_dict(updated)
    finally:
        conn.close()


def _get_construct_id_for_cassette(cassette_id: str) -> str:
    clean_id = _clean_text(cassette_id)
    if not clean_id:
        return ""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT construct_id FROM expression_construct_cassettes WHERE cassette_id = ?",
            (clean_id,),
        ).fetchone()
        return _clean_text(row["construct_id"]) if row else ""
    finally:
        conn.close()


def add_construct_gene_link(
    construct_id: str,
    *,
    gene_label: str = "",
    gene_reference: str = "",
    source_reference: str = "",
    provenance_note: str = "",
) -> dict[str, Any]:
    clean_construct_id = _clean_text(construct_id)
    if not get_construct_profile(clean_construct_id):
        return {}
    timestamp = _utc_now()
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO expression_construct_gene_links (
                construct_id,
                gene_label,
                gene_reference,
                source_reference,
                provenance_note,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                clean_construct_id,
                _optional_text(gene_label),
                _optional_text(gene_reference),
                _optional_text(source_reference),
                _optional_text(provenance_note),
                timestamp,
            ),
        )
        conn.commit()
        link_id = int(cursor.lastrowid)
        row = conn.execute(
            "SELECT * FROM expression_construct_gene_links WHERE id = ?",
            (link_id,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_construct_gene_link(
    link_id: int,
    *,
    gene_label: str | None = None,
    gene_reference: str | None = None,
    source_reference: str | None = None,
    provenance_note: str | None = None,
) -> dict[str, Any]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM expression_construct_gene_links WHERE id = ?",
            (link_id,),
        ).fetchone()
        existing = _row_to_dict(row)
        if not existing:
            return {}
        conn.execute(
            """
            UPDATE expression_construct_gene_links
            SET gene_label = ?,
                gene_reference = ?,
                source_reference = ?,
                provenance_note = ?
            WHERE id = ?
            """,
            (
                _optional_text(existing.get("gene_label") if gene_label is None else gene_label),
                _optional_text(existing.get("gene_reference") if gene_reference is None else gene_reference),
                _optional_text(existing.get("source_reference") if source_reference is None else source_reference),
                _optional_text(existing.get("provenance_note") if provenance_note is None else provenance_note),
                link_id,
            ),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM expression_construct_gene_links WHERE id = ?",
            (link_id,),
        ).fetchone()
        return _row_to_dict(updated)
    finally:
        conn.close()


def add_construct_pathway_step_link(
    construct_id: str,
    *,
    pathway_step_id: str = "",
    pathway_step_label: str = "",
    source_reference: str = "",
    provenance_note: str = "",
) -> dict[str, Any]:
    clean_construct_id = _clean_text(construct_id)
    if not get_construct_profile(clean_construct_id):
        return {}
    timestamp = _utc_now()
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO expression_construct_pathway_step_links (
                construct_id,
                pathway_step_id,
                pathway_step_label,
                source_reference,
                provenance_note,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                clean_construct_id,
                _optional_text(pathway_step_id),
                _optional_text(pathway_step_label),
                _optional_text(source_reference),
                _optional_text(provenance_note),
                timestamp,
            ),
        )
        conn.commit()
        link_id = int(cursor.lastrowid)
        row = conn.execute(
            "SELECT * FROM expression_construct_pathway_step_links WHERE id = ?",
            (link_id,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_construct_pathway_step_link(
    link_id: int,
    *,
    pathway_step_id: str | None = None,
    pathway_step_label: str | None = None,
    source_reference: str | None = None,
    provenance_note: str | None = None,
) -> dict[str, Any]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM expression_construct_pathway_step_links WHERE id = ?",
            (link_id,),
        ).fetchone()
        existing = _row_to_dict(row)
        if not existing:
            return {}
        conn.execute(
            """
            UPDATE expression_construct_pathway_step_links
            SET pathway_step_id = ?,
                pathway_step_label = ?,
                source_reference = ?,
                provenance_note = ?
            WHERE id = ?
            """,
            (
                _optional_text(existing.get("pathway_step_id") if pathway_step_id is None else pathway_step_id),
                _optional_text(existing.get("pathway_step_label") if pathway_step_label is None else pathway_step_label),
                _optional_text(existing.get("source_reference") if source_reference is None else source_reference),
                _optional_text(existing.get("provenance_note") if provenance_note is None else provenance_note),
                link_id,
            ),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM expression_construct_pathway_step_links WHERE id = ?",
            (link_id,),
        ).fetchone()
        return _row_to_dict(updated)
    finally:
        conn.close()


def create_construct_project_link(
    *,
    project_id: int | str | None,
    construct_id: str,
    link_label: str = "",
    link_note: str = "",
    source_context: str = "",
    curation_status: str = "",
    review_note: str = "",
) -> dict[str, Any]:
    clean_project_id = _clean_text(project_id)
    clean_construct_id = _clean_text(construct_id)
    if not clean_project_id or not get_construct_profile(clean_construct_id):
        return {}
    timestamp = _utc_now()
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO expression_construct_project_links (
                project_id,
                construct_id,
                link_label,
                link_note,
                source_context,
                curation_status,
                review_note,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_project_id,
                clean_construct_id,
                _optional_text(link_label),
                _optional_text(link_note),
                _optional_text(source_context),
                _optional_text(curation_status),
                _optional_text(review_note),
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        return get_construct_project_link(int(cursor.lastrowid))
    finally:
        conn.close()


def update_construct_project_link(
    link_id: int | str | None,
    *,
    link_label: str | None = None,
    link_note: str | None = None,
    source_context: str | None = None,
    curation_status: str | None = None,
    review_note: str | None = None,
) -> dict[str, Any]:
    existing = get_construct_project_link(link_id)
    if not existing:
        return {}
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE expression_construct_project_links
            SET link_label = ?,
                link_note = ?,
                source_context = ?,
                curation_status = ?,
                review_note = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                _optional_text(existing.get("link_label") if link_label is None else link_label),
                _optional_text(existing.get("link_note") if link_note is None else link_note),
                _optional_text(existing.get("source_context") if source_context is None else source_context),
                _optional_text(existing.get("curation_status") if curation_status is None else curation_status),
                _optional_text(existing.get("review_note") if review_note is None else review_note),
                _utc_now(),
                int(existing["id"]),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_construct_project_link(existing["id"])
