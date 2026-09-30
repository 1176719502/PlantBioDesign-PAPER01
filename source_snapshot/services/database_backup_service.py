from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class DatabaseBackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupRecord:
    path: Path
    sha256: str
    source_version: int
    target_version: int
    kind: str


@dataclass(frozen=True)
class _BackupFilename:
    path: Path
    timestamp: str
    sha256_prefix: str
    kind: str


_FORMAL_BACKUP_FILENAME_PATTERN = re.compile(
    r"^biodesign_unified\.v\d+_to_v\d+\."
    r"(?P<timestamp>\d{8}T\d{6}Z)\."
    r"(?P<sha256_prefix>[0-9a-f]{12})\."
    r"(?P<kind>automatic|manual|migration|reconciliation|restore)"
    r"(?:\.[0-9a-f]{8})?\.db$"
)
_LEGACY_BACKUP_FILENAME_PATTERN = re.compile(
    r"^db\.v\d+-v\d+\."
    r"(?P<timestamp>\d{8}T\d{6}Z)\."
    r"(?P<sha256_prefix>[0-9a-f]{12})\."
    r"(?P<kind>automatic|manual|migration|reconciliation|restore)"
    r"(?:\.[0-9a-f]{8})?\.db$"
)
_BACKUP_FILENAME_PATTERNS = (
    _FORMAL_BACKUP_FILENAME_PATTERN,
    _LEGACY_BACKUP_FILENAME_PATTERN,
)

_AUTOMATIC_BACKUP_LIMIT = 5
_MIGRATION_BACKUP_LIMIT = 3


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _integrity_check(path: Path) -> None:
    connection = sqlite3.connect(str(path), timeout=2.0)
    try:
        result = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        connection.close()
    if result != "ok":
        raise DatabaseBackupError(f"Backup integrity_check returned {result!r}.")


def verify_database_backup(path: str | Path) -> str:
    """Verify a backup can be opened and return its current SHA-256."""
    backup = Path(path).resolve(strict=True)
    _integrity_check(backup)
    return sha256_file(backup)


def _formal_backup_filename(
    *,
    source_version: int,
    target_version: int,
    timestamp: str,
    sha256_prefix: str,
    kind: str,
) -> str:
    """Return the governance-approved filename for a newly written backup."""
    return (
        f"biodesign_unified.v{source_version}_to_v{target_version}."
        f"{timestamp}.{sha256_prefix}.{kind}.db"
    )


def create_database_backup(
    source_path: str | Path,
    backup_dir: str | Path,
    *,
    source_version: int,
    target_version: int,
    kind: str = "migration",
    now: datetime | None = None,
) -> BackupRecord:
    source = Path(source_path).resolve(strict=True)
    destination_dir = Path(backup_dir).resolve(strict=False)
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    temporary = destination_dir / f".backup-{uuid4().hex[:12]}.tmp"
    final_path: Path | None = None

    source_connection: sqlite3.Connection | None = None
    backup_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(
            f"{source.as_uri()}?mode=ro", uri=True, timeout=2.0
        )
        backup_connection = sqlite3.connect(str(temporary))
        source_connection.backup(backup_connection)
        backup_connection.commit()
        backup_connection.close()
        backup_connection = None
        _integrity_check(temporary)
        _fsync_file(temporary)
        backup_hash = sha256_file(temporary)
        filename = _formal_backup_filename(
            source_version=source_version,
            target_version=target_version,
            timestamp=timestamp,
            sha256_prefix=backup_hash[:12],
            kind=kind,
        )
        final_path = destination_dir / filename
        if final_path.exists():
            final_path = destination_dir / f"{final_path.stem}.{uuid4().hex[:8]}.db"
        os.replace(temporary, final_path)
        _fsync_file(final_path)
    except Exception as exc:
        if temporary.exists():
            temporary.unlink()
        if isinstance(exc, DatabaseBackupError):
            raise
        raise DatabaseBackupError(
            f"Could not create a verified database backup in {destination_dir}: {exc}"
        ) from exc
    finally:
        if backup_connection is not None:
            backup_connection.close()
        if source_connection is not None:
            source_connection.close()

    if final_path is None:
        raise DatabaseBackupError("Backup final path was not created.")
    record = BackupRecord(final_path, sha256_file(final_path), source_version, target_version, kind)
    prune_database_backups(destination_dir)
    return record


def mark_failed_migration_backup(record: BackupRecord) -> Path:
    return _mark_preserved_backup(record, "migration")


def mark_failed_reconciliation_backup(record: BackupRecord) -> Path:
    return _mark_preserved_backup(record, "reconciliation")


def _mark_preserved_backup(record: BackupRecord, operation: str) -> Path:
    marker = record.path.with_suffix(record.path.suffix + ".preserve")
    marker.write_text(
        f"Retained because the associated {operation} did not complete.\n",
        encoding="utf-8",
    )
    return marker


def _parse_backup_filename(path: Path) -> _BackupFilename | None:
    """Recognize formal names and legacy ``db.v*`` names for read/pruning only."""
    for pattern in _BACKUP_FILENAME_PATTERNS:
        match = pattern.fullmatch(path.name)
        if match is not None:
            return _BackupFilename(
                path=path,
                timestamp=match.group("timestamp"),
                sha256_prefix=match.group("sha256_prefix"),
                kind=match.group("kind"),
            )
    return None


def _verified_backup_filename(path: Path) -> _BackupFilename | None:
    parsed = _parse_backup_filename(path)
    if parsed is None:
        return None
    try:
        actual_prefix = sha256_file(path)[:12]
    except OSError:
        return None
    return parsed if actual_prefix == parsed.sha256_prefix else None


def _retention_sort_key(backup: _BackupFilename) -> tuple[str, int, str]:
    return (backup.timestamp, backup.path.stat().st_mtime_ns, backup.path.name)


def _prune_backup_kind(
    backups: list[_BackupFilename],
    *,
    limit: int,
    protected: set[Path],
) -> None:
    eligible = [backup for backup in backups if backup.path not in protected]
    keep = {
        backup.path
        for backup in sorted(eligible, key=_retention_sort_key, reverse=True)[:limit]
    }
    stale = sorted(
        (backup for backup in eligible if backup.path not in keep),
        key=_retention_sort_key,
    )
    for backup in stale:
        try:
            backup.path.unlink()
        except OSError as exc:
            raise DatabaseBackupError(
                f"Could not prune database backup {backup.path}: {exc}"
            ) from exc


def prune_database_backups(backup_dir: str | Path) -> None:
    directory = Path(backup_dir)
    if not directory.exists():
        return
    candidates = [
        parsed
        for path in directory.iterdir()
        if path.is_file() and (parsed := _verified_backup_filename(path)) is not None
    ]
    protected = {
        backup.path
        for backup in candidates
        if backup.path.with_suffix(backup.path.suffix + ".preserve").exists()
        or ".pinned." in backup.path.name
    }
    automatic = [backup for backup in candidates if backup.kind == "automatic"]
    migration = [backup for backup in candidates if backup.kind == "migration"]
    _prune_backup_kind(automatic, limit=_AUTOMATIC_BACKUP_LIMIT, protected=protected)
    _prune_backup_kind(migration, limit=_MIGRATION_BACKUP_LIMIT, protected=protected)


def restore_database_backup(
    backup_path: str | Path,
    target_path: str | Path,
    *,
    confirmed: bool,
) -> Path:
    if not confirmed:
        raise DatabaseBackupError("Restoring over a user database requires explicit confirmation.")
    backup = Path(backup_path).resolve(strict=True)
    target = Path(target_path).resolve(strict=False)
    _integrity_check(backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    candidate = target.parent / f".{target.name}.restore.tmp.{uuid4().hex}"
    source_connection = sqlite3.connect(str(backup), timeout=2.0)
    candidate_connection = sqlite3.connect(str(candidate))
    try:
        source_connection.backup(candidate_connection)
        candidate_connection.commit()
    finally:
        candidate_connection.close()
        source_connection.close()
    _integrity_check(candidate)
    _fsync_file(candidate)

    quarantine: Path | None = None
    if target.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        quarantine = target.with_name(
            f"{target.name}.failed.{stamp}.{sha256_file(target)[:12]}"
        )
        os.replace(target, quarantine)
    try:
        os.replace(candidate, target)
        _fsync_file(target)
    except Exception:
        if quarantine is not None and quarantine.exists() and not target.exists():
            os.replace(quarantine, target)
        raise
    return quarantine or target
