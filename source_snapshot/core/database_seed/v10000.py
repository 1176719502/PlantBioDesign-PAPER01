from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


SEED_VERSION = 10000
SEED_RELEASE_TIMESTAMP = "2026-07-22T00:00:00+00:00"
EXPECTED_NORMALIZED_SHA256 = "ac7d21bacf962153792bf9af271764ae96c73b588d28335ca2519ee2c43d43de"

SEED_KEYS: dict[str, tuple[str, tuple[str, ...]]] = {
    "promoters": (
        "id",
        (
            "PRO_CAMV35S", "PRO_NOS", "PRO_OSACT1", "PRO_PBAD", "PRO_PLAC",
            "PRO_PT7", "PRO_ZMUBI1",
        ),
    ),
    "genes": (
        "id",
        (
            "GENE_BAR", "GENE_DREB1A", "GENE_HPTII", "GENE_LUC",
            "GENE_MGFP5", "GENE_NPTII", "GENE_SPCAS9", "GENE_UIDA",
        ),
    ),
    "terminators": (
        "id", ("TER_35S", "TER_35SPOLY", "TER_NOS", "TER_RNBT1", "TER_T7")
    ),
    "tags": (
        "id",
        (
            "RBS_KOZAK_MIN", "RBS_KOZAK_OPT", "RBS_MED_SD", "RBS_STRONG_SD",
            "RBS_WEAK_SD", "RBS_YEAST_OPT", "TAG_6XHIS", "TAG_FLAG", "TAG_GST",
            "TAG_HA", "TAG_KDEL", "TAG_MCHERRY", "TAG_MYC", "TAG_NLS",
        ),
    ),
    "plasmids": (
        "name", ("pCAMBIA1300", "pCAMBIA2300", "pET-21a(+)", "pET-28a(+)", "pGreen0029", "pUC19")
    ),
    "strains": ("name", ("BL21(DE3)", "DH5alpha", "EHA105", "GV3101", "Top10")),
    "primers": (
        "name", ("35S_Promoter_Fwd", "M13_Fwd_20", "M13_Rev", "NOS_Term_Fwd", "SP6_Primer", "T7_Promoter_Primer")
    ),
    "biological_parts": (
        "name",
        (
            "6xHis Tag Coding Sequence", "ADH1 Terminator", "Alpha Factor Signal Peptide",
            "B0030 RBS", "B0031 RBS", "B0032 RBS", "B0034 RBS",
            "CaMV 35S Core Promoter", "Consensus Shine-Dalgarno RBS",
            "Extended Shine-Dalgarno RBS", "FLAG Tag Coding Sequence", "GAL1 Promoter",
            "HPT CDS Fragment", "NOS Terminator Core", "NPTII CDS Fragment",
            "NanoLuc CDS Fragment", "OCS Terminator Core", "T7 Promoter", "T7 Terminator",
            "TEF1 Promoter", "UBQ10 Promoter", "ZmUbi1 Promoter", "araBAD Promoter",
            "eGFP CDS Fragment", "lacUV5 Promoter", "mCherry CDS Fragment",
            "mScarlet-I CDS Fragment", "pBR322 Origin Segment", "pCAMBIA1300 MCS Segment",
            "pET-28a Plus MCS Segment", "pGreenII MCS Segment", "pUC19 MCS Segment",
            "pYES2 MCS Segment", "rrnB T1 Terminator", "rrnB T1-T7Te Terminator",
            "sfGFP CDS Fragment", "spacer-6 RBS", "spacer-8 RBS", "tac Promoter",
            "trc Promoter",
        ),
    ),
}

EXCLUDED_COLUMNS = {
    "promoters": {"created_at", "updated_at"},
    "genes": {"created_at", "updated_at"},
    "terminators": {"created_at", "updated_at"},
    "tags": {"created_at", "updated_at"},
    "plasmids": {"id", "entry_date"},
    "strains": {"id", "entry_date"},
    "primers": {"id", "design_date"},
    "biological_parts": {"id", "created_at"},
}


class SeedVerificationError(RuntimeError):
    pass


def manifest_checksum() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _normalized_seed_payload(connection: sqlite3.Connection) -> dict[str, list[dict]]:
    payload: dict[str, list[dict]] = {}
    for table, (key_column, expected_keys) in SEED_KEYS.items():
        columns = [
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            if str(row[1]) not in EXCLUDED_COLUMNS[table]
        ]
        placeholders = ",".join("?" for _ in expected_keys)
        rows = connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} "
            f"WHERE {key_column} IN ({placeholders}) ORDER BY {key_column}",
            expected_keys,
        ).fetchall()
        actual_keys = {
            str(row[0])
            for row in connection.execute(
                f"SELECT {key_column} FROM {table} "
                f"WHERE {key_column} IN ({placeholders})",
                expected_keys,
            ).fetchall()
        }
        missing = sorted(set(expected_keys) - actual_keys)
        if missing:
            raise SeedVerificationError(f"Seed table {table} is missing keys: {missing}")
        payload[table] = [dict(zip(columns, row)) for row in rows]
    return payload


def normalized_seed_sha256(connection: sqlite3.Connection) -> str:
    payload = _normalized_seed_payload(connection)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_seed(connection: sqlite3.Connection) -> str:
    from core.database import seed_builtin_parts
    from core.seed_database import seed_all

    seed_builtin_parts(connection)
    seed_all(connection)
    return verify_seed(connection)


def verify_seed(connection: sqlite3.Connection) -> str:
    digest = normalized_seed_sha256(connection)
    if digest != EXPECTED_NORMALIZED_SHA256:
        raise SeedVerificationError(
            "Built-in seed content conflicts with the V10000 manifest; existing rows were not overwritten."
        )
    return digest
