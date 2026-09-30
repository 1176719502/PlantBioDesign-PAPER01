from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "docs" / "qa" / "V2_7_R28_0900_CHECKPOINT_HANDOFF_GUARD.md"


def _handoff_source() -> str:
    return HANDOFF.read_text(encoding="utf-8")


def test_r28_handoff_exists_and_names_checkpoint_map() -> None:
    source = _handoff_source()

    for expected in [
        "2026-07-04 09:00 Asia/Shanghai",
        "docs/qa/V2_7_R27_R10_R26_CHECKPOINT_MANIFEST_REFRESH.md",
        "docs/qa/V2_7_R26_R10_R25_CHECKPOINT_COPY_BOUNDARY_GUARD.md",
        "tests/test_v2_7_r10_r26_checkpoint_manifest_refresh.py",
        "tests/test_v2_7_r10_r27_0900_checkpoint_handoff.py",
        "views/pathway_workspace_sections/project_outputs_section.py",
        "views/pathway_workspace_sections/project_report_download_section.py",
    ]:
        assert expected in source


def test_r28_handoff_records_verification_and_commit_policy() -> None:
    source = _handoff_source()

    for expected in [
        "2598 passed, 8 skipped, 2 warnings",
        "9 passed in 0.46s",
        "6 passed in 0.35s",
        "10 passed in 0.43s",
        "7 passed in 0.29s",
        "No staging, commit, or tag was performed",
        "without explicit user authorization",
    ]:
        assert expected in source


def test_r28_handoff_preserves_stop_conditions_and_copy_boundary() -> None:
    source = _handoff_source().lower()

    for expected in [
        "documentation-only",
        "review and traceability area",
        "do not change database schema",
        "do not change import/export package schema",
        "do not change expression wizard core algorithms",
        "do not move `_render_import_package_preview()`",
    ]:
        assert expected in source

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
