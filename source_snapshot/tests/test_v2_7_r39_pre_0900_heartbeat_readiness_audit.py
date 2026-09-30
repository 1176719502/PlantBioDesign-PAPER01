from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEARTBEAT = ROOT / "docs" / "qa" / "V2_7_R39_PRE_0900_HEARTBEAT_READINESS_AUDIT.md"


def _heartbeat_source() -> str:
    return HEARTBEAT.read_text(encoding="utf-8")


def test_r39_heartbeat_names_time_target_and_nonfinal_status() -> None:
    source = _heartbeat_source()

    for expected in [
        "Heartbeat time: 2026-07-04 04:09 Asia/Shanghai",
        "Target checkpoint: 2026-07-04 09:00 Asia/Shanghai",
        "This heartbeat audit is not final checkpoint evidence",
        "active goal must remain open",
    ]:
        assert expected in source


def test_r39_heartbeat_lists_guard_cluster_commands() -> None:
    source = _heartbeat_source()

    for expected in [
        "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
        "tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py",
        "tests/test_v2_7_r10_r28_qa_note_structure_refresh.py",
        "tests/test_v2_7_r10_r25_checkpoint_copy_boundary.py",
        "tests/test_v2_7_r33_0900_final_check_command_bundle.py",
        "tests/test_v2_7_r38_pre_0900_completion_claim_guard.py",
        "tests/test_v2_7_r39_pre_0900_heartbeat_readiness_audit.py",
        "git diff --check",
        "scripts/dev_autonomous_check.py --mode docs-only",
        "git status --short --untracked-files=all",
        "git diff --stat",
    ]:
        assert expected in source


def test_r39_heartbeat_preserves_no_commit_and_copy_boundary() -> None:
    source = _heartbeat_source().lower()

    assert "no staging, commit, or tag was performed" in source
    assert "documentation-only" in source
    assert "review-framed" in source
    assert "r35 completion criteria and r37 decision rules" in source

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
