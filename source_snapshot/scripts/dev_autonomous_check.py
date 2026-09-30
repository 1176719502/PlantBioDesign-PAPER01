from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]

MODES = ("docs-only", "cleanup-hygiene", "test-fix-check", "full-check")

FORBIDDEN_COPY_PHRASES = (
    "successful import",
    "project imported",
    "ready for execution",
    "experiment-ready",
    "production-ready",
    "validated construct",
    "optimized pathway",
    "yield prediction",
    "lab-ready",
    "wet-lab ready",
    "proven construct",
    "validated pathway",
)

NEGATIVE_CONTEXT_RE = re.compile(
    r"\b("
    r"no|not|never|without|avoid|forbid(?:den)?|denylist|"
    r"does not|do not|must not|should not|cannot|"
    r"not a|not an|not imply|not claim|not treated|"
    r"does not imply|does not certify|does not predict|does not optimize|"
    r"guardrail|safety boundary|blocked|skip|skipped"
    r")\b"
)

CACHE_DIR_NAMES = {
    "__pycache__",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    ".tmppytest",
    ".tmp_pytest",
    ".tmp_pytest_cache",
    ".tmp_pytest_run",
    "htmlcov",
}

CACHE_DIR_PREFIXES = (
    ".pytest_cache",
    ".pytest_tmp",
    ".tmp",
)

GENERATED_FILE_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".log",
    ".coverage",
)

PROTECTED_PATH_MARKERS = (
    "ai literature research",
    "ai_literature_research",
)

PRUNED_SCAN_DIRS = {
    ".git",
    ".venv",
    ".venv_primer3_test",
    "archive",
    "archive_v1_dormant",
    "data",
    "docs",
    "views",
    "services",
    "core",
    "components",
    "locales",
    "utils",
}


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class CleanupClassification:
    cleanup_candidates: list[str]
    eligible_for_delete: list[str]
    skipped_tracked_files: list[str]
    deferred_ambiguous_items: list[str]
    protected_skipped_items: list[str]


@dataclass
class CleanupDeletionResult:
    deleted_files: list[str]
    failed_delete_items: list[dict[str, str]]


CommandRunner = Callable[[Sequence[str], Path], CommandResult]


def repo_relative(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        relative = path
    return relative.as_posix()


def run_command(command: Sequence[str], cwd: Path) -> CommandResult:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        command=" ".join(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def is_cleanup_candidate(path: Path) -> bool:
    name = path.name
    lower_name = name.lower()
    if path.is_dir():
        return name in CACHE_DIR_NAMES or any(name.startswith(prefix) for prefix in CACHE_DIR_PREFIXES)
    return lower_name.endswith(GENERATED_FILE_SUFFIXES)


def is_protected_path(path: Path) -> bool:
    normalized = path.as_posix().lower()
    return any(marker in normalized for marker in PROTECTED_PATH_MARKERS)


def collect_cleanup_candidates(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for current_root, dirs, files in os.walk(root):
        current = Path(current_root)
        dirs[:] = [
            directory
            for directory in dirs
            if directory not in PRUNED_SCAN_DIRS and not is_protected_path(current / directory)
        ]

        for directory in list(dirs):
            path = current / directory
            if is_cleanup_candidate(path):
                candidates.append(path)
                dirs.remove(directory)

        for filename in files:
            path = current / filename
            if is_cleanup_candidate(path) and not is_protected_path(path):
                candidates.append(path)

    return sorted(candidates, key=lambda item: repo_relative(item, root))


def list_git_files(command: Sequence[str], root: Path, runner: CommandRunner) -> tuple[set[str], CommandResult]:
    result = runner(command, root)
    files = {
        line.strip().replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.strip()
    }
    return files, result


def check_git_ignored(paths: Iterable[Path], root: Path, runner: CommandRunner) -> tuple[set[str], list[CommandResult]]:
    ignored: set[str] = set()
    results: list[CommandResult] = []
    for path in paths:
        relative = repo_relative(path, root)
        result = runner(("git", "check-ignore", "-q", "--", relative), root)
        results.append(result)
        if result.returncode == 0:
            ignored.add(relative)
    return ignored, results


def classify_cleanup_candidates(
    root: Path,
    candidates: Iterable[Path],
    tracked_files: set[str],
    ignored_files: set[str],
) -> CleanupClassification:
    cleanup_candidates: list[str] = []
    eligible_for_delete: list[str] = []
    skipped_tracked_files: list[str] = []
    deferred_ambiguous_items: list[str] = []
    protected_skipped_items: list[str] = []

    for path in sorted(candidates, key=lambda item: repo_relative(item, root)):
        relative = repo_relative(path, root)
        cleanup_candidates.append(relative)

        if is_protected_path(path):
            protected_skipped_items.append(relative)
        elif relative in tracked_files:
            skipped_tracked_files.append(relative)
        elif relative in ignored_files:
            eligible_for_delete.append(relative)
        else:
            deferred_ambiguous_items.append(relative)

    return CleanupClassification(
        cleanup_candidates=cleanup_candidates,
        eligible_for_delete=eligible_for_delete,
        skipped_tracked_files=skipped_tracked_files,
        deferred_ambiguous_items=deferred_ambiguous_items,
        protected_skipped_items=protected_skipped_items,
    )


def deletion_failure_entry(relative: str, error: Exception) -> dict[str, str]:
    return {
        "path": relative,
        "error_type": type(error).__name__,
        "reason": str(error),
    }


def delete_cleanup_candidates(root: Path, relative_paths: Iterable[str], dry_run: bool) -> CleanupDeletionResult:
    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    for relative in relative_paths:
        path = (root / relative).resolve()
        if root.resolve() not in path.parents and path != root.resolve():
            failed.append(
                {
                    "path": relative,
                    "error_type": "UnsafePath",
                    "reason": "Resolved path is outside the repository root.",
                }
            )
            continue
        if dry_run:
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
                deleted.append(relative)
            elif path.exists():
                path.unlink()
                deleted.append(relative)
        except PermissionError as error:
            failed.append(deletion_failure_entry(relative, error))
        except OSError as error:
            failed.append(deletion_failure_entry(relative, error))
        except Exception as error:
            failed.append(deletion_failure_entry(relative, error))
    return CleanupDeletionResult(deleted_files=deleted, failed_delete_items=failed)


def parse_status_paths(status_output: str) -> list[str]:
    paths: list[str] = []
    for line in status_output.splitlines():
        if not line.strip():
            continue
        payload = line[3:].strip()
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        paths.append(payload.replace("\\", "/").strip('"'))
    return paths


def changed_docs_from_status(root: Path, runner: CommandRunner) -> tuple[list[Path], CommandResult]:
    result = runner(("git", "status", "--short"), root)
    docs: list[Path] = []
    for relative in parse_status_paths(result.stdout):
        path = root / relative
        if path.suffix.lower() == ".md" and path.exists():
            docs.append(path)
    return sorted(docs), result


def scan_copy_denylist(paths: Iterable[Path], root: Path) -> dict[str, object]:
    hits: list[dict[str, object]] = []
    scanned_files: list[str] = []
    for path in sorted(paths):
        relative = repo_relative(path, root)
        scanned_files.append(relative)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            normalized = line.lower()
            if NEGATIVE_CONTEXT_RE.search(normalized):
                continue
            for phrase in FORBIDDEN_COPY_PHRASES:
                if phrase in normalized:
                    hits.append(
                        {
                            "file": relative,
                            "line": line_number,
                            "phrase": phrase,
                        }
                    )
    return {
        "scanned_files": scanned_files,
        "forbidden_phrases": list(FORBIDDEN_COPY_PHRASES),
        "hits": hits,
        "passed": not hits,
    }


def command_result_entry(result: CommandResult) -> dict[str, object]:
    return asdict(result)


def base_report(mode: str, clean_local_cache: bool, dry_run: bool) -> dict[str, object]:
    return {
        "mode": mode,
        "clean_local_cache": clean_local_cache,
        "dry_run": dry_run,
        "commands_run": [],
        "command_results": [],
        "command_plan": [],
        "cleanup_candidates": [],
        "deleted_files": [],
        "failed_delete_items": [],
        "skipped_tracked_files": [],
        "deferred_ambiguous_items": [],
        "risks": [],
        "blocked_reason": "",
        "failure_type": "",
        "failed_command": "",
        "resume_hint": "",
        "safe_to_commit_assessment": "",
        "next_recommended_action": "",
    }


def add_command_result(report: dict[str, object], result: CommandResult) -> None:
    report["commands_run"].append(result.command)
    report["command_results"].append(command_result_entry(result))


def set_blocked_report(
    report: dict[str, object],
    *,
    failure_type: str,
    failed_command: str,
    blocked_reason: str,
    resume_hint: str,
    safe_to_commit_assessment: str,
) -> None:
    if not report["blocked_reason"]:
        report["blocked_reason"] = blocked_reason
    if not report["failure_type"]:
        report["failure_type"] = failure_type
    if not report["failed_command"]:
        report["failed_command"] = failed_command
    if not report["resume_hint"]:
        report["resume_hint"] = resume_hint
    if not report["safe_to_commit_assessment"]:
        report["safe_to_commit_assessment"] = safe_to_commit_assessment


def run_diff_check(report: dict[str, object], root: Path, runner: CommandRunner) -> None:
    result = runner(("git", "diff", "--check"), root)
    add_command_result(report, result)
    if result.returncode != 0:
        report["risks"].append("git diff --check reported whitespace or patch errors.")
        set_blocked_report(
            report,
            failure_type="test_check",
            failed_command=result.command,
            blocked_reason="git diff --check failed.",
            resume_hint="Fix the patch formatting issue, then rerun the same check from the last clean state.",
            safe_to_commit_assessment="Not safe to commit until git diff --check passes.",
        )


def run_copy_scan(report: dict[str, object], root: Path, runner: CommandRunner) -> None:
    docs, status_result = changed_docs_from_status(root, runner)
    add_command_result(report, status_result)
    scan = scan_copy_denylist(docs, root)
    report["copy_denylist_scan"] = scan
    if not scan["passed"]:
        report["risks"].append("Changed documentation contains copy denylist hits outside negative boundary context.")


def run_cleanup_hygiene(
    report: dict[str, object],
    root: Path,
    runner: CommandRunner,
    clean_local_cache: bool,
    dry_run: bool,
) -> None:
    status_result = runner(("git", "status", "--short"), root)
    add_command_result(report, status_result)
    if status_result.returncode != 0:
        report["risks"].append("Could not inspect git status before cleanup candidate handling.")
        set_blocked_report(
            report,
            failure_type="infrastructure",
            failed_command=status_result.command,
            blocked_reason="git status --short failed before cleanup classification.",
            resume_hint="Restore git availability, then rerun cleanup-hygiene from the last clean commit/tag.",
            safe_to_commit_assessment="Not safe to commit until repository state can be inspected.",
        )

    tracked_files, ls_result = list_git_files(("git", "ls-files"), root, runner)
    add_command_result(report, ls_result)
    if ls_result.returncode != 0:
        report["risks"].append("Could not inspect tracked files; cleanup deletion remains disabled.")

    candidates = collect_cleanup_candidates(root)
    ignored_files, ignore_results = check_git_ignored(candidates, root, runner)
    for result in ignore_results:
        add_command_result(report, result)

    classification = classify_cleanup_candidates(root, candidates, tracked_files, ignored_files)
    report["cleanup_candidates"] = classification.cleanup_candidates
    report["eligible_for_delete"] = classification.eligible_for_delete
    report["skipped_tracked_files"] = classification.skipped_tracked_files
    report["deferred_ambiguous_items"] = (
        classification.deferred_ambiguous_items + classification.protected_skipped_items
    )

    if classification.skipped_tracked_files:
        report["risks"].append("Tracked cleanup-shaped paths were skipped and deferred for manual review.")
    if classification.protected_skipped_items:
        report["risks"].append("Protected AI Literature Research paths were skipped.")
    if classification.deferred_ambiguous_items:
        report["risks"].append("Unignored or ambiguous cleanup-shaped paths were deferred.")

    if clean_local_cache and ls_result.returncode == 0:
        deletion_result = delete_cleanup_candidates(
            root,
            classification.eligible_for_delete,
            dry_run=dry_run,
        )
        report["deleted_files"] = deletion_result.deleted_files
        report["failed_delete_items"] = deletion_result.failed_delete_items
        if deletion_result.failed_delete_items:
            report["risks"].append(
                "Some ignored local cleanup candidates could not be deleted and were deferred."
            )
            first_failed = deletion_result.failed_delete_items[0]
            set_blocked_report(
                report,
                failure_type="filesystem",
                failed_command="delete_cleanup_candidates",
                blocked_reason=(
                    f"Cleanup deletion failed for {first_failed['path']} "
                    f"with {first_failed['error_type']}."
                ),
                resume_hint=(
                    "Clear the lock or permission issue, then rerun cleanup-hygiene from the last clean state."
                ),
                safe_to_commit_assessment="Not safe to commit until blocked delete items are resolved.",
            )
    elif not clean_local_cache:
        report["risks"].append("Cleanup deletion was not requested; candidates were listed only.")


def run_autonomous_check(
    mode: str,
    root: Path = REPO_ROOT,
    clean_local_cache: bool = False,
    dry_run: bool = True,
    runner: CommandRunner = run_command,
) -> dict[str, object]:
    report = base_report(mode=mode, clean_local_cache=clean_local_cache, dry_run=dry_run)

    if mode == "docs-only":
        run_diff_check(report, root, runner)
        run_copy_scan(report, root, runner)
        report["next_recommended_action"] = (
            "Review git diff --check and copy scan results; pytest is intentionally skipped for docs-only mode."
        )
    elif mode == "cleanup-hygiene":
        run_cleanup_hygiene(report, root, runner, clean_local_cache, dry_run)
        report["next_recommended_action"] = (
            "Review eligible and deferred cleanup items before re-running with --clean-local-cache if deletion is intended."
        )
    elif mode == "test-fix-check":
        run_diff_check(report, root, runner)
        report["command_plan"] = [
            "Select the smallest targeted pytest command for the changed module.",
            "Run the targeted pytest command manually or via Codex.",
            "Have Codex inspect failures and apply the smallest safe fix; this runner does not modify code.",
        ]
        report["next_recommended_action"] = "Use the command plan to run targeted tests, then fix reported failures without hiding them."
    elif mode == "full-check":
        run_diff_check(report, root, runner)
        run_copy_scan(report, root, runner)
        report["command_plan"] = [
            "python -m pytest -vv -s",
        ]
        report["risks"].append("Full pytest is planned but not run automatically by this guardrail runner.")
        report["next_recommended_action"] = "Run the listed full pytest command before declaring the development stage complete."
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    return report


def write_report(report: dict[str, object], report_path: Path | None) -> None:
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text + "\n", encoding="utf-8")
    print(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local autonomous guardrail checks for BioDesign Studio."
    )
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument(
        "--clean-local-cache",
        action="store_true",
        help="Allow deletion of eligible ignored local cache artifacts in cleanup-hygiene mode.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        help="Optional JSON report path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force list-only behavior. This is the default unless --clean-local-cache is provided.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    effective_dry_run = args.dry_run or not args.clean_local_cache
    report = run_autonomous_check(
        mode=args.mode,
        root=REPO_ROOT,
        clean_local_cache=args.clean_local_cache,
        dry_run=effective_dry_run,
    )
    write_report(report, args.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
