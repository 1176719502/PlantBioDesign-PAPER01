from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QA_DIR = ROOT / "docs" / "qa"

R10_R28_NOTES = [
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
    "V2_7_R23_R10_R22_QA_CHECKPOINT_INTEGRITY_GUARD.md",
    "V2_7_R24_R10_R23_QA_NOTE_STRUCTURE_GUARD.md",
    "V2_7_R25_R10_R24_CHECKPOINT_MANIFEST.md",
    "V2_7_R26_R10_R25_CHECKPOINT_COPY_BOUNDARY_GUARD.md",
    "V2_7_R27_R10_R26_CHECKPOINT_MANIFEST_REFRESH.md",
    "V2_7_R28_0900_CHECKPOINT_HANDOFF_GUARD.md",
]

REQUIRED_HEADING_GROUPS = {
    "why": ["## Why this batch exists"],
    "scope_or_changes": [
        "## What changed",
        "## Audit scope",
        "## Checkpoint scope",
        "## Current checkpoint state",
        "## Current checkpoint map",
    ],
    "non_goals": [
        "## What did not change",
        "## What should not change",
        "## Protected-area audit",
        "## Stop conditions for the checkpoint",
    ],
    "boundary": ["## Product-boundary notes", "## Boundary audit"],
    "checks": [
        "## Checks",
        "## Checks and tests",
        "## Current verification evidence",
        "## Verification evidence",
        "## Verification evidence to carry forward",
    ],
}


def _read(note_name: str) -> str:
    return (QA_DIR / note_name).read_text(encoding="utf-8")


def _has_any(source: str, headings: list[str]) -> bool:
    lowered = source.lower()
    return any(heading.lower() in lowered for heading in headings)


def test_r10_r28_qa_notes_exist_and_have_required_review_structure() -> None:
    missing: list[str] = []

    for note_name in R10_R28_NOTES:
        path = QA_DIR / note_name
        if not path.exists():
            missing.append(f"{note_name}: file")
            continue

        source = path.read_text(encoding="utf-8")
        for group_name, headings in REQUIRED_HEADING_GROUPS.items():
            if not _has_any(source, headings):
                missing.append(f"{note_name}: {group_name}")

    assert missing == []


def test_r10_r28_qa_notes_record_commit_or_no_commit_context() -> None:
    missing = [
        note_name
        for note_name in R10_R28_NOTES
        if not _has_any(
            _read(note_name),
            [
                "No commit",
                "No staging",
                "Commit and tag status",
                "commit/tag",
                "committed as",
                "Do not auto-commit",
            ],
        )
    ]

    assert missing == []


def test_r10_r28_qa_notes_keep_next_step_or_followup_context() -> None:
    missing = [
        note_name
        for note_name in R10_R28_NOTES
        if not _has_any(
            _read(note_name),
            [
                "## Recommended next batch",
                "## Remaining risk",
                "## Remaining risks",
                "## Remaining risk and follow-up",
                "## Recommended next step",
                "## Next recommended batch",
            ],
        )
    ]

    assert missing == []


def test_r10_r28_qa_notes_have_no_unresolved_placeholders() -> None:
    placeholder_terms = ["to run before closeout", "tbd", "todo"]
    hits = []

    for note_name in R10_R28_NOTES:
        source = _read(note_name).lower()
        for term in placeholder_terms:
            if term in source:
                hits.append(f"{note_name}: {term}")

    assert hits == []
