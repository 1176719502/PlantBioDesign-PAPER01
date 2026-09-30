from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAIN_GUARD = ROOT / "docs" / "qa" / "V2_7_R52_0900_CURRENT_CHAIN_CONSISTENCY_GUARD.md"


def _chain_guard_source() -> str:
    return CHAIN_GUARD.read_text(encoding="utf-8")


def test_r52_names_the_current_0900_source_chain() -> None:
    source = _chain_guard_source()

    for expected in [
        "R52 adds a current-chain consistency guard",
        "R48 order, R47 command bundle, R49 fields, R50 completion criteria, and R51 decision rules",
        "Use R52 as the current chain-consistency guard",
        "Use R48 as the current execution-order source",
        "Use R47 as the current command-bundle source",
        "Use R49 as the current timed-audit field source",
        "Use R50 as the current completion-criteria source",
        "Use R51 as the current decision-rule source",
    ]:
        assert expected in source


def test_r52_treats_older_references_as_historical_context_only() -> None:
    source = _chain_guard_source()

    for expected in [
        "remain useful historical source-refresh records",
        "written before later refreshes existed",
        "Older references inside R47, R48, R49, or R50 remain historical context only",
        "must not override the current R52/R48/R47/R49/R50/R51 chain",
    ]:
        assert expected in source


def test_r52_final_audit_evidence_requires_direct_current_chain_fields() -> None:
    source = _chain_guard_source()

    for expected in [
        "direct at-or-after-09:00 evidence",
        "active goal status before completion decision",
        "R52 current-chain consistency result",
        "R48 execution-order status",
        "R47 command-bundle rerun status",
        "R49 field completion status",
        "R50 completion-criteria result",
        "R51 decision-rule result",
        "protected-area drift review",
        "documentation-only boundary review",
    ]:
        assert expected in source


def test_r52_is_nonfinal_and_preserves_product_boundaries() -> None:
    source = _chain_guard_source().lower()

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
