from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRITERIA_REFRESH = ROOT / "docs" / "qa" / "V2_7_R50_0900_CURRENT_COMPLETION_CRITERIA_REFRESH.md"


def _criteria_source() -> str:
    return CRITERIA_REFRESH.read_text(encoding="utf-8")


def test_r50_refresh_points_completion_to_current_sources() -> None:
    source = _criteria_source()

    for expected in [
        "R48 became the current execution-order source",
        "R47 became the current command-bundle source",
        "R49 became the current timed-audit field source",
        "R35 remains useful historical completion-criteria evidence",
        "use this R50 criteria refresh",
        "R37 decision rules",
    ]:
        assert expected in source


def test_r50_current_completion_criteria_require_current_chain() -> None:
    source = _criteria_source()

    for expected in [
        "The current time is at or after 2026-07-04 09:00 Asia/Shanghai.",
        "The final timed audit follows the R48 current execution order.",
        "The R47 current final command bundle has been rerun after the target checkpoint time.",
        "The final timed audit note uses the R49 current timed-audit field list.",
        "The final timed audit note records the actual checkpoint time.",
        "The final timed audit note records pass/fail results",
        "The final timed audit note records protected-area drift review.",
        "The final timed audit note confirms the documentation-only product boundary is still intact.",
        "R37 decision rules are applied after all R49 fields are filled with direct current evidence.",
    ]:
        assert expected in source


def test_r50_rejects_pre_checkpoint_refresh_evidence_as_completion() -> None:
    source = _criteria_source()

    for expected in [
        "R34 dry-run evidence is useful but not enough",
        "R20 full regression evidence is necessary context but not enough",
        "Passing focused guards before 09:00 is useful but not enough",
        "A clean copy scan before 09:00 is useful but not enough",
        "R47 command-refresh evidence is useful but not enough",
        "R48 order-refresh evidence is useful but not enough",
        "R49 field-refresh evidence is useful but not enough",
    ]:
        assert expected in source


def test_r50_refresh_is_nonfinal_and_preserves_boundaries() -> None:
    source = _criteria_source().lower()

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
