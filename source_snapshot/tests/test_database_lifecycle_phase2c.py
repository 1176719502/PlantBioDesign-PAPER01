from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core import database_lifecycle as lifecycle
from core.config import (
    BIODESIGN_BACKUP_DIR_ENV,
    BIODESIGN_DB_PATH_ENV,
    resolve_biodesign_backup_dir,
    resolve_biodesign_db_path,
)
from core.database import seed_builtin_parts
from core.database_migrations.fingerprints import DatabaseKind, classify_database
from core.seed_database import seed_all
from services.database_backup_service import (
    DatabaseBackupError,
    create_database_backup,
    mark_failed_migration_backup,
    prune_database_backups,
    restore_database_backup,
    sha256_file,
    verify_database_backup,
)


ROOT = Path(__file__).resolve().parents[1]
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_legacy_34(path: Path, *, saved_design: bool = False) -> Path:
    lifecycle._build_unversioned_schema(path)
    connection = sqlite3.connect(path)
    try:
        seed_builtin_parts(connection)
        seed_all(connection)
        if saved_design:
            connection.execute(
                "INSERT INTO project_history "
                "(project_name, version, chassis, design_data, created_at, creator, status) "
                "VALUES ('legacy-design', 1, 'Plant', '{}', '2026-01-01', 'test', 'draft')"
            )
            connection.execute(
                "INSERT INTO sequences "
                "(name, sequence, category, description, date_added) "
                "VALUES ('legacy-design', 'ATGC', 'design', 'paired', '2026-01-01')"
            )
        connection.commit()
    finally:
        connection.close()
    return path


def _user_version(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()


def _build_retention_source(path: Path, marker: str = "source") -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE retention_probe (marker TEXT NOT NULL)")
        connection.execute("INSERT INTO retention_probe VALUES (?)", (marker,))
        connection.commit()
    finally:
        connection.close()
    return path


def _backup_at(
    source: Path,
    backup_dir: Path,
    *,
    kind: str,
    offset: int,
):
    return create_database_backup(
        source,
        backup_dir,
        source_version=1,
        target_version=1,
        kind=kind,
        now=datetime(2026, 7, 31, tzinfo=UTC) + timedelta(seconds=offset),
    )


def test_default_database_and_backup_paths_use_local_app_data(tmp_path: Path) -> None:
    env = {"LOCALAPPDATA": str(tmp_path)}
    assert Path(resolve_biodesign_db_path(env)) == (
        tmp_path / "BioDesignStudio" / "data" / "biodesign_unified.db"
    ).resolve()
    assert resolve_biodesign_backup_dir(env) == (
        tmp_path / "BioDesignStudio" / "backups" / "database"
    ).resolve()


def test_database_and_backup_path_overrides(tmp_path: Path) -> None:
    env = {
        BIODESIGN_DB_PATH_ENV: str(tmp_path / "custom.db"),
        BIODESIGN_BACKUP_DIR_ENV: str(tmp_path / "custom-backups"),
    }
    assert Path(resolve_biodesign_db_path(env)) == (tmp_path / "custom.db").resolve()
    assert resolve_biodesign_backup_dir(env) == (tmp_path / "custom-backups").resolve()


def test_first_run_is_atomic_versioned_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "user" / "biodesign_unified.db"
    first = lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")
    first_hash = _sha256(path)
    second = lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")

    assert first.action == "created"
    assert second.action == "validated"
    assert _user_version(path) == 10000
    assert _sha256(path) == first_hash
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute(
            "SELECT version, status FROM schema_migrations"
        ).fetchall() == [(10000, "applied")]
        assert connection.execute(
            "SELECT seed_version, result FROM seed_releases"
        ).fetchall() == [(10000, "applied")]
    finally:
        connection.close()


def test_first_run_failure_leaves_no_final_database(tmp_path: Path) -> None:
    path = tmp_path / "user" / "biodesign_unified.db"

    def fail(stage: str) -> None:
        if stage == "after_seed":
            raise RuntimeError("injected seed boundary failure")

    with pytest.raises(lifecycle.DatabaseLifecycleError, match="isolated"):
        lifecycle.ensure_database_ready(
            path, backup_dir=tmp_path / "backups", fault_hook=fail
        )
    assert not path.exists()
    assert list(path.parent.glob(".failed-*.db"))


def test_three_fresh_databases_are_physically_deterministic(tmp_path: Path) -> None:
    hashes = []
    for index in range(3):
        path = tmp_path / str(index) / "biodesign_unified.db"
        lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")
        hashes.append(_sha256(path))
    assert len(set(hashes)) == 1


def test_legacy_34_profile_migrates_and_preserves_saved_designs(tmp_path: Path) -> None:
    path = _build_legacy_34(tmp_path / "legacy34.db", saved_design=True)
    assert classify_database(path).kind == DatabaseKind.LEGACY_34

    result = lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")

    assert result.action == "migrated"
    assert result.profile.kind == DatabaseKind.VERSIONED
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM project_history").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM sequences").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tool_artifacts'"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_legacy_35_profile_preserves_tool_artifacts_and_saved_designs(tmp_path: Path) -> None:
    from services import tool_artifact_service

    path = tmp_path / "legacy35.db"
    _build_legacy_34(path, saved_design=True)
    original_db_path = tool_artifact_service.DB_PATH
    try:
        tool_artifact_service.DB_PATH = str(path)
        connection = tool_artifact_service._connect()
        connection.close()
    finally:
        tool_artifact_service.DB_PATH = original_db_path

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO tool_artifacts "
            "(artifact_type,title,source_module,summary,payload_json,boundary_label,created_at) "
            "VALUES ('note','legacy','test','summary','{}','review record','2026-01-01')"
        )
        connection.commit()
    finally:
        connection.close()
    assert classify_database(path).kind == DatabaseKind.LEGACY_35_TOOL_ARTIFACTS

    result = lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")

    assert result.action == "migrated"
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM project_history").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM sequences").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM tool_artifacts").fetchone()[0] == 1
    finally:
        connection.close()


def test_migration_creates_verified_backup_before_write(tmp_path: Path) -> None:
    path = _build_legacy_34(tmp_path / "legacy.db")
    result = lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")

    assert result.backup is not None
    assert result.backup.sha256[:12] in result.backup.path.name
    assert result.backup.sha256 == sha256_file(result.backup.path)
    assert _user_version(result.backup.path) == 0


def test_migration_failure_rolls_back_and_preserves_backup(tmp_path: Path) -> None:
    path = _build_legacy_34(tmp_path / "legacy.db", saved_design=True)

    def fail(stage: str) -> None:
        if stage == "before_commit":
            raise RuntimeError("injected migration failure")

    with pytest.raises(lifecycle.DatabaseLifecycleError, match="original database"):
        lifecycle.ensure_database_ready(
            path, backup_dir=tmp_path / "backups", fault_hook=fail
        )
    assert _user_version(path) == 0
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM project_history").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()[0] == 0
    finally:
        connection.close()
    backups = list((tmp_path / "backups").glob("*.migration.db"))
    assert len(backups) == 1
    assert backups[0].with_suffix(backups[0].suffix + ".preserve").exists()


def test_seed_collision_fails_closed_without_overwrite(tmp_path: Path) -> None:
    path = _build_legacy_34(tmp_path / "legacy.db")
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE promoters SET description='user edit' WHERE id='PRO_CAMV35S'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(lifecycle.DatabaseLifecycleError, match="seed content conflicts"):
        lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")
    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT description FROM promoters WHERE id='PRO_CAMV35S'"
        ).fetchone()[0] == "user edit"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        connection.close()


def test_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "versioned.db"
    lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE schema_migrations SET checksum='changed'")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(lifecycle.DatabaseLifecycleError, match="checksum"):
        lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")


def test_future_unknown_and_corrupt_databases_are_rejected_without_writes(tmp_path: Path) -> None:
    future = tmp_path / "future.db"
    connection = sqlite3.connect(future)
    connection.execute("CREATE TABLE future_table (id INTEGER)")
    connection.execute("PRAGMA user_version=10001")
    connection.commit()
    connection.close()
    future_hash = _sha256(future)
    with pytest.raises(lifecycle.DatabaseLifecycleError, match="newer than supported"):
        lifecycle.ensure_database_ready(future, backup_dir=tmp_path / "backups")
    assert _sha256(future) == future_hash

    unknown = tmp_path / "unknown.db"
    connection = sqlite3.connect(unknown)
    connection.execute("CREATE TABLE unknown_table (id INTEGER)")
    connection.commit()
    connection.close()
    unknown_hash = _sha256(unknown)
    with pytest.raises(lifecycle.DatabaseLifecycleError, match="unknown schema fingerprint"):
        lifecycle.ensure_database_ready(unknown, backup_dir=tmp_path / "backups")
    assert _sha256(unknown) == unknown_hash

    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")
    corrupt_hash = _sha256(corrupt)
    with pytest.raises(lifecycle.DatabaseLifecycleError, match="integrity"):
        lifecycle.ensure_database_ready(corrupt, backup_dir=tmp_path / "backups")
    assert _sha256(corrupt) == corrupt_hash


def test_locked_database_fails_without_forced_unlock(tmp_path: Path) -> None:
    path = _build_legacy_34(tmp_path / "locked.db")
    lock_connection = sqlite3.connect(path)
    lock_connection.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(lifecycle.DatabaseLifecycleError, match="locked"):
            lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")
    finally:
        lock_connection.rollback()
        lock_connection.close()
    assert _user_version(path) == 0


def test_unwritable_parent_and_low_disk_fail_before_database_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("blocked", encoding="utf-8")
    with pytest.raises(lifecycle.DatabaseLifecycleError, match="not writable"):
        lifecycle.ensure_database_ready(parent_file / "user.db")

    class Usage:
        free = 0

    monkeypatch.setattr(lifecycle.shutil, "disk_usage", lambda _path: Usage())
    with pytest.raises(lifecycle.DatabaseLifecycleError, match="Insufficient free space"):
        lifecycle.ensure_database_ready(tmp_path / "low-disk" / "user.db")


def test_repository_database_is_never_opened_for_runtime_writes() -> None:
    with pytest.raises(lifecycle.DatabaseLifecycleError, match="repository database"):
        lifecycle.ensure_database_ready(lifecycle.REPOSITORY_DATABASE)


def test_restore_requires_confirmation_and_quarantines_current_database(tmp_path: Path) -> None:
    target = tmp_path / "target.db"
    backup_source = tmp_path / "source.db"
    lifecycle.ensure_database_ready(target, backup_dir=tmp_path / "backups")
    lifecycle.ensure_database_ready(backup_source, backup_dir=tmp_path / "backups")
    connection = sqlite3.connect(backup_source)
    connection.execute("INSERT INTO sequences(name,sequence,category) VALUES('restore','ATGC','design')")
    connection.commit()
    connection.close()
    backup = create_database_backup(
        backup_source,
        tmp_path / "backups",
        source_version=10000,
        target_version=10000,
        kind="automatic",
    )

    with pytest.raises(DatabaseBackupError, match="explicit confirmation"):
        restore_database_backup(backup.path, target, confirmed=False)
    quarantine = restore_database_backup(backup.path, target, confirmed=True)
    assert quarantine != target
    assert quarantine.exists()
    connection = sqlite3.connect(target)
    try:
        assert connection.execute("SELECT name FROM sequences").fetchone()[0] == "restore"
    finally:
        connection.close()


@pytest.mark.parametrize(
    "kind",
    ["automatic", "manual", "migration", "reconciliation", "restore"],
)
def test_new_backups_use_only_formal_filename_family(
    tmp_path: Path, kind: str
) -> None:
    source = _build_retention_source(tmp_path / "source.db")

    record = _backup_at(source, tmp_path / "backups", kind=kind, offset=0)

    assert record.path.name.startswith("biodesign_unified.v1_to_v1.")
    assert not record.path.name.startswith("db.v")
    assert record.path.name.endswith(f".{record.sha256[:12]}.{kind}.db")


def test_automatic_retention_recognizes_formal_and_legacy_names_without_broad_deletion(
    tmp_path: Path,
) -> None:
    source = _build_retention_source(tmp_path / "source.db")
    backups = tmp_path / "backups"
    backups.mkdir()
    source_hash = sha256_file(source)
    legacy = backups / (
        "db.v1-v1.20260730T235959Z."
        f"{source_hash[:12]}.automatic.db"
    )
    shutil.copy2(source, legacy)
    manual = _backup_at(source, backups, kind="manual", offset=0)
    reconciliation = _backup_at(source, backups, kind="reconciliation", offset=1)
    restore = _backup_at(source, backups, kind="restore", offset=2)
    manual_marker = manual.path.with_suffix(manual.path.suffix + ".preserve")
    manual_marker.write_text("keep\n", encoding="utf-8")
    audit = backups / "reconciliation-audit.json"
    audit.write_text("{}\n", encoding="utf-8")
    unrelated = backups / "db.notes.db"
    unrelated.write_text("not a backup\n", encoding="utf-8")
    malformed = backups / "db.v1-v1.20260731T000000Z.not-a-hash.automatic.db"
    malformed.write_text("not a backup\n", encoding="utf-8")
    mismatched_hash = backups / (
        "db.v1-v1.20260731T000000Z.000000000000.automatic.db"
    )
    mismatched_hash.write_text("not a backup\n", encoding="utf-8")

    created = [
        _backup_at(source, backups, kind="automatic", offset=10 + index)
        for index in range(5)
    ]

    retained = sorted(
        path
        for path in backups.glob("*.automatic.db")
        if path not in {malformed, mismatched_hash}
    )
    assert len(retained) == 5
    assert legacy not in retained
    assert {path.name for path in retained} == {record.path.name for record in created}
    assert all(
        record.path.name.startswith("biodesign_unified.v1_to_v1.")
        for record in created
    )
    assert all(verify_database_backup(record.path) == record.sha256 for record in created)
    assert manual.path.exists()
    assert reconciliation.path.exists()
    assert restore.path.exists()
    assert manual_marker.exists()
    assert audit.exists()
    assert unrelated.read_text(encoding="utf-8") == "not a backup\n"
    assert malformed.read_text(encoding="utf-8") == "not a backup\n"
    assert mismatched_hash.read_text(encoding="utf-8") == "not a backup\n"


def test_retention_keeps_protected_and_non_automatic_backup_types(tmp_path: Path) -> None:
    source = _build_retention_source(tmp_path / "source.db")
    backups = tmp_path / "backups"
    protected = _backup_at(source, backups, kind="migration", offset=0)
    marker = mark_failed_migration_backup(protected)
    migration_records = [
        _backup_at(source, backups, kind="migration", offset=index)
        for index in range(1, 5)
    ]
    manual_records = [
        _backup_at(source, backups, kind="manual", offset=10 + index)
        for index in range(2)
    ]
    reconciliation_records = [
        _backup_at(source, backups, kind="reconciliation", offset=20 + index)
        for index in range(4)
    ]

    assert protected.path.exists()
    assert marker.exists()
    assert not migration_records[0].path.exists()
    assert all(record.path.exists() for record in migration_records[1:])
    assert all(record.path.exists() for record in manual_records)
    assert all(record.path.exists() for record in reconciliation_records)


def test_retention_is_directory_scoped_for_distinct_databases(tmp_path: Path) -> None:
    source_a = _build_retention_source(tmp_path / "source-a.db", "a")
    source_b = _build_retention_source(tmp_path / "source-b.db", "b")
    backups_a = tmp_path / "backups-a"
    backups_b = tmp_path / "backups-b"
    records_b = [
        _backup_at(source_b, backups_b, kind="automatic", offset=index)
        for index in range(2)
    ]

    records_a = [
        _backup_at(source_a, backups_a, kind="automatic", offset=index)
        for index in range(6)
    ]

    assert not records_a[0].path.exists()
    assert all(record.path.exists() for record in records_a[1:])
    assert all(record.path.exists() for record in records_b)
    assert len(list(backups_b.glob("*.automatic.db"))) == 2


def test_pruning_order_is_deterministic_for_equal_timestamps_and_mtimes(
    tmp_path: Path,
) -> None:
    source = _build_retention_source(tmp_path / "source.db")
    source_hash = sha256_file(source)
    backups = tmp_path / "backups"
    backups.mkdir()
    names = []
    for index in range(7):
        name = (
            "db.v1-v1.20260731T000000Z."
            f"{source_hash[:12]}.automatic.{index:08x}.db"
        )
        path = backups / name
        shutil.copyfile(source, path)
        os.utime(path, ns=(1_700_000_000_000_000_000,) * 2)
        names.append(name)

    prune_database_backups(backups)
    first_result = sorted(
        path.name for path in backups.glob("*.db") if ".automatic." in path.name
    )
    prune_database_backups(backups)
    second_result = sorted(
        path.name for path in backups.glob("*.db") if ".automatic." in path.name
    )

    assert first_result == sorted(names[-5:])
    assert second_result == first_result


def test_pruning_failure_reports_database_backup_error_and_preserves_valid_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _build_retention_source(tmp_path / "source.db")
    source_hash = sha256_file(source)
    backups = tmp_path / "backups"
    records = [
        _backup_at(source, backups, kind="automatic", offset=index)
        for index in range(5)
    ]
    oldest = records[0].path
    real_unlink = Path.unlink

    def fail_oldest(path: Path, *args, **kwargs):
        if path == oldest:
            raise PermissionError("injected pruning failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_oldest)
    with pytest.raises(DatabaseBackupError, match="Could not prune database backup"):
        _backup_at(source, backups, kind="automatic", offset=5)

    retained = list(backups.glob("*.automatic.db"))
    assert len(retained) == 6
    assert sha256_file(source) == source_hash
    assert all(len(verify_database_backup(path)) == 64 for path in retained)
