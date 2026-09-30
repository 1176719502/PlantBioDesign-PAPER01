from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "docs" / "qa" / "V2_7_R33_0900_FINAL_CHECK_COMMAND_BUNDLE.md"


def _bundle_source() -> str:
    return BUNDLE.read_text(encoding="utf-8")


def test_r33_final_check_bundle_names_target_checkpoint_and_required_commands() -> None:
    source = _bundle_source()

    for expected in [
        "2026-07-04 09:00 Asia/Shanghai",
        "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
        "tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py",
        "tests/test_v2_7_r10_r28_qa_note_structure_refresh.py",
        "tests/test_v2_7_r10_r25_checkpoint_copy_boundary.py",
        "tests/test_v2_7_r33_0900_final_check_command_bundle.py",
        "git diff --check",
        "scripts/dev_autonomous_check.py --mode docs-only",
        "git status --short --untracked-files=all",
        "git diff --stat",
    ]:
        assert expected in source


def test_r33_final_check_bundle_records_full_regression_decision() -> None:
    source = _bundle_source()

    for expected in [
        "Do not rerun full pytest for R33 unless",
        "R20-covered Project Outputs files",
        "2598 passed, 8 skipped, 2 warnings",
    ]:
        assert expected in source


def test_r33_final_check_bundle_keeps_no_commit_policy_and_copy_boundary() -> None:
    source = _bundle_source().lower()

    assert "no staging, commit, or tag was performed" in source
    assert "without explicit user authorization" in source
    assert "documentation-only" in source
    assert "review-framed" in source

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
