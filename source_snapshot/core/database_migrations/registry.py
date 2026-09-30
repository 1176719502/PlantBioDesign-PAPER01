from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.database_checksums import canonical_source_file_checksum
from core.database_migrations import V10000__adopt_versioned_database as v10000


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    checksum: str
    apply: Callable


def _module_checksum(path: str) -> str:
    return canonical_source_file_checksum(path)


MIGRATIONS = (
    Migration(v10000.VERSION, v10000.NAME, _module_checksum(v10000.__file__), v10000.apply),
)


def validate_registry() -> tuple[Migration, ...]:
    versions = [migration.version for migration in MIGRATIONS]
    if versions != sorted(versions) or len(versions) != len(set(versions)):
        raise RuntimeError("Database migration registry contains duplicate or unordered versions.")
    if not versions or versions[0] != 10000:
        raise RuntimeError("Database migration registry must begin at version 10000.")
    for previous, current in zip(versions, versions[1:]):
        if current != previous + 1:
            raise RuntimeError(
                f"Database migration registry skips version {previous + 1}."
            )
    return MIGRATIONS
