from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence, TextIO


REPO_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_ARTIFACT_BASE = Path(
    os.environ.get("BIODESIGN_ACCEPTANCE_ARTIFACT_ROOT")
    or Path(tempfile.gettempdir()) / "BioDesignStudio" / "formal_acceptance"
).expanduser().resolve(strict=False)
PYTEST_BASETEMP = Path(
    os.environ.get("BIODESIGN_PYTEST_BASETEMP")
    or Path(tempfile.gettempdir()) / "BioDesignStudio" / "pytest_tmp" / "integrated_v1_release_gate"
).expanduser().resolve(strict=False)
for external_root in (ACCEPTANCE_ARTIFACT_BASE, PYTEST_BASETEMP):
    if external_root == REPO_ROOT or REPO_ROOT in external_root.parents:
        raise RuntimeError("acceptance and pytest roots must be outside the repository")
ARTIFACT_ROOT = ACCEPTANCE_ARTIFACT_BASE / "integrated_v1_release_gate"
RESULT_PATH = ARTIFACT_ROOT / "release_gate_result.json"
FORMAL_PYTEST_DISPLAY_COMMAND = f"python -m pytest -vv -s --basetemp {PYTEST_BASETEMP}"


@dataclass(frozen=True)
class AcceptanceStage:
    name: str
    display_name: str
    script_path: Path
    result_path: Path

    @property
    def command(self) -> tuple[str, ...]:
        return (sys.executable, str(self.script_path))


ACCEPTANCE_STAGES = (
    AcceptanceStage(
        name="single_gene_blank",
        display_name="Formal single-gene blank workflow",
        script_path=REPO_ROOT / "scripts" / "acceptance" / "run_formal_single_gene_blank_acceptance.py",
        result_path=ACCEPTANCE_ARTIFACT_BASE / "formal_single_gene_blank_acceptance" / "acceptance_result.json",
    ),
    AcceptanceStage(
        name="multi_tu_blank",
        display_name="Formal Multi-TU blank workflow",
        script_path=REPO_ROOT / "scripts" / "acceptance" / "run_formal_multi_tu_blank_acceptance.py",
        result_path=ACCEPTANCE_ARTIFACT_BASE / "formal_multi_tu_blank_acceptance" / "acceptance_result.json",
    ),
    AcceptanceStage(
        name="pathway_blank",
        display_name="Formal betalain Gate 3 cold-reopen workflow",
        script_path=REPO_ROOT / "scripts" / "acceptance" / "run_formal_pathway_blank_acceptance.py",
        result_path=ACCEPTANCE_ARTIFACT_BASE / "formal_pathway_blank_acceptance" / "acceptance_result.json",
    ),
)

CommandRunner = Callable[[Sequence[str], Path], int]
ResultLoader = Callable[[Path], dict[str, Any]]
PortChecker = Callable[[int], bool]


def _run_command(command: Sequence[str], cwd: Path) -> int:
    return subprocess.run(list(command), cwd=cwd, check=False).returncode


def _load_result(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _port_is_bindable(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validate_acceptance_result(
    stage: AcceptanceStage,
    result: dict[str, Any],
    *,
    port_checker: PortChecker,
) -> dict[str, Any]:
    errors: list[str] = []
    if result.get("passed") is not True:
        errors.append("acceptance result did not pass")
    if result.get("entrypoint") != "app.py":
        errors.append("formal entrypoint was not app.py")
    if result.get("first_blocker"):
        errors.append(f"first blocker: {result['first_blocker']}")
    if result.get("browser_errors"):
        errors.append("browser errors were recorded")
    if result.get("server_exception_count") != 0:
        errors.append("server exceptions were recorded")
    for field in (
        "process_cleanup_complete",
        "browser_cleanup_complete",
        "port_cleanup_complete",
        "fasta_bytes_identical",
        "genbank_bytes_identical",
        "professional_review_zip_unavailable_before_restart",
        "professional_review_zip_unavailable_after_restart",
    ):
        if result.get(field) is not True:
            errors.append(f"{field} was not true")

    port = result.get("port")
    if not isinstance(port, int) or not 0 < port < 65536:
        errors.append("acceptance result did not contain a valid isolated port")
    elif not port_checker(port):
        errors.append(f"isolated port {port} could not be rebound after acceptance")

    evidence = result.get("after_restart")
    if not isinstance(evidence, dict):
        errors.append("after-restart evidence was missing")
        evidence = {}
    canonical_sha256 = evidence.get("canonical_sha256")
    if not _is_sha256(canonical_sha256):
        errors.append("canonical SHA-256 was missing or invalid")
    if evidence.get("fasta_matches_canonical") is not True:
        errors.append("FASTA sequence did not match canonical")
    if evidence.get("genbank_matches_canonical") is not True:
        errors.append("GenBank sequence did not match canonical")

    fasta_file_sha256 = result.get("fasta_sha256")
    genbank_file_sha256 = result.get("genbank_sha256")
    if not _is_sha256(fasta_file_sha256):
        errors.append("FASTA file SHA-256 was missing or invalid")
    if not _is_sha256(genbank_file_sha256):
        errors.append("GenBank file SHA-256 was missing or invalid")

    if errors:
        raise ValueError("; ".join(errors))

    return {
        "canonical_sequence_sha256": canonical_sha256,
        "fasta_sequence_sha256": canonical_sha256,
        "genbank_sequence_sha256": canonical_sha256,
        "fasta_file_sha256": fasta_file_sha256,
        "genbank_file_sha256": genbank_file_sha256,
    }


def execute_release_gate(
    *,
    acceptance_stages: Sequence[AcceptanceStage] = ACCEPTANCE_STAGES,
    command_runner: CommandRunner = _run_command,
    result_loader: ResultLoader = _load_result,
    port_checker: PortChecker = _port_is_bindable,
    pytest_command: Sequence[str] | None = None,
    output: TextIO = sys.stdout,
) -> tuple[int, dict[str, Any]]:
    started = time.perf_counter()
    pytest_command = tuple(
        pytest_command
        or (
            sys.executable,
            "-m",
            "pytest",
            "-vv",
            "-s",
            "--basetemp",
            str(PYTEST_BASETEMP),
        )
    )
    summary: dict[str, Any] = {
        "gate": "BioDesign Studio Integrated V1.0",
        "passed": False,
        "entrypoint": "app.py",
        "formal_pytest_command": FORMAL_PYTEST_DISPLAY_COMMAND,
        "stage_order": [stage.name for stage in acceptance_stages] + ["formal_pytest"],
        "stages": {},
        "first_failure": None,
    }

    for index, stage in enumerate(acceptance_stages, start=1):
        print(f"[{index}/{len(acceptance_stages) + 1}] START {stage.display_name}", file=output, flush=True)
        stage_started = time.perf_counter()
        before_mtime = stage.result_path.stat().st_mtime_ns if stage.result_path.exists() else None
        returncode = command_runner(stage.command, REPO_ROOT)
        duration = time.perf_counter() - stage_started
        stage_summary: dict[str, Any] = {
            "display_name": stage.display_name,
            "command": [str(part) for part in stage.command],
            "duration_seconds": round(duration, 3),
            "returncode": returncode,
            "passed": False,
        }
        summary["stages"][stage.name] = stage_summary
        try:
            failure_reasons: list[str] = []
            if returncode != 0:
                failure_reasons.append(f"acceptance command returned {returncode}")
            if not stage.result_path.exists():
                failure_reasons.append(f"acceptance result was not written: {stage.result_path}")
            else:
                after_mtime = stage.result_path.stat().st_mtime_ns
                if before_mtime is not None and after_mtime == before_mtime:
                    failure_reasons.append("acceptance result was stale")
                else:
                    result = result_loader(stage.result_path)
                    stage_summary["browser_error_count"] = len(result.get("browser_errors") or [])
                    stage_summary["server_exception_count"] = result.get("server_exception_count")
                    stage_summary["owned_process_ids"] = result.get("owned_streamlit_process_ids")
                    stage_summary["process_cleanup_complete"] = result.get(
                        "process_cleanup_complete"
                    )
                    stage_summary["browser_cleanup_complete"] = result.get(
                        "browser_cleanup_complete"
                    )
                    stage_summary["port"] = result.get("port")
                    try:
                        stage_summary["hashes"] = _validate_acceptance_result(
                            stage, result, port_checker=port_checker
                        )
                        stage_summary["port_rebind_complete"] = True
                    except Exception as exc:
                        failure_reasons.append(f"{type(exc).__name__}: {exc}")
                        stage_summary["port_rebind_complete"] = False
            if failure_reasons:
                raise RuntimeError("; ".join(failure_reasons))
            stage_summary["passed"] = True
        except Exception as exc:
            stage_summary["error"] = f"{type(exc).__name__}: {exc}"
            summary["first_failure"] = {"stage": stage.name, "error": stage_summary["error"]}
            summary["total_duration_seconds"] = round(time.perf_counter() - started, 3)
            print(
                f"[{index}/{len(acceptance_stages) + 1}] FAIL {stage.display_name} "
                f"({duration:.3f}s): {stage_summary['error']}",
                file=output,
                flush=True,
            )
            return 1, summary
        print(
            f"[{index}/{len(acceptance_stages) + 1}] PASS {stage.display_name} ({duration:.3f}s)",
            file=output,
            flush=True,
        )

    pytest_index = len(acceptance_stages) + 1
    print(
        f"[{pytest_index}/{pytest_index}] START Formal pytest gate: {FORMAL_PYTEST_DISPLAY_COMMAND}",
        file=output,
        flush=True,
    )
    pytest_started = time.perf_counter()
    pytest_returncode = command_runner(pytest_command, REPO_ROOT)
    pytest_duration = time.perf_counter() - pytest_started
    pytest_summary = {
        "display_name": "Formal pytest regression gate",
        "command": FORMAL_PYTEST_DISPLAY_COMMAND,
        "duration_seconds": round(pytest_duration, 3),
        "returncode": pytest_returncode,
        "passed": pytest_returncode == 0,
    }
    summary["stages"]["formal_pytest"] = pytest_summary
    if pytest_returncode != 0:
        summary["first_failure"] = {
            "stage": "formal_pytest",
            "error": f"pytest command returned {pytest_returncode}",
        }
        summary["total_duration_seconds"] = round(time.perf_counter() - started, 3)
        print(
            f"[{pytest_index}/{pytest_index}] FAIL Formal pytest gate ({pytest_duration:.3f}s)",
            file=output,
            flush=True,
        )
        return 1, summary

    print(
        f"[{pytest_index}/{pytest_index}] PASS Formal pytest gate ({pytest_duration:.3f}s)",
        file=output,
        flush=True,
    )
    summary["passed"] = True
    summary["total_duration_seconds"] = round(time.perf_counter() - started, 3)
    return 0, summary


def main() -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    exit_code, summary = execute_release_gate()
    RESULT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\nFINAL SUMMARY")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Result: {RESULT_PATH}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
