"""Validate a commit-bound V1 release evidence package."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs" / "release" / "v1_runtime_evidence.schema.json"
FORMAL_PRODUCT_BASE = "e41f4e606c7a6333f3ab973689afb7c2bd3d4b9d"
# Historical origin of the R1 Matrix identity, not a current-readiness claim.
MATRIX_ADOPTION_COMMIT = "0c50203eeb7c2b3970fd9414e7d18542c824a0d1"
MATRIX_PATH = ROOT / "docs" / "release" / "V1_RELEASE_READINESS_MATRIX_20260812.md"
RUNTIME_LOCK_PATH = ROOT / "requirements-runtime.lock"
MATRIX_SHA256 = hashlib.sha256(MATRIX_PATH.read_bytes()).hexdigest()
P0_ROW_IDS = {f"V1-{index:02d}" for index in range(1, 31)} - {"V1-23"}
REQUIRED_GATES = (
    "dependency_contract",
    "focused_pytest",
    "full_pytest",
    "import_smoke",
    "py_compile",
    "integrated_release_gate",
    "canonical_export_consistency",
    "git_diff_check",
    "clean_tree",
)
CANONICAL_ROLES = {
    "canonical_sequence": "canonical-sequence",
    "fasta": "fasta",
    "genbank": "genbank",
}


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _json_path(parts: Any) -> str:
    return ".".join(str(part) for part in parts) or "<root>"


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _safe_package_path(package_root: Path, raw_path: object) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    posix_path = PurePosixPath(raw_path.replace("\\", "/"))
    if posix_path.is_absolute() or ".." in posix_path.parts or posix_path.parts[0].endswith(":"):
        return None
    root = package_root.resolve()
    resolved = root.joinpath(*posix_path.parts).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_package_bytes(payload: dict[str, Any]) -> bytes:
    canonical = dict(payload)
    canonical.pop("package_id", None)
    return json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def package_id(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_package_bytes(payload)).hexdigest()


def _git_value(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _artifact_index(payload: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = artifact.get("id")
        artifact_path = artifact.get("path")
        if isinstance(artifact_id, str):
            if artifact_id in index:
                errors.append(f"duplicate artifact id: {artifact_id}")
            else:
                index[artifact_id] = artifact
        if isinstance(artifact_path, str):
            normalized = artifact_path.replace("\\", "/")
            if normalized in paths:
                errors.append(f"duplicate artifact path: {normalized}")
            paths.add(normalized)
    return index


def _require_artifact(
    artifact_id: object,
    expected_role: str | None,
    context: str,
    artifacts: dict[str, dict[str, Any]],
    errors: list[str],
) -> dict[str, Any] | None:
    if not isinstance(artifact_id, str) or artifact_id not in artifacts:
        errors.append(f"{context} references missing artifact: {artifact_id!r}")
        return None
    artifact = artifacts[artifact_id]
    if expected_role is not None and artifact.get("role") != expected_role:
        errors.append(
            f"{context} artifact {artifact_id} has role {artifact.get('role')!r}, "
            f"expected {expected_role!r}"
        )
    return artifact


def _validate_gate(
    run_id: str,
    gate_name: str,
    gate: object,
    artifacts: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    context = f"run {run_id} gate {gate_name}"
    if not isinstance(gate, dict):
        return
    _require_artifact(gate.get("output_artifact_id"), "command-output", context, artifacts, errors)
    if gate.get("result") == "PASS" and gate.get("returncode") != 0:
        errors.append(f"{context} reports PASS with a non-zero return code")
    if gate_name in {"focused_pytest", "full_pytest"}:
        counts = [
            gate.get(name)
            for name in ("collected", "passed", "failed", "errors", "skipped", "xfailed", "xpassed", "blocked")
        ]
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in counts):
            return
        collected, passed, failed, collection_errors, skipped, xfailed, xpassed, blocked = counts
        if gate.get("result") == "PASS":
            if failed != 0 or collection_errors != 0 or xfailed != 0 or xpassed != 0 or blocked != 0:
                errors.append(f"{context} reports PASS with pytest failures or collection errors")
            if passed + skipped != collected:
                errors.append(f"{context} pytest counts do not reconcile")
            if skipped and gate.get("skips_reviewed") is not True:
                errors.append(f"{context} reports PASS with unreviewed skips")
            skip_details = gate.get("skip_details")
            recorded_skip_count = len(skip_details) if isinstance(skip_details, list) else 0
            if skipped != recorded_skip_count:
                errors.append(f"{context} skip details do not match the skip count")


def validate(
    payload: dict[str, Any],
    *,
    expected_candidate_sha: str | None,
    expected_parent_sha: str | None = None,
    expected_matrix_revision_sha: str | None = None,
    package_root: Path | None = None,
) -> list[str]:
    """Return all structural, binding, and evidence-integrity errors."""

    errors: list[str] = []
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path)):
        errors.append(f"schema {_json_path(error.absolute_path)}: {error.message}")

    if payload.get("package_id") != package_id(payload):
        errors.append("package_id does not match canonical manifest content")

    candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
    if expected_candidate_sha is None:
        errors.append("expected candidate SHA is required for commit binding")
    elif candidate.get("commit") != expected_candidate_sha:
        errors.append(
            f"candidate.commit {candidate.get('commit')!r} does not match expected candidate "
            f"{expected_candidate_sha!r}"
        )
    if expected_parent_sha is not None and candidate.get("parent_commit") != expected_parent_sha:
        errors.append(
            f"candidate.parent_commit {candidate.get('parent_commit')!r} does not match "
            f"expected parent {expected_parent_sha!r}"
        )
    if candidate.get("formal_product_base") not in (None, FORMAL_PRODUCT_BASE):
        errors.append("candidate.formal_product_base does not match the adopted formal product base")

    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    if matrix.get("adoption_commit") not in (None, MATRIX_ADOPTION_COMMIT):
        errors.append("matrix adoption commit is stale or unsupported")
    if expected_matrix_revision_sha is None:
        errors.append("expected Matrix revision SHA is required for candidate binding")
    elif matrix.get("revision_commit") != expected_matrix_revision_sha:
        errors.append("matrix revision commit does not match the candidate checkout")
    if matrix.get("sha256") not in (None, MATRIX_SHA256):
        errors.append("matrix SHA-256 does not match the candidate checkout")

    artifacts = _artifact_index(payload, errors)
    if package_root is None:
        if payload.get("status") == "PASS":
            errors.append("PASS evidence requires package_root for file integrity verification")
    else:
        for artifact_id, artifact in artifacts.items():
            path = _safe_package_path(package_root, artifact.get("path"))
            if path is None:
                errors.append(f"artifact {artifact_id} path is absolute or escapes the package root")
                continue
            if not path.is_file():
                errors.append(f"artifact {artifact_id} is missing: {artifact.get('path')}")
                continue
            if path.stat().st_size != artifact.get("bytes"):
                errors.append(f"artifact {artifact_id} byte size does not match the manifest")
            if _sha256(path) != artifact.get("sha256"):
                errors.append(f"artifact {artifact_id} SHA-256 does not match the manifest")

    fixture = payload.get("fixture") if isinstance(payload.get("fixture"), dict) else {}
    fixture_artifact = _require_artifact(
        fixture.get("artifact_id"), "fixture", "fixture", artifacts, errors
    )
    if fixture_artifact is not None and fixture_artifact.get("sha256") != fixture.get("sha256"):
        errors.append("fixture hash does not match its artifact")

    runs = payload.get("runs") if isinstance(payload.get("runs"), list) else []
    environment_ids: set[str] = set()
    runtime_identities: list[tuple[object, ...]] = []
    cross_run_hashes: dict[str, set[str]] = {key: set() for key in CANONICAL_ROLES}
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_id = str(run.get("id", "?"))
        environment_id = run.get("environment_id")
        if isinstance(environment_id, str):
            if environment_id in environment_ids:
                errors.append("Run A and Run B must use distinct environment identities")
            environment_ids.add(environment_id)
        started_at = _parse_timestamp(run.get("started_at"))
        ended_at = _parse_timestamp(run.get("ended_at"))
        if started_at is not None and ended_at is not None and ended_at <= started_at:
            errors.append(f"run {run_id} ended_at must be later than started_at")

        runtime = run.get("runtime") if isinstance(run.get("runtime"), dict) else {}
        dependencies = runtime.get("dependencies") if isinstance(runtime.get("dependencies"), dict) else {}
        python_identity = runtime.get("python") if isinstance(runtime.get("python"), dict) else {}
        launcher = runtime.get("launcher") if isinstance(runtime.get("launcher"), dict) else {}
        launcher_path = ROOT / str(launcher.get("path") or "")
        launcher_module_path = ROOT / str(launcher.get("module_path") or "")
        if launcher_path.is_file() and launcher.get("sha256") != _sha256(launcher_path):
            errors.append(f"run {run_id} launcher SHA-256 does not match the candidate checkout")
        if launcher_module_path.is_file() and launcher.get("module_sha256") != _sha256(launcher_module_path):
            errors.append(f"run {run_id} launcher module SHA-256 does not match the candidate checkout")
        runtime_identities.append(
            (
                runtime.get("os"),
                runtime.get("architecture"),
                runtime.get("pointer_bits"),
                python_identity.get("implementation"),
                python_identity.get("version"),
                python_identity.get("executable_sha256"),
                runtime.get("streamlit"),
                runtime.get("pytest"),
                runtime.get("playwright"),
                launcher.get("sha256"),
                launcher.get("module_sha256"),
                dependencies.get("runtime_lock_sha256"),
                dependencies.get("inventory_sha256"),
            )
        )
        if dependencies.get("runtime_lock_sha256") not in (None, _sha256(RUNTIME_LOCK_PATH)):
            errors.append(f"run {run_id} runtime lock SHA-256 does not match the candidate checkout")
        dependency_artifact = _require_artifact(
            dependencies.get("inventory_artifact_id"),
            "dependency-inventory",
            f"run {run_id} dependency inventory",
            artifacts,
            errors,
        )
        if dependency_artifact is not None and dependency_artifact.get("sha256") != dependencies.get("inventory_sha256"):
            errors.append(f"run {run_id} dependency inventory hash does not match its artifact")
        if run.get("result") == "PASS" and dependencies.get("pip_check_returncode") != 0:
            errors.append(f"run {run_id} reports PASS with failed dependency validation")

        gates = run.get("gates") if isinstance(run.get("gates"), dict) else {}
        for gate_name in REQUIRED_GATES:
            _validate_gate(run_id, gate_name, gates.get(gate_name), artifacts, errors)
        if run.get("result") == "PASS" and any(
            not isinstance(gates.get(name), dict) or gates[name].get("result") != "PASS"
            for name in REQUIRED_GATES
        ):
            errors.append(f"run {run_id} reports PASS without every required test gate PASS")

        browser = run.get("browser") if isinstance(run.get("browser"), dict) else {}
        _require_artifact(browser.get("server_log_artifact_id"), "server-log", f"run {run_id} browser", artifacts, errors)
        for lane_name in ("desktop", "mobile"):
            lane = browser.get(lane_name) if isinstance(browser.get(lane_name), dict) else {}
            for screenshot_id in lane.get("screenshot_artifact_ids", []) if isinstance(lane.get("screenshot_artifact_ids"), list) else []:
                _require_artifact(screenshot_id, "screenshot", f"run {run_id} {lane_name}", artifacts, errors)
            if lane.get("result") == "PASS" and (
                lane.get("console_errors") != 0 or lane.get("network_failures") != 0
            ):
                errors.append(f"run {run_id} {lane_name} reports PASS with browser errors")
            expected_viewport = "1440x900" if lane_name == "desktop" else "390x844"
            if lane.get("viewport") not in (None, expected_viewport):
                errors.append(f"run {run_id} {lane_name} viewport does not match {expected_viewport}")
        if run.get("result") == "PASS" and (
            browser.get("page_errors") != 0
            or browser.get("server_exceptions") != 0
            or browser.get("new_context") is not True
            or browser.get("cold_reopen_complete") is not True
            or browser.get("process_cleanup_complete") is not True
            or browser.get("browser_cleanup_complete") is not True
            or browser.get("port_cleanup_complete") is not True
        ):
            errors.append(f"run {run_id} reports PASS without browser cold-start and cleanup completion")
        browser_started_at = _parse_timestamp(browser.get("started_at"))
        browser_stopped_at = _parse_timestamp(browser.get("stopped_at"))
        if (
            browser_started_at is not None
            and browser_stopped_at is not None
            and browser_stopped_at <= browser_started_at
        ):
            errors.append(f"run {run_id} browser stopped_at must be later than started_at")
        if (
            browser.get("initial_process_id") is not None
            and browser.get("initial_process_id") == browser.get("cold_reopen_process_id")
        ):
            errors.append(f"run {run_id} cold reopen must use a new server process")
        if run.get("result") == "PASS" and any(
            not isinstance(browser.get(lane), dict) or browser[lane].get("result") != "PASS"
            for lane in ("desktop", "mobile")
        ):
            errors.append(f"run {run_id} reports PASS without desktop and mobile browser PASS")

        bindings = run.get("canonical_artifacts") if isinstance(run.get("canonical_artifacts"), dict) else {}
        phase_hashes: dict[str, dict[str, str]] = {}
        for phase_name in ("pre_stop", "cold_reopen"):
            phase = bindings.get(phase_name) if isinstance(bindings.get(phase_name), dict) else {}
            phase_hashes[phase_name] = {}
            for binding_name, expected_role in CANONICAL_ROLES.items():
                binding = phase.get(binding_name) if isinstance(phase.get(binding_name), dict) else {}
                artifact = _require_artifact(
                    binding.get("artifact_id"),
                    expected_role,
                    f"run {run_id} {phase_name} {binding_name}",
                    artifacts,
                    errors,
                )
                binding_hash = binding.get("sha256")
                if artifact is not None and artifact.get("sha256") != binding_hash:
                    errors.append(f"run {run_id} {phase_name} {binding_name} hash does not match its artifact")
                if isinstance(binding_hash, str):
                    phase_hashes[phase_name][binding_name] = binding_hash
                    cross_run_hashes[binding_name].add(binding_hash)
        for binding_name in CANONICAL_ROLES:
            if (
                phase_hashes["pre_stop"].get(binding_name) is not None
                and phase_hashes["pre_stop"].get(binding_name)
                != phase_hashes["cold_reopen"].get(binding_name)
            ):
                errors.append(f"run {run_id} {binding_name} changed after cold reopen")

    for binding_name, hashes in cross_run_hashes.items():
        if len(hashes) > 1:
            errors.append(f"Run A and Run B {binding_name} hashes do not match")
    if len(runtime_identities) == 2 and runtime_identities[0] != runtime_identities[1]:
        errors.append("Run A and Run B runtime/dependency identities do not match")

    package_status = payload.get("status")
    matrix_rows = set(matrix.get("row_ids", [])) if isinstance(matrix.get("row_ids"), list) else set()
    if package_status == "PASS":
        if matrix_rows != P0_ROW_IDS:
            errors.append("PASS evidence must assess every V1 P0 Matrix row")
        if any(not isinstance(run, dict) or run.get("result") != "PASS" for run in runs):
            errors.append("package reports PASS without two PASS runs")

    release = payload.get("release_decision") if isinstance(payload.get("release_decision"), dict) else {}
    if release.get("decision") == "GO":
        p0_rows = release.get("p0_rows") if isinstance(release.get("p0_rows"), dict) else {}
        if set(p0_rows) != P0_ROW_IDS or any(status != "PASS" for status in p0_rows.values()):
            errors.append("release GO requires every V1 P0 Matrix row PASS")
        if release.get("unresolved_blockers") != []:
            errors.append("release GO requires zero unresolved blockers")
        if release.get("independent_runs_complete") is not True:
            errors.append("release GO requires both independent clean runs complete")
        if package_status != "PASS" or len(runs) != 2 or any(run.get("result") != "PASS" for run in runs if isinstance(run, dict)):
            errors.append("release GO requires a PASS evidence package with Run A and Run B PASS")

    return sorted(set(errors))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="path to evidence.json")
    parser.add_argument("--package-root", type=Path, help="evidence package root; defaults to evidence.json parent")
    parser.add_argument("--expected-candidate", help="expected 40-character candidate SHA; defaults to repository HEAD")
    parser.add_argument("--expected-parent", help="expected candidate parent SHA; defaults to repository HEAD parent")
    parser.add_argument("--expected-matrix-revision", help="latest candidate commit that changed the Matrix")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = json.loads(args.evidence.read_text(encoding="utf-8"))
        expected_candidate = args.expected_candidate or _git_value("rev-parse", "HEAD")
        expected_parent = args.expected_parent or _git_value("rev-parse", "HEAD^")
        expected_matrix_revision = args.expected_matrix_revision or _git_value(
            "log", "-1", "--format=%H", "--", str(MATRIX_PATH.relative_to(ROOT))
        )
        errors = validate(
            payload,
            expected_candidate_sha=expected_candidate,
            expected_parent_sha=expected_parent,
            expected_matrix_revision_sha=expected_matrix_revision,
            package_root=args.package_root or args.evidence.parent,
        )
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"BLOCKER: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"BLOCKER: {error}", file=sys.stderr)
        return 1
    print("PASS: evidence package satisfies the V1 runtime evidence contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
