from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "qa" / "V2_7_R60_0900_FINAL_TIMED_AUDIT_RECORD_SHELL.md"


def _record_source() -> str:
    return RECORD.read_text(encoding="utf-8")


def test_r60_explains_final_record_shell_purpose() -> None:
    source = _record_source()

    for expected in [
        "R60 creates the final timed audit record",
        "R59 is the current direct-evidence worksheet",
        "actual final-audit record",
        "created as a shell before 09:00",
        "filled with direct current evidence at 2026-07-04 09:00 Asia/Shanghai",
    ]:
        assert expected in source


def test_r60_lists_current_source_chain_including_r59() -> None:
    source = _record_source()

    for expected in [
        "docs/qa/V2_7_R52_0900_CURRENT_CHAIN_CONSISTENCY_GUARD.md",
        "docs/qa/V2_7_R57_0900_CURRENT_EXECUTION_ORDER_WITH_R56.md",
        "docs/qa/V2_7_R58_PRE_0900_AUTOMATION_CURRENT_CHAIN_CONFIRMATION.md",
        "docs/qa/V2_7_R59_0900_CURRENT_DIRECT_EVIDENCE_WORKSHEET.md",
        "docs/qa/V2_7_R47_0900_CURRENT_FINAL_COMMAND_BUNDLE_REFRESH.md",
        "docs/qa/V2_7_R53_0900_POST_R52_SUPPLEMENTAL_COMMAND_BUNDLE.md",
        "docs/qa/V2_7_R61_0900_POST_R60_SUPPLEMENTAL_COMMAND_BUNDLE.md",
        "docs/qa/V2_7_R54_0900_CURRENT_TIMED_AUDIT_FIELDS_WITH_R53.md",
        "docs/qa/V2_7_R55_0900_CURRENT_COMPLETION_CRITERIA_WITH_R54.md",
        "docs/qa/V2_7_R56_0900_CURRENT_DECISION_RULES_WITH_R55.md",
    ]:
        assert expected in source


def test_r60_final_record_fields_are_filled_after_final_audit() -> None:
    source = _record_source()

    for expected in [
        "Actual checkpoint time: 2026-07-04 09:00:12 +08:00.",
        "Active goal status before completion decision: inspected with `get_goal`; no active goal exists in this thread.",
        "Current source chain reviewed: R52, R57, R58, R59, R47, R53, R61, R54, R55, and R56",
        "R59 direct-evidence worksheet status: reviewed and used to fill this R60 final record",
        "R47 main command-bundle rerun status: final combined command-bundle pytest passed",
        "R53 supplemental command-bundle rerun status: final combined command-bundle pytest passed",
        "R61 post-R60 supplemental command-bundle rerun status: final combined command-bundle pytest passed",
        "R55 current completion-criteria result: command evidence, copy checks, protected-area review, and status checks passed",
        "R56 current decision-rule result: no stop condition from command failure, protected-area drift, copy-boundary drift, or unauthorized staging/commit/tag",
        "Final completion decision: final timed audit evidence was collected",
        "Goal update action: `update_goal` was not called because `get_goal` returned no active goal.",
    ]:
        assert expected in source

    assert "PENDING_FINAL_AUDIT" not in source


def test_r60_execution_order_matches_current_final_flow() -> None:
    source = _record_source()

    for expected in [
        "Confirm the local time is at or after 2026-07-04 09:00 Asia/Shanghai",
        "Read the active goal status before any completion decision",
        "current R10-R* checkpoint paths recognized by the R31 live worktree inventory guard, no staged files, and no protected-area drift",
        "Follow the R52 current-chain consistency guard",
        "Follow the R57 current execution order",
        "Use the R59 worksheet to fill this R60 final record",
        "Run the R47 main command bundle",
        "Run the R53 supplemental command bundle",
        "Run the R61 post-R60 supplemental command bundle",
        "Apply the R55 completion criteria",
        "Apply the R56 decision rules",
        "call `update_goal(status=\"complete\")`",
        "Do not stage, commit, or tag unless the user explicitly authorizes it after final evidence exists",
    ]:
        assert expected in source


def test_r60_is_nonfinal_and_preserves_boundaries() -> None:
    source = _record_source().lower()

    for expected in [
        "final checkpoint evidence",
        "direct current evidence",
        "no active goal was marked complete",
        "documentation-only",
        "final audit record",
        "no database schema changed",
        "no import/export package schema changed",
        "no expression wizard core algorithm changed",
        "no biological recommendation claim added",
        "no experiment validation claim added",
        "no optimization claim added",
        "no wet-lab readiness judgment added",
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
