from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.validation.validate_v1_release_evidence import (
    FORMAL_PRODUCT_BASE,
    MATRIX_ADOPTION_COMMIT,
    MATRIX_SHA256,
    P0_ROW_IDS,
    validate,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "release" / "v1_runtime_evidence.schema.json"
CONTRACT_PATH = ROOT / "docs" / "release" / "V1_RUNTIME_TEST_DURABLE_EVIDENCE_CONTRACT.md"
VALIDATOR_PATH = ROOT / "scripts" / "validation" / "validate_v1_release_evidence.py"
CANDIDATE = "c" * 40
PARENT = "d" * 40
MATRIX_REVISION = "8" * 40
TIMESTAMP = "2026-08-12T15:00:00+08:00"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_artifact(
    package_root: Path,
    artifacts: list[dict[str, object]],
    *,
    artifact_id: str,
    role: str,
    data: bytes,
) -> dict[str, object]:
    relative_path = f"artifacts/{artifact_id}.bin"
    path = package_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    record: dict[str, object] = {
        "id": artifact_id,
        "path": relative_path,
        "role": role,
        "sha256": _sha(data),
        "bytes": len(data),
        "created_at": TIMESTAMP,
    }
    artifacts.append(record)
    return record


def _gate(output_id: str, *, pytest: bool = False) -> dict[str, object]:
    gate: dict[str, object] = {
        "command": "python -m pytest -q" if pytest else "python gate.py",
        "returncode": 0,
        "result": "PASS",
        "output_artifact_id": output_id,
    }
    if pytest:
        gate.update(
            collected=12,
            passed=10,
            failed=0,
            errors=0,
            skipped=2,
            skips_reviewed=True,
            skip_details=["expected optional case one", "expected optional case two"],
            xfailed=0,
            xpassed=0,
            blocked=0,
        )
    return gate


def _run(
    package_root: Path,
    artifacts: list[dict[str, object]],
    run_id: str,
) -> dict[str, object]:
    prefix = run_id.lower()
    command_ids: dict[str, str] = {}
    for gate_name in (
        "dependency_contract",
        "focused_pytest",
        "full_pytest",
        "import_smoke",
        "py_compile",
        "integrated_release_gate",
        "canonical_export_consistency",
        "git_diff_check",
        "clean_tree",
    ):
        artifact_id = f"{prefix}-{gate_name}"
        _write_artifact(
            package_root,
            artifacts,
            artifact_id=artifact_id,
            role="command-output",
            data=f"{run_id} {gate_name} passed\n".encode(),
        )
        command_ids[gate_name] = artifact_id

    dependency = _write_artifact(
        package_root,
        artifacts,
        artifact_id=f"{prefix}-dependencies",
        role="dependency-inventory",
        data=b"biopython==1.87\nplaywright==1.61.0\npytest==8.4.2\nstreamlit==1.55.0\n",
    )
    _write_artifact(
        package_root,
        artifacts,
        artifact_id=f"{prefix}-server-log",
        role="server-log",
        data=f"server {run_id} HTTP 200\n".encode(),
    )
    for lane in ("desktop", "mobile"):
        _write_artifact(
            package_root,
            artifacts,
            artifact_id=f"{prefix}-{lane}-step6",
            role="screenshot",
            data=f"PNG {run_id} {lane}".encode(),
        )

    canonical_bindings: dict[str, dict[str, dict[str, str]]] = {}
    for phase in ("pre_stop", "cold_reopen"):
        canonical_bindings[phase] = {}
        for binding_name, role, data in (
            ("canonical_sequence", "canonical-sequence", b"AACCGGTT"),
            ("fasta", "fasta", b">fixture\nAACCGGTT\n"),
            ("genbank", "genbank", b"LOCUS fixture\nORIGIN\nAACCGGTT\n//\n"),
        ):
            artifact = _write_artifact(
                package_root,
                artifacts,
                artifact_id=f"{prefix}-{phase}-{binding_name}",
                role=role,
                data=data,
            )
            canonical_bindings[phase][binding_name] = {
                "artifact_id": str(artifact["id"]),
                "sha256": str(artifact["sha256"]),
            }

    gates = {
        name: _gate(artifact_id, pytest=name in {"focused_pytest", "full_pytest"})
        for name, artifact_id in command_ids.items()
    }
    return {
        "id": run_id,
        "environment_id": f"clean-windows-environment-{run_id}",
        "started_at": TIMESTAMP,
        "ended_at": "2026-08-12T15:30:00+08:00",
        "timezone": "Asia/Shanghai",
        "clean_isolated_environment": True,
        "runtime": {
            "os": "Windows 11",
            "os_version": "11 24H2",
            "architecture": "AMD64",
            "pointer_bits": 64,
            "python": {
                "implementation": "CPython",
                "executable": "C:/runtime/python.exe",
                "executable_sha256": "1" * 64,
                "version": "3.12.10",
            },
            "streamlit": "1.55.0",
            "pytest": "8.4.2",
            "playwright": "1.61.0",
            "launcher": {
                "path": "scripts/windows/start_biodesign_formal_safe.ps1",
                "sha256": _sha((ROOT / "scripts/windows/start_biodesign_formal_safe.ps1").read_bytes()),
                "module_path": "scripts/windows/biodesign_formal_launcher.py",
                "module_sha256": _sha((ROOT / "scripts/windows/biodesign_formal_launcher.py").read_bytes()),
            },
            "entrypoint": "app.py",
            "port": 8528,
            "dependencies": {
                "runtime_lock_path": "requirements-runtime.lock",
                "runtime_lock_sha256": _sha((ROOT / "requirements-runtime.lock").read_bytes()),
                "inventory_artifact_id": dependency["id"],
                "inventory_sha256": dependency["sha256"],
                "pip_check_returncode": 0,
                "relevant_versions": {
                    "streamlit": "1.55.0",
                    "pytest": "8.4.2",
                    "playwright": "1.61.0",
                    "biopython": "1.87",
                },
            },
        },
        "gates": gates,
        "browser": {
            "name": "Chromium",
            "version": "140.0.0.0",
            "channel": "chromium",
            "automation_runtime": "Playwright 1.61.0",
            "executable_sha256": "e" * 64,
            "initial_process_id": 1000 if run_id == "A" else 2000,
            "cold_reopen_process_id": 1001 if run_id == "A" else 2001,
            "cold_reopen_browser_context_id": f"browser-context-{run_id}-cold",
            "started_at": TIMESTAMP,
            "stopped_at": "2026-08-12T15:20:00+08:00",
            "new_context": True,
            "cold_reopen_complete": True,
            "process_cleanup_complete": True,
            "browser_cleanup_complete": True,
            "port_cleanup_complete": True,
            "page_errors": 0,
            "server_exceptions": 0,
            "server_log_artifact_id": f"{prefix}-server-log",
            "desktop": {
                "viewport": "1440x900",
                "workflow_ids": ["formal-single-gene", "formal-multi-tu"],
                "screenshot_artifact_ids": [f"{prefix}-desktop-step6"],
                "console_errors": 0,
                "network_failures": 0,
                "result": "PASS",
            },
            "mobile": {
                "viewport": "390x844",
                "workflow_ids": ["formal-single-gene", "formal-multi-tu"],
                "screenshot_artifact_ids": [f"{prefix}-mobile-step6"],
                "console_errors": 0,
                "network_failures": 0,
                "result": "PASS",
            },
        },
        "canonical_artifacts": canonical_bindings,
        "result": "PASS",
    }


def _valid_package(package_root: Path) -> dict[str, object]:
    artifacts: list[dict[str, object]] = []
    fixture = _write_artifact(
        package_root,
        artifacts,
        artifact_id="formal-fixture",
        role="fixture",
        data=b'{"fixture":"formal-complete-vector-fixture-v1"}\n',
    )
    runs = [_run(package_root, artifacts, "A"), _run(package_root, artifacts, "B")]
    p0_statuses = {row_id: "PASS" for row_id in P0_ROW_IDS}
    p0_statuses["V1-14"] = "BLOCKED"
    payload: dict[str, object] = {
        "schema_version": "biodesign.v1.runtime-evidence.r1",
        "contract": "V1_RUNTIME_TEST_DURABLE_EVIDENCE_CONTRACT_R1",
        "package_id": "sha256:" + "0" * 64,
        "matrix": {
            "path": "docs/release/V1_RELEASE_READINESS_MATRIX_20260812.md",
            "adoption_commit": MATRIX_ADOPTION_COMMIT,
            "revision_commit": MATRIX_REVISION,
            "sha256": MATRIX_SHA256,
            "row_ids": sorted(P0_ROW_IDS),
        },
        "candidate": {
            "commit": CANDIDATE,
            "parent_commit": PARENT,
            "formal_product_base": FORMAL_PRODUCT_BASE,
            "branch": "release/v1-runtime-evidence-reconcile-20260812",
            "worktree": "C:/clean/v1-run",
            "worktree_clean": True,
        },
        "fixture": {
            "id": "formal-complete-vector-fixture-v1",
            "project_ids": ["single-gene-project", "multi-tu-project", "betalain-gate3-project"],
            "artifact_id": fixture["id"],
            "sha256": fixture["sha256"],
            "description": "Deterministic documentation-only release fixture.",
        },
        "runs": runs,
        "artifacts": artifacts,
        "status": "PASS",
        "release_decision": {
            "decision": "NO_GO",
            "p0_rows": p0_statuses,
            "unresolved_blockers": ["Readiness classifications require post-adoption refresh."],
            "independent_runs_complete": True,
        },
    }
    from scripts.validation.validate_v1_release_evidence import package_id

    payload["package_id"] = package_id(payload)
    return payload


def _errors(payload: dict[str, object], package_root: Path) -> list[str]:
    return validate(
        payload,
        expected_candidate_sha=CANDIDATE,
        expected_parent_sha=PARENT,
        expected_matrix_revision_sha=MATRIX_REVISION,
        package_root=package_root,
    )


def _reseal(payload: dict[str, object]) -> None:
    from scripts.validation.validate_v1_release_evidence import package_id

    payload["package_id"] = package_id(payload)


def test_contract_uses_release_directory_without_promoting_stale_matrix_statuses() -> None:
    assert CONTRACT_PATH.is_file()
    source = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "docs/release/V1_RELEASE_READINESS_MATRIX_20260812.md" in source
    assert FORMAL_PRODUCT_BASE in source
    assert "post-adoption refresh" in source
    assert "classifications recorded in that older snapshot remain current" in source
    assert not (ROOT / "docs" / "releases" / "V1_RUNTIME_TEST_DURABLE_EVIDENCE_CONTRACT.md").exists()


def test_release_matrix_is_the_authoritative_30_row_capability_matrix() -> None:
    matrix_path = ROOT / "docs" / "release" / "V1_RELEASE_READINESS_MATRIX_20260812.md"
    assert matrix_path.is_file()

    source = matrix_path.read_text(encoding="utf-8")
    capability_rows = [line for line in source.splitlines() if line.startswith("| V1-")]
    capability_ids = [line.split("|", maxsplit=2)[1].strip() for line in capability_rows]

    assert "## 2. Authoritative 30-row Matrix" in source
    assert capability_ids == [f"V1-{number:02d}" for number in range(1, 31)]
    assert "Current release verdict: **NO-GO**" in source
    assert "Final Run A: **NOT RUN**" in source
    assert "Independent Run B: **NOT RUN**" in source
    assert "structural placeholder requiring post-adoption refresh" not in source


def test_schema_is_valid_draft_2020_12_and_accepts_complete_manifest(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors(_valid_package(tmp_path))) == []


def test_valid_complete_package_is_accepted(tmp_path: Path) -> None:
    assert _errors(_valid_package(tmp_path), tmp_path) == []


def test_missing_candidate_sha_is_rejected(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    del payload["candidate"]["commit"]
    assert any("candidate" in error and "commit" in error for error in _errors(payload, tmp_path))


def test_wrong_or_stale_candidate_binding_is_rejected(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    errors = validate(
        payload,
        expected_candidate_sha="9" * 40,
        expected_matrix_revision_sha=MATRIX_REVISION,
        package_root=tmp_path,
    )
    assert any("does not match expected candidate" in error for error in errors)


def test_manifest_change_invalidates_deterministic_package_id(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["fixture"]["description"] = "Changed after evidence capture."

    assert any("package_id does not match" in error for error in _errors(payload, tmp_path))


def test_matrix_hash_must_match_candidate_checkout(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["matrix"]["sha256"] = "0" * 64
    _reseal(payload)

    assert any("Matrix" in error or "matrix SHA-256" in error for error in _errors(payload, tmp_path))


def test_matrix_revision_must_match_candidate_checkout(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["matrix"]["revision_commit"] = "7" * 40
    _reseal(payload)

    assert any("matrix revision commit" in error for error in _errors(payload, tmp_path))


def test_missing_formal_product_base_is_rejected(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    del payload["candidate"]["formal_product_base"]
    assert any("formal_product_base" in error for error in _errors(payload, tmp_path))


def test_malformed_runtime_identity_is_rejected(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["runs"][0]["runtime"]["python"]["version"] = "latest"
    payload["runs"][0]["timezone"] = ""
    errors = _errors(payload, tmp_path)
    assert any("python.version" in error for error in errors)
    assert any("timezone" in error for error in errors)


def test_required_collection_failure_cannot_report_pass(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    gate = payload["runs"][0]["gates"]["full_pytest"]
    gate["errors"] = 1
    gate["passed"] = 9
    errors = _errors(payload, tmp_path)
    assert any("pytest failures or collection errors" in error for error in errors)


def test_unexpected_xfail_or_blocked_test_cannot_report_pass(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    gate = payload["runs"][0]["gates"]["focused_pytest"]
    gate["xfailed"] = 1
    gate["blocked"] = 1
    _reseal(payload)

    assert any("pytest failures or collection errors" in error for error in _errors(payload, tmp_path))


def test_missing_required_gate_rejects_run_and_package_pass(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    del payload["runs"][1]["gates"]["import_smoke"]
    errors = _errors(payload, tmp_path)
    assert any("import_smoke" in error for error in errors)
    assert any("without every required test gate PASS" in error for error in errors)


def test_browser_errors_cannot_report_pass(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["runs"][0]["browser"]["mobile"]["console_errors"] = 1
    assert any("mobile reports PASS with browser errors" in error for error in _errors(payload, tmp_path))


def test_browser_viewports_cannot_be_swapped(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["runs"][0]["browser"]["desktop"]["viewport"] = "390x844"
    payload["runs"][0]["browser"]["mobile"]["viewport"] = "1440x900"
    _reseal(payload)

    errors = _errors(payload, tmp_path)
    assert any("desktop viewport" in error for error in errors)
    assert any("mobile viewport" in error for error in errors)


def test_runs_must_be_independently_identified(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["runs"][1]["environment_id"] = payload["runs"][0]["environment_id"]
    assert any("distinct environment identities" in error for error in _errors(payload, tmp_path))


def test_runs_must_have_consistent_runtime_and_dependency_identity(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["runs"][1]["runtime"]["dependencies"]["inventory_sha256"] = "0" * 64
    _reseal(payload)

    errors = _errors(payload, tmp_path)
    assert any("runtime/dependency identities do not match" in error for error in errors)


def test_cross_run_canonical_hash_drift_is_rejected(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["runs"][1]["canonical_artifacts"]["pre_stop"]["canonical_sequence"]["sha256"] = "0" * 64
    errors = _errors(payload, tmp_path)
    assert any("pre_stop canonical_sequence hash does not match its artifact" in error for error in errors)
    assert any("Run A and Run B canonical_sequence hashes do not match" in error for error in errors)


def test_cold_reopen_artifact_drift_is_rejected(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["runs"][0]["canonical_artifacts"]["cold_reopen"]["fasta"]["sha256"] = "0" * 64
    _reseal(payload)

    assert any("fasta changed after cold reopen" in error for error in _errors(payload, tmp_path))


def test_tampered_artifact_is_rejected(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    artifact = payload["artifacts"][0]
    (tmp_path / artifact["path"]).write_bytes(b"tampered")
    errors = _errors(payload, tmp_path)
    assert any("byte size does not match" in error for error in errors)
    assert any("SHA-256 does not match" in error for error in errors)


def test_pass_requires_package_root_for_file_integrity(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    errors = validate(
        payload,
        expected_candidate_sha=CANDIDATE,
        expected_matrix_revision_sha=MATRIX_REVISION,
    )
    assert any("requires package_root" in error for error in errors)


def test_release_go_requires_all_p0_pass_and_zero_blockers(tmp_path: Path) -> None:
    payload = _valid_package(tmp_path)
    payload["release_decision"]["decision"] = "GO"
    errors = _errors(payload, tmp_path)
    assert any("every V1 P0 Matrix row PASS" in error for error in errors)
    assert any("zero unresolved blockers" in error for error in errors)


def test_validator_cli_and_import_contract(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    payload = _valid_package(package_root)
    evidence_path = package_root / "evidence.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_PATH),
            str(evidence_path),
            "--expected-candidate",
            CANDIDATE,
            "--expected-parent",
            PARENT,
            "--expected-matrix-revision",
            MATRIX_REVISION,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "PASS:" in result.stdout

    stale = copy.deepcopy(payload)
    stale["candidate"]["commit"] = "9" * 40
    evidence_path.write_text(json.dumps(stale), encoding="utf-8")
    rejected = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_PATH),
            str(evidence_path),
            "--expected-candidate",
            CANDIDATE,
            "--expected-parent",
            PARENT,
            "--expected-matrix-revision",
            MATRIX_REVISION,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 1
    assert "does not match expected candidate" in rejected.stderr
