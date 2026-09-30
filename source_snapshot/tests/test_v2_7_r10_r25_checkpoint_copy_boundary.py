from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CHECKPOINT_QA_NOTES = [
    ROOT / "docs" / "qa" / f"V2_7_R{index}_{suffix}.md"
    for index, suffix in [
        (10, "TRACEABILITY_BOUNDARY_AUDIT"),
        (11, "PROJECT_OUTPUTS_DETAIL_TABLE_STATE"),
        (12, "PROJECT_OUTPUTS_BOUNDARY_GUARD"),
        (13, "PROJECT_OUTPUTS_DETAIL_TABLE_WIDTH_GUARD"),
        (14, "PROJECT_OUTPUTS_NEXT_CUT_AUDIT"),
        (15, "PROJECT_OUTPUTS_SECTION_EXTRACTION_FEASIBILITY_AUDIT"),
        (16, "PROJECT_OUTPUTS_SECTION_SHELL_EXTRACTION"),
        (17, "PROJECT_OUTPUTS_CALLBACK_MIGRATION_AUDIT"),
        (18, "PROJECT_REPORT_DOWNLOAD_SECTION_EXTRACTION"),
        (19, "IMPORT_PREVIEW_CALLBACK_BOUNDARY_GUARD"),
        (20, "R10_R19_CHECKPOINT_FULL_REGRESSION"),
        (21, "R10_R20_HANDOFF_AND_PROTECTED_AREA_AUDIT"),
        (22, "PROJECT_OUTPUTS_CHECKPOINT_PROTECTED_AREA_GUARD"),
        (23, "R10_R22_QA_CHECKPOINT_INTEGRITY_GUARD"),
        (24, "R10_R23_QA_NOTE_STRUCTURE_GUARD"),
        (25, "R10_R24_CHECKPOINT_MANIFEST"),
    ]
]

CHECKPOINT_SOURCE_FILES = [
    ROOT / "views" / "PathwayWorkspace.py",
    ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py",
    ROOT / "views" / "pathway_workspace_sections" / "project_report_download_section.py",
    ROOT / "services" / "pathway_outputs_workflow_view_model.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def _forbidden_phrases() -> list[str]:
    return [
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


def test_r10_r25_checkpoint_qa_notes_stay_free_of_forbidden_copy() -> None:
    missing = [str(path.relative_to(ROOT)) for path in CHECKPOINT_QA_NOTES if not path.exists()]
    assert missing == []

    hits = [
        f"{path.relative_to(ROOT)}: {phrase}"
        for path in CHECKPOINT_QA_NOTES
        for phrase in _forbidden_phrases()
        if phrase in _read(path)
    ]

    assert hits == []


def test_r10_r25_project_outputs_checkpoint_source_stays_free_of_forbidden_copy() -> None:
    missing = [str(path.relative_to(ROOT)) for path in CHECKPOINT_SOURCE_FILES if not path.exists()]
    assert missing == []

    hits = [
        f"{path.relative_to(ROOT)}: {phrase}"
        for path in CHECKPOINT_SOURCE_FILES
        for phrase in _forbidden_phrases()
        if phrase in _read(path)
    ]

    assert hits == []


def test_r10_r25_checkpoint_copy_guard_covers_manifest_and_extracted_sections() -> None:
    covered = {path.relative_to(ROOT).as_posix() for path in CHECKPOINT_QA_NOTES + CHECKPOINT_SOURCE_FILES}

    for required in [
        "docs/qa/V2_7_R25_R10_R24_CHECKPOINT_MANIFEST.md",
        "views/pathway_workspace_sections/project_outputs_section.py",
        "views/pathway_workspace_sections/project_report_download_section.py",
        "services/pathway_outputs_workflow_view_model.py",
    ]:
        assert required in covered
