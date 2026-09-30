"""Import smoke check for the BioDesign Studio runtime baseline.

Purpose
-------
Verify that the local environment contains the packages and modules required for:
- Streamlit app startup
- SQLite-backed data initialization
- Primer design support
- Export/report support
- Minimal API/async primer support

This script does not start servers and does not make network requests.

Run with:
    python scripts/test_imports.py
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEPENDENCY_IMPORTS = [
    ("streamlit", "Streamlit app runtime"),
    ("pandas", "Tabular data processing"),
    ("openpyxl", "Excel export"),
    ("reportlab", "Report generation"),
    ("Bio", "Biopython sequence utilities"),
    ("primer3", "Primer3 Python binding"),
    ("fastapi", "Primer API runtime"),
    ("requests", "HTTP client for primer API"),
    ("rq", "Async queue support"),
    ("redis", "Redis client for async queue"),
]

PROJECT_IMPORTS = [
    ("core.config", "Configuration constants"),
    ("core.database", "Biological parts database layer"),
    ("core.unified_database", "Unified SQLite startup layer"),
    ("core.design_session", "Wizard session model"),
    ("services.sequence_service", "Sequence service"),
    ("services.primer_service", "Primer scoring service"),
    ("services.primer_api_client", "Primer API client"),
    ("services.primer_queue", "Primer async queue integration"),
    ("services.report_service", "Report service"),
    ("components.export_manager", "GenBank export manager"),
    ("views.wizard_flow", "Wizard router"),
]


def _try_import(module_name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(module_name)
        return True, "OK"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    print("=" * 72)
    print("BioDesign Studio import smoke check")
    print("=" * 72)
    print(f"Python executable : {sys.executable}")
    print(f"Python version    : {sys.version.split()[0]}")
    print(f"Project root      : {ROOT}")
    print(f"Requirements file : {ROOT / 'requirements.txt'}")
    print()

    failures: list[str] = []

    print("[1/3] Checking third-party runtime dependencies")
    for module_name, purpose in DEPENDENCY_IMPORTS:
        ok, detail = _try_import(module_name)
        status = "OK  " if ok else "FAIL"
        print(f"  {status}  {module_name:<12} {purpose}")
        if not ok:
            failures.append(f"Dependency import failed: {module_name} -> {detail}")
    print()

    print("[2/3] Checking project modules used by startup and smoke path")
    for module_name, purpose in PROJECT_IMPORTS:
        ok, detail = _try_import(module_name)
        status = "OK  " if ok else "FAIL"
        print(f"  {status}  {module_name:<28} {purpose}")
        if not ok:
            failures.append(f"Project import failed: {module_name} -> {detail}")
    print()

    print("[3/3] Checking key files and directories")
    expected_paths = [
        ROOT / "app.py",
        ROOT / "requirements.txt",
        ROOT / ".streamlit" / "config.toml",
        ROOT / "data",
    ]
    for path in expected_paths:
        exists = path.exists()
        status = "OK  " if exists else "FAIL"
        print(f"  {status}  {path}")
        if not exists:
            failures.append(f"Missing required path: {path}")
    print()

    if failures:
        print("Import smoke check failed:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("All import smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
