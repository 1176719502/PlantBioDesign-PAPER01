from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSHEET = ROOT / "docs" / "qa" / "V2_7_R59_0900_CURRENT_DIRECT_EVIDENCE_WORKSHEET.md"


def _worksheet_source() -> str:
    return WORKSHEET.read_text(encoding="utf-8")


def test_r59_explains_why_current_worksheet_exists() -> None:
    source = _worksheet_source()

    for expected in [
        "R59 provides a current direct-evidence worksheet",
        "R36 and R43 remain useful historical templates",
        "written before the current R52/R57/R47/R53/R54/R55/R56 chain existed",
        "does not replace the R57 execution order or the R58 automation confirmation",
        "copy direct command evidence before applying the R55 completion criteria and R56 decision rules",
    ]:
        assert expected in source


def test_r59_lists_current_source_chain() -> None:
    source = _worksheet_source()

    for expected in [
        "docs/qa/V2_7_R52_0900_CURRENT_CHAIN_CONSISTENCY_GUARD.md",
        "docs/qa/V2_7_R57_0900_CURRENT_EXECUTION_ORDER_WITH_R56.md",
        "docs/qa/V2_7_R58_PRE_0900_AUTOMATION_CURRENT_CHAIN_CONFIRMATION.md",
        "docs/qa/V2_7_R47_0900_CURRENT_FINAL_COMMAND_BUNDLE_REFRESH.md",
        "docs/qa/V2_7_R53_0900_POST_R52_SUPPLEMENTAL_COMMAND_BUNDLE.md",
        "docs/qa/V2_7_R54_0900_CURRENT_TIMED_AUDIT_FIELDS_WITH_R53.md",
        "docs/qa/V2_7_R55_0900_CURRENT_COMPLETION_CRITERIA_WITH_R54.md",
        "docs/qa/V2_7_R56_0900_CURRENT_DECISION_RULES_WITH_R55.md",
    ]:
        assert expected in source


def test_r59_has_fillable_direct_evidence_fields() -> None:
    source = _worksheet_source()

    for expected in [
        "Actual checkpoint time: PENDING_FINAL_AUDIT",
        "Active goal status before completion decision: PENDING_FINAL_AUDIT",
        "R52 current-chain consistency result: PENDING_FINAL_AUDIT",
        "R57 current execution-order status: PENDING_FINAL_AUDIT",
        "R58 automation current-chain confirmation status: PENDING_FINAL_AUDIT",
        "R47 main command-bundle rerun status: PENDING_FINAL_AUDIT",
        "R53 supplemental command-bundle rerun status: PENDING_FINAL_AUDIT",
        "R54 current field-list completion status: PENDING_FINAL_AUDIT",
        "R55 current completion-criteria result: PENDING_FINAL_AUDIT",
        "R56 current decision-rule result: PENDING_FINAL_AUDIT",
        "Documentation-only product boundary status: PENDING_FINAL_AUDIT",
        "Staging, commit, and tag status: PENDING_FINAL_AUDIT",
        "Remaining git status: PENDING_FINAL_AUDIT",
    ]:
        assert expected in source


def test_r59_required_sequence_matches_current_decision_flow() -> None:
    source = _worksheet_source()

    for expected in [
        "Confirm the local time is at or after 2026-07-04 09:00 Asia/Shanghai",
        "Read the active goal status before any completion decision",
        "expected R10-R59 paths, no staged files, and no protected-area drift",
        "Run the R47 main command bundle",
        "Run the R53 supplemental command bundle",
        "Fill every field in this worksheet with direct at-or-after-09:00 evidence",
        "Apply the R55 completion criteria",
        "Apply the R56 decision rules",
        "call `update_goal(status=\"complete\")`",
        "Do not stage, commit, or tag unless the user explicitly authorizes it after final evidence exists",
    ]:
        assert expected in source


def test_r59_is_nonfinal_and_preserves_boundaries() -> None:
    source = _worksheet_source().lower()

    for expected in [
        "not final checkpoint evidence",
        "pending_final_audit",
        "active goal must remain open",
        "direct at-or-after-09:00 evidence",
        "does not complete the active goal",
        "documentation-only",
        "review worksheet",
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
