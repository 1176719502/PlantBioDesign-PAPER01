from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORDER_REFRESH = ROOT / "docs" / "qa" / "V2_7_R57_0900_CURRENT_EXECUTION_ORDER_WITH_R56.md"


def _order_source() -> str:
    return ORDER_REFRESH.read_text(encoding="utf-8")


def test_r57_refreshes_execution_order_after_r56_decisions() -> None:
    source = _order_source()

    for expected in [
        "R57 refreshes the current final timed audit execution order after R56 became the current decision-rule source",
        "R48 remains useful historical execution-order evidence",
        "written before R53, R54, R55, and R56 existed",
        "R52 chain guard, R57 execution order, R47 main command bundle, R53 supplemental command bundle, R54 field list, R55 completion criteria, and R56 decision rules",
    ]:
        assert expected in source


def test_r57_final_audit_order_uses_current_chain() -> None:
    source = _order_source()

    for expected in [
        "Confirm the local time is at or after 2026-07-04 09:00 Asia/Shanghai",
        "Re-read the active BioDesign skills and AGENTS constraints",
        "Confirm the active goal status before any completion decision",
        "expected R10-R57 paths, no staged files, and no protected-area drift",
        "Follow the R52 current-chain consistency guard",
        "Run the R47 main command bundle",
        "Run the R53 supplemental command bundle",
        "Fill the R54 fields with direct at-or-after-09:00 evidence",
        "Apply the R55 completion criteria",
        "Apply the R56 decision rules",
        "call `update_goal(status=\"complete\")`",
        "Do not stage, commit, or tag unless the user explicitly authorizes it after final evidence exists",
    ]:
        assert expected in source


def test_r57_requires_current_direct_evidence_fields() -> None:
    source = _order_source()

    for expected in [
        "Actual checkpoint time",
        "Active goal status before completion decision",
        "R52 current-chain consistency result",
        "R57 current execution-order status",
        "R47 main command-bundle rerun status",
        "R53 supplemental command-bundle rerun status",
        "R49 historical field-list supersession note",
        "R54 current field-list completion status",
        "R55 current completion-criteria result",
        "R56 current decision-rule result",
        "Protected-area drift status",
        "Documentation-only product boundary status",
        "Staging, commit, and tag status",
        "Remaining git status",
    ]:
        assert expected in source


def test_r57_rejects_pre_0900_evidence_and_sets_source_precedence() -> None:
    source = _order_source()

    for expected in [
        "Pre-09:00 dry-run, heartbeat, prompt-refresh, command-refresh, order-refresh, field-refresh, criteria-refresh, decision-refresh, chain-consistency, or supplemental-bundle evidence",
        "not final timed-audit evidence",
        "Use this R57 note as the current execution-order source",
        "R52 as the chain-consistency guard",
        "R47 as the main command-bundle source",
        "R53 as the supplemental command-bundle source",
        "R54 as the timed-audit field source",
        "R55 as the completion-criteria source",
        "R56 as the decision-rule source",
    ]:
        assert expected in source


def test_r57_is_nonfinal_and_preserves_product_boundaries() -> None:
    source = _order_source().lower()

    for expected in [
        "does not make the active goal complete",
        "at or after 2026-07-04 09:00 asia/shanghai",
        "direct current evidence",
        "no staging, commit, or tag was performed",
        "documentation-only",
        "review records",
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
