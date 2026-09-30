from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from services import parts_registry_repository as repo


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _success(record: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "record": record, "error": ""}


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "record": {}, "error": message}


def _validate_term(value: str, allowed: tuple[str, ...], label: str) -> str | None:
    if value not in allowed:
        return f"{label} must use an allowed documentation term."
    return None


def _part_exists(conn: sqlite3.Connection, local_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM parts WHERE local_id = ?", (local_id,)).fetchone()
    return row is not None


def _version_belongs_to_part(
    conn: sqlite3.Connection,
    local_id: str,
    part_version_id: int | None,
) -> bool:
    if part_version_id is None:
        return True
    row = conn.execute(
        "SELECT 1 FROM part_versions WHERE id = ? AND part_local_id = ?",
        (part_version_id, local_id),
    ).fetchone()
    return row is not None


def _get_record_by_id(conn: sqlite3.Connection, table: str, row_id: int) -> dict[str, Any]:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    return dict(row) if row is not None else {}


def create_local_part(
    *,
    local_id: str,
    part_type: str,
    display_name: str,
    description: str = "",
) -> dict[str, Any]:
    local_id = _clean_text(local_id)
    part_type = _clean_text(part_type)
    display_name = _clean_text(display_name)
    description = _clean_text(description)

    if not local_id:
        return _error("local_id is required.")
    if not display_name:
        return _error("display_name is required.")
    term_error = _validate_term(part_type, repo.PART_TYPE_VOCABULARY, "part_type")
    if term_error:
        return _error(term_error)

    repo.init_parts_registry_tables()
    conn = repo._connect()
    try:
        if _part_exists(conn, local_id):
            return _error("local_id already exists.")
        timestamp = _now_iso()
        conn.execute(
            """
            INSERT INTO parts
                (local_id, part_type, display_name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (local_id, part_type, display_name, description, timestamp, timestamp),
        )
        conn.commit()
        return _success(repo.get_part_by_local_id(local_id))
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return _error(f"Could not create local part record: {exc}")
    finally:
        conn.close()


def add_part_version(
    *,
    part_local_id: str,
    version_label: str,
    sequence: str | None = None,
    sequence_hash: str | None = None,
    sequence_hash_algorithm: str | None = None,
    version_note: str = "",
) -> dict[str, Any]:
    part_local_id = _clean_text(part_local_id)
    version_label = _clean_text(version_label)
    sequence_value = _clean_text(sequence) if sequence is not None else None
    sequence_hash_value = _clean_text(sequence_hash) if sequence_hash is not None else None
    algorithm_value = _clean_text(sequence_hash_algorithm) if sequence_hash_algorithm is not None else None
    version_note = _clean_text(version_note)

    if not part_local_id:
        return _error("part_local_id is required.")
    if not version_label:
        return _error("version_label is required.")
    has_sequence = bool(sequence_value)
    has_hash = bool(sequence_hash_value)
    has_algorithm = bool(algorithm_value)
    if has_sequence and not (has_hash and has_algorithm):
        return _error("sequence_hash and sequence_hash_algorithm are required when sequence is present.")
    if not has_sequence and (has_hash or has_algorithm):
        return _error("sequence metadata must be absent when sequence is absent.")
    if not has_sequence:
        sequence_value = None
        sequence_hash_value = None
        algorithm_value = None

    repo.init_parts_registry_tables()
    conn = repo._connect()
    try:
        if not _part_exists(conn, part_local_id):
            return _error("part_local_id does not match a local part record.")
        timestamp = _now_iso()
        cursor = conn.execute(
            """
            INSERT INTO part_versions
                (part_local_id, version_label, sequence, sequence_hash,
                 sequence_hash_algorithm, version_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                part_local_id,
                version_label,
                sequence_value,
                sequence_hash_value,
                algorithm_value,
                version_note,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        return _success(_get_record_by_id(conn, "part_versions", int(cursor.lastrowid)))
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return _error(f"Could not add part version record: {exc}")
    finally:
        conn.close()


def add_part_source(
    *,
    part_local_id: str,
    part_version_id: int | None = None,
    source_name: str = "",
    source_reference: str = "",
    organism_or_source_context: str = "",
    provenance_note: str = "",
) -> dict[str, Any]:
    part_local_id = _clean_text(part_local_id)
    source_name = _clean_text(source_name)
    source_reference = _clean_text(source_reference)
    organism_or_source_context = _clean_text(organism_or_source_context)
    provenance_note = _clean_text(provenance_note)

    repo.init_parts_registry_tables()
    conn = repo._connect()
    try:
        if not _part_exists(conn, part_local_id):
            return _error("part_local_id does not match a local part record.")
        if not _version_belongs_to_part(conn, part_local_id, part_version_id):
            return _error("part_version_id does not match the local part record.")
        cursor = conn.execute(
            """
            INSERT INTO part_sources
                (part_local_id, part_version_id, source_name, source_reference,
                 organism_or_source_context, provenance_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                part_local_id,
                part_version_id,
                source_name,
                source_reference,
                organism_or_source_context,
                provenance_note,
                _now_iso(),
            ),
        )
        conn.commit()
        return _success(_get_record_by_id(conn, "part_sources", int(cursor.lastrowid)))
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return _error(f"Could not add source record: {exc}")
    finally:
        conn.close()


def add_part_annotation(
    *,
    part_local_id: str,
    part_version_id: int | None = None,
    annotation_type: str = "documentation note",
    annotation_text: str = "",
) -> dict[str, Any]:
    part_local_id = _clean_text(part_local_id)
    annotation_type = _clean_text(annotation_type) or "documentation note"
    annotation_text = _clean_text(annotation_text)
    if not annotation_text:
        return _error("annotation_text is required.")

    repo.init_parts_registry_tables()
    conn = repo._connect()
    try:
        if not _part_exists(conn, part_local_id):
            return _error("part_local_id does not match a local part record.")
        if not _version_belongs_to_part(conn, part_local_id, part_version_id):
            return _error("part_version_id does not match the local part record.")
        cursor = conn.execute(
            """
            INSERT INTO part_annotations
                (part_local_id, part_version_id, annotation_type, annotation_text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (part_local_id, part_version_id, annotation_type, annotation_text, _now_iso()),
        )
        conn.commit()
        return _success(_get_record_by_id(conn, "part_annotations", int(cursor.lastrowid)))
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return _error(f"Could not add annotation record: {exc}")
    finally:
        conn.close()


def add_part_review_status(
    *,
    part_local_id: str,
    part_version_id: int | None = None,
    curation_status: str,
    human_review_status: str,
    review_note: str = "",
    reviewer_name_or_initials: str = "",
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    part_local_id = _clean_text(part_local_id)
    curation_status = _clean_text(curation_status)
    human_review_status = _clean_text(human_review_status)
    review_note = _clean_text(review_note)
    reviewer_name_or_initials = _clean_text(reviewer_name_or_initials)
    reviewed_at_value = _clean_text(reviewed_at) or None

    for value, allowed, label in (
        (curation_status, repo.CURATION_STATUS_TERMS, "curation_status"),
        (human_review_status, repo.HUMAN_REVIEW_STATUS_TERMS, "human_review_status"),
    ):
        term_error = _validate_term(value, allowed, label)
        if term_error:
            return _error(term_error)

    repo.init_parts_registry_tables()
    conn = repo._connect()
    try:
        if not _part_exists(conn, part_local_id):
            return _error("part_local_id does not match a local part record.")
        if not _version_belongs_to_part(conn, part_local_id, part_version_id):
            return _error("part_version_id does not match the local part record.")
        cursor = conn.execute(
            """
            INSERT INTO part_review_status
                (part_local_id, part_version_id, curation_status, human_review_status,
                 review_note, reviewer_name_or_initials, reviewed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                part_local_id,
                part_version_id,
                curation_status,
                human_review_status,
                review_note,
                reviewer_name_or_initials,
                reviewed_at_value,
                _now_iso(),
            ),
        )
        conn.commit()
        return _success(_get_record_by_id(conn, "part_review_status", int(cursor.lastrowid)))
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return _error(f"Could not add review status record: {exc}")
    finally:
        conn.close()


def add_part_link(
    *,
    part_local_id: str,
    part_version_id: int | None = None,
    target_type: str,
    target_id: str,
    target_label: str = "",
    link_note: str = "",
    review_status: str,
) -> dict[str, Any]:
    part_local_id = _clean_text(part_local_id)
    target_type = _clean_text(target_type)
    target_id = _clean_text(target_id)
    target_label = _clean_text(target_label)
    link_note = _clean_text(link_note)
    review_status = _clean_text(review_status)

    if not target_id:
        return _error("target_id is required.")
    for value, allowed, label in (
        (target_type, repo.PART_LINK_TARGET_TYPES, "target_type"),
        (review_status, repo.PART_LINK_REVIEW_STATUS_TERMS, "review_status"),
    ):
        term_error = _validate_term(value, allowed, label)
        if term_error:
            return _error(term_error)

    repo.init_parts_registry_tables()
    conn = repo._connect()
    try:
        if not _part_exists(conn, part_local_id):
            return _error("part_local_id does not match a local part record.")
        if not _version_belongs_to_part(conn, part_local_id, part_version_id):
            return _error("part_version_id does not match the local part record.")
        timestamp = _now_iso()
        cursor = conn.execute(
            """
            INSERT INTO part_project_links
                (part_local_id, part_version_id, target_type, target_id, target_label,
                 link_note, review_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                part_local_id,
                part_version_id,
                target_type,
                target_id,
                target_label,
                link_note,
                review_status,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        return _success(_get_record_by_id(conn, "part_project_links", int(cursor.lastrowid)))
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return _error(f"Could not add traceability link record: {exc}")
    finally:
        conn.close()
