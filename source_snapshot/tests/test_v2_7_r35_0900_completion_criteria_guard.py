from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "docs" / "qa" / "V2_7_R35_0900_COMPLETION_CRITERIA_GUARD.md"


def _criteria_source() -> str:
    return CRITERIA.read_text(encoding="utf-8")


def test_r35_completion_criteria_require_target_time_and_rerun() -> None:
    source = _criteria_source()

    for expected in [
        "at or after 2026-07-04 09:00 Asia/Shanghai",
        "R33 final command bundle has been rerun after the target checkpoint time",
        "records the actual checkpoint time",
        "remaining git status",
    ]:
        assert expected in source


def test_r35_completion_criteria_name_required_final_checks() -> None:
    source = _criteria_source()

    for expected in [
        "py_compile",
        "focused pytest",
        "git diff --check",
        "docs-only runner",
        "copy denylist scan",
        "git status --short --untracked-files=all",
        "git diff --stat",
        "no protected-area drift",
    ]:
        assert expected in source


def test_r35_completion_criteria_reject_pre_0900_evidence_as_complete() -> None:
    source = _criteria_source()

    for expected in [
        "R34 dry-run evidence is useful but not enough",
        "R20 full regression evidence is necessary context but not enough",
        "Passing focused guards before 09:00 is useful but not enough",
        "A clean copy scan before 09:00 is useful but not enough",
    ]:
        assert expected in source


def test_r35_completion_criteria_preserve_no_commit_and_copy_boundary() -> None:
    source = _criteria_source().lower()

    assert "no staging, commit, or tag was performed" in source
    assert "documentation-only" in source
    assert "review-framed" in source
    assert "without the user explicitly authorized" not in source

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
