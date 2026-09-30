from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QA_DIR = ROOT / "docs" / "qa"

R10_R22_NOTES = [
    "V2_7_R10_TRACEABILITY_BOUNDARY_AUDIT.md",
    "V2_7_R11_PROJECT_OUTPUTS_DETAIL_TABLE_STATE.md",
    "V2_7_R12_PROJECT_OUTPUTS_BOUNDARY_GUARD.md",
    "V2_7_R13_PROJECT_OUTPUTS_DETAIL_TABLE_WIDTH_GUARD.md",
    "V2_7_R14_PROJECT_OUTPUTS_NEXT_CUT_AUDIT.md",
    "V2_7_R15_PROJECT_OUTPUTS_SECTION_EXTRACTION_FEASIBILITY_AUDIT.md",
    "V2_7_R16_PROJECT_OUTPUTS_SECTION_SHELL_EXTRACTION.md",
    "V2_7_R17_PROJECT_OUTPUTS_CALLBACK_MIGRATION_AUDIT.md",
    "V2_7_R18_PROJECT_REPORT_DOWNLOAD_SECTION_EXTRACTION.md",
    "V2_7_R19_IMPORT_PREVIEW_CALLBACK_BOUNDARY_GUARD.md",
    "V2_7_R20_R10_R19_CHECKPOINT_FULL_REGRESSION.md",
    "V2_7_R21_R10_R20_HANDOFF_AND_PROTECTED_AREA_AUDIT.md",
    "V2_7_R22_PROJECT_OUTPUTS_CHECKPOINT_PROTECTED_AREA_GUARD.md",
]


def _read(note_name: str) -> str:
    return (QA_DIR / note_name).read_text(encoding="utf-8")


def test_r10_r22_qa_notes_exist_for_checkpoint_handoff() -> None:
    missing = [note_name for note_name in R10_R22_NOTES if not (QA_DIR / note_name).exists()]

    assert missing == []


def test_r10_r22_qa_notes_have_no_pending_closeout_placeholders() -> None:
    forbidden_placeholders = [
        "To run before closeout",
        "Post-note checks to run",
        "checks to run",
        "TBD",
        "TODO",
    ]
    hits = [
        f"{note_name}: {placeholder}"
        for note_name in R10_R22_NOTES
        for placeholder in forbidden_placeholders
        if placeholder in _read(note_name)
    ]

    assert hits == []


def test_r10_r22_qa_checkpoint_records_required_verification_evidence() -> None:
    r20 = _read("V2_7_R20_R10_R19_CHECKPOINT_FULL_REGRESSION.md")
    r21 = _read("V2_7_R21_R10_R20_HANDOFF_AND_PROTECTED_AREA_AUDIT.md")
    r22 = _read("V2_7_R22_PROJECT_OUTPUTS_CHECKPOINT_PROTECTED_AREA_GUARD.md")

    assert "2598 passed, 8 skipped, 2 warnings" in r20
    assert "No commit or tag was created" in r20
    assert "No staging, commit, or tag was performed" in r21
    assert "protected runtime areas" in r22
    assert "19 passed in 0.67s" in r22
    assert "No forbidden user-visible phrase was found" in r22


def test_r10_r22_qa_notes_do_not_introduce_copy_denylist_phrases() -> None:
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
        "wet" + "-lab ready",
        "proven" + " construct",
        "validated" + " pathway",
    ]
    hits = [
        f"{note_name}: {phrase}"
        for note_name in R10_R22_NOTES
        for phrase in forbidden
        if phrase in _read(note_name).lower()
    ]

    assert hits == []
