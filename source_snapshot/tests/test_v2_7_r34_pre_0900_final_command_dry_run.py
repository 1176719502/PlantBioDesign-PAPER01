from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRY_RUN = ROOT / "docs" / "qa" / "V2_7_R34_PRE_0900_FINAL_COMMAND_DRY_RUN.md"


def _dry_run_source() -> str:
    return DRY_RUN.read_text(encoding="utf-8")


def test_r34_dry_run_note_names_times_and_nonfinal_status() -> None:
    source = _dry_run_source()

    for expected in [
        "Dry-run time: 2026-07-04 03:52 Asia/Shanghai",
        "Target checkpoint: 2026-07-04 09:00 Asia/Shanghai",
        "This is not the final 09:00 checkpoint",
        "pre-09:00 dry run, not final checkpoint completion",
    ]:
        assert expected in source


def test_r34_dry_run_note_lists_r33_command_bundle_checks() -> None:
    source = _dry_run_source()

    for expected in [
        "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
        "tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py",
        "tests/test_v2_7_r10_r28_qa_note_structure_refresh.py",
        "tests/test_v2_7_r10_r25_checkpoint_copy_boundary.py",
        "tests/test_v2_7_r33_0900_final_check_command_bundle.py",
        "tests/test_v2_7_r34_pre_0900_final_command_dry_run.py",
        "git diff --check",
        "scripts/dev_autonomous_check.py --mode docs-only",
        "git status --short --untracked-files=all",
        "git diff --stat",
    ]:
        assert expected in source


def test_r34_dry_run_note_preserves_no_commit_and_copy_boundary() -> None:
    source = _dry_run_source().lower()

    assert "no staging, commit, or tag was performed" in source
    assert "documentation-only" in source
    assert "review-framed" in source
    assert "2598 passed, 8 skipped, 2 warnings" in source

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
