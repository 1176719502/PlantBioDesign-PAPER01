from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORDER_REFRESH = ROOT / "docs" / "qa" / "V2_7_R48_0900_CURRENT_EXECUTION_ORDER_REFRESH.md"


def _order_refresh_source() -> str:
    return ORDER_REFRESH.read_text(encoding="utf-8")


def test_r48_refresh_points_order_to_r47_bundle() -> None:
    source = _order_refresh_source()

    for expected in [
        "R47 became the current command-bundle source",
        "use this R48 order",
        "Run the R47 current final command bundle",
        "Fill the R43 final timed audit fields",
        "Apply the R35 completion criteria",
        "Apply the R37 decision rules",
    ]:
        assert expected in source


def test_r48_final_audit_order_is_sequenced_before_completion() -> None:
    source = _order_refresh_source()

    expected_order = [
        "Confirm the current local time",
        "Read the active goal",
        "Inspect `git status --short --untracked-files=all`",
        "Run the R47 current final command bundle",
        "Run changed-file copy-safety review",
        "Fill the R43 final timed audit fields",
        "Apply the R35 completion criteria",
        "Apply the R37 decision rules",
        "mark the active goal complete",
    ]
    positions = [source.index(item) for item in expected_order]
    assert positions == sorted(positions)


def test_r48_blocks_stale_order_sources_and_premature_actions() -> None:
    source = _order_refresh_source().lower()

    for expected in [
        "do not use r42 as the current command-bundle source when r47 exists",
        "do not mark the goal complete before running the r47 command bundle",
        "do not apply r37 decision rules before filling the r43 fields",
        "do not stage, commit, or tag before the final audit records the remaining git status",
        "do not use pre-09:00 heartbeat, dry-run, template, prompt-refresh, command-refresh, or order-refresh evidence",
    ]:
        assert expected in source


def test_r48_records_heartbeat_refresh_and_preserves_boundaries() -> None:
    source = _order_refresh_source().lower()

    for expected in [
        "automation id: `biodesign-v2-7-09-00-final-timed-audit`",
        "uses this r48 execution order and the r47 command bundle",
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
