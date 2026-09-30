# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sqlite3
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import project_catalog_asset_link_repository as repo
from services.project_asset_linkage_service import build_project_asset_link


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "project_catalog_asset_links.db"
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _link(**overrides):
    base = {
        "project_id": "project-r35",
        "asset_id": "asset-001",
        "asset_display_name": "Local catalog documentation record",
        "asset_type": "promoter",
        "linkage_role": "project_reference",
        "documentation_note": "Documentation-only reference for project traceability.",
        "source_context_snapshot": {
            "catalog": "Local Design Asset Catalog",
            "source_labels": "Fixture source",
            "version_context": "fixture-v1",
        },
        "review_status_snapshot": {
            "curation_statuses": "source review needed",
            "missing_metadata_count": 0,
        },
        "asset_snapshot": {
            "asset_type": "promoter",
            "asset_id": "asset-001",
            "asset_label": "Local catalog documentation record",
            "asset_version": "fixture-v1",
            "source_label": "Fixture source",
            "documentation_status": "source review needed",
            "species": "",
            "clade": "",
            "aliases": [],
            "tissue_contexts": [],
            "motif_labels": [],
            "limitation_note": "Pinned documentation snapshot for reference context only.",
        },
        "linked_at": "2026-06-17T09:00:00Z",
        "human_review_required": True,
    }
    base.update(overrides)
    return build_project_asset_link(**base)


def test_schema_creation_adds_project_catalog_asset_links_table(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)

    repo.init_project_catalog_asset_link_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "project_catalog_asset_links" in tables
    finally:
        conn.close()


def test_add_list_and_remove_link_round_trip(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    added, message, stored = repo.add_project_catalog_asset_link(_link())
    links = repo.list_project_catalog_asset_links("project-r35")
    removed, remove_message = repo.remove_project_catalog_asset_link(
        project_id="project-r35",
        link_id=stored["link_id"],
    )

    assert added is True
    assert "saved" in message
    assert len(links) == 1
    assert links[0]["asset_id"] == "asset-001"
    assert links[0]["asset_label"] == "Local catalog documentation record"
    assert links[0]["source_label"] == "Fixture source"
    assert links[0]["documentation_status"] == "source review needed"
    assert links[0]["source_context_snapshot"]["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert links[0]["asset_snapshot"]["asset_label"] == "Local catalog documentation record"
    assert links[0]["snapshot_schema_version"] == "2.6-r39-catalog-reference-snapshot"
    assert links[0]["snapshot_captured_at"] == "2026-06-17T09:00:00Z"
    assert removed is True
    assert "removed" in remove_message
    assert repo.list_project_catalog_asset_links("project-r35") == []


def test_duplicate_guard_returns_existing_link(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    first = repo.add_project_catalog_asset_link(_link())
    second = repo.add_project_catalog_asset_link(
        _link(documentation_note="Documentation-only reference for project traceability.")
    )

    assert first[0] is True
    assert second[0] is False
    assert second[2]["link_id"] == first[2]["link_id"]
    assert len(repo.list_project_catalog_asset_links("project-r35")) == 1


def test_find_project_catalog_asset_link_returns_matching_identity(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    added, _message, stored = repo.add_project_catalog_asset_link(_link())

    found = repo.find_project_catalog_asset_link(
        "project-r35",
        asset_id="asset-001",
        linkage_role="project_reference",
    )

    assert added is True
    assert found["link_id"] == stored["link_id"]


def test_find_project_catalog_asset_link_returns_empty_when_missing(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    assert repo.find_project_catalog_asset_link(
        "project-r35",
        asset_id="missing-asset",
        linkage_role="project_reference",
    ) == {}


def test_deterministic_ordering_by_label_asset_and_role(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    repo.add_project_catalog_asset_link(_link(asset_id="asset-b", asset_display_name="Beta record"))
    repo.add_project_catalog_asset_link(_link(asset_id="asset-a2", asset_display_name="Alpha record", linkage_role="report_context"))
    repo.add_project_catalog_asset_link(_link(asset_id="asset-a1", asset_display_name="Alpha record", linkage_role="project_reference"))

    links = repo.list_project_catalog_asset_links("project-r35")

    assert [(row["asset_display_name"], row["asset_id"], row["linkage_role"]) for row in links] == [
        ("Alpha record", "asset-a1", "project_reference"),
        ("Alpha record", "asset-a2", "report_context"),
        ("Beta record", "asset-b", "project_reference"),
    ]


def test_missing_optional_metadata_is_preserved_as_empty_strings(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    added, _message, stored = repo.add_project_catalog_asset_link(
        _link(
            source_context_snapshot={},
            review_status_snapshot={},
            asset_snapshot={},
        )
    )

    assert added is True
    assert stored["source_label"] == ""
    assert stored["documentation_status"] == ""
    assert stored["source_context_snapshot"] == {
        "project_documentation_context": "Pathway Workspace linked catalog assets"
    }
    assert stored["review_status_snapshot"] == {}
    assert stored["asset_snapshot"] == {}


def test_project_documentation_context_defaults_when_missing(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    added, _message, stored = repo.add_project_catalog_asset_link(
        _link(source_context_snapshot={"catalog": "Local Design Asset Catalog"})
    )

    assert added is True
    assert stored["source_context_snapshot"]["project_documentation_context"] == "Pathway Workspace linked catalog assets"


def test_schema_migration_adds_snapshot_columns_to_existing_table(tmp_path, monkeypatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE project_catalog_asset_links (
                link_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                asset_type TEXT NOT NULL DEFAULT '',
                asset_id TEXT NOT NULL,
                asset_label TEXT NOT NULL DEFAULT '',
                asset_version TEXT NOT NULL DEFAULT '',
                source_label TEXT NOT NULL DEFAULT '',
                documentation_status TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                linkage_role TEXT NOT NULL DEFAULT 'project_reference',
                source_context_snapshot_json TEXT NOT NULL DEFAULT '{}',
                review_status_snapshot_json TEXT NOT NULL DEFAULT '{}',
                human_review_required INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (project_id, asset_id, linkage_role)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    repo.init_project_catalog_asset_link_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(project_catalog_asset_links)").fetchall()}
    finally:
        conn.close()
    assert {"snapshot_schema_version", "asset_snapshot_json", "snapshot_captured_at"} <= columns
