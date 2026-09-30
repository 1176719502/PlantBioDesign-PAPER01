from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION_REFRESH = ROOT / "docs" / "qa" / "V2_7_R51_0900_CURRENT_DECISION_RULES_REFRESH.md"


def _decision_source() -> str:
    return DECISION_REFRESH.read_text(encoding="utf-8")


def test_r51_refresh_points_decisions_to_r50_completion() -> None:
    source = _decision_source()

    for expected in [
        "R50 became the current completion-criteria source",
        "R37 remains useful historical decision-rule evidence",
        "completion depends on R50",
        "preserve the R37 decision posture",
        "If every R50 completion criterion is satisfied",
    ]:
        assert expected in source


def test_r51_decision_rules_require_final_audit_and_direct_evidence() -> None:
    source = _decision_source()

    for expected in [
        "Apply these rules only after the final timed audit runs at or after 2026-07-04 09:00 Asia/Shanghai",
        "fills the R49 fields with direct current evidence",
        "If any required final command fails",
        "If the final audit finds protected-area drift",
        "If the final audit finds copy-boundary hits outside explicit policy or negative-test context",
        "If final evidence is missing or indirect",
        "If the user has not explicitly authorized staging, commit, or tag creation",
    ]:
        assert expected in source


def test_r51_source_precedence_uses_current_chain() -> None:
    source = _decision_source()

    for expected in [
        "Use this R51 note as the current decision-rule source",
        "Use R48 as the current execution-order source",
        "R47 as the current command-bundle source",
        "R49 as the current timed-audit field source",
        "R50 as the current completion-criteria source",
    ]:
        assert expected in source


def test_r51_refresh_is_nonfinal_and_preserves_boundaries() -> None:
    source = _decision_source().lower()

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
