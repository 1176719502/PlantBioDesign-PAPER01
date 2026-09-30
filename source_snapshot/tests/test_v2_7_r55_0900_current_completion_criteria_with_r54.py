from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRITERIA_REFRESH = ROOT / "docs" / "qa" / "V2_7_R55_0900_CURRENT_COMPLETION_CRITERIA_WITH_R54.md"


def _criteria_source() -> str:
    return CRITERIA_REFRESH.read_text(encoding="utf-8")


def test_r55_refreshes_completion_after_r53_and_r54() -> None:
    source = _criteria_source()

    for expected in [
        "R55 refreshes the current completion criteria after R53 added the supplemental command bundle",
        "R54 became the current timed-audit field source",
        "R50 remains useful historical completion-criteria evidence",
        "written before R51, R52, R53, and R54 existed",
        "use this R55 criteria refresh together with the R51 decision rules",
    ]:
        assert expected in source


def test_r55_completion_criteria_require_current_chain_evidence() -> None:
    source = _criteria_source()

    for expected in [
        "The current time is at or after 2026-07-04 09:00 Asia/Shanghai",
        "active goal status is inspected before any completion decision",
        "R52 current chain-consistency guard",
        "R48 current execution order",
        "R47 main command bundle has been rerun",
        "R53 supplemental command bundle has been rerun",
        "R54 current timed-audit field list",
        "R49 historical field-list supersession note",
        "R51 decision rules are applied after all R54 fields are filled with direct current evidence",
    ]:
        assert expected in source


def test_r55_rejects_pre_0900_and_refresh_only_evidence() -> None:
    source = _criteria_source()

    for expected in [
        "pre-09:00 dry-run, heartbeat, prompt-refresh, command-refresh, order-refresh, field-refresh, criteria-refresh, decision-refresh, chain-consistency, or supplemental-bundle evidence",
        "Passing focused guards before 09:00 is useful but not enough",
        "A clean copy scan before 09:00 is useful but not enough",
        "R47, R53, R54, or R55 refresh evidence is useful but not enough",
    ]:
        assert expected in source


def test_r55_source_precedence_and_boundaries_are_current() -> None:
    source = _criteria_source()

    for expected in [
        "Use this R55 note as the current completion-criteria source",
        "R52 as the chain-consistency guard",
        "R48 as the execution-order source",
        "R47 as the main command-bundle source",
        "R53 as the supplemental command-bundle source",
        "R54 as the timed-audit field source",
        "R51 as the decision-rule source",
    ]:
        assert expected in source

    lowered = source.lower()
    for expected in [
        "does not make the active goal complete",
        "documentation-only",
        "review-framed",
        "no database schema changed",
        "no import/export package schema changed",
        "no expression wizard core algorithm changed",
    ]:
        assert expected in lowered

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
    assert [phrase for phrase in forbidden if phrase in lowered] == []
