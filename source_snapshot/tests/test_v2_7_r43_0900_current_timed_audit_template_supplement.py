from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPLEMENT = ROOT / "docs" / "qa" / "V2_7_R43_0900_CURRENT_TIMED_AUDIT_TEMPLATE_SUPPLEMENT.md"


def _supplement_source() -> str:
    return SUPPLEMENT.read_text(encoding="utf-8")


def test_r43_supplement_points_final_audit_to_r42_command_source() -> None:
    source = _supplement_source()

    for expected in [
        "R42 current final command bundle",
        "docs/qa/V2_7_R42_0900_CURRENT_FINAL_COMMAND_BUNDLE_SUPPLEMENT.md",
        "unless a later R batch safely supersedes it before 09:00",
    ]:
        assert expected in source


def test_r43_supplement_lists_required_final_evidence_fields() -> None:
    source = _supplement_source()

    for expected in [
        "Actual checkpoint time",
        "R42 current final command bundle rerun status",
        "`py_compile` result",
        "Focused pytest result",
        "`git diff --check` result",
        "Docs-only runner result",
        "Changed-file copy-safety scan result",
        "`git status --short --untracked-files=all` result",
        "`git diff --stat` result",
        "Protected-area drift review",
        "Documentation-only boundary review",
        "Staging, commit, and tag status",
        "Remaining git status summary",
        "R35 completion criteria result",
        "R37 decision rule result",
    ]:
        assert expected in source


def test_r43_supplement_is_nonfinal_and_preserves_boundaries() -> None:
    source = _supplement_source().lower()

    assert "this supplement is not final evidence" in source
    assert "active goal must remain open" in source
    assert "at or after 2026-07-04 09:00 asia/shanghai" in source
    assert "r35 completion criteria and r37 decision rules" in source
    assert "no staging, commit, or tag was performed" in source
    assert "documentation-only" in source
    assert "review-framed" in source

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
