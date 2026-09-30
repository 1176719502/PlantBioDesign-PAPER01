from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPLEMENT = ROOT / "docs" / "qa" / "V2_7_R53_0900_POST_R52_SUPPLEMENTAL_COMMAND_BUNDLE.md"


def _supplement_source() -> str:
    return SUPPLEMENT.read_text(encoding="utf-8")


def test_r53_explains_why_post_r52_supplemental_commands_exist() -> None:
    source = _supplement_source()

    for expected in [
        "R53 adds a supplemental command bundle after R52 clarified the current source chain",
        "R47 remains the current main command-bundle source",
        "written before R48, R49, R50, R51, and R52 existed",
        "run the R47 main command bundle and then run this R53 supplemental bundle",
    ]:
        assert expected in source


def test_r53_supplemental_bundle_covers_post_r47_current_source_guards() -> None:
    source = _supplement_source()

    for expected in [
        "tests/test_v2_7_r48_0900_current_execution_order_refresh.py",
        "tests/test_v2_7_r49_0900_current_timed_audit_fields_refresh.py",
        "tests/test_v2_7_r50_0900_current_completion_criteria_refresh.py",
        "tests/test_v2_7_r51_0900_current_decision_rules_refresh.py",
        "tests/test_v2_7_r52_0900_current_chain_consistency_guard.py",
        "tests/test_v2_7_r53_0900_post_r52_supplemental_command_bundle.py",
        "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
        "--basetemp .pytest_tmp/v27_r53_0900_post_r52_supplemental_check",
    ]:
        assert expected in source


def test_r53_preserves_r47_as_main_bundle_and_adds_supplement_status() -> None:
    source = _supplement_source()

    for expected in [
        "does not replace R47",
        "R47 main command-bundle rerun status",
        "R53 supplemental command-bundle rerun status",
        "R53 supplemental command-bundle source for post-R47 guards",
        "R52/R48/R47/R53/R49/R50/R51 evidence chain",
    ]:
        assert expected in source


def test_r53_is_nonfinal_and_preserves_product_boundaries() -> None:
    source = _supplement_source().lower()

    for expected in [
        "does not make the active goal complete",
        "at or after 2026-07-04 09:00 asia/shanghai",
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
