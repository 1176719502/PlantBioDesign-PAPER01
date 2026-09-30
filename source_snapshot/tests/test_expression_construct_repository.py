# -*- coding: utf-8 -*-
"""V2.6-R16 read-only multi-gene construct product data model repository tests."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import expression_construct_repository as repo
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


def _expression_construct_db_path(filename: str) -> Path:
    return repo_local_sqlite_db_path(".pytest_tmp_r81_expression_construct_dbs", filename)


def _use_temp_db(monkeypatch):
    db_path = _expression_construct_db_path("expression_constructs.db")
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _seed_construct_records(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO expression_construct_profiles
            (construct_id, construct_label, construct_type, plasmid_backbone,
             host_context_note, source_reference, provenance_note, review_status,
             documentation_scope_note, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "construct-001",
            "Carotenoid documentation construct",
            "multi-cassette plasmid record",
            "pBIO-Doc-01",
            "Host context tracked as documentation only.",
            "Notebook-EC-12",
            "Source notes collected for traceability review.",
            "documentation review pending",
            "Documentation-only construct record.",
            "2026-06-16T09:00:00",
            "2026-06-16T09:00:00",
        ),
    )
    conn.execute(
        """
        INSERT INTO expression_construct_profiles
            (construct_id, construct_label, construct_type, plasmid_backbone,
             host_context_note, source_reference, provenance_note, review_status,
             documentation_scope_note, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "construct-002",
            "Empty documentation construct",
            "reference construct record",
            "",
            "",
            "",
            "",
            "",
            "",
            "2026-06-16T09:05:00",
            "2026-06-16T09:05:00",
        ),
    )
    for cassette_id, label, order_no in (
        ("cassette-002", "Cassette B", 2),
        ("cassette-001", "Cassette A", 1),
    ):
        conn.execute(
            """
            INSERT INTO expression_construct_cassettes
                (cassette_id, construct_id, cassette_label, cassette_role, cassette_order,
                 promoter_label, gene_label, terminator_label, source_reference,
                 provenance_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cassette_id,
                "construct-001",
                label,
                "expression cassette",
                order_no,
                f"Promoter {order_no}",
                f"Gene {order_no}",
                f"Terminator {order_no}",
                f"Notebook-{order_no}",
                f"Traceability note {order_no}",
                f"2026-06-16T09:1{order_no}:00",
                f"2026-06-16T09:1{order_no}:00",
            ),
        )
    for part_order, part_role, part_label in (
        (2, "cds", "crtI CDS"),
        (1, "promoter", "P-Doc-A"),
        (3, "terminator", "T-Doc-A"),
    ):
        conn.execute(
            """
            INSERT INTO expression_construct_cassette_parts
                (cassette_id, part_order, part_role, part_label, part_reference,
                 source_reference, provenance_note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cassette-001",
                part_order,
                part_role,
                part_label,
                f"ref-{part_order}",
                f"source-{part_order}",
                f"note-{part_order}",
                f"2026-06-16T09:2{part_order}:00",
                f"2026-06-16T09:2{part_order}:00",
            ),
        )
    for gene_label in ("crtI", "crtB"):
        conn.execute(
            """
            INSERT INTO expression_construct_gene_links
                (construct_id, gene_label, gene_reference, source_reference, provenance_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "construct-001",
                gene_label,
                f"{gene_label}-ref",
                "Pathway notebook",
                "Linked from project notes.",
                "2026-06-16T09:30:00",
            ),
        )
    for step_id, step_label in (("step-2", "Cyclization"), ("step-1", "Precursor supply")):
        conn.execute(
            """
            INSERT INTO expression_construct_pathway_step_links
                (construct_id, pathway_step_id, pathway_step_label, source_reference,
                 provenance_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "construct-001",
                step_id,
                step_label,
                "Project map",
                "Linked from pathway review notes.",
                "2026-06-16T09:40:00",
            ),
        )


def test_schema_startup_creates_construct_tables(monkeypatch):
    db_path = _use_temp_db(monkeypatch)

    repo.init_expression_construct_tables()

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
        "expression_construct_profiles",
        "expression_construct_cassettes",
        "expression_construct_cassette_parts",
        "expression_construct_gene_links",
        "expression_construct_pathway_step_links",
        "expression_construct_project_links",
    }.issubset(tables)


def test_schema_startup_adds_promoter_catalog_link_columns_to_existing_part_table(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE expression_construct_cassette_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cassette_id TEXT NOT NULL,
                part_order INTEGER NOT NULL DEFAULT 0,
                part_role TEXT NOT NULL,
                part_label TEXT NOT NULL DEFAULT '',
                part_reference TEXT NOT NULL DEFAULT '',
                source_reference TEXT NOT NULL DEFAULT '',
                provenance_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    repo.init_expression_construct_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(expression_construct_cassette_parts)"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "source_catalog",
        "source_record_id",
        "source_record_label",
        "evidence_context_note",
    }.issubset(columns)


def test_database_startup_initializes_construct_tables(monkeypatch):
    from core import database as db
    from core import seed_database as sd
    from core import unified_database as ud
    from services import parts_registry_repository as parts_repo

    db_path = _expression_construct_db_path("expression_construct_startup.db")
    monkeypatch.setattr(ud, "DB_PATH", str(db_path))
    monkeypatch.setattr(sd, "DB_PATH", str(db_path))
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    monkeypatch.setattr(parts_repo, "DB_PATH", str(db_path))
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))

    ud.initialize_database_on_startup()

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

    assert "expression_construct_profiles" in tables
    assert "expression_construct_cassettes" in tables
    assert "expression_construct_cassette_parts" in tables
    assert "expression_construct_gene_links" in tables
    assert "expression_construct_pathway_step_links" in tables
    assert "expression_construct_project_links" in tables


def test_empty_state_returns_safe_empty_records(monkeypatch):
    _use_temp_db(monkeypatch)

    assert repo.list_construct_profiles() == []
    assert repo.get_construct_profile("missing") == {}
    assert repo.get_construct_profile("") == {}
    assert repo.list_construct_cassettes("missing") == []
    assert repo.list_construct_cassette_parts("missing") == []
    assert repo.list_construct_gene_links("missing") == []
    assert repo.list_construct_pathway_step_links("missing") == []
    assert repo.list_construct_project_links(project_id="missing") == []
    assert repo.list_construct_profiles_for_project("missing") == []


def test_construct_profile_listing_and_lookup(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_expression_construct_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _seed_construct_records(conn)
        conn.commit()
    finally:
        conn.close()

    profiles = repo.list_construct_profiles()
    profile = repo.get_construct_profile("construct-001")

    assert [row["construct_id"] for row in profiles] == ["construct-001", "construct-002"]
    assert profile["construct_label"] == "Carotenoid documentation construct"
    assert "ready" not in profile["review_status"].lower()


def test_multiple_cassettes_are_listed_in_deterministic_order(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_expression_construct_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _seed_construct_records(conn)
        conn.commit()
    finally:
        conn.close()

    cassettes = repo.list_construct_cassettes("construct-001")

    assert [row["cassette_id"] for row in cassettes] == ["cassette-001", "cassette-002"]


def test_cassette_part_ordering_is_preserved(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_expression_construct_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _seed_construct_records(conn)
        conn.commit()
    finally:
        conn.close()

    parts = repo.list_construct_cassette_parts("cassette-001")

    assert [row["part_role"] for row in parts] == ["promoter", "cds", "terminator"]


def test_multiple_gene_links_and_pathway_step_links_read_back(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_expression_construct_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        _seed_construct_records(conn)
        conn.commit()
    finally:
        conn.close()

    gene_links = repo.list_construct_gene_links("construct-001")
    pathway_links = repo.list_construct_pathway_step_links("construct-001")

    assert [row["gene_label"] for row in gene_links] == ["crtB", "crtI"]
    assert [row["pathway_step_label"] for row in pathway_links] == ["Cyclization", "Precursor supply"]


def test_missing_ids_return_safe_empty_data(monkeypatch):
    _use_temp_db(monkeypatch)

    assert repo.list_construct_cassettes("") == []
    assert repo.list_construct_cassette_parts("") == []
    assert repo.list_construct_gene_links("") == []
    assert repo.list_construct_pathway_step_links("") == []
    assert repo.list_construct_project_links(project_id="") == []
    assert repo.list_construct_project_links(construct_id="") == []


def test_repository_write_methods_round_trip_and_preserve_order(monkeypatch):
    _use_temp_db(monkeypatch)

    profile = repo.create_construct_profile(
        construct_label="Draft construct",
        construct_type="multi-cassette record",
        host_context_note="Documentation-only host note.",
        source_reference="Notebook-1",
        provenance_note="Captured for review.",
        review_status="draft review",
        documentation_scope_note="Initial review note.",
    )
    construct_id = profile["construct_id"]

    updated_profile = repo.update_construct_profile(
        construct_id,
        construct_label="Updated draft construct",
        review_status="curation review pending",
        documentation_scope_note="Updated review note.",
    )
    cassette = repo.create_construct_cassette(
        construct_id,
        cassette_label="Cassette Z",
        cassette_order=2,
        cassette_role="expression cassette",
        source_reference="Cassette notebook",
        provenance_note="Cassette review note.",
    )
    cassette_2 = repo.create_construct_cassette(
        construct_id,
        cassette_label="Cassette A",
        cassette_order=1,
        cassette_role="support cassette",
    )
    updated_cassette = repo.update_construct_cassette(
        cassette["cassette_id"],
        cassette_label="Cassette Z updated",
        cassette_order=3,
    )
    part = repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=2,
        part_role="cds",
        part_label="crtI CDS",
        source_reference="Part notebook",
        provenance_note="Part review note.",
    )
    updated_part = repo.update_construct_cassette_part(
        part["id"],
        part_order=1,
        part_label="crtI CDS updated",
    )
    gene_link = repo.add_construct_gene_link(
        construct_id,
        gene_label="crtI",
        gene_reference="crtI-ref",
        source_reference="Gene notebook",
        provenance_note="Gene review note.",
    )
    updated_gene_link = repo.update_construct_gene_link(
        gene_link["id"],
        gene_label="crtI-updated",
    )
    pathway_link = repo.add_construct_pathway_step_link(
        construct_id,
        pathway_step_id="step-1",
        pathway_step_label="Precursor supply",
        source_reference="Pathway notebook",
        provenance_note="Pathway review note.",
    )
    updated_pathway_link = repo.update_construct_pathway_step_link(
        pathway_link["id"],
        pathway_step_label="Precursor supply updated",
    )

    cassettes = repo.list_construct_cassettes(construct_id)
    parts = repo.list_construct_cassette_parts(cassette["cassette_id"])
    gene_links = repo.list_construct_gene_links(construct_id)
    pathway_links = repo.list_construct_pathway_step_links(construct_id)

    assert updated_profile["construct_label"] == "Updated draft construct"
    assert [row["cassette_id"] for row in cassettes] == [cassette_2["cassette_id"], cassette["cassette_id"]]
    assert updated_cassette["cassette_label"] == "Cassette Z updated"
    assert parts[0]["part_label"] == "crtI CDS updated"
    assert updated_part["part_order"] == 1
    assert updated_gene_link["gene_label"] == "crtI-updated"
    assert gene_links[0]["gene_label"] == "crtI-updated"
    assert updated_pathway_link["pathway_step_label"] == "Precursor supply updated"
    assert pathway_links[0]["pathway_step_label"] == "Precursor supply updated"


def test_cassette_part_promoter_catalog_reference_round_trips(monkeypatch):
    _use_temp_db(monkeypatch)

    profile = repo.create_construct_profile(construct_label="Promoter-linked construct")
    cassette = repo.create_construct_cassette(profile["construct_id"], cassette_label="Cassette A")
    part = repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="Manual promoter label",
        source_reference="Notebook source note",
        source_catalog="Plant Promoter Catalog",
        source_record_id="plant-promoter-001",
        source_record_label="Maize promoter source record",
        evidence_context_note="monocot | Zea mays (maize) | root | literature-reported | Fixture source",
        provenance_note="Linked for documentation review.",
    )
    updated = repo.update_construct_cassette_part(
        part["id"],
        source_record_label="Updated promoter source record",
        evidence_context_note="updated documentation context",
    )

    parts = repo.list_construct_cassette_parts(cassette["cassette_id"])

    assert part["source_catalog"] == "Plant Promoter Catalog"
    assert part["source_record_id"] == "plant-promoter-001"
    assert updated["source_record_label"] == "Updated promoter source record"
    assert parts[0]["evidence_context_note"] == "updated documentation context"


def test_manual_promoter_part_without_catalog_reference_remains_supported(monkeypatch):
    _use_temp_db(monkeypatch)

    profile = repo.create_construct_profile(construct_label="Manual promoter construct")
    cassette = repo.create_construct_cassette(profile["construct_id"], cassette_label="Cassette A")
    part = repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="Manual promoter label",
    )

    assert part["part_label"] == "Manual promoter label"
    assert part["source_catalog"] == ""
    assert part["source_record_id"] == ""


def test_write_methods_handle_blank_optional_fields_and_missing_ids_safely(monkeypatch):
    _use_temp_db(monkeypatch)

    profile = repo.create_construct_profile(construct_label="")
    cassette = repo.create_construct_cassette(profile["construct_id"], cassette_label="")
    part = repo.add_construct_cassette_part(cassette["cassette_id"], part_role="not-a-valid-role", part_label="")
    gene_link = repo.add_construct_gene_link(profile["construct_id"])
    pathway_link = repo.add_construct_pathway_step_link(profile["construct_id"])

    assert profile["construct_label"] == "Untitled construct draft"
    assert cassette["cassette_label"] == "Untitled cassette draft"
    assert part["part_role"] == "other"
    assert part["part_label"] == ""
    assert gene_link["gene_label"] == ""
    assert pathway_link["pathway_step_label"] == ""
    assert repo.update_construct_profile("missing") == {}
    assert repo.create_construct_cassette("missing", cassette_label="Draft") == {}
    assert repo.update_construct_cassette("missing") == {}
    assert repo.add_construct_cassette_part("missing") == {}
    assert repo.update_construct_cassette_part(999999) == {}
    assert repo.add_construct_gene_link("missing") == {}
    assert repo.update_construct_gene_link(999999) == {}
    assert repo.add_construct_pathway_step_link("missing") == {}
    assert repo.update_construct_pathway_step_link(999999) == {}


def test_construct_copy_stays_documentation_only():
    combined = "\n".join(
        [
            repo.EXPRESSION_CONSTRUCT_PROFILES_TABLE_SQL,
            repo.EXPRESSION_CONSTRUCT_CASSETTES_TABLE_SQL,
            repo.EXPRESSION_CONSTRUCT_CASSETTE_PARTS_TABLE_SQL,
            repo.EXPRESSION_CONSTRUCT_GENE_LINKS_TABLE_SQL,
            repo.EXPRESSION_CONSTRUCT_PATHWAY_STEP_LINKS_TABLE_SQL,
            repo.EXPRESSION_CONSTRUCT_PROJECT_LINKS_TABLE_SQL,
        ]
    ).lower()
    forbidden = [
        "recommend" + "ation",
        "recommend" + "ed",
        "scor" + "ing",
        "rank" + "ing",
        "optim" + "ization",
        "optim" + "ized",
        "valid" + "ated",
        "host " + "compatibility",
        "ready for " + "synthesis",
        "ready for " + "wet lab",
        "transformation " + "protocol",
        "experimentally " + "confirmed",
        "expression " + "prediction",
        "yield " + "improvement",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
