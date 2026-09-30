from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN_DOC = ROOT / "docs" / "project_import_package_design.md"


REQUIRED_IMPORT_DESIGN_TERMS = [
    "documentation-only",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not provide wet-lab protocols",
    "package_version",
    "manifest.json",
    "README_BOUNDARY.txt",
    "no overwrite",
    "import as new project only",
    "path traversal",
    "executable files",
    "malformed JSON",
    "project_id remapping",
    "linked tool artifact id remapping",
    "computational previews",
    "review records only",
]


def test_project_import_package_design_doc_exists() -> None:
    assert DESIGN_DOC.exists(), "V1.6 import design spec should exist"


def test_project_import_package_design_covers_required_terms() -> None:
    content = DESIGN_DOC.read_text(encoding="utf-8")
    normalized = content.lower()

    missing_terms = [
        term for term in REQUIRED_IMPORT_DESIGN_TERMS if term.lower() not in normalized
    ]

    assert not missing_terms, (
        "Import package design spec is missing required safety/design terms: "
        + ", ".join(missing_terms)
    )


def test_project_import_package_design_is_design_only() -> None:
    content = DESIGN_DOC.read_text(encoding="utf-8").lower()

    assert "does not implement import behavior" in content
    assert "no database schema migration" in content
    assert "no changes to the export package structure" in content
