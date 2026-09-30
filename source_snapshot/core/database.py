"""
core/database.py
~~~~~~~~~~~~~~~~
Dedicated SQLite persistence layer for the Biological Parts Registry.

Design principles
-----------------
* Uses a context manager for every connection so the file is never left locked.
* All write paths clean and re-validate the sequence before committing.
* Pure stdlib — no Streamlit, no session_state references.
* The table `biological_parts` lives inside the same unified DB file used by
  the rest of the application so there is only one database to manage.

Public API
----------
    init_db()                        — idempotent: create table if absent
    add_part(data)                   — validate + insert one part row
    get_all_parts(filter_type=None)  — return pandas DataFrame
    delete_part(part_id)             — remove a row by INTEGER primary key
    get_part_types()                 — list of distinct part_type values in DB
"""
from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, Optional

import pandas as pd

from core.config import DB_PATH

BUILTIN_SEED_TIMESTAMP = "2026-07-22 00:00:00+00:00"

_METADATA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("source_type", "TEXT NOT NULL DEFAULT ''"),
    ("function_summary", "TEXT NOT NULL DEFAULT ''"),
    ("common_usage", "TEXT NOT NULL DEFAULT ''"),
    ("key_features", "TEXT NOT NULL DEFAULT ''"),
    ("recommended_pairing", "TEXT NOT NULL DEFAULT ''"),
    ("notes", "TEXT NOT NULL DEFAULT ''"),
)


# ---------------------------------------------------------------------------
# Path — single source of truth from core.config.DB_PATH
# ---------------------------------------------------------------------------






# ---------------------------------------------------------------------------
# Allowed part types (must match values used across the UI)
# ---------------------------------------------------------------------------

ALLOWED_TYPES: tuple[str, ...] = (
    "Promoter",
    "RBS",
    "CDS",
    "Terminator",
    "Vector",
)

# Canonical organism names (match species_presets.py keys + common aliases)
ALLOWED_ORGANISMS: tuple[str, ...] = (
    "Rice",
    "Arabidopsis",
    "E.coli",
    "Yeast",
    "Tobacco",
    "Universal",
)

_VALID_BASES: frozenset[str] = frozenset("ATCGN")

# ---------------------------------------------------------------------------
# Default seed data for the active parts registry
# ---------------------------------------------------------------------------

_DEFAULT_PARTS: tuple[dict[str, str], ...] = (
    {
        "name": "T7 Promoter",
        "part_type": "Promoter",
        "organism": "E.coli",
        "sequence": "TAATACGACTCACTATA",
        "description": "Strong bacteriophage T7 promoter for high-level expression in E.coli strains carrying T7 RNA polymerase.",
    },
    {
        "name": "lacUV5 Promoter",
        "part_type": "Promoter",
        "organism": "E.coli",
        "sequence": "AATTGTGAGCGGATAACAATT",
        "description": "IPTG-inducible lacUV5 promoter commonly used in bacterial expression vectors.",
    },
    {
        "name": "trc Promoter",
        "part_type": "Promoter",
        "organism": "E.coli",
        "sequence": "TTGACAATTAATCATCGGCTCGTATAATGTGTGGA",
        "description": "Hybrid trp-lac promoter used for strong inducible expression in E.coli.",
    },
    {
        "name": "tac Promoter",
        "part_type": "Promoter",
        "organism": "E.coli",
        "sequence": "TTGACAATTAATCATCGGCTCGTATAATG",
        "description": "Hybrid tac promoter for controllable bacterial expression with lac regulation.",
    },
    {
        "name": "araBAD Promoter",
        "part_type": "Promoter",
        "organism": "E.coli",
        "sequence": "TTTACACTTTATGCTTCCGGCTCGTATGTTGTGTGG",
        "description": "Arabinose-inducible bacterial promoter for tightly regulated expression workflows.",
    },
    {
        "name": "GAL1 Promoter",
        "part_type": "Promoter",
        "organism": "Yeast",
        "sequence": "CGGATAATACGCGCCACATATAAGTGTGGATTTA",
        "description": "Galactose-inducible yeast promoter used for regulated expression in Saccharomyces workflows.",
    },
    {
        "name": "TEF1 Promoter",
        "part_type": "Promoter",
        "organism": "Yeast",
        "sequence": "TTTATTCGCTTTGCTGTTTTTCTCGAGGTCGACGGTATCG",
        "description": "Constitutive yeast promoter derived from translation elongation factor 1 alpha.",
    },
    {
        "name": "CaMV 35S Core Promoter",
        "part_type": "Promoter",
        "organism": "Tobacco",
        "sequence": "GCTCCTACAAATGCCATCA",
        "description": "Compact default plant constitutive promoter entry for dicot expression workflows.",
    },
    {
        "name": "UBQ10 Promoter",
        "part_type": "Promoter",
        "organism": "Arabidopsis",
        "sequence": "CAGCTCACTCTCTCTCTACCGTTGTCGACGATCGA",
        "description": "Arabidopsis ubiquitin 10 promoter entry for constitutive plant expression designs.",
    },
    {
        "name": "ZmUbi1 Promoter",
        "part_type": "Promoter",
        "organism": "Rice",
        "sequence": "GCGATCGATTTGCGGTTCCGATCGATCGTTGACCA",
        "description": "Monocot ubiquitin promoter entry commonly used for strong expression in cereal systems.",
    },
    {
        "name": "B0034 RBS",
        "part_type": "RBS",
        "organism": "E.coli",
        "sequence": "AAAGAGGAGAAA",
        "description": "Strong Shine-Dalgarno ribosome binding site widely used in bacterial expression constructs.",
    },
    {
        "name": "B0032 RBS",
        "part_type": "RBS",
        "organism": "E.coli",
        "sequence": "AAAGAAGAGAAA",
        "description": "Moderately strong bacterial ribosome binding site for balanced translation initiation.",
    },
    {
        "name": "B0030 RBS",
        "part_type": "RBS",
        "organism": "E.coli",
        "sequence": "AAAGAGTGGAAA",
        "description": "Mid-strength bacterial ribosome binding site used in standard BioBrick assemblies.",
    },
    {
        "name": "B0031 RBS",
        "part_type": "RBS",
        "organism": "E.coli",
        "sequence": "AAAGATGAGAAA",
        "description": "Lower-strength bacterial ribosome binding site for tuning translation output.",
    },
    {
        "name": "Consensus Shine-Dalgarno RBS",
        "part_type": "RBS",
        "organism": "E.coli",
        "sequence": "AGGAGG",
        "description": "Minimal consensus Shine-Dalgarno sequence for prokaryotic translation initiation.",
    },
    {
        "name": "Extended Shine-Dalgarno RBS",
        "part_type": "RBS",
        "organism": "E.coli",
        "sequence": "TAAGGAGGT",
        "description": "Extended Shine-Dalgarno entry for bacterial construct prototyping.",
    },
    {
        "name": "spacer-6 RBS",
        "part_type": "RBS",
        "organism": "E.coli",
        "sequence": "AGGAGGAAAAAA",
        "description": "Consensus Shine-Dalgarno motif with a short spacer region for bacterial CDS coupling.",
    },
    {
        "name": "spacer-8 RBS",
        "part_type": "RBS",
        "organism": "E.coli",
        "sequence": "AGGAGGAAAAAAAA",
        "description": "Consensus Shine-Dalgarno motif with an extended spacer region for bacterial starter designs.",
    },
    {
        "name": "eGFP CDS Fragment",
        "part_type": "CDS",
        "organism": "Universal",
        "sequence": "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCCATCCTGGTCGAGCTG",
        "description": "Default reporter CDS fragment derived from enhanced green fluorescent protein.",
    },
    {
        "name": "mCherry CDS Fragment",
        "part_type": "CDS",
        "organism": "Universal",
        "sequence": "ATGGTGAGCAAGGGCGAGGAGGATAACATGGCCATCATCAAGGAGTTCATGCGCTTC",
        "description": "Default red fluorescent reporter CDS fragment for expression and visualization demos.",
    },
    {
        "name": "mScarlet-I CDS Fragment",
        "part_type": "CDS",
        "organism": "Universal",
        "sequence": "ATGGTGAGCAAGGGCGAGGCCGTCCTGAAGGGCGAGGCCCTGATCAACGG",
        "description": "Bright monomeric red fluorescent protein CDS fragment for reporter construct planning.",
    },
    {
        "name": "sfGFP CDS Fragment",
        "part_type": "CDS",
        "organism": "Universal",
        "sequence": "ATGAGCAAAGGCGAGGAGGATAACATGGCCATCATCAAGGAGTTCATGCGC",
        "description": "Superfolder GFP CDS fragment for robust reporter expression workflows.",
    },
    {
        "name": "NanoLuc CDS Fragment",
        "part_type": "CDS",
        "organism": "Universal",
        "sequence": "ATGGTCTTCACACTCGAAGATTTCGTTGGGGACTGGCGACAGACAGCCGG",
        "description": "Compact luciferase reporter CDS fragment for luminescence assay planning.",
    },
    {
        "name": "NPTII CDS Fragment",
        "part_type": "CDS",
        "organism": "Universal",
        "sequence": "ATGATTGAACAAGATGGATTGCACGCAGGTTCTCCGGCCGCTTGGGTGGA",
        "description": "Neomycin phosphotransferase II selection marker CDS fragment.",
    },
    {
        "name": "HPT CDS Fragment",
        "part_type": "CDS",
        "organism": "Universal",
        "sequence": "ATGAAAAAGCCTGAACTCACCGCGACGTCTGTCGAGAAGTTTCTGATCGA",
        "description": "Hygromycin phosphotransferase selection marker CDS fragment.",
    },
    {
        "name": "6xHis Tag Coding Sequence",
        "part_type": "CDS",
        "organism": "Universal",
        "sequence": "CACCACCACCACCACCAC",
        "description": "Affinity purification tag coding sequence stored as CDS for compatibility with the active registry filters.",
    },
    {
        "name": "FLAG Tag Coding Sequence",
        "part_type": "CDS",
        "organism": "Universal",
        "sequence": "GACTACAAAGACGATGACGACAAG",
        "description": "FLAG epitope tag coding sequence stored as CDS for simple fusion design workflows.",
    },
    {
        "name": "Alpha Factor Signal Peptide",
        "part_type": "CDS",
        "organism": "Yeast",
        "sequence": "ATGAGATTTCCTTCAATTGTTCTACTGATTGTTGCTGCTGCTTCTTCTACTGCTGCT",
        "description": "Yeast secretion signal peptide stored as CDS for compatibility with the active registry filters.",
    },
    {
        "name": "T7 Terminator",
        "part_type": "Terminator",
        "organism": "E.coli",
        "sequence": "CTCGAGTTATTGCTCAGCGGTGGCAGCAGCCAACTCAGCTTCCTTTCGGGCTTTGTTAGCAGCCGGATCTCAGTGGTGGTGGTGGTGGTG",
        "description": "Default bacterial transcription terminator used downstream of T7-driven expression cassettes.",
    },
    {
        "name": "rrnB T1 Terminator",
        "part_type": "Terminator",
        "organism": "E.coli",
        "sequence": "GCGTTTTTTCGCTGCGTTATCCCCTGATTCTGTGGATAACCGTATTACCGCCATGC",
        "description": "Bacterial rrnB T1 terminator entry for transcription insulation in E.coli constructs.",
    },
    {
        "name": "rrnB T1-T7Te Terminator",
        "part_type": "Terminator",
        "organism": "E.coli",
        "sequence": "GCGTTTTTTCGCTGCGTTATCCCCTGATTCTGTGGATAACCGTATTACCGCCATGCTTAACCCGCGAAATTAATACGACTCACTATAGGG",
        "description": "Composite bacterial terminator entry combining rrnB and T7 terminator features.",
    },
    {
        "name": "ADH1 Terminator",
        "part_type": "Terminator",
        "organism": "Yeast",
        "sequence": "GATCCGGTACCTCGAGTTTAAACGAGCTCGAATTCGTAATCATGGTCATAGCTGTT",
        "description": "Common yeast transcription terminator derived from alcohol dehydrogenase 1.",
    },
    {
        "name": "NOS Terminator Core",
        "part_type": "Terminator",
        "organism": "Tobacco",
        "sequence": "GTTGCGCGCTATATTTTGTTTTCTATCGCGT",
        "description": "Compact default plant terminator entry derived from the nopaline synthase terminator region.",
    },
    {
        "name": "OCS Terminator Core",
        "part_type": "Terminator",
        "organism": "Arabidopsis",
        "sequence": "ATCGTTGATCGTTTGCTGCGATGTTTCTCCGATATC",
        "description": "Plant octopine synthase terminator core entry for basic cassette termination.",
    },
    {
        "name": "pET-28a Plus MCS Segment",
        "part_type": "Vector",
        "organism": "E.coli",
        "sequence": "CATATGGCTAGCGGTACCCGGGGATCCTCTAGAGTCGACCTGCAGGCATGCAAGCTT",
        "description": "Representative pET-28a(+) multiple cloning site segment for bacterial expression planning.",
    },
    {
        "name": "pUC19 MCS Segment",
        "part_type": "Vector",
        "organism": "E.coli",
        "sequence": "GAATTCGAGCTCGGTACCCGGGGATCCTCTAGAGTCGACCTGCAGGCATGCAAGCTT",
        "description": "Standard pUC19 multiple cloning site segment for routine bacterial cloning workflows.",
    },
    {
        "name": "pBR322 Origin Segment",
        "part_type": "Vector",
        "organism": "E.coli",
        "sequence": "CTGTTGACAATTAATCATCGGCTCGTATAATGTGTGGAATTGTGAGCGGATAACAAT",
        "description": "Representative pBR322-derived vector segment for bacterial backbone selection.",
    },
    {
        "name": "pYES2 MCS Segment",
        "part_type": "Vector",
        "organism": "Yeast",
        "sequence": "GGTACCCGGGGATCCACTAGTTCTAGAGCGGCCGCTGCAGGAATTCGATATCAAGCT",
        "description": "Representative yeast shuttle vector MCS segment for GAL-based expression designs.",
    },
    {
        "name": "pCAMBIA1300 MCS Segment",
        "part_type": "Vector",
        "organism": "Tobacco",
        "sequence": "TCTAGAGGATCCCCGGGTACCGAGCTCGAATTCGTCGACCTGCAGGCATGCAAGCTT",
        "description": "Representative plant binary vector MCS segment for Agrobacterium-compatible cloning plans.",
    },
    {
        "name": "pGreenII MCS Segment",
        "part_type": "Vector",
        "organism": "Arabidopsis",
        "sequence": "GGATCCGGTACCGAATTCCTGCAGCCCGGGGGATCCACTAGTCTAGAGTCGAC",
        "description": "Representative plant cloning vector MCS segment for Arabidopsis transformation workflows.",
    },
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


@contextmanager
def _get_conn() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that opens a SQLite connection, yields it, commits on
    clean exit, and always closes — even when an exception is raised.
    This prevents the database file from being left in a locked state.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _clean_sequence(raw: str) -> str:
    """Strip whitespace and digits, convert to uppercase."""
    return re.sub(r"[\s0-9]", "", raw).upper()


def _validate_sequence(seq: str) -> tuple[bool, str]:
    """Return (is_valid, error_message). Valid: non-empty, only ATCGN."""
    if not seq:
        return False, "Sequence must not be empty."
    invalid = sorted(set(seq) - _VALID_BASES)
    if invalid:
        return False, (
            f"Sequence contains invalid characters: {', '.join(invalid)}. "
            "Only A, T, C, G, and N are permitted."
        )
    return True, ""


def _compute_gc(seq: str) -> float:
    """Return GC content rounded to 2 decimal places (0–100 scale)."""
    if not seq:
        return 0.0
    gc = (seq.count("G") + seq.count("C")) / len(seq) * 100
    return round(gc, 2)


def _host_context(organism: str) -> str:
    if organism == "E.coli":
        return "细菌表达"
    if organism == "Yeast":
        return "酵母表达"
    if organism in {"Tobacco", "Arabidopsis", "Rice"}:
        return "植物表达"
    return "通用构建原型设计"


def _default_metadata_for_part(part: dict[str, str]) -> dict[str, str]:
    name = part["name"]
    part_type = part["part_type"]
    organism = part["organism"]
    host_context = _host_context(organism)

    source_type = "常用参考元件"
    if any(token in name for token in ("Fragment", "Segment", "Core")):
        source_type = "内部整理"
    elif any(token in name for token in ("Plus MCS", "Origin Segment", "Signal Peptide")):
        source_type = "系统默认元件"

    if part_type == "Promoter":
        function_summary = f"Drives transcription input for {host_context} workflows."
        common_usage = "Placed upstream of a CDS to start constitutive or inducible expression."
        key_features = "Expression-driving control element with host-aligned starter-library coverage."
        if organism == "E.coli":
            recommended_pairing = "Documented context: commonly recorded with a bacterial RBS, reporter CDS, and rrnB or T7-family terminator in starter documentation sets."
        elif organism == "Yeast":
            recommended_pairing = "Documented context: commonly recorded with a CDS fragment and ADH1 Terminator in yeast-vector documentation sets."
        else:
            recommended_pairing = "Documented context: commonly recorded with a plant CDS and NOS or OCS terminator in binary-vector documentation sets."
    elif part_type == "RBS":
        function_summary = "Supports translation initiation by recruiting the bacterial ribosome."
        common_usage = "Inserted between a bacterial promoter and CDS to tune protein expression level."
        key_features = "Simple translational tuning part for starter bacterial expression cassettes."
        recommended_pairing = "Documented context: commonly recorded between E.coli promoter references, reporter CDS fragments, and bacterial terminators in starter documentation sets."
    elif part_type == "CDS":
        function_summary = "Encodes the main protein output, reporter, marker, tag, or targeting function."
        common_usage = "Used as the translated payload within expression or screening constructs."
        key_features = "Starter payload entry for reporting, selection, tagging, or secretion-oriented designs."
        if "Tag" in name:
            recommended_pairing = "Documented context: commonly recorded with an upstream promoter and in-frame fusion CDS in local expression-vector documentation."
        elif "Signal Peptide" in name:
            recommended_pairing = "Documented context: commonly recorded with a secreted protein CDS, yeast promoter, and ADH1 Terminator in yeast secretion documentation."
        else:
            recommended_pairing = "Documented context: commonly recorded with an upstream promoter or RBS context and a downstream terminator."
    elif part_type == "Terminator":
        function_summary = "Stops transcription and helps define the end of the expression cassette."
        common_usage = "Placed downstream of a CDS to improve transcript termination and insulation."
        key_features = "Starter transcription-stop element for cleaner cassette boundaries."
        recommended_pairing = "Documented context: commonly recorded downstream of promoter-CDS assemblies within the same documented host context."
    else:
        function_summary = "Provides backbone or cloning-site context for assembling expression constructs."
        common_usage = "Used as a recipient backbone or MCS reference during cassette assembly planning."
        key_features = "Starter cloning backbone reference for routine assembly and export workflows."
        recommended_pairing = "Documented context: commonly recorded with promoter, CDS, and terminator cassette notes for the target host documentation set."

    return {
        "source_type": source_type,
        "function_summary": function_summary,
        "common_usage": common_usage,
        "key_features": key_features,
        "recommended_pairing": recommended_pairing,
        "notes": "起始库参考条目。",
    }


def _ensure_metadata_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(biological_parts)").fetchall()
    }
    for column_name, ddl in _METADATA_COLUMNS:
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE biological_parts ADD COLUMN {column_name} {ddl}")


def _enrich_seed_metadata(conn: sqlite3.Connection) -> None:
    for part in _DEFAULT_PARTS:
        metadata = _default_metadata_for_part(part)
        conn.execute(
            """
            UPDATE biological_parts
            SET
                source_type = CASE WHEN TRIM(source_type) = '' THEN ? ELSE source_type END,
                function_summary = CASE WHEN TRIM(function_summary) = '' THEN ? ELSE function_summary END,
                common_usage = CASE WHEN TRIM(common_usage) = '' THEN ? ELSE common_usage END,
                key_features = CASE WHEN TRIM(key_features) = '' THEN ? ELSE key_features END,
                recommended_pairing = CASE WHEN TRIM(recommended_pairing) = '' THEN ? ELSE recommended_pairing END,
                notes = CASE WHEN TRIM(notes) = '' THEN ? ELSE notes END
            WHERE name = ?
              AND (
                  TRIM(source_type) = ''
                  OR TRIM(function_summary) = ''
                  OR TRIM(common_usage) = ''
                  OR TRIM(key_features) = ''
                  OR TRIM(recommended_pairing) = ''
                  OR TRIM(notes) = ''
              )
            """,
            (
                metadata["source_type"],
                metadata["function_summary"],
                metadata["common_usage"],
                metadata["key_features"],
                metadata["recommended_pairing"],
                metadata["notes"],
                part["name"],
            ),
        )


def seed_builtin_parts(conn: sqlite3.Connection) -> bool:
    """Insert missing built-in parts by stable name without changing existing rows."""
    existing_names = {
        str(row[0])
        for row in conn.execute("SELECT name FROM biological_parts").fetchall()
    }
    insert_sql = """
        INSERT INTO biological_parts
            (
                name,
                part_type,
                organism,
                sequence,
                length_bp,
                gc_content,
                description,
                source_type,
                function_summary,
                common_usage,
                key_features,
                recommended_pairing,
                notes,
                created_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    created_at = BUILTIN_SEED_TIMESTAMP
    payload = []
    for part in _DEFAULT_PARTS:
        if part["name"] in existing_names:
            continue
        metadata = _default_metadata_for_part(part)
        payload.append(
            (
                part["name"],
                part["part_type"],
                part["organism"],
                part["sequence"],
                len(part["sequence"]),
                _compute_gc(part["sequence"]),
                part["description"],
                metadata["source_type"],
                metadata["function_summary"],
                metadata["common_usage"],
                metadata["key_features"],
                metadata["recommended_pairing"],
                metadata["notes"],
                created_at,
            )
        )
    if payload:
        conn.executemany(insert_sql, payload)
    return bool(payload)


def _seed_default_parts_if_empty(conn: sqlite3.Connection) -> None:
    """Compatibility wrapper for the versioned built-in seed."""
    seed_builtin_parts(conn)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_db(*, seed_defaults: bool = True) -> None:
    """
    Ensure the `biological_parts` table exists in the unified database.
    Safe to call multiple times (CREATE TABLE IF NOT EXISTS).
    """
    ddl = """
        CREATE TABLE IF NOT EXISTS biological_parts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            part_type   TEXT    NOT NULL,
            organism    TEXT    NOT NULL DEFAULT '',
            sequence    TEXT    NOT NULL,
            length_bp   INTEGER NOT NULL,
            gc_content  REAL    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            source_type TEXT    NOT NULL DEFAULT '',
            function_summary TEXT NOT NULL DEFAULT '',
            common_usage TEXT NOT NULL DEFAULT '',
            key_features TEXT NOT NULL DEFAULT '',
            recommended_pairing TEXT NOT NULL DEFAULT '',
            notes       TEXT    NOT NULL DEFAULT '',
            created_at  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_bp_type
            ON biological_parts (part_type);
        CREATE INDEX IF NOT EXISTS idx_bp_name
            ON biological_parts (name);
        CREATE INDEX IF NOT EXISTS idx_bp_organism
            ON biological_parts (organism);
        CREATE INDEX IF NOT EXISTS idx_bp_type_organism
            ON biological_parts (part_type, organism);
    """
    with _get_conn() as conn:
        conn.executescript(ddl)
        _ensure_metadata_columns(conn)
        if seed_defaults:
            _seed_default_parts_if_empty(conn)
            _enrich_seed_metadata(conn)


def add_part(data: dict) -> tuple[bool, str]:
    """
    Validate, clean, and insert a new biological part.

    Parameters
    ----------
    data : dict with keys:
        name        (str)  — unique human-readable identifier
        part_type   (str)  — one of ALLOWED_TYPES
        sequence    (str)  — raw DNA (will be cleaned automatically)
        description (str)  — optional functional description

    Returns
    -------
    (True, part_name)   on success
    (False, error_msg)  on validation or DB failure
    """
    name = str(data.get("name", "")).strip()
    part_type = str(data.get("part_type", "")).strip()
    raw_seq = str(data.get("sequence", ""))
    description = str(data.get("description", "")).strip()
    organism = str(data.get("organism", "")).strip()

    # ---- field-level validation ----------------------------------------
    if not name:
        return False, "Part Name is required."
    if part_type not in ALLOWED_TYPES:
        return False, (
            f"Invalid part type '{part_type}'. "
            f"Allowed: {', '.join(ALLOWED_TYPES)}."
        )

    seq_clean = _clean_sequence(raw_seq)
    ok, err = _validate_sequence(seq_clean)
    if not ok:
        return False, err

    length_bp = len(seq_clean)
    gc_content = _compute_gc(seq_clean)
    created_at = datetime.now().isoformat(sep=" ", timespec="seconds")

    # ---- persist -----------------------------------------------------------
    sql = """
        INSERT INTO biological_parts
            (
                name,
                part_type,
                organism,
                sequence,
                length_bp,
                gc_content,
                description,
                source_type,
                function_summary,
                common_usage,
                key_features,
                recommended_pairing,
                notes,
                created_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    metadata = {
        "source_type": "用户导入",
        "function_summary": description,
        "common_usage": "",
        "key_features": "",
        "recommended_pairing": "",
        "notes": "",
    }
    try:
        with _get_conn() as conn:
            conn.execute(
                sql,
                (
                    name,
                    part_type,
                    organism,
                    seq_clean,
                    length_bp,
                    gc_content,
                    description,
                    metadata["source_type"],
                    metadata["function_summary"],
                    metadata["common_usage"],
                    metadata["key_features"],
                    metadata["recommended_pairing"],
                    metadata["notes"],
                    created_at,
                ),
            )
        return True, name
    except sqlite3.IntegrityError:
        return False, f"A part named '{name}' already exists in the registry."
    except sqlite3.Error as exc:
        return False, f"Database error: {exc}"


def get_all_parts(filter_type: Optional[str] = None) -> pd.DataFrame:
    """
    Read all biological_parts rows and return a display-ready DataFrame.

    Parameters
    ----------
    filter_type : optional part_type string to restrict results.

    Returns
    -------
    pd.DataFrame with columns:
        ID | Name | Type | Length (bp) | GC Content (%) | Description |
        Sequence Preview | Created At
    Returns an empty DataFrame (with correct columns) when the table is
    empty or the database does not exist yet.
    """
    _EMPTY_COLS = [
        "ID", "Name", "Type", "Organism", "Sequence", "Length (bp)",
        "GC Content (%)", "Description", "Source Type", "Function Summary",
        "Common Usage", "Key Features", "Recommended Pairing", "Notes",
        "Sequence Preview", "Created At",
    ]

    try:
        params: list = []
        where = ""
        if filter_type and filter_type in ALLOWED_TYPES:
            where = "WHERE part_type = ?"
            params.append(filter_type)

        sql = f"""
            SELECT
                id,
                name,
                part_type,
                organism,
                length_bp,
                gc_content,
                description,
                source_type,
                function_summary,
                common_usage,
                key_features,
                recommended_pairing,
                notes,
                sequence,
                created_at
            FROM biological_parts
            {where}
            ORDER BY created_at DESC
        """
        with _get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        if not rows:
            return pd.DataFrame(columns=_EMPTY_COLS)

        records = []
        for r in rows:
            seq = r["sequence"]
            preview = (seq[:45] + "...") if len(seq) > 45 else seq
            records.append(
                {
                    "ID": r["id"],
                    "Name": r["name"],
                    "Type": r["part_type"],
                    "Organism": r["organism"],
                    "Sequence": seq,
                    "Length (bp)": r["length_bp"],
                    "GC Content (%)": r["gc_content"],
                    "Description": r["description"],
                    "Source Type": r["source_type"],
                    "Function Summary": r["function_summary"],
                    "Common Usage": r["common_usage"],
                    "Key Features": r["key_features"],
                    "Recommended Pairing": r["recommended_pairing"],
                    "Notes": r["notes"],
                    "Sequence Preview": preview,
                    "Created At": r["created_at"],
                }
            )
        return pd.DataFrame(records)

    except sqlite3.Error:
        return pd.DataFrame(columns=_EMPTY_COLS)


def delete_part(part_id: int) -> tuple[bool, str]:
    """
    Delete a part by its integer primary key.

    Returns
    -------
    (True, 'Deleted')     on success
    (False, error_msg)    if not found or DB error
    """
    try:
        with _get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM biological_parts WHERE id = ?", (part_id,)
            )
        if cursor.rowcount == 0:
            return False, f"No part found with ID {part_id}."
        return True, "Deleted"
    except sqlite3.Error as exc:
        return False, f"Database error: {exc}"


def update_part(part_id: int, data: dict) -> tuple[bool, str]:
    """
    Update editable fields of an existing biological part.

    Parameters
    ----------
    part_id : int  — primary key of the row to update
    data    : dict — same shape as add_part data:
        name, part_type, organism, sequence, description,
        source_type, function_summary, common_usage,
        key_features, recommended_pairing, notes

    Returns
    -------
    (True, part_name)   on success
    (False, error_msg)  on validation or DB failure
    """
    name = str(data.get("name", "")).strip()
    part_type = str(data.get("part_type", "")).strip()
    raw_seq = str(data.get("sequence", ""))
    description = str(data.get("description", "")).strip()
    organism = str(data.get("organism", "")).strip()
    source_type = str(data.get("source_type", "")).strip()
    function_summary = str(data.get("function_summary", "")).strip()
    common_usage = str(data.get("common_usage", "")).strip()
    key_features = str(data.get("key_features", "")).strip()
    recommended_pairing = str(data.get("recommended_pairing", "")).strip()
    notes = str(data.get("notes", "")).strip()

    if not name:
        return False, "Part Name is required."
    if part_type not in ALLOWED_TYPES:
        return False, (
            f"Invalid part type '{part_type}'. "
            f"Allowed: {', '.join(ALLOWED_TYPES)}."
        )

    seq_clean = _clean_sequence(raw_seq)
    ok, err = _validate_sequence(seq_clean)
    if not ok:
        return False, err

    length_bp = len(seq_clean)
    gc_content = _compute_gc(seq_clean)

    sql = """
        UPDATE biological_parts
        SET
            name               = ?,
            part_type          = ?,
            organism           = ?,
            sequence           = ?,
            length_bp          = ?,
            gc_content         = ?,
            description        = ?,
            source_type        = ?,
            function_summary   = ?,
            common_usage       = ?,
            key_features       = ?,
            recommended_pairing = ?,
            notes              = ?
        WHERE id = ?
    """
    try:
        with _get_conn() as conn:
            cursor = conn.execute(
                sql,
                (
                    name,
                    part_type,
                    organism,
                    seq_clean,
                    length_bp,
                    gc_content,
                    description,
                    source_type,
                    function_summary,
                    common_usage,
                    key_features,
                    recommended_pairing,
                    notes,
                    part_id,
                ),
            )
        if cursor.rowcount == 0:
            return False, f"No part found with ID {part_id}."
        return True, name
    except sqlite3.IntegrityError:
        return False, f"A part named '{name}' already exists in the registry."
    except sqlite3.Error as exc:
        return False, f"Database error: {exc}"


def get_existing_names() -> frozenset[str]:
    """
    Return a frozenset of all part names currently in the registry.
    Used by the batch-import preview to flag duplicates before writing.
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT name FROM biological_parts"
            ).fetchall()
        return frozenset(r[0] for r in rows)
    except sqlite3.Error:
        return frozenset()


def add_parts_batch(
    records: list[dict],
    overwrite: bool = False,
) -> tuple[int, int, list[str]]:
    """
    Transactional bulk insert for a list of part dicts.

    Each dict must have keys: name, part_type, sequence, description.
    Sequences are cleaned and validated before any write is attempted.
    The entire batch runs inside a single SQLite transaction — if any
    unexpected DB error occurs the transaction is rolled back and no
    rows are written.

    Parameters
    ----------
    records  : list of dicts (name, part_type, sequence, description)
    overwrite: if True, existing rows with the same name are replaced
               (DELETE + INSERT); if False they are skipped.

    Returns
    -------
    (inserted, skipped, errors)
        inserted — number of rows successfully written
        skipped  — number of rows skipped because name already existed
        errors   — list of human-readable error strings for bad records
    """
    inserted = 0
    skipped = 0
    errors: list[str] = []
    created_at = datetime.now().isoformat(sep=" ", timespec="seconds")

    insert_sql = """
        INSERT INTO biological_parts
            (
                name,
                part_type,
                organism,
                sequence,
                length_bp,
                gc_content,
                description,
                source_type,
                function_summary,
                common_usage,
                key_features,
                recommended_pairing,
                notes,
                created_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    delete_sql = "DELETE FROM biological_parts WHERE name = ?"

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN")
        existing = frozenset(
            r[0] for r in conn.execute("SELECT name FROM biological_parts").fetchall()
        )

        for idx, rec in enumerate(records, start=1):
            name = str(rec.get("name", "")).strip()
            part_type = str(rec.get("part_type", "")).strip()
            raw_seq = str(rec.get("sequence", ""))
            description = str(rec.get("description", "")).strip()

            organism = str(rec.get("organism", "")).strip()
            source_type = str(rec.get("source_type", "用户导入")).strip() or "用户导入"
            function_summary = str(rec.get("function_summary", description)).strip()
            common_usage = str(rec.get("common_usage", "")).strip()
            key_features = str(rec.get("key_features", "")).strip()
            recommended_pairing = str(rec.get("recommended_pairing", "")).strip()
            notes = str(rec.get("notes", "")).strip()

            if not name:
                errors.append(f"Record {idx}: name is empty — skipped.")
                skipped += 1
                continue
            if part_type not in ALLOWED_TYPES:
                errors.append(
                    f"Record {idx} '{name}': invalid part_type '{part_type}' — skipped."
                )
                skipped += 1
                continue

            seq_clean = _clean_sequence(raw_seq)
            ok, err = _validate_sequence(seq_clean)
            if not ok:
                errors.append(f"Record {idx} '{name}': {err}")
                skipped += 1
                continue

            if name in existing:
                if not overwrite:
                    skipped += 1
                    continue
                # overwrite: delete old row first
                conn.execute(delete_sql, (name,))

            conn.execute(
                insert_sql,
                (
                    name,
                    part_type,
                    organism,
                    seq_clean,
                    len(seq_clean),
                    _compute_gc(seq_clean),
                    description,
                    source_type,
                    function_summary,
                    common_usage,
                    key_features,
                    recommended_pairing,
                    notes,
                    created_at,
                ),
            )
            inserted += 1

        conn.commit()
    except Exception as exc:
        conn.rollback()
        errors.append(f"Transaction rolled back due to unexpected error: {exc}")
    finally:
        conn.close()

    return inserted, skipped, errors


def get_part_types() -> list[str]:
    """
    Return a sorted list of distinct part_type values currently in the DB.
    Falls back to ALLOWED_TYPES if the table is empty or missing.
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT part_type FROM biological_parts ORDER BY part_type"
            ).fetchall()
        types = [r[0] for r in rows]
        return types if types else list(ALLOWED_TYPES)
    except sqlite3.Error:
        return list(ALLOWED_TYPES)


def get_parts_by_organism(
    organism: str,
    part_type: Optional[str] = None,
) -> list[dict]:
    """Return parts matching *organism* (case-insensitive prefix match).

    Also returns parts where organism is 'Universal' or empty string,
    since those apply to any host.

    Parameters
    ----------
    organism  : str  — e.g. 'Rice', 'E.coli', 'Arabidopsis'
    part_type : str  — optional filter, e.g. 'Promoter'

    Returns
    -------
    list of dicts with keys: id, name, part_type, organism,
    sequence, length_bp, gc_content, description
    """
    try:
        conditions = [
            "(LOWER(organism) = LOWER(?) OR organism = '' OR LOWER(organism) = 'universal')"
        ]
        params: list = [organism]
        if part_type and part_type in ALLOWED_TYPES:
            conditions.append("part_type = ?")
            params.append(part_type)
        where = "WHERE " + " AND ".join(conditions)
        sql = f"""
            SELECT id, name, part_type, organism,
                   sequence, length_bp, gc_content, description,
                   source_type, function_summary, common_usage,
                   key_features, recommended_pairing, notes
            FROM biological_parts
            {where}
            ORDER BY name
        """
        with _get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []

# ---------------------------------------------------------------------------
# Startup-driven initialization only (no import-time side effects)
# ---------------------------------------------------------------------------
