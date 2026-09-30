from __future__ import annotations

import re
from datetime import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTINUATION_NOTE = (
    ROOT / "docs" / "qa" / "V2_7_R46_PRE_0900_ACTIVE_GOAL_CONTINUATION_GUARD.md"
)


def _continuation_source() -> str:
    return CONTINUATION_NOTE.read_text(encoding="utf-8")


def test_r46_records_pre_checkpoint_active_goal_state() -> None:
    source = _continuation_source()

    for expected in [
        "Observed continuation time: 2026-07-04 04:46:50 +08:00",
        "Target checkpoint: 2026-07-04 09:00 Asia/Shanghai",
        "Observed active goal status: active",
        "pre-checkpoint work can strengthen the audit path",
    ]:
        assert expected in source


def test_r46_observed_time_is_before_target_checkpoint() -> None:
    source = _continuation_source()

    observed_match = re.search(r"Observed continuation time: \d{4}-\d{2}-\d{2} (\d{2}):(\d{2}):", source)
    target_match = re.search(r"Target checkpoint: \d{4}-\d{2}-\d{2} (\d{2}):(\d{2}) ", source)

    assert observed_match is not None
    assert target_match is not None

    observed = time(int(observed_match.group(1)), int(observed_match.group(2)))
    target = time(int(target_match.group(1)), int(target_match.group(2)))

    assert observed < target


def test_r46_keeps_final_decision_dependent_on_current_audit_chain() -> None:
    source = _continuation_source()

    for expected in [
        "R42 remains the current command-bundle source",
        "R43 remains the current final timed audit field list",
        "R44 remains the current final audit execution order",
        "R35 completion criteria and R37 decision rules still govern",
        "This R46 note is not final checkpoint evidence",
        "direct current evidence",
    ]:
        assert expected in source


def test_r46_preserves_documentation_only_boundary() -> None:
    source = _continuation_source().lower()

    for expected in [
        "documentation-only",
        "review-framed",
        "no staging, commit, or tag was performed",
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
