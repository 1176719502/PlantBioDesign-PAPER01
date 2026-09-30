from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_REFRESH = ROOT / "docs" / "qa" / "V2_7_R45_0900_HEARTBEAT_PROMPT_REFRESH.md"


def _prompt_refresh_source() -> str:
    return PROMPT_REFRESH.read_text(encoding="utf-8")


def test_r45_records_heartbeat_prompt_refresh_target() -> None:
    source = _prompt_refresh_source()

    for expected in [
        "Automation id: `biodesign-v2-7-09-00-final-timed-audit`",
        "Updated the heartbeat automation prompt",
        "mode `update`",
        "Target checkpoint: 2026-07-04 09:00 Asia/Shanghai",
    ]:
        assert expected in source


def test_r45_prompt_refresh_points_to_current_audit_plan() -> None:
    source = _prompt_refresh_source()

    for expected in [
        "docs/qa/V2_7_R44_0900_FINAL_AUDIT_EXECUTION_ORDER.md",
        "Use the R42 current final command bundle",
        "Fill the R43 final timed audit fields",
        "Apply the R35 completion criteria",
        "Apply the R37 decision rules",
        "Record direct command-output evidence before any completion claim",
    ]:
        assert expected in source


def test_r45_prompt_refresh_is_nonfinal_and_preserves_boundaries() -> None:
    source = _prompt_refresh_source().lower()

    assert "this prompt refresh is not final checkpoint evidence" in source
    assert "active goal must remain open" in source
    assert "direct current evidence" in source
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
