from __future__ import annotations

import sqlite3


VERSION = 10000
NAME = "adopt_versioned_database"


def apply(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            application_version TEXT NOT NULL,
            started_at_utc TEXT NOT NULL,
            completed_at_utc TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('applied')),
            pre_schema_sha256 TEXT NOT NULL,
            post_schema_sha256 TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE seed_releases (
            seed_version INTEGER PRIMARY KEY,
            manifest_checksum TEXT NOT NULL,
            logical_seed_sha256 TEXT NOT NULL,
            applied_at_utc TEXT NOT NULL,
            result TEXT NOT NULL CHECK (result IN ('applied'))
        )
        """
    )
