from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIRMATION = ROOT / "docs" / "qa" / "V2_7_R58_PRE_0900_AUTOMATION_CURRENT_CHAIN_CONFIRMATION.md"


def _confirmation_source() -> str:
    return CONFIRMATION.read_text(encoding="utf-8")


def test_r58_records_automation_identity_and_target() -> None:
    source = _confirmation_source()

    for expected in [
        "Automation id: `biodesign-v2-7-09-00-final-timed-audit`",
        "Automation kind: heartbeat",
        "Target checkpoint: 2026-07-04 09:00 Asia/Shanghai",
        "Target thread: active V2.7 checkpoint thread",
    ]:
        assert expected in source


def test_r58_confirms_prompt_points_to_current_chain() -> None:
    source = _confirmation_source()

    for expected in [
        "docs/qa/V2_7_R57_0900_CURRENT_EXECUTION_ORDER_WITH_R56.md",
        "docs/qa/V2_7_R52_0900_CURRENT_CHAIN_CONSISTENCY_GUARD.md",
        "docs/qa/V2_7_R47_0900_CURRENT_FINAL_COMMAND_BUNDLE_REFRESH.md",
        "docs/qa/V2_7_R53_0900_POST_R52_SUPPLEMENTAL_COMMAND_BUNDLE.md",
        "docs/qa/V2_7_R54_0900_CURRENT_TIMED_AUDIT_FIELDS_WITH_R53.md",
        "docs/qa/V2_7_R55_0900_CURRENT_COMPLETION_CRITERIA_WITH_R54.md",
        "docs/qa/V2_7_R56_0900_CURRENT_DECISION_RULES_WITH_R55.md",
    ]:
        assert expected in source


def test_r58_records_direct_automation_check_evidence() -> None:
    source = _confirmation_source()

    for expected in [
        "automation_update",
        "Select-String",
        "automation.toml",
        "Prompt text naming `R57 current execution order`",
        "R47 main command bundle first and then the R53 supplemental command bundle",
        "direct at-or-after-09:00 evidence before any completion decision",
        "call `update_goal(status=\"complete\")` only when all R55 criteria pass and R56 finds no stop condition",
        "not to stage, commit, or tag unless the user explicitly authorizes it after final evidence exists",
    ]:
        assert expected in source


def test_r58_is_nonfinal_and_preserves_boundaries() -> None:
    source = _confirmation_source().lower()

    for expected in [
        "not final checkpoint evidence",
        "must still run at or after 2026-07-04 09:00 asia/shanghai",
        "direct current evidence",
        "does not complete the active goal",
        "documentation-only",
        "review record",
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
