from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIELDS_REFRESH = ROOT / "docs" / "qa" / "V2_7_R49_0900_CURRENT_TIMED_AUDIT_FIELDS_REFRESH.md"


def _fields_source() -> str:
    return FIELDS_REFRESH.read_text(encoding="utf-8")


def test_r49_refresh_points_fields_to_current_sources() -> None:
    source = _fields_source()

    for expected in [
        "R47 became the current command-bundle source",
        "R48 became the current execution-order source",
        "use this R49 field list",
        "follow the R48 order",
        "run the R47 command bundle",
        "apply the R35/R37 gates",
    ]:
        assert expected in source


def test_r49_final_timed_audit_fields_include_current_order_bundle_and_gates() -> None:
    source = _fields_source()

    for expected in [
        "Actual checkpoint time.",
        "R48 current execution-order status.",
        "R47 current final command bundle rerun status.",
        "`py_compile` result.",
        "Focused pytest result.",
        "`git diff --check` result.",
        "Docs-only runner result.",
        "Changed-file copy-safety scan result",
        "`git status --short --untracked-files=all` result.",
        "`git diff --stat` result.",
        "Protected-area drift review.",
        "Documentation-only boundary review.",
        "Staging, commit, and tag status.",
        "Remaining git status summary.",
        "R35 completion criteria result.",
        "R37 decision rule result.",
    ]:
        assert expected in source


def test_r49_source_precedence_uses_current_chain() -> None:
    source = _fields_source()

    for expected in [
        "Use this R49 note as the current final timed audit field source",
        "Use R48 as the current execution-order source",
        "R47 as the current command-bundle source",
        "R35/R37 as the completion and decision gates",
        "uses this R49 field list",
    ]:
        assert expected in source


def test_r49_refresh_is_nonfinal_and_preserves_boundaries() -> None:
    source = _fields_source().lower()

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
