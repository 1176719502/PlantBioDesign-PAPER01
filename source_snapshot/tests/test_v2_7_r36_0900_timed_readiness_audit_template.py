from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "qa" / "V2_7_R36_0900_TIMED_READINESS_AUDIT_TEMPLATE.md"


def _template_source() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_r36_template_requires_at_or_after_0900_evidence() -> None:
    source = _template_source()

    for expected in [
        "Fill these fields only at or after 2026-07-04 09:00 Asia/Shanghai",
        "This template is not final evidence",
        "R35 completion criteria are satisfied",
        "PENDING_FINAL_AUDIT",
    ]:
        assert expected in source


def test_r36_template_lists_required_final_audit_fields() -> None:
    source = _template_source()

    for expected in [
        "Actual checkpoint time",
        "R33 final command bundle rerun",
        "`py_compile` result",
        "Focused pytest result",
        "`git diff --check` result",
        "Docs-only runner result",
        "Copy denylist scan result",
        "`git status --short --untracked-files=all` result",
        "`git diff --stat` result",
        "Protected-area drift review",
        "Documentation-only boundary review",
        "Staging/commit/tag status",
        "Remaining git status summary",
        "R35 completion criteria satisfied",
    ]:
        assert expected in source


def test_r36_template_lists_r33_final_commands() -> None:
    source = _template_source()

    for expected in [
        "tests/test_v2_7_r10_r30_live_worktree_inventory_guard.py",
        "tests/test_v2_7_r20_r31_post_full_regression_scope_guard.py",
        "tests/test_v2_7_r10_r28_qa_note_structure_refresh.py",
        "tests/test_v2_7_r10_r25_checkpoint_copy_boundary.py",
        "tests/test_v2_7_r33_0900_final_check_command_bundle.py",
        "git diff --check",
        "scripts/dev_autonomous_check.py --mode docs-only",
        "git status --short --untracked-files=all",
        "git diff --stat",
    ]:
        assert expected in source


def test_r36_template_preserves_no_commit_and_copy_boundary() -> None:
    source = _template_source().lower()

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
