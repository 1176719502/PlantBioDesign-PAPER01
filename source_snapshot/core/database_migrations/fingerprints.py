from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


LEGACY_34_SCHEMA_SHA256 = "66e0a832bc9e07fd315570f7662907ce762ebbce83964c116ab0a6dbe369fa3b"
LEGACY_35_SCHEMA_SHA256 = "f443a297bcf2ed161fc435f5f2ee96c6b49c98bb9ed1cd7564a1c86ab5c3bf95"
CURRENT_SCHEMA_VERSION = 10000


class DatabaseKind(StrEnum):
    LEGACY_34 = "legacy_34"
    LEGACY_35_TOOL_ARTIFACTS = "legacy_35_tool_artifacts"
    VERSIONED = "versioned"
    FUTURE = "future"
    UNKNOWN = "unknown"
    CORRUPT = "corrupt"


@dataclass(frozen=True)
class DatabaseProfile:
    kind: DatabaseKind
    user_version: int
    schema_sha256: str
    table_count: int
    integrity_check: str


def schema_fingerprint(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_connection(connection: sqlite3.Connection) -> DatabaseProfile:
    try:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        schema_hash = schema_fingerprint(connection)
        table_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        )
    except (sqlite3.DatabaseError, TypeError, ValueError):
        return DatabaseProfile(DatabaseKind.CORRUPT, -1, "", 0, "failed")

    if integrity != "ok":
        kind = DatabaseKind.CORRUPT
    elif user_version > CURRENT_SCHEMA_VERSION:
        kind = DatabaseKind.FUTURE
    elif user_version == CURRENT_SCHEMA_VERSION:
        kind = DatabaseKind.VERSIONED
    elif user_version == 0 and schema_hash == LEGACY_34_SCHEMA_SHA256 and table_count == 34:
        kind = DatabaseKind.LEGACY_34
    elif user_version == 0 and schema_hash == LEGACY_35_SCHEMA_SHA256 and table_count == 35:
        kind = DatabaseKind.LEGACY_35_TOOL_ARTIFACTS
    else:
        kind = DatabaseKind.UNKNOWN
    return DatabaseProfile(kind, user_version, schema_hash, table_count, integrity)


def classify_database(path: str | Path) -> DatabaseProfile:
    connection = sqlite3.connect(str(path), timeout=1.0)
    try:
        return classify_connection(connection)
    finally:
        connection.close()
