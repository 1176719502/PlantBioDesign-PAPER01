from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN_DOC = ROOT / "docs" / "import_execution_ui_gating_design.md"


REQUIRED_GATING_TERMS = [
    "valid package",
    "dry-run plan",
    "confirmation checkbox",
    "Create New Documentation Project",
    "enable_database_write=True",
    "default False",
    "no overwrite",
    "no merge",
    "documentation-only",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not provide wet-lab protocols",
    "computational previews",
    "review records only",
    "limited rollback",
    "audit summary",
    "service, not repository write APIs",
    "invalid package never shows execution button",
    "no raw payload_json restoration",
]


def test_import_execution_ui_gating_design_doc_exists() -> None:
    assert DESIGN_DOC.exists(), "V1.8.4 import execution UI gating design should exist"


def test_import_execution_ui_gating_design_covers_required_terms() -> None:
    content = DESIGN_DOC.read_text(encoding="utf-8")
    normalized = content.lower()

    missing_terms = [
        term for term in REQUIRED_GATING_TERMS if term.lower() not in normalized
    ]

    assert not missing_terms, (
        "Import execution UI gating design is missing required terms: "
        + ", ".join(missing_terms)
    )


def test_import_execution_ui_gating_design_preserves_preview_boundary() -> None:
    content = DESIGN_DOC.read_text(encoding="utf-8").lower()

    assert "read-only preview" in content
    assert "validation report" in content
    assert "dry-run import plan" in content
    assert "no database writes" in content
    assert "no project creation" in content
    assert "separate gated block" in content


def test_import_execution_ui_gating_design_rejects_unsafe_button_language() -> None:
    content = DESIGN_DOC.read_text(encoding="utf-8")

    for unsafe_label in [
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Restore Project",
        "Merge Project",
        "Overwrite Project",
    ]:
        assert unsafe_label in content

    assert "Do not use" in content
    assert "Recommended primary button text: `Create New Documentation Project`" in content
