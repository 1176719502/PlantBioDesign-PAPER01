from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sqlite_sequence(path: Path) -> list[tuple[str, int]]:
    conn = sqlite3.connect(path)
    try:
        return [
            (str(row[0]), int(row[1]))
            for row in conn.execute(
                "SELECT name, seq FROM sqlite_sequence ORDER BY name"
            ).fetchall()
        ]
    finally:
        conn.close()


def _patch_database_paths(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    from core import activity_log, database, seed_database, unified_database
    from services import (
        expression_construct_repository,
        parts_registry_repository,
        pathway_repository,
        project_catalog_asset_link_repository,
    )

    for module in (
        activity_log,
        database,
        seed_database,
        unified_database,
        expression_construct_repository,
        parts_registry_repository,
        pathway_repository,
        project_catalog_asset_link_repository,
    ):
        monkeypatch.setattr(module, "DB_PATH", str(path))


def _build_versioned_test_database(path: Path) -> Path:
    from core import database_lifecycle

    database_lifecycle.ensure_database_ready(
        path, backup_dir=path.parent / "backups"
    )
    return path


def test_default_database_path_is_user_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import config

    monkeypatch.chdir(ROOT)
    monkeypatch.delenv(config.BIODESIGN_DB_PATH_ENV, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert Path(config.resolve_biodesign_db_path()) == (
        tmp_path / "BioDesignStudio" / "data" / "biodesign_unified.db"
    ).resolve()


def test_database_path_override_reaches_runtime_modules(tmp_path: Path) -> None:
    override = tmp_path / "override.db"
    script = """
import json
from core import activity_log, config, database, seed_database, unified_database
from services import design_saver, expression_construct_repository
from services import parts_registry_repository, pathway_repository
from services import project_catalog_asset_link_repository, tool_artifact_service
from components import project_manager
from components.design_modules import db_utils

modules = {
    "config": config.DB_PATH,
    "database": database.DB_PATH,
    "seed_database": seed_database.DB_PATH,
    "unified_database": unified_database.DB_PATH,
    "activity_log": activity_log.DB_PATH,
    "design_saver": design_saver.DB_PATH,
    "expression_construct_repository": expression_construct_repository.DB_PATH,
    "parts_registry_repository": parts_registry_repository.DB_PATH,
    "pathway_repository": pathway_repository.DB_PATH,
    "project_catalog_asset_link_repository": project_catalog_asset_link_repository.DB_PATH,
    "tool_artifact_service": tool_artifact_service.DB_PATH,
    "project_manager": project_manager.DB_PATH,
    "design_module_db_utils": db_utils.DB_PATH,
}
print(json.dumps(modules, sort_keys=True))
"""
    env = os.environ.copy()
    env["BIODESIGN_DB_PATH"] = str(override)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    paths = json.loads(result.stdout)
    assert set(paths.values()) == {str(override.resolve())}


def test_activity_log_uses_shared_database_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import activity_log

    db_path = tmp_path / "activity.db"
    monkeypatch.setattr(activity_log, "DB_PATH", str(db_path))

    assert activity_log.log_activity("test", "Phase 1.5C path check") is True

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT message FROM activity_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("Phase 1.5C path check",)


def test_seed_does_not_advance_sequences_when_rows_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import seed_database

    db_path = _build_versioned_test_database(tmp_path / "seed.db")
    before_hash = _sha256(db_path)
    before_sequence = _sqlite_sequence(db_path)
    monkeypatch.setattr(seed_database, "DB_PATH", str(db_path))

    seed_database.seed_all()

    assert _sha256(db_path) == before_hash
    assert _sqlite_sequence(db_path) == before_sequence


def test_unified_initialization_does_not_rewrite_existing_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import unified_database

    db_path = _build_versioned_test_database(tmp_path / "unified.db")
    before_hash = _sha256(db_path)
    monkeypatch.setattr(unified_database, "DB_PATH", str(db_path))

    unified_database.init_unified_database()

    assert _sha256(db_path) == before_hash


def test_formal_startup_is_idempotent_on_isolated_database(tmp_path: Path) -> None:
    db_path = _build_versioned_test_database(tmp_path / "formal_startup.db")
    env = os.environ.copy()
    env["BIODESIGN_DB_PATH"] = str(db_path)
    env["BIODESIGN_BACKUP_DIR"] = str(tmp_path / "backups")
    env["BIODESIGN_PLANT_PROJECT_DRAFT_DIR"] = str(tmp_path / "drafts")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    script = "import app"

    before_hash = _sha256(db_path)
    first = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    after_first = _sha256(db_path)
    second = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    after_second = _sha256(db_path)

    assert first.returncode == 0
    assert second.returncode == 0
    assert after_first == before_hash
    assert after_second == after_first
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10000
    finally:
        conn.close()


def test_isolated_database_integrity_and_user_version_remain_observable(
    tmp_path: Path,
) -> None:
    db_path = _build_versioned_test_database(tmp_path / "integrity.db")
    conn = sqlite3.connect(db_path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        table_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert integrity == "ok"
    assert user_version == 10000
    assert table_count > 0
