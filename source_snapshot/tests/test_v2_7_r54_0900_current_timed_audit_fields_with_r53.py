from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIELDS_REFRESH = ROOT / "docs" / "qa" / "V2_7_R54_0900_CURRENT_TIMED_AUDIT_FIELDS_WITH_R53.md"


def _fields_source() -> str:
    return FIELDS_REFRESH.read_text(encoding="utf-8")


def test_r54_refreshes_field_list_after_r53_supplement() -> None:
    source = _fields_source()

    for expected in [
        "R54 refreshes the current final timed audit field list after R53 added the post-R52 supplemental command bundle",
        "R49 remains useful historical field-list evidence",
        "written before R50, R51, R52, and R53 existed",
        "records both the R47 main command-bundle rerun and the R53 supplemental command-bundle rerun",
    ]:
        assert expected in source


def test_r54_current_fields_include_current_chain_and_r53_evidence() -> None:
    source = _fields_source()

    for expected in [
        "Actual checkpoint time",
        "Active goal status before any completion decision",
        "R52 current-chain consistency result",
        "R48 current execution-order status",
        "R47 main command-bundle rerun status",
        "R53 supplemental command-bundle rerun status",
        "R49 historical field-list supersession note",
        "R54 current field-list completion status",
        "R50 completion-criteria result",
        "R51 decision-rule result",
    ]:
        assert expected in source


def test_r54_source_precedence_uses_current_sources() -> None:
    source = _fields_source()

    for expected in [
        "Use this R54 note as the current final timed audit field source",
        "R52 as the chain-consistency guard",
        "R48 as the execution-order source",
        "R47 as the main command-bundle source",
        "R53 as the supplemental command-bundle source",
        "R50 as the completion-criteria source",
        "R51 as the decision-rule source",
    ]:
        assert expected in source


def test_r54_is_nonfinal_and_preserves_product_boundaries() -> None:
    source = _fields_source().lower()

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
