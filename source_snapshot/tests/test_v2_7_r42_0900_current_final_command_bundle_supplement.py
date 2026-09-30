from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPLEMENT = ROOT / "docs" / "qa" / "V2_7_R42_0900_CURRENT_FINAL_COMMAND_BUNDLE_SUPPLEMENT.md"


def _supplement_source() -> str:
    return SUPPLEMENT.read_text(encoding="utf-8")


def test_r42_supplement_lists_post_r33_guard_tests() -> None:
    source = _supplement_source()

    for expected in [
        "tests/test_v2_7_r38_pre_0900_completion_claim_guard.py",
        "tests/test_v2_7_r39_pre_0900_heartbeat_readiness_audit.py",
        "tests/test_v2_7_r40_pre_0900_heartbeat_automation_handoff.py",
        "tests/test_v2_7_r41_pre_0900_automation_view_confirmation.py",
        "tests/test_v2_7_r42_0900_current_final_command_bundle_supplement.py",
    ]:
        assert expected in source


def test_r42_supplement_lists_required_final_repository_checks() -> None:
    source = _supplement_source()

    for expected in [
        "python -m py_compile",
        "python -m pytest",
        "git diff --check",
        "scripts/dev_autonomous_check.py --mode docs-only",
        "git status --short --untracked-files=all",
        "git diff --stat",
        "Changed-file copy denylist scan",
    ]:
        assert expected in source or expected.lower() in source.lower()


def test_r42_supplement_is_nonfinal_and_preserves_boundaries() -> None:
    source = _supplement_source().lower()

    assert "does not make the active goal complete" in source
    assert "r35 completion criteria and r37 decision rules still apply" in source
    assert "at or after 2026-07-04 09:00 asia/shanghai" in source
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
