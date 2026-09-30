from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


CANONICAL_MIGRATION_CHECKSUM = (
    "4bf13835d30c7f25021350419f5b389aa73722fec82d0819b13655daca2fe182"
)
CANONICAL_SEED_MANIFEST_CHECKSUM = (
    "277375096836298109e6c7e3b58c607c9309eb7e6b634988e07e61afbf5656b2"
)
WINDOWS_CRLF_MIGRATION_CHECKSUM = (
    "b5072df2c8e50f44be33a3b451bfd4493c87213daf7a3a27f47e0516e1230885"
)
WINDOWS_CRLF_SEED_MANIFEST_CHECKSUM = (
    "cbc6be3cfb5ec472856c18d358716caa3b0519daca6a249bb8a92cdfb4e499fd"
)
VERSIONED_36_SCHEMA_SHA256 = (
    "11e4ca3bc1af41921e9a3af598194cf37740397c3567c3ed227959314ceffcad"
)
VERSIONED_37_TOOL_ARTIFACTS_SCHEMA_SHA256 = (
    "15d33edb30b66ed37c076458eea46f1dd99f02987b3c6acdf66b0d868f0c97d3"
)
EXPECTED_LOGICAL_SEED_SHA256 = (
    "ac7d21bacf962153792bf9af271764ae96c73b588d28335ca2519ee2c43d43de"
)


class SignatureDisposition(StrEnum):
    CANONICAL = "canonical"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True)
class VersionedLedgerSignature:
    signature_id: str
    source_type: str
    migration_checksum: str
    seed_manifest_checksum: str
    schema_sha256: str
    table_count: int
    disposition: SignatureDisposition


# STARTUP-DB-01A R-A approval: exact pairs and exact schema profiles only.
APPROVED_VERSIONED_SIGNATURES = (
    VersionedLedgerSignature(
        signature_id="canonical-lf-fresh-36",
        source_type="canonical_lf",
        migration_checksum=CANONICAL_MIGRATION_CHECKSUM,
        seed_manifest_checksum=CANONICAL_SEED_MANIFEST_CHECKSUM,
        schema_sha256=VERSIONED_36_SCHEMA_SHA256,
        table_count=36,
        disposition=SignatureDisposition.CANONICAL,
    ),
    VersionedLedgerSignature(
        signature_id="historical-lf-source-37",
        source_type="historical_git_lf",
        migration_checksum=CANONICAL_MIGRATION_CHECKSUM,
        seed_manifest_checksum=CANONICAL_SEED_MANIFEST_CHECKSUM,
        schema_sha256=VERSIONED_37_TOOL_ARTIFACTS_SCHEMA_SHA256,
        table_count=37,
        disposition=SignatureDisposition.RECONCILIATION_REQUIRED,
    ),
    VersionedLedgerSignature(
        signature_id="windows-crlf-fresh-36",
        source_type="windows_worktree_crlf",
        migration_checksum=WINDOWS_CRLF_MIGRATION_CHECKSUM,
        seed_manifest_checksum=WINDOWS_CRLF_SEED_MANIFEST_CHECKSUM,
        schema_sha256=VERSIONED_36_SCHEMA_SHA256,
        table_count=36,
        disposition=SignatureDisposition.RECONCILIATION_REQUIRED,
    ),
)


def match_versioned_signature(
    *,
    migration_checksum: str,
    seed_manifest_checksum: str,
    schema_sha256: str,
    table_count: int,
) -> VersionedLedgerSignature | None:
    """Match only a complete checksum pair bound to an approved schema profile."""
    for signature in APPROVED_VERSIONED_SIGNATURES:
        if (
            signature.migration_checksum == migration_checksum
            and signature.seed_manifest_checksum == seed_manifest_checksum
            and signature.schema_sha256 == schema_sha256
            and signature.table_count == table_count
        ):
            return signature
    return None
