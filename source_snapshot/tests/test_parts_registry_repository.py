# -*- coding: utf-8 -*-
"""V2.3-R1 read-only biological parts registry schema tests."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import parts_registry_repository as repo
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


def _parts_registry_db_path(filename: str) -> str:
    return str(repo_local_sqlite_db_path(".pytest_tmp_r81_parts_registry_dbs", filename))


def _use_temp_db(monkeypatch):
    db_path = _parts_registry_db_path("parts_registry.db")
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _insert_part(conn: sqlite3.Connection, local_id: str = "part-local-001") -> None:
    conn.execute(
        """
        INSERT INTO parts
            (local_id, part_type, display_name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            local_id,
            "Promoter",
            "Local promoter documentation record",
            "Local catalog metadata record for provenance review.",
            "2026-06-12T09:00:00",
            "2026-06-12T09:00:00",
        ),
    )


def test_parts_registry_schema_migration_creates_required_tables(monkeypatch):
    db_path = _use_temp_db(monkeypatch)

    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "parts",
        "part_versions",
        "part_sources",
        "part_annotations",
        "part_review_status",
    }.issubset(tables)


def test_empty_registry_read_paths_return_empty_records(monkeypatch):
    _use_temp_db(monkeypatch)

    assert repo.list_parts() == []
    assert repo.get_part_by_local_id("missing") == {}
    assert repo.list_versions_for_part("missing") == []
    assert repo.list_source_records("missing") == []
    assert repo.list_annotations("missing") == []
    assert repo.list_review_status_records("missing") == []


def test_part_type_vocabulary_accepts_rbs_five_prime_utr(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO parts
                (local_id, part_type, display_name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "part-rbs-utr-001",
                "RBS / 5' UTR",
                "RBS or 5 prime UTR documentation record",
                "Local catalog metadata record for provenance review.",
                "2026-06-12T09:00:00",
                "2026-06-12T09:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    part = repo.get_part_by_local_id("part-rbs-utr-001")

    assert part["part_type"] == "RBS / 5' UTR"


def test_part_version_can_document_no_sequence_without_hash(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_part(conn)
        conn.execute(
            """
            INSERT INTO part_versions
                (part_local_id, version_label, sequence, sequence_hash,
                 sequence_hash_algorithm, version_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "part-local-001",
                "metadata-only-v1",
                None,
                None,
                None,
                "Version record preserves metadata without sequence.",
                "2026-06-12T09:10:00",
                "2026-06-12T09:10:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    versions = repo.list_versions_for_part("part-local-001")

    assert len(versions) == 1
    assert versions[0]["sequence"] is None
    assert versions[0]["sequence_hash"] is None
    assert versions[0]["sequence_hash_algorithm"] is None


def test_part_version_with_sequence_requires_documentation_hash(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()
    sequence = "ATGCGTAA"
    sequence_hash = hashlib.sha256(sequence.encode("utf-8")).hexdigest()

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_part(conn)
        conn.execute(
            """
            INSERT INTO part_versions
                (part_local_id, version_label, sequence, sequence_hash,
                 sequence_hash_algorithm, version_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "part-local-001",
                "sequence-documented-v1",
                sequence,
                sequence_hash,
                "sha256",
                "Sequence and hash are stored as documentation metadata only.",
                "2026-06-12T09:10:00",
                "2026-06-12T09:10:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    version = repo.list_versions_for_part("part-local-001")[0]

    assert version["sequence"] == sequence
    assert version["sequence_hash"] == sequence_hash
    assert version["sequence_hash_algorithm"] == "sha256"


def test_sequence_hash_without_sequence_is_rejected(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_part(conn)
        try:
            conn.execute(
                """
                INSERT INTO part_versions
                    (part_local_id, version_label, sequence, sequence_hash,
                     sequence_hash_algorithm, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "part-local-001",
                    "invalid-hash-only",
                    None,
                    "abc123",
                    "sha256",
                    "2026-06-12T09:10:00",
                    "2026-06-12T09:10:00",
                ),
            )
            conn.commit()
            raised = False
        except sqlite3.IntegrityError:
            raised = True
    finally:
        conn.close()

    assert raised is True


def test_sequence_without_hash_metadata_is_rejected(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_part(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO part_versions
                    (part_local_id, version_label, sequence, sequence_hash,
                     sequence_hash_algorithm, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "part-local-001",
                    "invalid-sequence-without-hash",
                    "ATGCGTAA",
                    None,
                    None,
                    "2026-06-12T09:10:00",
                    "2026-06-12T09:10:00",
                ),
            )
            conn.commit()
    finally:
        conn.close()


def test_part_version_ordering_is_most_recent_first(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_part(conn)
        for label, created_at in (
            ("v1", "2026-06-12T09:10:00"),
            ("v2", "2026-06-12T09:20:00"),
            ("v3", "2026-06-12T09:15:00"),
        ):
            conn.execute(
                """
                INSERT INTO part_versions
                    (part_local_id, version_label, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                ("part-local-001", label, created_at, created_at),
            )
        conn.commit()
    finally:
        conn.close()

    assert [row["version_label"] for row in repo.list_versions_for_part("part-local-001")] == [
        "v2",
        "v3",
        "v1",
    ]


def test_provenance_source_record_read_path(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_part(conn)
        conn.execute(
            """
            INSERT INTO part_sources
                (part_local_id, source_name, source_reference,
                 organism_or_source_context, provenance_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "part-local-001",
                "Local notebook",
                "NB-2026-06-12",
                "source context recorded from local documentation",
                "Provenance context for human review.",
                "2026-06-12T09:30:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    sources = repo.list_source_records("part-local-001")

    assert len(sources) == 1
    assert sources[0]["source_name"] == "Local notebook"
    assert sources[0]["source_reference"] == "NB-2026-06-12"
    assert sources[0]["organism_or_source_context"] == "source context recorded from local documentation"
    assert sources[0]["provenance_note"] == "Provenance context for human review."


def test_review_status_terms_are_documentation_only(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_parts_registry_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_part(conn)
        conn.execute(
            """
            INSERT INTO part_review_status
                (part_local_id, curation_status, human_review_status,
                 review_note, reviewer_name_or_initials, reviewed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "part-local-001",
                "metadata reviewed",
                "human review documented",
                "Curation status records documentation review only.",
                "AB",
                "2026-06-12T10:00:00",
                "2026-06-12T10:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    statuses = repo.list_review_status_records("part-local-001")

    assert statuses[0]["curation_status"] == "metadata reviewed"
    assert statuses[0]["human_review_status"] == "human review documented"
    assert "ready" not in statuses[0]["curation_status"].lower()
    assert "recommended" not in statuses[0]["human_review_status"].lower()
    assert "validated" not in statuses[0]["review_note"].lower()
