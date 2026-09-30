from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from core.database_migrations.fingerprints import (
    CURRENT_SCHEMA_VERSION,
    DatabaseKind,
    schema_fingerprint,
)
from core.database_migrations.legacy_compatibility import (
    EXPECTED_LOGICAL_SEED_SHA256,
    SignatureDisposition,
    VersionedLedgerSignature,
    match_versioned_signature,
)
from core.database_migrations.registry import validate_registry
from core.database_seed import (
    SEED_VERSION,
    apply_seed,
    manifest_checksum,
    verify_seed,
)
from core.database_seed.v10000 import SEED_RELEASE_TIMESTAMP


APPLICATION_VERSION = "phase2c"


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VersionedValidationResult:
    signature: VersionedLedgerSignature

    @property
    def reconciliation_required(self) -> bool:
        return self.signature.disposition == SignatureDisposition.RECONCILIATION_REQUIRED


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _run_fault_hook(fault_hook: Callable[[str], None] | None, stage: str) -> None:
    if fault_hook is not None:
        fault_hook(stage)


def _check_database(connection: sqlite3.Connection) -> None:
    foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_rows:
        raise MigrationError(f"foreign_key_check reported {len(foreign_key_rows)} row(s).")
    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    if integrity != "ok":
        raise MigrationError(f"integrity_check returned {integrity!r}.")


def migrate_legacy_database(
    connection: sqlite3.Connection,
    *,
    database_kind: DatabaseKind,
    verify_preserved: Callable[[sqlite3.Connection], None] | None = None,
    deterministic_audit: bool = False,
    fault_hook: Callable[[str], None] | None = None,
) -> None:
    if database_kind not in {
        DatabaseKind.LEGACY_34,
        DatabaseKind.LEGACY_35_TOOL_ARTIFACTS,
    }:
        raise MigrationError(f"Cannot migrate database classified as {database_kind}.")

    migrations = validate_registry()
    started_at = SEED_RELEASE_TIMESTAMP if deterministic_audit else _utc_now()
    try:
        connection.execute("PRAGMA busy_timeout = 1500")
        connection.execute("BEGIN IMMEDIATE")
        _run_fault_hook(fault_hook, "after_begin")
        current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version != 0:
            raise MigrationError(f"Expected legacy version 0, found {current_version}.")

        pre_schema = schema_fingerprint(connection)
        for migration in migrations:
            _run_fault_hook(fault_hook, f"before_migration_{migration.version}")
            migration.apply(connection)
            _run_fault_hook(fault_hook, f"after_migration_{migration.version}")

        logical_seed_hash = apply_seed(connection)
        _run_fault_hook(fault_hook, "after_seed")
        if verify_preserved is not None:
            verify_preserved(connection)
        _check_database(connection)
        _run_fault_hook(fault_hook, "after_integrity_check")

        completed_at = SEED_RELEASE_TIMESTAMP if deterministic_audit else _utc_now()
        post_schema = schema_fingerprint(connection)
        migration = migrations[-1]
        connection.execute(
            """
            INSERT INTO schema_migrations (
                version, name, checksum, application_version,
                started_at_utc, completed_at_utc, status,
                pre_schema_sha256, post_schema_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, 'applied', ?, ?)
            """,
            (
                migration.version,
                migration.name,
                migration.checksum,
                APPLICATION_VERSION,
                started_at,
                completed_at,
                pre_schema,
                post_schema,
            ),
        )
        connection.execute(
            """
            INSERT INTO seed_releases (
                seed_version, manifest_checksum, logical_seed_sha256,
                applied_at_utc, result
            ) VALUES (?, ?, ?, ?, 'applied')
            """,
            (
                SEED_VERSION,
                manifest_checksum(),
                logical_seed_hash,
                completed_at,
            ),
        )
        _run_fault_hook(fault_hook, "before_user_version")
        connection.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        _run_fault_hook(fault_hook, "before_commit")
        connection.commit()
    except Exception as exc:
        connection.rollback()
        if isinstance(exc, MigrationError):
            raise
        raise MigrationError(f"Database migration to version 10000 failed: {exc}") from exc


def validate_versioned_database(
    connection: sqlite3.Connection,
) -> VersionedValidationResult:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != CURRENT_SCHEMA_VERSION:
        raise MigrationError(
            f"Expected schema version {CURRENT_SCHEMA_VERSION}, found {version}."
        )
    migrations = validate_registry()
    try:
        rows = connection.execute(
            "SELECT version, name, checksum, status FROM schema_migrations ORDER BY version"
        ).fetchall()
        seed_rows = connection.execute(
            "SELECT seed_version, manifest_checksum, logical_seed_sha256, result "
            "FROM seed_releases ORDER BY seed_version"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise MigrationError("Version 10000 database is missing lifecycle ledgers.") from exc

    if len(rows) != len(migrations):
        raise MigrationError("Migration ledger checksum or ordering does not match this application.")
    expected_identity = [
        (migration.version, migration.name, "applied") for migration in migrations
    ]
    actual_identity = [(row[0], row[1], row[3]) for row in rows]
    if actual_identity != expected_identity:
        raise MigrationError("Migration ledger checksum or ordering does not match this application.")
    if len(seed_rows) != 1 or seed_rows[0][0] != SEED_VERSION or seed_rows[0][3] != "applied":
        raise MigrationError("Seed release ledger checksum does not match this application.")

    schema_sha256 = schema_fingerprint(connection)
    table_count = int(
        connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
    )
    signature = match_versioned_signature(
        migration_checksum=str(rows[0][2]),
        seed_manifest_checksum=str(seed_rows[0][1]),
        schema_sha256=schema_sha256,
        table_count=table_count,
    )
    if signature is None:
        raise MigrationError(
            "Migration and seed checksum signature does not match an approved schema profile."
        )

    actual_seed_hash = verify_seed(connection)
    if (
        seed_rows[0][2] != actual_seed_hash
        or actual_seed_hash != EXPECTED_LOGICAL_SEED_SHA256
    ):
        raise MigrationError("Seed release ledger logical hash does not match database content.")
    _check_database(connection)
    return VersionedValidationResult(signature)
