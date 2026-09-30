# -*- coding: utf-8 -*-
"""Database and startup smoke tests for the reproducible local baseline."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_explicit_startup_initializes_unified_db(monkeypatch, tmp_path: Path):
    """Startup entrypoint should create DB + required tables explicitly."""
    from core import unified_database as ud
    from core import database as db
    from core import seed_database as sd
    from services import expression_construct_repository as construct_repo
    from services import parts_registry_repository as parts_repo
    from services import project_catalog_asset_link_repository as project_catalog_link_repo

    db_file = tmp_path / "phase1_startup_smoke.db"
    db_path = str(db_file)

    monkeypatch.setattr(ud, "DB_PATH", db_path)
    monkeypatch.setattr(sd, "DB_PATH", db_path)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(parts_repo, "DB_PATH", db_path)
    monkeypatch.setattr(construct_repo, "DB_PATH", db_path)
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", db_path)

    assert not db_file.exists(), "DB should not exist before explicit startup init"

    ud.initialize_database_on_startup()

    assert db_file.exists(), "DB file should be created by explicit startup init"

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        required_tables = {
            "promoters",
            "genes",
            "terminators",
            "tags",
            "sequences",
            "project_history",
            "biological_parts",
            "parts",
            "part_versions",
            "part_project_links",
            "expression_construct_profiles",
            "expression_construct_cassettes",
            "expression_construct_cassette_parts",
            "expression_construct_gene_links",
            "expression_construct_pathway_step_links",
            "project_catalog_asset_links",
            "database_meta",
        }
        assert required_tables.issubset(tables)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10000
    finally:
        conn.close()


def test_database_layer_has_no_streamlit_dependency() -> None:
    """Database layer should stay framework-agnostic."""
    db_file = Path(ROOT) / "core" / "database.py"
    content = db_file.read_text(encoding="utf-8")

    assert "import streamlit" not in content
    assert "@st.cache_data" not in content


def test_runtime_baseline_dependencies_import() -> None:
    """Key runtime dependencies for Windows startup should import cleanly."""
    import Bio  # noqa: F401
    import fastapi  # noqa: F401
    import openpyxl  # noqa: F401
    import pandas  # noqa: F401
    import primer3  # noqa: F401
    import reportlab  # noqa: F401
    import requests  # noqa: F401
    import rq  # noqa: F401
    import redis  # noqa: F401
    import streamlit  # noqa: F401


def test_startup_entry_files_exist() -> None:
    """Install/startup chain should expose the expected local entry points."""
    required_paths = [
        Path(ROOT) / "requirements.txt",
        Path(ROOT) / "START.bat",
        Path(ROOT) / "app.py",
        Path(ROOT) / ".streamlit" / "config.toml",
    ]
    for path in required_paths:
        assert path.exists(), f"Missing startup path: {path}"


def test_requirements_file_is_utf8_clean_text() -> None:
    """requirements.txt should be UTF-8 clean and safe for pip on Windows."""
    req_path = Path(ROOT) / "requirements.txt"
    raw = req_path.read_bytes()

    assert not raw.startswith(b"\xef\xbb\xbf"), "requirements.txt must not use UTF-8 BOM"

    decoded = raw.decode("utf-8")
    assert "\x00" not in decoded
    assert "streamlit==" in decoded
    assert "primer3-py==" in decoded
