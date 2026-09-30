from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "docs" / "qa" / "V2_7_R40_PRE_0900_HEARTBEAT_AUTOMATION_HANDOFF.md"


def _handoff_source() -> str:
    return HANDOFF.read_text(encoding="utf-8")


def test_r40_handoff_records_automation_and_target_time() -> None:
    source = _handoff_source()

    for expected in [
        "Automation id: `biodesign-v2-7-09-00-final-timed-audit`",
        "Target checkpoint: 2026-07-04 09:00 Asia/Shanghai",
        "The heartbeat is scheduled for `2026-07-04 09:00 Asia/Shanghai`.",
        "The heartbeat targets the active V2.7 checkpoint thread.",
    ]:
        assert expected in source


def test_r40_handoff_lists_required_final_audit_evidence() -> None:
    source = _handoff_source()

    for expected in [
        "`py_compile` on the final guard tests",
        "Focused pytest for the final guard cluster with a repo-local basetemp",
        "`git diff --check`",
        "Docs-only autonomous check",
        "Changed-file copy denylist scan",
        "`git status --short --untracked-files=all`",
        "`git diff --stat`",
        "Protected-area drift review",
        "Documentation-only product-boundary review",
    ]:
        assert expected in source


def test_r40_handoff_is_nonfinal_and_preserves_boundaries() -> None:
    source = _handoff_source().lower()

    assert "this handoff note is not final checkpoint evidence" in source
    assert "active goal must remain open" in source
    assert "r35 completion criteria and r37 decision rules" in source
    assert "no staging, commit, or tag was performed" in source
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
