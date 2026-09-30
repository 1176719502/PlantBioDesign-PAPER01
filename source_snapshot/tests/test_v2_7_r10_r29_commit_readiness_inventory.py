from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "qa" / "V2_7_R30_R10_R29_COMMIT_READINESS_INVENTORY.md"

INTENDED_PRODUCT_FILES = [
    "services/pathway_outputs_workflow_view_model.py",
    "views/PathwayWorkspace.py",
    "views/pathway_workspace_sections/__init__.py",
    "views/pathway_workspace_sections/project_outputs_section.py",
    "views/pathway_workspace_sections/project_report_download_section.py",
]

INTENDED_GUARD_TESTS = [
    "tests/test_copy_safety_boundaries.py",
    "tests/test_pathway_outputs_workflow_view_model.py",
    "tests/test_pathway_workspace_project_outputs_boundary.py",
    "tests/test_pathway_workspace_project_outputs_section_extraction.py",
    "tests/test_pathway_workspace_project_report_download_section_extraction.py",
    "tests/test_pathway_workspace_import_preview_callback_boundary.py",
    "tests/test_v2_7_project_outputs_checkpoint_protected_area_guard.py",
    "tests/test_v2_7_r10_r22_qa_checkpoint_integrity.py",
    "tests/test_v2_7_r10_r23_qa_note_structure_guard.py",
    "tests/test_v2_7_r10_r24_checkpoint_manifest.py",
    "tests/test_v2_7_r10_r25_checkpoint_copy_boundary.py",
    "tests/test_v2_7_r10_r26_checkpoint_manifest_refresh.py",
    "tests/test_v2_7_r10_r27_0900_checkpoint_handoff.py",
    "tests/test_v2_7_r10_r28_qa_note_structure_refresh.py",
    "tests/test_v2_7_r10_r29_commit_readiness_inventory.py",
]

INTENDED_QA_NOTES = [
    f"docs/qa/V2_7_R{number}"
    for number in range(10, 31)
]

PROTECTED_AREA_MARKERS = [
    "Database schema and migration files are out of scope.",
    "Import/export package schema files are out of scope.",
    "services/project_import_service.py",
    "services/project_export_package_service.py",
    "Expression Wizard core algorithms are out of scope.",
    "primer3",
    ".venv",
    "No staging, commit, or tag was performed",
]


def _inventory_source() -> str:
    return INVENTORY.read_text(encoding="utf-8")


def test_r30_inventory_exists_and_lists_intended_product_files() -> None:
    source = _inventory_source()
    missing = [path for path in INTENDED_PRODUCT_FILES if path not in source]

    assert missing == []


def test_r30_inventory_lists_checkpoint_guard_tests() -> None:
    source = _inventory_source()
    missing = [path for path in INTENDED_GUARD_TESTS if path not in source]

    assert missing == []


def test_r30_inventory_lists_checkpoint_qa_note_range() -> None:
    source = _inventory_source()
    missing = [prefix for prefix in INTENDED_QA_NOTES if prefix not in source]

    assert missing == []


def test_r30_inventory_records_protected_area_exclusions_and_no_commit_state() -> None:
    source = _inventory_source()
    missing = [marker for marker in PROTECTED_AREA_MARKERS if marker not in source]

    assert missing == []


def test_r30_inventory_stays_documentation_only_and_copy_safe() -> None:
    source = _inventory_source().lower()

    assert "documentation-only" in source
    assert "inventory guard only" in source
    forbidden = [
        "successful" + " import",
        "project" + " imported",
        "ready" + " for execution",
        "experiment" + "-ready",
        "production" + "-ready",
        "validated" + " construct",
        "optimized" + " pathway",
        "yield" + " prediction",
        "lab" + "-ready",
        "wet-lab" + " ready",
        "proven" + " construct",
        "validated" + " pathway",
    ]
    assert [phrase for phrase in forbidden if phrase in source] == []
