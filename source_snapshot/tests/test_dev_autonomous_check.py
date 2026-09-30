from __future__ import annotations

import importlib.util
import shutil
import sys
import uuid
from pathlib import Path
from typing import Sequence

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev_autonomous_check.py"

spec = importlib.util.spec_from_file_location("dev_autonomous_check", SCRIPT)
dev_check = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["dev_autonomous_check"] = dev_check
spec.loader.exec_module(dev_check)


@pytest.fixture
def tmp_path() -> Path:
    base = ROOT / ".codex_tmp" / "test_dev_autonomous_check"
    path = base / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _result(command: Sequence[str], returncode: int = 0, stdout: str = "", stderr: str = ""):
    return dev_check.CommandResult(
        command=" ".join(command),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_cleanup_candidate_classification_recognizes_cache_and_generated_artifacts(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / ".pytest_cache_v26_runner"
    cache_dir.mkdir()
    pycache_dir = tmp_path / "__pycache__"
    pycache_dir.mkdir()
    log_file = tmp_path / "pytest.log"
    log_file.write_text("local test output", encoding="utf-8")
    product_file = tmp_path / "app.py"
    product_file.write_text("print('keep')\n", encoding="utf-8")

    candidates = {
        dev_check.repo_relative(path, tmp_path)
        for path in dev_check.collect_cleanup_candidates(tmp_path)
    }

    assert ".pytest_cache_v26_runner" in candidates
    assert "__pycache__" in candidates
    assert "pytest.log" in candidates
    assert "app.py" not in candidates


def test_tracked_cleanup_shaped_files_are_skipped_and_deferred(tmp_path: Path) -> None:
    tracked_log = tmp_path / "pytest.log"
    tracked_log.write_text("tracked diagnostic log", encoding="utf-8")
    ignored_cache = tmp_path / ".pytest_cache_v26_runner"
    ignored_cache.mkdir()

    classification = dev_check.classify_cleanup_candidates(
        root=tmp_path,
        candidates=[tracked_log, ignored_cache],
        tracked_files={"pytest.log"},
        ignored_files={".pytest_cache_v26_runner"},
    )

    assert classification.eligible_for_delete == [".pytest_cache_v26_runner"]
    assert classification.skipped_tracked_files == ["pytest.log"]
    assert classification.deferred_ambiguous_items == []


def test_cleanup_dry_run_does_not_delete_files_or_directories(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".pytest_cache_v26_runner"
    cache_dir.mkdir()
    cache_file = cache_dir / "README.md"
    cache_file.write_text("cache", encoding="utf-8")
    log_file = tmp_path / "pytest.log"
    log_file.write_text("log", encoding="utf-8")

    deletion_result = dev_check.delete_cleanup_candidates(
        tmp_path,
        [".pytest_cache_v26_runner", "pytest.log"],
        dry_run=True,
    )

    assert deletion_result.deleted_files == []
    assert deletion_result.failed_delete_items == []
    assert cache_dir.exists()
    assert log_file.exists()


def test_cleanup_delete_removes_only_explicit_eligible_paths(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".pytest_cache_v26_runner"
    cache_dir.mkdir()
    (cache_dir / "README.md").write_text("cache", encoding="utf-8")
    product_file = tmp_path / "app.py"
    product_file.write_text("print('keep')\n", encoding="utf-8")

    deletion_result = dev_check.delete_cleanup_candidates(
        tmp_path,
        [".pytest_cache_v26_runner"],
        dry_run=False,
    )

    assert deletion_result.deleted_files == [".pytest_cache_v26_runner"]
    assert deletion_result.failed_delete_items == []
    assert not cache_dir.exists()
    assert product_file.exists()


def test_cleanup_delete_records_failure_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_cache = tmp_path / ".pytest_cache_blocked"
    blocked_cache.mkdir()
    (blocked_cache / "README.md").write_text("blocked", encoding="utf-8")
    removable_cache = tmp_path / ".pytest_cache_removable"
    removable_cache.mkdir()
    (removable_cache / "README.md").write_text("removable", encoding="utf-8")

    real_rmtree = dev_check.shutil.rmtree

    def fake_rmtree(path: Path) -> None:
        if Path(path).name == ".pytest_cache_blocked":
            raise PermissionError("access denied for test")
        real_rmtree(path)

    monkeypatch.setattr(dev_check.shutil, "rmtree", fake_rmtree)

    deletion_result = dev_check.delete_cleanup_candidates(
        tmp_path,
        [".pytest_cache_blocked", ".pytest_cache_removable"],
        dry_run=False,
    )

    assert deletion_result.deleted_files == [".pytest_cache_removable"]
    assert deletion_result.failed_delete_items == [
        {
            "path": ".pytest_cache_blocked",
            "error_type": "PermissionError",
            "reason": "access denied for test",
        }
    ]
    assert blocked_cache.exists()
    assert not removable_cache.exists()


def test_docs_only_report_runs_diff_check_and_changed_docs_copy_scan(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs" / "dev"
    docs_dir.mkdir(parents=True)
    workflow_doc = docs_dir / "CODEX_AUTONOMOUS_WORKFLOW.md"
    workflow_doc.write_text(
        "This local runner is documentation-only and does not certify experimental readiness.\n",
        encoding="utf-8",
    )

    def fake_runner(command: Sequence[str], cwd: Path):
        if tuple(command) == ("git", "diff", "--check"):
            return _result(command)
        if tuple(command) == ("git", "status", "--short"):
            return _result(command, stdout=" M docs/dev/CODEX_AUTONOMOUS_WORKFLOW.md\n")
        raise AssertionError(f"unexpected command: {command}")

    report = dev_check.run_autonomous_check(
        mode="docs-only",
        root=tmp_path,
        runner=fake_runner,
    )

    assert report["mode"] == "docs-only"
    assert report["commands_run"] == ["git diff --check", "git status --short"]
    assert report["copy_denylist_scan"]["passed"] is True
    assert report["copy_denylist_scan"]["scanned_files"] == [
        "docs/dev/CODEX_AUTONOMOUS_WORKFLOW.md"
    ]
    assert "pytest is intentionally skipped" in report["next_recommended_action"]
    assert report["blocked_reason"] == ""
    assert report["failure_type"] == ""
    assert report["failed_command"] == ""
    assert report["resume_hint"] == ""


def test_docs_only_report_sets_blocked_fields_on_diff_check_failure(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs" / "dev"
    docs_dir.mkdir(parents=True)
    workflow_doc = docs_dir / "CODEX_AUTONOMOUS_WORKFLOW.md"
    workflow_doc.write_text(
        "This local runner is documentation-only and does not certify experimental readiness.\n",
        encoding="utf-8",
    )

    def fake_runner(command: Sequence[str], cwd: Path):
        if tuple(command) == ("git", "diff", "--check"):
            return _result(command, returncode=1, stderr="whitespace error")
        if tuple(command) == ("git", "status", "--short"):
            return _result(command, stdout=" M docs/dev/CODEX_AUTONOMOUS_WORKFLOW.md\n")
        raise AssertionError(f"unexpected command: {command}")

    report = dev_check.run_autonomous_check(
        mode="docs-only",
        root=tmp_path,
        runner=fake_runner,
    )

    assert report["blocked_reason"] == "git diff --check failed."
    assert report["failure_type"] == "test_check"
    assert report["failed_command"] == "git diff --check"
    assert "Fix the patch formatting issue" in report["resume_hint"]
    assert "Not safe to commit" in report["safe_to_commit_assessment"]


def test_cleanup_hygiene_report_lists_candidates_without_clean_flag(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".pytest_cache_v26_runner"
    cache_dir.mkdir()
    tracked_log = tmp_path / "pytest.log"
    tracked_log.write_text("tracked", encoding="utf-8")
    ambiguous_log = tmp_path / "manual.log"
    ambiguous_log.write_text("manual", encoding="utf-8")

    def fake_runner(command: Sequence[str], cwd: Path):
        command_tuple = tuple(command)
        if command_tuple == ("git", "status", "--short"):
            return _result(command)
        if command_tuple == ("git", "ls-files"):
            return _result(command, stdout="pytest.log\n")
        if command_tuple[:3] == ("git", "check-ignore", "-q"):
            relative = command_tuple[-1]
            return _result(command, returncode=0 if relative == ".pytest_cache_v26_runner" else 1)
        raise AssertionError(f"unexpected command: {command}")

    report = dev_check.run_autonomous_check(
        mode="cleanup-hygiene",
        root=tmp_path,
        clean_local_cache=False,
        dry_run=True,
        runner=fake_runner,
    )

    assert report["cleanup_candidates"] == [
        ".pytest_cache_v26_runner",
        "manual.log",
        "pytest.log",
    ]
    assert report["eligible_for_delete"] == [".pytest_cache_v26_runner"]
    assert report["deleted_files"] == []
    assert report["skipped_tracked_files"] == ["pytest.log"]
    assert report["deferred_ambiguous_items"] == ["manual.log"]
    assert cache_dir.exists()


def test_cleanup_hygiene_report_records_delete_failures_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_cache = tmp_path / ".pytest_cache_blocked"
    blocked_cache.mkdir()
    (blocked_cache / "README.md").write_text("blocked", encoding="utf-8")
    removable_cache = tmp_path / ".pytest_cache_removable"
    removable_cache.mkdir()
    (removable_cache / "README.md").write_text("removable", encoding="utf-8")

    real_rmtree = dev_check.shutil.rmtree

    def fake_rmtree(path: Path) -> None:
        if Path(path).name == ".pytest_cache_blocked":
            raise PermissionError("access denied for test")
        real_rmtree(path)

    monkeypatch.setattr(dev_check.shutil, "rmtree", fake_rmtree)

    def fake_runner(command: Sequence[str], cwd: Path):
        command_tuple = tuple(command)
        if command_tuple == ("git", "status", "--short"):
            return _result(command)
        if command_tuple == ("git", "ls-files"):
            return _result(command)
        if command_tuple[:3] == ("git", "check-ignore", "-q"):
            return _result(command, returncode=0)
        raise AssertionError(f"unexpected command: {command}")

    report = dev_check.run_autonomous_check(
        mode="cleanup-hygiene",
        root=tmp_path,
        clean_local_cache=True,
        dry_run=False,
        runner=fake_runner,
    )

    assert report["deleted_files"] == [".pytest_cache_removable"]
    assert report["failed_delete_items"] == [
        {
            "path": ".pytest_cache_blocked",
            "error_type": "PermissionError",
            "reason": "access denied for test",
        }
    ]
    assert report["blocked_reason"] == "Cleanup deletion failed for .pytest_cache_blocked with PermissionError."
    assert report["failure_type"] == "filesystem"
    assert report["failed_command"] == "delete_cleanup_candidates"
    assert "Clear the lock or permission issue" in report["resume_hint"]
    assert "Some ignored local cleanup candidates could not be deleted and were deferred." in report["risks"]
    assert blocked_cache.exists()
    assert not removable_cache.exists()


@pytest.mark.parametrize(
    (
        "failure_type",
        "failed_command",
        "blocked_reason",
        "resume_hint",
        "safe_to_commit_assessment",
    ),
    [
        (
            "approval_service",
            "git commit -m Add failure recovery simulation coverage",
            "Approval service returned 502 while requesting a required git metadata write.",
            "Resume from the last clean commit/tag after the approval service is available.",
            "Not safe to commit until the approval result is known and staging is rechecked.",
        ),
        (
            "network",
            "python -m pip install example-package",
            "Network unavailable while resolving a package install request.",
            "Mark blocked; retry only after network access is restored and do not guess the install result.",
            "Not safe to commit because dependency state could not be verified.",
        ),
        (
            "test_timeout",
            "python -m pytest tests/test_dev_autonomous_check.py -vv -s",
            "Focused pytest command timed out before a reliable pass/fail result was produced.",
            "Resume by rerunning the same focused test command once the timeout cause is understood.",
            "Not safe to commit until the focused test command completes successfully.",
        ),
        (
            "filesystem",
            "delete_cleanup_candidates",
            "Cleanup candidate was locked by another process and could not be removed.",
            "Clear the file lock, preserve the working tree, and rerun cleanup-hygiene without guessing.",
            "Not safe to commit until locked cleanup items are resolved or explicitly deferred.",
        ),
    ],
)
def test_blocked_report_fields_support_runner_safe_failure_simulations(
    failure_type: str,
    failed_command: str,
    blocked_reason: str,
    resume_hint: str,
    safe_to_commit_assessment: str,
) -> None:
    report = dev_check.base_report(
        mode="test-fix-check",
        clean_local_cache=False,
        dry_run=True,
    )

    dev_check.set_blocked_report(
        report,
        failure_type=failure_type,
        failed_command=failed_command,
        blocked_reason=blocked_reason,
        resume_hint=resume_hint,
        safe_to_commit_assessment=safe_to_commit_assessment,
    )

    for field in (
        "failure_type",
        "blocked_reason",
        "failed_command",
        "resume_hint",
        "safe_to_commit_assessment",
    ):
        assert report[field]

    assert report["failure_type"] == failure_type
    assert report["failed_command"] == failed_command
    assert report["blocked_reason"] == blocked_reason
    assert report["resume_hint"] == resume_hint
    assert report["safe_to_commit_assessment"] == safe_to_commit_assessment


def test_parse_status_paths_preserves_modified_and_renamed_paths() -> None:
    parsed = dev_check.parse_status_paths(
        " M docs/dev/CODEX_AUTONOMOUS_WORKFLOW.md\nR  old.md -> new.md\n?? scripts/dev_autonomous_check.py\n"
    )

    assert parsed == [
        "docs/dev/CODEX_AUTONOMOUS_WORKFLOW.md",
        "new.md",
        "scripts/dev_autonomous_check.py",
    ]
