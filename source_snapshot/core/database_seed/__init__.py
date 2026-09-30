"""Versioned built-in seed definitions."""

from core.database_checksums import canonical_source_file_checksum
from core.database_seed import v10000
from core.database_seed.v10000 import (
    SEED_VERSION,
    SeedVerificationError,
    apply_seed,
    normalized_seed_sha256,
    verify_seed,
)


def manifest_checksum() -> str:
    return canonical_source_file_checksum(v10000.__file__)

__all__ = [
    "SEED_VERSION",
    "SeedVerificationError",
    "apply_seed",
    "manifest_checksum",
    "normalized_seed_sha256",
    "verify_seed",
]
