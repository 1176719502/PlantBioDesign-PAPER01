from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "qa" / "V2_7_R27_R10_R26_CHECKPOINT_MANIFEST_REFRESH.md"


def _manifest_source() -> str:
    return MANIFEST.read_text(encoding="utf-8")


def test_r27_manifest_refresh_exists_and_includes_latest_guard_files() -> None:
    source = _manifest_source()

    for expected in [
        "tests/test_v2_7_r10_r25_checkpoint_copy_boundary.py",
        "tests/test_v2_7_r10_r26_checkpoint_manifest_refresh.py",
        "docs/qa/V2_7_R26_R10_R25_CHECKPOINT_COPY_BOUNDARY_GUARD.md",
        "docs/qa/V2_7_R27_R10_R26_CHECKPOINT_MANIFEST_REFRESH.md",
        "views/pathway_workspace_sections/project_outputs_section.py",
        "views/pathway_workspace_sections/project_report_download_section.py",
    ]:
        assert expected in source


def test_r27_manifest_refresh_records_current_verification_evidence() -> None:
    source = _manifest_source()

    for expected in [
        "2598 passed, 8 skipped, 2 warnings",
        "6 passed in 0.35s",
        "10 passed in 0.43s",
        "7 passed in 0.29s",
        "No staging, commit, or tag was performed",
    ]:
        assert expected in source


def test_r27_manifest_refresh_stays_documentation_only_and_copy_safe() -> None:
    source = _manifest_source().lower()

    assert "documentation-only" in source
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
