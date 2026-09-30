from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "qa" / "V2_7_R25_R10_R24_CHECKPOINT_MANIFEST.md"

REQUIRED_PRODUCT_FILES = [
    "services/pathway_outputs_workflow_view_model.py",
    "views/PathwayWorkspace.py",
    "views/pathway_workspace_sections/__init__.py",
    "views/pathway_workspace_sections/project_outputs_section.py",
    "views/pathway_workspace_sections/project_report_download_section.py",
]

REQUIRED_TEST_FILES = [
    "tests/test_pathway_workspace_project_outputs_boundary.py",
    "tests/test_pathway_workspace_project_outputs_section_extraction.py",
    "tests/test_pathway_workspace_project_report_download_section_extraction.py",
    "tests/test_pathway_workspace_import_preview_callback_boundary.py",
    "tests/test_v2_7_project_outputs_checkpoint_protected_area_guard.py",
    "tests/test_v2_7_r10_r22_qa_checkpoint_integrity.py",
    "tests/test_v2_7_r10_r23_qa_note_structure_guard.py",
    "tests/test_v2_7_r10_r24_checkpoint_manifest.py",
]

REQUIRED_QA_NOTES = [
    "docs/qa/V2_7_R10_TRACEABILITY_BOUNDARY_AUDIT.md",
    "docs/qa/V2_7_R16_PROJECT_OUTPUTS_SECTION_SHELL_EXTRACTION.md",
    "docs/qa/V2_7_R20_R10_R19_CHECKPOINT_FULL_REGRESSION.md",
    "docs/qa/V2_7_R21_R10_R20_HANDOFF_AND_PROTECTED_AREA_AUDIT.md",
    "docs/qa/V2_7_R22_PROJECT_OUTPUTS_CHECKPOINT_PROTECTED_AREA_GUARD.md",
    "docs/qa/V2_7_R23_R10_R22_QA_CHECKPOINT_INTEGRITY_GUARD.md",
    "docs/qa/V2_7_R24_R10_R23_QA_NOTE_STRUCTURE_GUARD.md",
    "docs/qa/V2_7_R25_R10_R24_CHECKPOINT_MANIFEST.md",
]


def _manifest_source() -> str:
    return MANIFEST.read_text(encoding="utf-8")


def test_checkpoint_manifest_exists_and_lists_required_files() -> None:
    source = _manifest_source()
    missing = [
        path
        for path in REQUIRED_PRODUCT_FILES + REQUIRED_TEST_FILES + REQUIRED_QA_NOTES
        if path not in source
    ]

    assert missing == []


def test_checkpoint_manifest_records_latest_verification_and_no_commit_state() -> None:
    source = _manifest_source()

    for expected in [
        "2598 passed, 8 skipped, 2 warnings",
        "19 passed in 0.67s",
        "4 passed in 0.23s",
        "7 passed in 0.29s",
        "No staging, commit, or tag was performed",
        "Commit/tag remains blocked by policy until the user explicitly authorizes it.",
    ]:
        assert expected in source


def test_checkpoint_manifest_preserves_documentation_only_boundary() -> None:
    source = _manifest_source().lower()

    assert "local documentation-only workspace" in source
    assert "review and traceability area" in source
    forbidden = [
        "successful" + " import",
        "project" + " imported",
        "ready" + " for execution",
        "experiment" + "-ready",
        "production" + "-ready",
        "validated" + " construct",
        "optimized" + " pathway",
        "yield" + " prediction",
    ]
    assert [phrase for phrase in forbidden if phrase in source] == []
