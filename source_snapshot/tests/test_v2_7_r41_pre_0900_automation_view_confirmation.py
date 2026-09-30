from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIRMATION = ROOT / "docs" / "qa" / "V2_7_R41_PRE_0900_AUTOMATION_VIEW_CONFIRMATION.md"


def _confirmation_source() -> str:
    return CONFIRMATION.read_text(encoding="utf-8")


def test_r41_confirmation_records_view_resolved_automation_id() -> None:
    source = _confirmation_source()

    for expected in [
        "Automation id: `biodesign-v2-7-09-00-final-timed-audit`",
        "`automation_update` view resolved `biodesign-v2-7-09-00-final-timed-audit`",
        "rendered the automation card in the app",
        "Target checkpoint: 2026-07-04 09:00 Asia/Shanghai",
    ]:
        assert expected in source


def test_r41_confirmation_rejects_invalid_shell_probe_as_evidence() -> None:
    source = _confirmation_source()

    for expected in [
        "`$env:CODEX_HOME` was empty",
        "searched the wrong location",
        "unrelated permission-denied paths",
        "not used as completion evidence",
        "not used as completion evidence, product evidence, or automation configuration evidence",
    ]:
        assert expected in source


def test_r41_confirmation_is_nonfinal_and_preserves_boundaries() -> None:
    source = _confirmation_source().lower()

    assert "this confirmation is not final checkpoint evidence" in source
    assert "active goal must remain open" in source
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
