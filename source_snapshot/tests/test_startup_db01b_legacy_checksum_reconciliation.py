from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from core import database_lifecycle as lifecycle
from core.database_checksums import canonical_source_checksum
from core.database_migrations.fingerprints import schema_fingerprint
from core.database_migrations.legacy_compatibility import (
    APPROVED_VERSIONED_SIGNATURES,
    CANONICAL_MIGRATION_CHECKSUM,
    CANONICAL_SEED_MANIFEST_CHECKSUM,
    VERSIONED_36_SCHEMA_SHA256,
    VERSIONED_37_TOOL_ARTIFACTS_SCHEMA_SHA256,
    WINDOWS_CRLF_MIGRATION_CHECKSUM,
    WINDOWS_CRLF_SEED_MANIFEST_CHECKSUM,
    match_versioned_signature,
)
from core.database_migrations.registry import MIGRATIONS
from core.database_seed import manifest_checksum
from services import legacy_database_reconciliation_service as reconciliation
from services import tool_artifact_service
from services.database_backup_service import DatabaseBackupError, verify_database_backup


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fresh_database(path: Path, backup_dir: Path) -> Path:
    lifecycle.ensure_database_ready(path, backup_dir=backup_dir)
    return path


def _set_ledger_pair(path: Path, migration_checksum: str, seed_checksum: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = 10000",
            (migration_checksum,),
        )
        connection.execute(
            "UPDATE seed_releases SET manifest_checksum = ? WHERE seed_version = 10000",
            (seed_checksum,),
        )
        connection.commit()
    finally:
        connection.close()


def _add_tool_artifacts_profile(path: Path) -> None:
    original = tool_artifact_service.DB_PATH
    try:
        tool_artifact_service.DB_PATH = str(path)
        connection = tool_artifact_service._connect()
        connection.commit()
        connection.close()
    finally:
        tool_artifact_service.DB_PATH = original


def _governance_snapshot(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(path)
    try:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {
            "sha256": _sha256(path),
            "user_version": connection.execute("PRAGMA user_version").fetchone()[0],
            "schema_objects": connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            ).fetchall(),
            "row_counts": {
                table: connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
                for table in tables
            },
            "sqlite_sequence": connection.execute(
                "SELECT name, seq FROM sqlite_sequence ORDER BY name"
            ).fetchall(),
            "migration_rows": connection.execute(
                "SELECT version, name, checksum, status FROM schema_migrations ORDER BY version"
            ).fetchall(),
            "seed_rows": connection.execute(
                "SELECT seed_version, manifest_checksum, logical_seed_sha256, result "
                "FROM seed_releases ORDER BY seed_version"
            ).fetchall(),
        }
    finally:
        connection.close()


def test_source_checksum_is_stable_for_lf_crlf_and_cr() -> None:
    lf = b"alpha = 1\nbeta = 'plant'\n"
    expected = canonical_source_checksum(lf)

    assert canonical_source_checksum(lf.replace(b"\n", b"\r\n")) == expected
    assert canonical_source_checksum(lf.replace(b"\n", b"\r")) == expected
    assert canonical_source_checksum(lf) == expected


def test_runtime_checksums_equal_audited_canonical_values() -> None:
    assert MIGRATIONS[0].checksum == CANONICAL_MIGRATION_CHECKSUM
    assert manifest_checksum() == CANONICAL_SEED_MANIFEST_CHECKSUM


def test_allowlist_matches_only_complete_bound_pairs() -> None:
    assert len(APPROVED_VERSIONED_SIGNATURES) == 3
    assert match_versioned_signature(
        migration_checksum=CANONICAL_MIGRATION_CHECKSUM,
        seed_manifest_checksum=CANONICAL_SEED_MANIFEST_CHECKSUM,
        schema_sha256=VERSIONED_36_SCHEMA_SHA256,
        table_count=36,
    ) is not None
    assert match_versioned_signature(
        migration_checksum=WINDOWS_CRLF_MIGRATION_CHECKSUM,
        seed_manifest_checksum=CANONICAL_SEED_MANIFEST_CHECKSUM,
        schema_sha256=VERSIONED_36_SCHEMA_SHA256,
        table_count=36,
    ) is None
    assert match_versioned_signature(
        migration_checksum=CANONICAL_MIGRATION_CHECKSUM,
        seed_manifest_checksum=WINDOWS_CRLF_SEED_MANIFEST_CHECKSUM,
        schema_sha256=VERSIONED_36_SCHEMA_SHA256,
        table_count=36,
    ) is None
    assert match_versioned_signature(
        migration_checksum=WINDOWS_CRLF_MIGRATION_CHECKSUM,
        seed_manifest_checksum=WINDOWS_CRLF_SEED_MANIFEST_CHECKSUM,
        schema_sha256=VERSIONED_37_TOOL_ARTIFACTS_SCHEMA_SHA256,
        table_count=37,
    ) is None


def test_historical_37_table_signature_is_backed_up_audited_and_idempotent(
    tmp_path: Path,
) -> None:
    path = _fresh_database(tmp_path / "historical.db", tmp_path / "bootstrap-backups")
    _add_tool_artifacts_profile(path)
    before = _governance_snapshot(path)
    assert before["sha256"] == _sha256(path)
    connection = sqlite3.connect(path)
    try:
        assert schema_fingerprint(connection) == VERSIONED_37_TOOL_ARTIFACTS_SCHEMA_SHA256
    finally:
        connection.close()

    first = lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")
    after_first = _governance_snapshot(path)
    second = lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")

    assert first.action == "reconciled"
    assert second.action == "validated"
    assert first.reconciliation is not None and first.reconciliation.created
    assert second.reconciliation is not None and not second.reconciliation.created
    assert verify_database_backup(first.backup.path) == first.backup.sha256
    assert before == after_first == _governance_snapshot(path)
    assert len(list((tmp_path / "backups").glob("*.reconciliation.db"))) == 1
    audit_files = list((tmp_path / "backups" / "reconciliation-audit").glob("*.json"))
    assert len(audit_files) == 1
    audit = json.loads(audit_files[0].read_text(encoding="utf-8"))
    assert audit["signature_id"] == "historical-lf-source-37"
    assert audit["migration_order"] == "1 of 1"
    assert "row_counts" not in audit


def test_windows_crlf_pair_is_reconciled_without_ledger_write(tmp_path: Path) -> None:
    path = _fresh_database(tmp_path / "windows.db", tmp_path / "bootstrap-backups")
    _set_ledger_pair(
        path,
        WINDOWS_CRLF_MIGRATION_CHECKSUM,
        WINDOWS_CRLF_SEED_MANIFEST_CHECKSUM,
    )
    before = _governance_snapshot(path)

    result = lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")

    assert result.action == "reconciled"
    assert _governance_snapshot(path) == before
    assert result.reconciliation.signature.signature_id == "windows-crlf-fresh-36"


@pytest.mark.parametrize(
    ("migration_checksum", "seed_checksum"),
    [
        (WINDOWS_CRLF_MIGRATION_CHECKSUM, CANONICAL_SEED_MANIFEST_CHECKSUM),
        (CANONICAL_MIGRATION_CHECKSUM, WINDOWS_CRLF_SEED_MANIFEST_CHECKSUM),
        ("0" * 64, CANONICAL_SEED_MANIFEST_CHECKSUM),
        (CANONICAL_MIGRATION_CHECKSUM, "f" * 64),
    ],
)
def test_crossed_and_unknown_checksum_pairs_fail_closed(
    tmp_path: Path,
    migration_checksum: str,
    seed_checksum: str,
) -> None:
    path = _fresh_database(tmp_path / "rejected.db", tmp_path / "bootstrap-backups")
    _set_ledger_pair(path, migration_checksum, seed_checksum)
    before = _sha256(path)

    with pytest.raises(lifecycle.DatabaseLifecycleError, match="approved schema profile"):
        lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")

    assert _sha256(path) == before
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("mutation", ["name", "extra_migration", "extra_seed"])
def test_wrong_ledger_identity_or_count_fails_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    path = _fresh_database(tmp_path / "identity.db", tmp_path / "bootstrap-backups")
    connection = sqlite3.connect(path)
    try:
        if mutation == "name":
            connection.execute("UPDATE schema_migrations SET name='wrong'")
        elif mutation == "extra_migration":
            connection.execute(
                "INSERT INTO schema_migrations VALUES "
                "(10001,'extra','x','test','a','b','applied','c','d')"
            )
        else:
            connection.execute(
                "INSERT INTO seed_releases VALUES (10001,'x','y','a','applied')"
            )
        connection.commit()
    finally:
        connection.close()
    before = _sha256(path)

    with pytest.raises(lifecycle.DatabaseLifecycleError, match="ledger"):
        lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")

    assert _sha256(path) == before


def test_schema_fingerprint_mismatch_fails_before_backup(tmp_path: Path) -> None:
    path = _fresh_database(tmp_path / "fingerprint.db", tmp_path / "bootstrap-backups")
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE unsupported_similar_profile (id INTEGER)")
    connection.commit()
    connection.close()
    before = _sha256(path)

    with pytest.raises(lifecycle.DatabaseLifecycleError, match="approved schema profile"):
        lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")

    assert _sha256(path) == before
    assert not (tmp_path / "backups").exists()


def test_backup_failure_does_not_write_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _fresh_database(tmp_path / "backup-failure.db", tmp_path / "bootstrap-backups")
    _set_ledger_pair(
        path,
        WINDOWS_CRLF_MIGRATION_CHECKSUM,
        WINDOWS_CRLF_SEED_MANIFEST_CHECKSUM,
    )
    before = _governance_snapshot(path)

    def fail_backup(*_args, **_kwargs):
        raise DatabaseBackupError("injected backup failure")

    monkeypatch.setattr(reconciliation, "create_database_backup", fail_backup)
    with pytest.raises(lifecycle.DatabaseLifecycleError, match="backup failure"):
        lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")

    assert _governance_snapshot(path) == before
    assert not list((tmp_path / "backups").glob("*.db"))
    assert not list((tmp_path / "backups" / "reconciliation-audit").glob("*.json"))


def test_external_audit_transaction_failure_rolls_back_record_only(tmp_path: Path) -> None:
    path = _fresh_database(tmp_path / "transaction.db", tmp_path / "bootstrap-backups")
    _set_ledger_pair(
        path,
        WINDOWS_CRLF_MIGRATION_CHECKSUM,
        WINDOWS_CRLF_SEED_MANIFEST_CHECKSUM,
    )
    before = _governance_snapshot(path)

    def fail(stage: str) -> None:
        if stage == "before_reconciliation_audit_commit":
            raise RuntimeError("injected audit transaction failure")

    with pytest.raises(lifecycle.DatabaseLifecycleError, match="transaction failure"):
        lifecycle.ensure_database_ready(
            path, backup_dir=tmp_path / "backups", fault_hook=fail
        )

    assert _governance_snapshot(path) == before
    backups = list((tmp_path / "backups").glob("*.reconciliation.db"))
    assert len(backups) == 1
    assert backups[0].with_suffix(backups[0].suffix + ".preserve").exists()
    assert not list((tmp_path / "backups" / "reconciliation-audit").glob("*.json"))
    assert not list((tmp_path / "backups" / "reconciliation-audit").glob("*.tmp"))


def test_fresh_database_uses_canonical_pair_without_reconciliation(tmp_path: Path) -> None:
    path = tmp_path / "fresh.db"
    result = lifecycle.ensure_database_ready(path, backup_dir=tmp_path / "backups")
    snapshot = _governance_snapshot(path)

    assert result.action == "created"
    assert snapshot["migration_rows"][0][2] == CANONICAL_MIGRATION_CHECKSUM
    assert snapshot["seed_rows"][0][1] == CANONICAL_SEED_MANIFEST_CHECKSUM
    assert not (tmp_path / "backups").exists()


def test_production_reconciliation_never_updates_lifecycle_ledgers() -> None:
    source = Path(reconciliation.__file__).read_text(encoding="utf-8")
    lifecycle_source = Path(lifecycle.__file__).read_text(encoding="utf-8")

    assert "UPDATE schema_migrations" not in source
    assert "UPDATE seed_releases" not in source
    assert "UPDATE schema_migrations" not in lifecycle_source
    assert "UPDATE seed_releases" not in lifecycle_source
