"""Minimal functional smoke test for BioDesign Studio.

Goal
----
Validate the reproducible local runtime path without touching business UI logic.
This smoke test stays offline and focuses on:
- database startup initialization
- core service availability
- report/export primitives
- FastAPI app import

Run with:
    python scripts/functional_test.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


RESULTS: list[tuple[str, str, str]] = []


def record(name: str, fn) -> None:
    try:
        message = fn()
        RESULTS.append(("PASS", name, str(message or "OK")))
    except Exception as exc:
        RESULTS.append(("FAIL", name, f"{type(exc).__name__}: {exc}"))


from core.config import DB_PATH
from core.design_session import DesignSession
from core.unified_database import initialize_database_on_startup
from services.report_service import generate_report_content
from components.export_manager import generate_genbank_string
from services.sequence_service import clean, gc_content, get_tm
from scripts.dev.api_primer import app as primer_api_app


def t_database_startup() -> str:
    initialize_database_on_startup()
    if not os.path.exists(DB_PATH):
        raise AssertionError(f"Database file was not created: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    required = {"promoters", "genes", "terminators", "tags", "project_history", "sequences"}
    missing = required.difference(tables)
    if missing:
        raise AssertionError(f"Missing tables: {sorted(missing)}")
    return f"database ready at {DB_PATH}"


def t_sequence_service() -> str:
    seq, warnings = clean("atg gcc taa")
    if seq != "ATGGCCTAA":
        raise AssertionError(f"Unexpected cleaned sequence: {seq}")
    gc = gc_content(seq)
    tm = get_tm("ATGGTGAGCAAGGGCGAGGAG")
    if gc <= 0:
        raise AssertionError("GC calculation failed")
    if tm <= 0:
        raise AssertionError("Tm calculation failed")
    return f"clean={seq}, warnings={len(warnings)}, gc={gc:.1f}, tm={tm:.1f}"


def t_report_generation() -> str:
    ds = DesignSession(
        step=6,
        gene_name="SmokeGene",
        original_seq="ATG" + "GCC" * 20 + "TAA",
        optimized_seq="ATG" + "GCC" * 20 + "TAA",
        host="E.coli BL21(DE3)",
        tag="No tag",
        cloning_method="Gibson Assembly",
        frame={
            "success": True,
            "final_sequence": "ATG" + "GCC" * 20 + "TAA",
            "total_length": 66,
            "gc_content": 63.6,
            "vector_suggestion": "pET-28a",
            "parts": [
                {"name": "CDS", "type": "CDS", "seq": "ATG" + "GCC" * 20 + "TAA"},
            ],
        },
        primers=[],
        validation_results=[],
    )
    report = generate_report_content(ds)
    required_keys = {"meta", "sequence", "elements", "primers", "validation_results", "codon_report", "generated_at"}
    missing = required_keys.difference(report.keys())
    if missing:
        raise AssertionError(f"Missing report keys: {sorted(missing)}")
    return f"report keys={sorted(required_keys)}"


def t_genbank_export() -> str:
    gb = generate_genbank_string(
        sequence="ATGCATGC",
        features=[{"name": "Demo CDS", "type": "CDS", "start": 1, "end": 8}],
        project_name="Smoke Construct",
    )
    if "LOCUS" not in gb or "Demo CDS" not in gb:
        raise AssertionError("GenBank export content is incomplete")
    return "GenBank export OK"


def t_fastapi_import() -> str:
    routes = {route.path for route in primer_api_app.routes}
    expected = {"/health", "/primers/design", "/primers/design/tasks", "/primers/design/tasks/{task_id}"}
    missing = expected.difference(routes)
    if missing:
        raise AssertionError(f"Missing API routes: {sorted(missing)}")
    return f"routes={sorted(expected)}"


def run_smoke_tests() -> int:
    RESULTS.clear()
    record("Database startup initialization", t_database_startup)
    record("Sequence service primitives", t_sequence_service)
    record("Report generation baseline", t_report_generation)
    record("GenBank export baseline", t_genbank_export)
    record("Primer API import baseline", t_fastapi_import)

    print("=" * 72)
    print("BioDesign Studio minimal functional smoke")
    print("=" * 72)
    passed = sum(1 for status, _, _ in RESULTS if status == "PASS")
    for status, name, message in RESULTS:
        print(f"[{status}] {name}")
        print(f"       {message}")
    print("=" * 72)
    print(f"Result: {passed}/{len(RESULTS)} passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(run_smoke_tests())
