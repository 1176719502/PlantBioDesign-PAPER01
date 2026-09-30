from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORDER_NOTE = ROOT / "docs" / "qa" / "V2_7_R44_0900_FINAL_AUDIT_EXECUTION_ORDER.md"


def _order_source() -> str:
    return ORDER_NOTE.read_text(encoding="utf-8")


def test_r44_order_references_current_command_fields_and_rules() -> None:
    source = _order_source()

    for expected in [
        "R42 defines the current command bundle",
        "R43 defines the current audit fields",
        "R37 defines decision rules",
        "Apply the R35 completion criteria",
        "Apply the R37 decision rules",
    ]:
        assert expected in source


def test_r44_order_sequences_final_audit_before_completion() -> None:
    source = _order_source()

    expected_order = [
        "Confirm the current local time",
        "Read the active goal",
        "Inspect `git status --short --untracked-files=all`",
        "Run the R42 current final command bundle",
        "Run changed-file copy-safety review",
        "Fill the R43 final timed audit fields",
        "Apply the R35 completion criteria",
        "Apply the R37 decision rules",
        "mark the active goal complete",
    ]
    positions = [source.index(item) for item in expected_order]
    assert positions == sorted(positions)


def test_r44_order_blocks_premature_completion_and_commit_actions() -> None:
    source = _order_source().lower()

    for expected in [
        "do not mark the goal complete before running the r42 command bundle",
        "do not apply r37 decision rules before filling the r43 fields",
        "do not stage, commit, or tag before the final audit records the remaining git status",
        "do not use pre-09:00 heartbeat, dry-run, or template evidence as final checkpoint evidence",
        "no staging, commit, or tag was performed",
        "documentation-only",
        "review-framed",
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
