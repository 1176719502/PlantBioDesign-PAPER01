from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFRESH_NOTE = ROOT / "docs" / "qa" / "V2_7_R47_0900_CURRENT_FINAL_COMMAND_BUNDLE_REFRESH.md"


def _refresh_source() -> str:
    return REFRESH_NOTE.read_text(encoding="utf-8")


def test_r47_refresh_supersedes_r42_as_current_command_source() -> None:
    source = _refresh_source()

    for expected in [
        "R42 was the prior command-bundle source",
        "using this R47 command bundle as the current command source",
        "Use this R47 command bundle as the current command source",
        "R44 remains the execution-order source",
        "R43 remains the final timed audit field list",
        "R35/R37 remain the completion and decision gates",
    ]:
        assert expected in source


def test_r47_current_bundle_covers_post_r42_guards() -> None:
    source = _refresh_source()

    for expected in [
        "tests/test_v2_7_r43_0900_current_timed_audit_template_supplement.py",
        "tests/test_v2_7_r44_0900_final_audit_execution_order.py",
        "tests/test_v2_7_r45_0900_heartbeat_prompt_refresh.py",
        "tests/test_v2_7_r46_pre_0900_active_goal_continuation_guard.py",
        "tests/test_v2_7_r47_0900_current_final_command_bundle_refresh.py",
        "--basetemp .pytest_tmp/v27_r47_0900_current_final_check",
    ]:
        assert expected in source


def test_r47_records_heartbeat_prompt_refresh_intent() -> None:
    source = _refresh_source()

    for expected in [
        "Automation id: `biodesign-v2-7-09-00-final-timed-audit`",
        "The heartbeat prompt",
        "uses R47 as the current command source",
        "09:00 continuation",
    ]:
        assert expected in source


def test_r47_refresh_is_nonfinal_and_preserves_boundaries() -> None:
    source = _refresh_source().lower()

    for expected in [
        "this refresh does not make the active goal complete",
        "direct current evidence",
        "no staging, commit, or tag was performed",
        "documentation-only",
        "review-framed",
        "no database schema changed",
        "no import/export package schema changed",
        "no expression wizard core algorithm changed",
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
