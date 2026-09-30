from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "docs" / "qa" / "V2_7_R61_0900_POST_R60_SUPPLEMENTAL_COMMAND_BUNDLE.md"


def _bundle_source() -> str:
    return BUNDLE.read_text(encoding="utf-8")


def test_r61_explains_post_r60_command_coverage() -> None:
    source = _bundle_source()

    for expected in [
        "R61 adds a post-R60 supplemental command bundle",
        "R59 created the direct-evidence worksheet",
        "R60 created the final timed audit record shell",
        "R47 remains the main command-bundle source",
        "R53 remains the post-R52 supplemental source",
        "run R47 first, R53 second, and this R61 post-R60 supplemental bundle third",
    ]:
        assert expected in source


def test_r61_commands_cover_latest_final_record_guards() -> None:
    source = _bundle_source()

    for expected in [
        "tests/test_v2_7_r54_0900_current_timed_audit_fields_with_r53.py",
        "tests/test_v2_7_r55_0900_current_completion_criteria_with_r54.py",
        "tests/test_v2_7_r56_0900_current_decision_rules_with_r55.py",
        "tests/test_v2_7_r57_0900_current_execution_order_with_r56.py",
        "tests/test_v2_7_r58_pre_0900_automation_current_chain_confirmation.py",
        "tests/test_v2_7_r59_0900_current_direct_evidence_worksheet.py",
        "tests/test_v2_7_r60_0900_final_timed_audit_record_shell.py",
        "tests/test_v2_7_r61_0900_post_r60_supplemental_command_bundle.py",
        "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
    ]:
        assert expected in source


def test_r61_records_three_command_bundle_statuses() -> None:
    source = _bundle_source()

    for expected in [
        "R47 main command-bundle rerun status",
        "R53 supplemental command-bundle rerun status",
        "R61 post-R60 supplemental command-bundle rerun status",
    ]:
        assert expected in source


def test_r61_source_chain_is_current() -> None:
    source = _bundle_source()

    for expected in [
        "R52 chain-consistency guard",
        "R57 execution-order source",
        "R58 automation current-chain confirmation",
        "R59 direct-evidence worksheet",
        "R60 final timed audit record shell",
        "R47 main command-bundle source",
        "R53 post-R52 supplemental command-bundle source",
        "R61 post-R60 supplemental command-bundle source",
        "R54 timed-audit field source",
        "R55 completion-criteria source",
        "R56 decision-rule source",
    ]:
        assert expected in source


def test_r61_is_nonfinal_and_preserves_boundaries() -> None:
    source = _bundle_source().lower()

    for expected in [
        "does not make the active goal complete",
        "at or after 2026-07-04 09:00 asia/shanghai",
        "direct current evidence",
        "does not complete the active goal",
        "documentation-only",
        "supplemental command record",
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
