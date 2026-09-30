from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from core.database_migrations.fingerprints import schema_fingerprint
from core.database_migrations.legacy_compatibility import VersionedLedgerSignature
from services.database_backup_service import (
    BackupRecord,
    create_database_backup,
    mark_failed_reconciliation_backup,
    sha256_file,
    verify_database_backup,
)


class LegacyReconciliationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReconciliationRecord:
    audit_path: Path
    source_sha256: str
    backup: BackupRecord
    signature: VersionedLedgerSignature
    created: bool


def _readonly_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve(strict=True).as_uri()}?mode=ro", uri=True)


def _database_summary(path: Path) -> dict[str, object]:
    connection = _readonly_connection(path)
    try:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        row_counts = {
            table: int(
                connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )
            for table in tables
        }
        sqlite_sequence = []
        if connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='sqlite_sequence'"
        ).fetchone()[0]:
            sqlite_sequence = connection.execute(
                "SELECT name, seq FROM sqlite_sequence ORDER BY name"
            ).fetchall()
        return {
            "integrity_check": integrity,
            "foreign_key_error_count": len(foreign_key_rows),
            "user_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
            "schema_sha256": schema_fingerprint(connection),
            "table_count": len(tables),
            "row_counts": row_counts,
            "sqlite_sequence": sqlite_sequence,
        }
    finally:
        connection.close()


def _audit_path(
    audit_dir: Path,
    source_sha256: str,
    signature: VersionedLedgerSignature,
) -> Path:
    key = f"{source_sha256}:{signature.signature_id}".encode("ascii")
    key_sha256 = hashlib.sha256(key).hexdigest()
    return audit_dir / f"reconciliation-{key_sha256[:24]}.json"


def _backup_from_payload(payload: dict[str, object], backup_dir: Path) -> BackupRecord:
    filename = str(payload.get("backup_filename", ""))
    if not filename or Path(filename).name != filename:
        raise LegacyReconciliationError("Reconciliation audit has an invalid backup filename.")
    return BackupRecord(
        path=backup_dir / filename,
        sha256=str(payload.get("backup_sha256", "")),
        source_version=int(payload.get("user_version", -1)),
        target_version=int(payload.get("user_version", -1)),
        kind="reconciliation",
    )


def _validate_existing_record(
    audit_path: Path,
    database_path: Path,
    backup_dir: Path,
    source_sha256: str,
    signature: VersionedLedgerSignature,
) -> ReconciliationRecord:
    try:
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyReconciliationError("Reconciliation audit record is unreadable.") from exc
    expected = {
        "contract_version": 1,
        "record_type": "legacy_checksum_reconciliation",
        "database_sha256": source_sha256,
        "signature_id": signature.signature_id,
        "migration_checksum": signature.migration_checksum,
        "seed_manifest_checksum": signature.seed_manifest_checksum,
        "schema_sha256": signature.schema_sha256,
        "table_count": signature.table_count,
        "user_version": 10000,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise LegacyReconciliationError("Reconciliation audit record does not match the database signature.")
    backup = _backup_from_payload(payload, backup_dir)
    if verify_database_backup(backup.path) != backup.sha256:
        raise LegacyReconciliationError("Reconciliation backup checksum does not match its audit record.")
    if _database_summary(database_path) != _database_summary(backup.path):
        raise LegacyReconciliationError("Reconciliation backup does not match database governance metadata.")
    return ReconciliationRecord(audit_path, source_sha256, backup, signature, False)


def reconcile_legacy_database_signature(
    database_path: str | Path,
    backup_dir: str | Path,
    signature: VersionedLedgerSignature,
    *,
    fault_hook: Callable[[str], None] | None = None,
) -> ReconciliationRecord:
    """Back up and atomically audit an exact legacy signature without DB writes."""
    source = Path(database_path).resolve(strict=True)
    backups = Path(backup_dir).resolve(strict=False)
    backups.mkdir(parents=True, exist_ok=True)
    audit_dir = backups / "reconciliation-audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    source_sha256 = sha256_file(source)
    audit_path = _audit_path(audit_dir, source_sha256, signature)
    if audit_path.exists():
        return _validate_existing_record(
            audit_path, source, backups, source_sha256, signature
        )

    source_summary = _database_summary(source)
    if (
        source_summary["integrity_check"] != "ok"
        or source_summary["foreign_key_error_count"] != 0
        or source_summary["user_version"] != 10000
        or source_summary["schema_sha256"] != signature.schema_sha256
        or source_summary["table_count"] != signature.table_count
    ):
        raise LegacyReconciliationError(
            "Database governance metadata changed before reconciliation backup."
        )
    if fault_hook is not None:
        fault_hook("before_reconciliation_backup")

    backup: BackupRecord | None = None
    temporary_audit = audit_dir / f".audit-{uuid4().hex[:12]}.tmp"
    try:
        backup = create_database_backup(
            source,
            backups,
            source_version=10000,
            target_version=10000,
            kind="reconciliation",
        )
        if fault_hook is not None:
            fault_hook("after_reconciliation_backup")
        if verify_database_backup(backup.path) != backup.sha256:
            raise LegacyReconciliationError("Verified reconciliation backup checksum changed.")
        if _database_summary(backup.path) != source_summary:
            raise LegacyReconciliationError(
                "Reconciliation backup does not preserve database governance metadata."
            )
        if sha256_file(source) != source_sha256:
            raise LegacyReconciliationError("Source database changed during reconciliation.")
        if fault_hook is not None:
            fault_hook("before_reconciliation_audit_commit")

        payload = {
            "contract_version": 1,
            "record_type": "legacy_checksum_reconciliation",
            "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "database_sha256": source_sha256,
            "backup_filename": backup.path.name,
            "backup_sha256": backup.sha256,
            "signature_id": signature.signature_id,
            "signature_source_type": signature.source_type,
            "migration_id": 10000,
            "migration_name": "adopt_versioned_database",
            "migration_order": "1 of 1",
            "migration_checksum": signature.migration_checksum,
            "seed_manifest_checksum": signature.seed_manifest_checksum,
            "schema_sha256": signature.schema_sha256,
            "table_count": signature.table_count,
            "user_version": 10000,
            "integrity_check": "ok",
            "foreign_key_error_count": 0,
        }
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        descriptor = os.open(temporary_audit, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary_audit, audit_path)
        return ReconciliationRecord(audit_path, source_sha256, backup, signature, True)
    except Exception as exc:
        temporary_audit.unlink(missing_ok=True)
        if backup is not None:
            mark_failed_reconciliation_backup(backup)
        if isinstance(exc, LegacyReconciliationError):
            raise
        raise LegacyReconciliationError(f"Legacy checksum reconciliation failed: {exc}") from exc
