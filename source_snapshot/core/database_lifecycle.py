from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterator
from uuid import uuid4

from core.config import DB_PATH, resolve_biodesign_backup_dir
from core.database_migrations import (
    CURRENT_SCHEMA_VERSION,
    MigrationError,
    migrate_legacy_database,
    validate_versioned_database,
)
from core.database_migrations.fingerprints import (
    DatabaseKind,
    DatabaseProfile,
    classify_database,
)
from services.database_backup_service import (
    BackupRecord,
    create_database_backup,
    mark_failed_migration_backup,
    sha256_file,
)
from services.legacy_database_reconciliation_service import (
    LegacyReconciliationError,
    ReconciliationRecord,
    reconcile_legacy_database_signature,
)


REPOSITORY_DATABASE = (
    Path(__file__).resolve().parents[1] / "data" / "biodesign_unified.db"
).resolve(strict=False)


class DatabaseLifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class LifecycleResult:
    database_path: Path
    profile: DatabaseProfile
    action: str
    backup: BackupRecord | None = None
    legacy_summary: dict | None = None
    reconciliation: ReconciliationRecord | None = None


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _ensure_allowed_database_path(path: Path) -> None:
    if path.resolve(strict=False) == REPOSITORY_DATABASE:
        raise DatabaseLifecycleError(
            f"Refusing to use the repository database at {REPOSITORY_DATABASE}. "
            "Choose a user-data path with BIODESIGN_DB_PATH."
        )


def _ensure_directory_ready(path: Path, required_bytes: int) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(path).free
    except OSError as exc:
        raise DatabaseLifecycleError(
            f"Database directory is not writable: {path}. Fix its permissions and retry. ({exc})"
        ) from exc
    if free < required_bytes:
        raise DatabaseLifecycleError(
            f"Insufficient free space in {path}: {free} bytes available, "
            f"{required_bytes} bytes required. Free space or choose another approved path."
        )


@contextmanager
def _process_lock(database_path: Path, timeout_seconds: float = 1.5) -> Iterator[None]:
    lock_path = database_path.with_suffix(database_path.suffix + ".lifecycle.lock")
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise DatabaseLifecycleError(
                    f"Database lifecycle is locked by another process: {lock_path}. "
                    "Close the other BioDesign Studio process and retry."
                ) from exc
            time.sleep(0.05)
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def _temporary_module_database_path(path: Path) -> Iterator[None]:
    from core import database, seed_database, unified_database
    from services import (
        expression_construct_repository,
        parts_registry_repository,
        pathway_repository,
        project_catalog_asset_link_repository,
    )

    modules: tuple[ModuleType, ...] = (
        database,
        seed_database,
        unified_database,
        expression_construct_repository,
        parts_registry_repository,
        pathway_repository,
        project_catalog_asset_link_repository,
    )
    originals = {module: module.DB_PATH for module in modules}
    try:
        for module in modules:
            module.DB_PATH = str(path)
        yield
    finally:
        for module, original in originals.items():
            module.DB_PATH = original


def _build_unversioned_schema(path: Path) -> None:
    from core.database import init_db
    from core.unified_database import init_unified_database
    from services.expression_construct_repository import init_expression_construct_tables
    from services.parts_registry_repository import init_parts_registry_tables
    from services.pathway_repository import init_pathway_tables
    from services.project_catalog_asset_link_repository import init_project_catalog_asset_link_tables

    with _temporary_module_database_path(path):
        init_db(seed_defaults=False)
        init_unified_database()
        init_parts_registry_tables()
        init_expression_construct_tables()
        init_project_catalog_asset_link_tables()
        init_pathway_tables()


def _fsync_database(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())
    try:
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_descriptor)
    except OSError:
        pass
    finally:
        os.close(directory_descriptor)


def _table_digest(connection: sqlite3.Connection, table: str) -> str:
    columns = [str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")]
    order = ", ".join(f'"{column}"' for column in columns)
    rows = connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}').fetchall()
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_legacy_summary(connection: sqlite3.Connection) -> dict:
    tables = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    rows = {
        table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        for table in tables
    }
    protected_tables = [
        table for table in ("project_history", "sequences", "tool_artifacts") if table in tables
    ]
    return {
        "tables": tables,
        "row_counts": rows,
        "protected_table_sha256": {
            table: _table_digest(connection, table) for table in protected_tables
        },
    }


def _preservation_check(summary: dict) -> Callable[[sqlite3.Connection], None]:
    def verify(connection: sqlite3.Connection) -> None:
        current_tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        for table, before_count in summary["row_counts"].items():
            if table not in current_tables:
                raise MigrationError(f"Legacy table {table} was removed during migration.")
            after_count = int(
                connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )
            if after_count < before_count:
                raise MigrationError(
                    f"Legacy table {table} lost rows ({before_count} -> {after_count})."
                )
        for table, before_hash in summary["protected_table_sha256"].items():
            if _table_digest(connection, table) != before_hash:
                raise MigrationError(f"Legacy user records in {table} changed during migration.")

    return verify


def _quarantine_temporary_database(path: Path) -> Path | None:
    if not path.exists():
        return None
    try:
        digest = sha256_file(path)[:12]
    except OSError:
        digest = "unreadable"
    quarantine = path.parent / f".failed-{_utc_stamp()}-{digest}.db"
    if quarantine.exists():
        quarantine = path.parent / f".failed-{_utc_stamp()}-{digest}-{uuid4().hex[:6]}.db"
    os.replace(path, quarantine)
    return quarantine


def _create_first_run_database(
    database_path: Path,
    *,
    fault_hook: Callable[[str], None] | None = None,
) -> LifecycleResult:
    temporary = database_path.parent / f".{database_path.name}.tmp.{uuid4().hex}"
    try:
        _build_unversioned_schema(temporary)
        profile = classify_database(temporary)
        if profile.kind != DatabaseKind.LEGACY_34:
            raise DatabaseLifecycleError(
                f"Fresh schema fingerprint was {profile.kind} ({profile.schema_sha256})."
            )
        connection = sqlite3.connect(str(temporary), timeout=1.5)
        try:
            migrate_legacy_database(
                connection,
                database_kind=profile.kind,
                deterministic_audit=True,
                fault_hook=fault_hook,
            )
        finally:
            connection.close()
        final_profile = classify_database(temporary)
        if final_profile.kind != DatabaseKind.VERSIONED:
            raise DatabaseLifecycleError("Fresh database did not reach schema version 10000.")
        validation_connection = sqlite3.connect(str(temporary), timeout=1.5)
        try:
            validate_versioned_database(validation_connection)
        finally:
            validation_connection.close()
        _fsync_database(temporary)
        if database_path.exists():
            raise DatabaseLifecycleError(
                f"A database appeared before atomic promotion: {database_path}. "
                "The existing file was not overwritten."
            )
        os.replace(temporary, database_path)
        _fsync_database(database_path)
        return LifecycleResult(database_path, final_profile, "created")
    except Exception as exc:
        quarantine = _quarantine_temporary_database(temporary)
        location = f" Incomplete data was isolated at {quarantine}." if quarantine else ""
        if isinstance(exc, DatabaseLifecycleError):
            raise DatabaseLifecycleError(f"{exc}{location}") from exc
        raise DatabaseLifecycleError(
            f"Could not create the user database at {database_path}.{location} "
            f"Fix the reported storage problem and retry. ({exc})"
        ) from exc


def _migrate_existing_database(
    database_path: Path,
    profile: DatabaseProfile,
    backup_dir: Path,
    *,
    fault_hook: Callable[[str], None] | None = None,
) -> LifecycleResult:
    read_connection = sqlite3.connect(str(database_path), timeout=1.5)
    try:
        summary = build_legacy_summary(read_connection)
    finally:
        read_connection.close()
    backup = create_database_backup(
        database_path,
        backup_dir,
        source_version=profile.user_version,
        target_version=CURRENT_SCHEMA_VERSION,
        kind="migration",
    )
    connection = sqlite3.connect(str(database_path), timeout=1.5)
    try:
        migrate_legacy_database(
            connection,
            database_kind=profile.kind,
            verify_preserved=_preservation_check(summary),
            fault_hook=fault_hook,
        )
    except Exception:
        mark_failed_migration_backup(backup)
        raise
    finally:
        connection.close()
    final_profile = classify_database(database_path)
    if final_profile.kind != DatabaseKind.VERSIONED:
        mark_failed_migration_backup(backup)
        raise DatabaseLifecycleError(
            f"Migration did not produce a supported database. Verified backup: {backup.path}"
        )
    return LifecycleResult(database_path, final_profile, "migrated", backup, summary)


def ensure_database_ready(
    database_path: str | Path = DB_PATH,
    *,
    backup_dir: str | Path | None = None,
    fault_hook: Callable[[str], None] | None = None,
) -> LifecycleResult:
    path = Path(database_path).expanduser().resolve(strict=False)
    _ensure_allowed_database_path(path)
    required_bytes = max(8 * 1024 * 1024, (path.stat().st_size * 3) if path.exists() else 0)
    _ensure_directory_ready(path.parent, required_bytes)
    resolved_backup_dir = Path(backup_dir or resolve_biodesign_backup_dir()).resolve(strict=False)

    with _process_lock(path):
        if not path.exists():
            return _create_first_run_database(path, fault_hook=fault_hook)

        profile = classify_database(path)
        if profile.kind == DatabaseKind.VERSIONED:
            connection = sqlite3.connect(str(path), timeout=1.5)
            try:
                try:
                    validation = validate_versioned_database(connection)
                except MigrationError as exc:
                    raise DatabaseLifecycleError(
                        f"Versioned database verification failed at {path}: {exc}"
                    ) from exc
            finally:
                connection.close()
            if validation.reconciliation_required:
                _ensure_directory_ready(resolved_backup_dir, required_bytes)
                try:
                    reconciliation = reconcile_legacy_database_signature(
                        path,
                        resolved_backup_dir,
                        validation.signature,
                        fault_hook=fault_hook,
                    )
                except LegacyReconciliationError as exc:
                    raise DatabaseLifecycleError(
                        "Legacy database checksum reconciliation stopped before "
                        f"compatibility acceptance. No database writes were made. ({exc})"
                    ) from exc
                return LifecycleResult(
                    path,
                    profile,
                    "reconciled" if reconciliation.created else "validated",
                    reconciliation.backup,
                    reconciliation=reconciliation,
                )
            return LifecycleResult(path, profile, "validated")
        if profile.kind in {
            DatabaseKind.LEGACY_34,
            DatabaseKind.LEGACY_35_TOOL_ARTIFACTS,
        }:
            _ensure_directory_ready(resolved_backup_dir, required_bytes)
            try:
                return _migrate_existing_database(
                    path,
                    profile,
                    resolved_backup_dir,
                    fault_hook=fault_hook,
                )
            except Exception as exc:
                if isinstance(exc, DatabaseLifecycleError):
                    raise
                raise DatabaseLifecycleError(
                    f"Database migration stopped without deleting the original database. "
                    f"Review the verified backup in {resolved_backup_dir} and retry after "
                    f"resolving the cause. ({exc})"
                ) from exc
        if profile.kind == DatabaseKind.FUTURE:
            raise DatabaseLifecycleError(
                f"Database schema version {profile.user_version} is newer than supported "
                f"version {CURRENT_SCHEMA_VERSION}. No writes were made; use a compatible app "
                "or export from the newer version."
            )
        if profile.kind == DatabaseKind.CORRUPT:
            raise DatabaseLifecycleError(
                f"Database integrity could not be verified at {path}. No writes were made; "
                f"select a verified backup from {resolved_backup_dir} for confirmed recovery."
            )
        raise DatabaseLifecycleError(
            f"Database version 0 has an unknown schema fingerprint {profile.schema_sha256}. "
            "No writes were made; manual compatibility review is required."
        )
