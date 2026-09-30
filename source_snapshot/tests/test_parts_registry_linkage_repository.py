# -*- coding: utf-8 -*-
"""V2.3-R4 read-only parts registry linkage schema tests."""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import parts_registry_repository as repo


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "parts_registry_linkage.db"
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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


def _insert_part_version(conn: sqlite3.Connection, local_id: str = "part-local-001") -> int:
    cursor = conn.execute(
        """
        INSERT INTO part_versions
            (part_local_id, version_label, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            local_id,
            "metadata-only-v1",
            "2026-06-12T09:10:00",
            "2026-06-12T09:10:00",
        ),
    )
    return int(cursor.lastrowid)


def _insert_link(
    conn: sqlite3.Connection,
    *,
    part_local_id: str = "part-local-001",
    part_version_id: int | None = None,
    target_type: str = "pathway_project",
    target_id: str = "pathway-project-001",
    target_label: str = "Pathway documentation project",
    review_status: str = "traceability review needed",
    created_at: str = "2026-06-12T09:20:00",
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO part_project_links
            (
                part_local_id, part_version_id, target_type, target_id,
                target_label, link_note, review_status, created_at, updated_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            part_local_id,
            part_version_id,
            target_type,
            target_id,
            target_label,
            "Traceability note for local documentation review.",
            review_status,
            created_at,
            created_at,
        ),
    )
    return int(cursor.lastrowid)


def test_part_linkage_schema_migration_creates_table(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)

    repo.init_parts_registry_tables()

    conn = _connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "part_project_links" in tables


def test_empty_linkage_reads_return_empty(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    assert repo.list_links_for_part("missing-part") == []
    assert repo.list_links_for_target("pathway_project", "missing-target") == []
    assert repo.get_link_by_id(999) == {}


def test_link_to_part_without_version(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)
    repo.init_parts_registry_tables()

    conn = _connect(db_path)
    try:
        _insert_part(conn)
        link_id = _insert_link(conn, part_version_id=None)
        conn.commit()
    finally:
        conn.close()

    link = repo.get_link_by_id(link_id)

    assert link["part_local_id"] == "part-local-001"
    assert link["part_version_id"] is None
    assert link["target_type"] == "pathway_project"


def test_link_to_specific_part_version(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)
    repo.init_parts_registry_tables()

    conn = _connect(db_path)
    try:
        _insert_part(conn)
        version_id = _insert_part_version(conn)
        link_id = _insert_link(
            conn,
            part_version_id=version_id,
            target_type="saved_expression_design",
            target_id="saved-design-001",
            target_label="Saved expression design record",
            review_status="traceability reviewed",
        )
        conn.commit()
    finally:
        conn.close()

    link = repo.get_link_by_id(link_id)

    assert link["part_version_id"] == version_id
    assert link["target_type"] == "saved_expression_design"
    assert link["review_status"] == "traceability reviewed"


def test_invalid_target_type_rejected(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)
    repo.init_parts_registry_tables()

    conn = _connect(db_path)
    try:
        _insert_part(conn)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_link(conn, target_type="host_compatibility_check")
            conn.commit()
    finally:
        conn.close()


def test_invalid_review_status_rejected(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)
    repo.init_parts_registry_tables()

    conn = _connect(db_path)
    try:
        _insert_part(conn)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_link(conn, review_status="system selected")
            conn.commit()
    finally:
        conn.close()


def test_list_links_for_part_orders_recent_first(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)
    repo.init_parts_registry_tables()

    conn = _connect(db_path)
    try:
        _insert_part(conn)
        _insert_link(
            conn,
            target_id="pathway-project-older",
            created_at="2026-06-12T09:20:00",
        )
        _insert_link(
            conn,
            target_id="pathway-project-newer",
            created_at="2026-06-12T09:30:00",
        )
        conn.commit()
    finally:
        conn.close()

    links = repo.list_links_for_part("part-local-001")

    assert [link["target_id"] for link in links] == [
        "pathway-project-newer",
        "pathway-project-older",
    ]


def test_list_links_for_target(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)
    repo.init_parts_registry_tables()

    conn = _connect(db_path)
    try:
        _insert_part(conn, "part-local-001")
        _insert_part(conn, "part-local-002")
        _insert_link(conn, part_local_id="part-local-001", target_id="pathway-step-001", target_type="pathway_step")
        _insert_link(conn, part_local_id="part-local-002", target_id="pathway-step-001", target_type="pathway_step")
        _insert_link(conn, part_local_id="part-local-002", target_id="pathway-step-002", target_type="pathway_step")
        conn.commit()
    finally:
        conn.close()

    links = repo.list_links_for_target("pathway_step", "pathway-step-001")

    assert {link["part_local_id"] for link in links} == {
        "part-local-001",
        "part-local-002",
    }
    assert {link["target_id"] for link in links} == {"pathway-step-001"}


def test_linkage_terms_stay_traceability_only():
    combined = "\n".join(
        [
            *repo.PART_LINK_TARGET_TYPES,
            *repo.PART_LINK_REVIEW_STATUS_TERMS,
            repo.PART_PROJECT_LINKS_TABLE_SQL,
        ]
    ).lower()
    forbidden = [
        "recommend" + "ed",
        "recommend" + "ation",
        "read" + "iness",
        "experiment" + "-ready",
        "production" + "-ready",
        "validated " + "construct",
        "optimized " + "pathway",
        "yield " + "prediction",
        "host " + "compatibility",
        "suit" + "ability",
        "scor" + "ing",
        "rank" + "ing",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
