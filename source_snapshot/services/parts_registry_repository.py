from __future__ import annotations

import os
import sqlite3
from typing import Any

from core.config import DB_PATH


PART_TYPE_VOCABULARY = (
    "Promoter",
    "RBS / 5' UTR",
    "Terminator",
    "CDS reference",
    "Tag / linker",
    "Origin",
    "Marker",
)

CURATION_STATUS_TERMS = (
    "metadata incomplete",
    "metadata reviewed",
    "provenance review needed",
)

HUMAN_REVIEW_STATUS_TERMS = (
    "human review needed",
    "human review documented",
    "follow-up documentation needed",
)

PART_LINK_TARGET_TYPES = (
    "pathway_project",
    "pathway_step",
    "saved_expression_design",
    "documentation_snapshot",
    "linked_tool_artifact",
)

PART_LINK_REVIEW_STATUS_TERMS = (
    "traceability review needed",
    "traceability reviewed",
    "follow-up documentation needed",
)

PLANT_PROMOTER_CLADE_TERMS = (
    "monocot",
    "dicot",
    "other / not specified",
)


PARTS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS parts (
    local_id TEXT PRIMARY KEY,
    part_type TEXT NOT NULL CHECK (part_type IN ({", ".join(repr(v) for v in PART_TYPE_VOCABULARY)})),
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

PART_VERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS part_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_local_id TEXT NOT NULL,
    version_label TEXT NOT NULL,
    sequence TEXT,
    sequence_hash TEXT,
    sequence_hash_algorithm TEXT,
    version_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (part_local_id) REFERENCES parts(local_id) ON DELETE CASCADE,
    UNIQUE (part_local_id, version_label),
    CHECK (
        (
            sequence IS NULL
            AND sequence_hash IS NULL
            AND sequence_hash_algorithm IS NULL
        )
        OR
        (
            sequence IS NOT NULL
            AND TRIM(sequence) <> ''
            AND sequence_hash IS NOT NULL
            AND TRIM(sequence_hash) <> ''
            AND sequence_hash_algorithm IS NOT NULL
            AND TRIM(sequence_hash_algorithm) <> ''
        )
    )
)
"""

PART_SOURCES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS part_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_local_id TEXT NOT NULL,
    part_version_id INTEGER,
    source_name TEXT NOT NULL DEFAULT '',
    source_reference TEXT NOT NULL DEFAULT '',
    organism_or_source_context TEXT NOT NULL DEFAULT '',
    provenance_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (part_local_id) REFERENCES parts(local_id) ON DELETE CASCADE,
    FOREIGN KEY (part_version_id) REFERENCES part_versions(id) ON DELETE CASCADE
)
"""

PART_ANNOTATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS part_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_local_id TEXT NOT NULL,
    part_version_id INTEGER,
    annotation_type TEXT NOT NULL DEFAULT 'documentation note',
    annotation_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (part_local_id) REFERENCES parts(local_id) ON DELETE CASCADE,
    FOREIGN KEY (part_version_id) REFERENCES part_versions(id) ON DELETE CASCADE
)
"""

PART_REVIEW_STATUS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS part_review_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_local_id TEXT NOT NULL,
    part_version_id INTEGER,
    curation_status TEXT NOT NULL CHECK (curation_status IN ({", ".join(repr(v) for v in CURATION_STATUS_TERMS)})),
    human_review_status TEXT NOT NULL CHECK (human_review_status IN ({", ".join(repr(v) for v in HUMAN_REVIEW_STATUS_TERMS)})),
    review_note TEXT NOT NULL DEFAULT '',
    reviewer_name_or_initials TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (part_local_id) REFERENCES parts(local_id) ON DELETE CASCADE,
    FOREIGN KEY (part_version_id) REFERENCES part_versions(id) ON DELETE CASCADE
)
"""

PART_PROJECT_LINKS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS part_project_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_local_id TEXT NOT NULL,
    part_version_id INTEGER,
    target_type TEXT NOT NULL CHECK (target_type IN ({", ".join(repr(v) for v in PART_LINK_TARGET_TYPES)})),
    target_id TEXT NOT NULL,
    target_label TEXT NOT NULL DEFAULT '',
    link_note TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL CHECK (review_status IN ({", ".join(repr(v) for v in PART_LINK_REVIEW_STATUS_TERMS)})),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (part_local_id) REFERENCES parts(local_id) ON DELETE CASCADE,
    FOREIGN KEY (part_version_id) REFERENCES part_versions(id) ON DELETE CASCADE
)
"""

PLANT_PROMOTER_PROFILES_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS plant_promoter_profiles (
    part_id TEXT PRIMARY KEY,
    plant_clade TEXT NOT NULL CHECK (plant_clade IN ({", ".join(repr(v) for v in PLANT_PROMOTER_CLADE_TERMS)})),
    species_scientific_name TEXT NOT NULL DEFAULT '',
    species_common_name TEXT NOT NULL DEFAULT '',
    taxonomy_id TEXT NOT NULL DEFAULT '',
    cultivar_or_ecotype TEXT NOT NULL DEFAULT '',
    native_gene_or_locus TEXT NOT NULL DEFAULT '',
    promoter_type TEXT NOT NULL DEFAULT '',
    sequence_availability TEXT NOT NULL DEFAULT '',
    sequence_scope_note TEXT NOT NULL DEFAULT '',
    tss_reference_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (part_id) REFERENCES parts(local_id) ON DELETE CASCADE
)
"""

PLANT_PROMOTER_TISSUE_EVIDENCE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS plant_promoter_tissue_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id TEXT NOT NULL,
    tissue_context TEXT NOT NULL DEFAULT '',
    plant_ontology_id TEXT NOT NULL DEFAULT '',
    development_stage TEXT NOT NULL DEFAULT '',
    expression_context_label TEXT NOT NULL DEFAULT '',
    evidence_type TEXT NOT NULL DEFAULT '',
    evidence_summary TEXT NOT NULL DEFAULT '',
    source_database TEXT NOT NULL DEFAULT '',
    source_accession TEXT NOT NULL DEFAULT '',
    publication_reference TEXT NOT NULL DEFAULT '',
    curation_status TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (part_id) REFERENCES plant_promoter_profiles(part_id) ON DELETE CASCADE
)
"""

PLANT_PROMOTER_MOTIF_ANNOTATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS plant_promoter_motif_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id TEXT NOT NULL,
    motif_name TEXT NOT NULL DEFAULT '',
    motif_source TEXT NOT NULL DEFAULT '',
    motif_accession TEXT NOT NULL DEFAULT '',
    motif_sequence_or_consensus TEXT NOT NULL DEFAULT '',
    motif_position_note TEXT NOT NULL DEFAULT '',
    associated_function_note TEXT NOT NULL DEFAULT '',
    evidence_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (part_id) REFERENCES plant_promoter_profiles(part_id) ON DELETE CASCADE
)
"""


def _connect() -> sqlite3.Connection:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def init_parts_registry_tables() -> None:
    """Create the V2.3-R1 read-only registry schema slice."""
    conn = _connect()
    try:
        conn.execute(PARTS_TABLE_SQL)
        conn.execute(PART_VERSIONS_TABLE_SQL)
        conn.execute(PART_SOURCES_TABLE_SQL)
        conn.execute(PART_ANNOTATIONS_TABLE_SQL)
        conn.execute(PART_REVIEW_STATUS_TABLE_SQL)
        conn.execute(PART_PROJECT_LINKS_TABLE_SQL)
        conn.execute(PLANT_PROMOTER_PROFILES_TABLE_SQL)
        conn.execute(PLANT_PROMOTER_TISSUE_EVIDENCE_TABLE_SQL)
        conn.execute(PLANT_PROMOTER_MOTIF_ANNOTATIONS_TABLE_SQL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_part_versions_part "
            "ON part_versions (part_local_id, created_at DESC, id DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_part_sources_part "
            "ON part_sources (part_local_id, part_version_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_part_annotations_part "
            "ON part_annotations (part_local_id, part_version_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_part_review_status_part "
            "ON part_review_status (part_local_id, part_version_id, created_at DESC, id DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_part_project_links_part "
            "ON part_project_links (part_local_id, part_version_id, created_at DESC, id DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_part_project_links_target "
            "ON part_project_links (target_type, target_id, created_at DESC, id DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plant_promoter_profiles_clade "
            "ON plant_promoter_profiles (plant_clade, species_scientific_name COLLATE NOCASE)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plant_promoter_profiles_species "
            "ON plant_promoter_profiles (species_scientific_name COLLATE NOCASE, species_common_name COLLATE NOCASE)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plant_promoter_tissue_part "
            "ON plant_promoter_tissue_evidence (part_id, tissue_context COLLATE NOCASE, created_at DESC, id DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plant_promoter_tissue_context "
            "ON plant_promoter_tissue_evidence (tissue_context COLLATE NOCASE, part_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plant_promoter_motifs_part "
            "ON plant_promoter_motif_annotations (part_id, created_at DESC, id DESC)"
        )
        conn.commit()
    finally:
        conn.close()


def list_parts() -> list[dict[str, Any]]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT local_id, part_type, display_name, description, created_at, updated_at
            FROM parts
            ORDER BY display_name COLLATE NOCASE, local_id
            """
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_part_by_local_id(local_id: str) -> dict[str, Any]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT local_id, part_type, display_name, description, created_at, updated_at
            FROM parts
            WHERE local_id = ?
            """,
            (str(local_id or "").strip(),),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_versions_for_part(local_id: str) -> list[dict[str, Any]]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                id, part_local_id, version_label, sequence, sequence_hash,
                sequence_hash_algorithm, version_note, created_at, updated_at
            FROM part_versions
            WHERE part_local_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (str(local_id or "").strip(),),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_source_records(local_id: str) -> list[dict[str, Any]]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                id, part_local_id, part_version_id, source_name, source_reference,
                organism_or_source_context, provenance_note, created_at
            FROM part_sources
            WHERE part_local_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (str(local_id or "").strip(),),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_annotations(local_id: str) -> list[dict[str, Any]]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                id, part_local_id, part_version_id, annotation_type,
                annotation_text, created_at
            FROM part_annotations
            WHERE part_local_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (str(local_id or "").strip(),),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_review_status_records(local_id: str) -> list[dict[str, Any]]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                id, part_local_id, part_version_id, curation_status,
                human_review_status, review_note, reviewer_name_or_initials,
                reviewed_at, created_at
            FROM part_review_status
            WHERE part_local_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (str(local_id or "").strip(),),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_links_for_part(local_id: str) -> list[dict[str, Any]]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                id, part_local_id, part_version_id, target_type, target_id,
                target_label, link_note, review_status, created_at, updated_at
            FROM part_project_links
            WHERE part_local_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (str(local_id or "").strip(),),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_links_for_target(target_type: str, target_id: str) -> list[dict[str, Any]]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                id, part_local_id, part_version_id, target_type, target_id,
                target_label, link_note, review_status, created_at, updated_at
            FROM part_project_links
            WHERE target_type = ? AND target_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (str(target_type or "").strip(), str(target_id or "").strip()),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_link_by_id(link_id: int | str) -> dict[str, Any]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT
                id, part_local_id, part_version_id, target_type, target_id,
                target_label, link_note, review_status, created_at, updated_at
            FROM part_project_links
            WHERE id = ?
            """,
            (link_id,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_plant_promoter_profiles(
    *,
    plant_clade: str | None = None,
    species: str | None = None,
    tissue_context: str | None = None,
) -> list[dict[str, Any]]:
    """Return read-only plant promoter profile rows with optional documentation filters."""
    init_parts_registry_tables()
    filters: list[str] = []
    params: list[str] = []

    clean_clade = _clean_text(plant_clade).lower()
    if clean_clade:
        filters.append("LOWER(pp.plant_clade) = ?")
        params.append(clean_clade)

    clean_species = _clean_text(species).lower()
    if clean_species:
        filters.append(
            "("
            "LOWER(pp.species_scientific_name) LIKE ? "
            "OR LOWER(pp.species_common_name) LIKE ?"
            ")"
        )
        species_like = f"%{clean_species}%"
        params.extend([species_like, species_like])

    clean_tissue = _clean_text(tissue_context).lower()
    if clean_tissue:
        filters.append(
            """
            EXISTS (
                SELECT 1
                FROM plant_promoter_tissue_evidence pte
                WHERE pte.part_id = pp.part_id
                  AND LOWER(pte.tissue_context) = ?
            )
            """
        )
        params.append(clean_tissue)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            SELECT
                pp.part_id,
                p.part_type,
                p.display_name,
                p.description,
                pp.plant_clade,
                pp.species_scientific_name,
                pp.species_common_name,
                pp.taxonomy_id,
                pp.cultivar_or_ecotype,
                pp.native_gene_or_locus,
                pp.promoter_type,
                pp.sequence_availability,
                pp.sequence_scope_note,
                pp.tss_reference_note,
                pp.created_at,
                pp.updated_at
            FROM plant_promoter_profiles pp
            JOIN parts p ON p.local_id = pp.part_id
            {where_clause}
            ORDER BY p.display_name COLLATE NOCASE, pp.part_id
            """,
            params,
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_plant_promoter_profile_by_part_id(part_id: str) -> dict[str, Any]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT
                pp.part_id,
                p.part_type,
                p.display_name,
                p.description,
                pp.plant_clade,
                pp.species_scientific_name,
                pp.species_common_name,
                pp.taxonomy_id,
                pp.cultivar_or_ecotype,
                pp.native_gene_or_locus,
                pp.promoter_type,
                pp.sequence_availability,
                pp.sequence_scope_note,
                pp.tss_reference_note,
                pp.created_at,
                pp.updated_at
            FROM plant_promoter_profiles pp
            JOIN parts p ON p.local_id = pp.part_id
            WHERE pp.part_id = ?
            """,
            (_clean_text(part_id),),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_plant_promoter_profiles_by_clade(plant_clade: str) -> list[dict[str, Any]]:
    return list_plant_promoter_profiles(plant_clade=plant_clade)


def list_plant_promoter_profiles_by_species(species: str) -> list[dict[str, Any]]:
    return list_plant_promoter_profiles(species=species)


def list_plant_promoter_profiles_by_tissue_context(tissue_context: str) -> list[dict[str, Any]]:
    return list_plant_promoter_profiles(tissue_context=tissue_context)


def list_plant_promoter_tissue_evidence(
    part_id: str,
    *,
    tissue_context: str | None = None,
) -> list[dict[str, Any]]:
    init_parts_registry_tables()
    filters = ["part_id = ?"]
    params = [_clean_text(part_id)]
    clean_tissue = _clean_text(tissue_context).lower()
    if clean_tissue:
        filters.append("LOWER(tissue_context) = ?")
        params.append(clean_tissue)

    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            SELECT
                id,
                part_id,
                tissue_context,
                plant_ontology_id,
                development_stage,
                expression_context_label,
                evidence_type,
                evidence_summary,
                source_database,
                source_accession,
                publication_reference,
                curation_status,
                review_note,
                created_at,
                updated_at
            FROM plant_promoter_tissue_evidence
            WHERE {' AND '.join(filters)}
            ORDER BY tissue_context COLLATE NOCASE, created_at DESC, id DESC
            """,
            params,
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def list_plant_promoter_motif_annotations(part_id: str) -> list[dict[str, Any]]:
    init_parts_registry_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                part_id,
                motif_name,
                motif_source,
                motif_accession,
                motif_sequence_or_consensus,
                motif_position_note,
                associated_function_note,
                evidence_note,
                created_at,
                updated_at
            FROM plant_promoter_motif_annotations
            WHERE part_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (_clean_text(part_id),),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()
