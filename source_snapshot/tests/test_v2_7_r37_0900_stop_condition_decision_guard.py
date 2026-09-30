from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "docs" / "qa" / "V2_7_R37_0900_STOP_CONDITION_DECISION_GUARD.md"


def _decision_source() -> str:
    return DECISION.read_text(encoding="utf-8")


def test_r37_decision_rules_require_final_audit_before_completion() -> None:
    source = _decision_source()

    for expected in [
        "only after the final timed readiness audit runs at or after 2026-07-04 09:00 Asia/Shanghai",
        "If every R35 completion criterion is satisfied, the active goal may be marked complete.",
        "If final evidence is missing or indirect, do not mark the active goal complete",
    ]:
        assert expected in source


def test_r37_decision_rules_block_completion_on_failures_or_drift() -> None:
    source = _decision_source()

    for expected in [
        "If any required final command fails",
        "protected-area drift",
        "copy-boundary hits outside explicit policy or negative-test context",
        "product runtime drift outside the R20-covered Project Outputs files",
        "stop expanding scope",
    ]:
        assert expected in source


def test_r37_decision_rules_preserve_no_commit_policy() -> None:
    source = _decision_source()

    for expected in [
        "do not stage, commit, or tag even when all checks pass",
        "No staging, commit, or tag was performed for R37",
        "user has not explicitly authorized staging, commit, or tag creation",
    ]:
        assert expected in source


def test_r37_stop_rules_protect_high_risk_areas_and_copy_boundary() -> None:
    source = _decision_source().lower()

    for expected in [
        "database schema or migration paths",
        "import/export package schema paths",
        "services/project_import_service.py",
        "services/project_export_package_service.py",
        "expression wizard core algorithm paths",
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
