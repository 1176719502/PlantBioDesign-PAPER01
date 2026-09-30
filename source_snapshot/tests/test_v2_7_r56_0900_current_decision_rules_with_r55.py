from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION_REFRESH = ROOT / "docs" / "qa" / "V2_7_R56_0900_CURRENT_DECISION_RULES_WITH_R55.md"


def _decision_source() -> str:
    return DECISION_REFRESH.read_text(encoding="utf-8")


def test_r56_refreshes_decisions_after_r55_completion() -> None:
    source = _decision_source()

    for expected in [
        "R56 refreshes the current decision rules after R55 became the current completion-criteria source",
        "R51 remains useful historical decision-rule evidence",
        "written before R52, R53, R54, and R55 existed",
        "completion depends on R55",
        "preserve the R51 decision posture",
    ]:
        assert expected in source


def test_r56_decision_rules_require_r54_fields_and_r55_criteria() -> None:
    source = _decision_source()

    for expected in [
        "fills the R54 fields with direct current evidence",
        "If every R55 completion criterion is satisfied",
        "If any required final command fails",
        "R47 main command bundle or R53 supplemental command bundle is not rerun",
        "If final evidence is missing, indirect, or based only on pre-09:00 refresh evidence",
        "If the user has not explicitly authorized staging, commit, or tag creation",
    ]:
        assert expected in source


def test_r56_source_precedence_uses_current_chain() -> None:
    source = _decision_source()

    for expected in [
        "Use this R56 note as the current decision-rule source",
        "R52 as the chain-consistency guard",
        "R48 as the execution-order source",
        "R47 as the main command-bundle source",
        "R53 as the supplemental command-bundle source",
        "R54 as the timed-audit field source",
        "R55 as the completion-criteria source",
    ]:
        assert expected in source


def test_r56_is_nonfinal_and_preserves_product_boundaries() -> None:
    source = _decision_source().lower()

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
