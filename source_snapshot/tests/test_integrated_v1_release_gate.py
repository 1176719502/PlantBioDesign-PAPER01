from __future__ import annotations

import io
import json
from pathlib import Path

from scripts.acceptance.run_integrated_v1_release_gate import (
    AcceptanceStage,
    FORMAL_PYTEST_DISPLAY_COMMAND,
    execute_release_gate,
)


SHA = "a" * 64


def _result(*, port: int) -> dict[str, object]:
    result: dict[str, object] = {
        "passed": True,
        "entrypoint": "app.py",
        "first_blocker": None,
        "browser_errors": [],
        "server_exception_count": 0,
        "owned_streamlit_process_ids": [101, 102],
        "process_cleanup_complete": True,
        "browser_cleanup_complete": True,
        "port_cleanup_complete": True,
        "fasta_bytes_identical": True,
        "genbank_bytes_identical": True,
        "professional_review_zip_unavailable_before_restart": True,
        "professional_review_zip_unavailable_after_restart": True,
        "port": port,
        "after_restart": {
            "canonical_sha256": SHA,
            "fasta_matches_canonical": True,
            "genbank_matches_canonical": True,
        },
        "fasta_sha256": "b" * 64,
        "genbank_sha256": "c" * 64,
    }
    return result


def _stages(tmp_path: Path) -> tuple[AcceptanceStage, ...]:
    return (
        AcceptanceStage("single_gene_blank", "single", tmp_path / "single.py", tmp_path / "single.json"),
        AcceptanceStage("multi_tu_blank", "multi", tmp_path / "multi.py", tmp_path / "multi.json"),
        AcceptanceStage("pathway_blank", "pathway", tmp_path / "pathway.py", tmp_path / "pathway.json"),
    )


def test_release_gate_runs_acceptances_then_fixed_pytest_and_records_hashes(tmp_path: Path) -> None:
    stages = _stages(tmp_path)
    calls: list[str] = []

    def runner(command: tuple[str, ...], _cwd: Path) -> int:
        calls.append(Path(command[-1]).name if command[-1].endswith(".py") else "pytest")
        for index, stage in enumerate(stages, start=1):
            if command[-1] == str(stage.script_path):
                stage.result_path.write_text(
                    json.dumps(_result(port=52000 + index)),
                    encoding="utf-8",
                )
        return 0

    exit_code, summary = execute_release_gate(
        acceptance_stages=stages,
        command_runner=runner,
        port_checker=lambda _port: True,
        pytest_command=("python", "-m", "pytest", "-vv", "-s"),
        output=io.StringIO(),
    )

    assert exit_code == 0
    assert summary["passed"] is True
    assert calls == ["single.py", "multi.py", "pathway.py", "pytest"]
    assert summary["stage_order"] == [
        "single_gene_blank",
        "multi_tu_blank",
        "pathway_blank",
        "formal_pytest",
    ]
    assert summary["formal_pytest_command"] == FORMAL_PYTEST_DISPLAY_COMMAND
    pathway_hashes = summary["stages"]["pathway_blank"]["hashes"]
    assert pathway_hashes["fasta_sequence_sha256"] == SHA
    assert pathway_hashes["genbank_sequence_sha256"] == SHA
    assert pathway_hashes["canonical_sequence_sha256"] == SHA
    assert pathway_hashes["fasta_file_sha256"] == "b" * 64
    assert pathway_hashes["genbank_file_sha256"] == "c" * 64


def _run_pathway_hash_failure(tmp_path: Path, result: dict[str, object]) -> tuple[int, dict[str, object]]:
    stage = AcceptanceStage(
        "pathway_blank", "pathway", tmp_path / "pathway.py", tmp_path / "pathway.json"
    )

    def runner(command: tuple[str, ...], _cwd: Path) -> int:
        if command[-1] == str(stage.script_path):
            stage.result_path.write_text(json.dumps(result), encoding="utf-8")
        return 0

    return execute_release_gate(
        acceptance_stages=(stage,),
        command_runner=runner,
        port_checker=lambda _port: True,
        output=io.StringIO(),
    )


def test_release_gate_fails_when_pathway_fasta_hash_is_missing(tmp_path: Path) -> None:
    result = _result(port=52501)
    del result["fasta_sha256"]

    exit_code, summary = _run_pathway_hash_failure(tmp_path, result)

    assert exit_code == 1
    assert summary["first_failure"]["stage"] == "pathway_blank"
    assert "FASTA file SHA-256 was missing or invalid" in summary["first_failure"]["error"]


def test_release_gate_fails_when_pathway_genbank_hash_is_missing(tmp_path: Path) -> None:
    result = _result(port=52502)
    del result["genbank_sha256"]

    exit_code, summary = _run_pathway_hash_failure(tmp_path, result)

    assert exit_code == 1
    assert summary["first_failure"]["stage"] == "pathway_blank"
    assert "GenBank file SHA-256 was missing or invalid" in summary["first_failure"]["error"]


def test_release_gate_fails_when_file_hash_format_is_invalid(tmp_path: Path) -> None:
    result = _result(port=52503)
    result["fasta_sha256"] = "A" * 64

    exit_code, summary = _run_pathway_hash_failure(tmp_path, result)

    assert exit_code == 1
    assert summary["first_failure"]["stage"] == "pathway_blank"
    assert "FASTA file SHA-256 was missing or invalid" in summary["first_failure"]["error"]


def test_release_gate_fails_when_formal_review_zip_boundary_is_missing(tmp_path: Path) -> None:
    result = _result(port=52504)
    result["professional_review_zip_unavailable_after_restart"] = False

    exit_code, summary = _run_pathway_hash_failure(tmp_path, result)

    assert exit_code == 1
    assert summary["first_failure"]["stage"] == "pathway_blank"
    assert (
        "professional_review_zip_unavailable_after_restart was not true"
        in summary["first_failure"]["error"]
    )


def test_release_gate_propagates_acceptance_failure_and_returns_nonzero(tmp_path: Path) -> None:
    stages = _stages(tmp_path)
    calls: list[str] = []

    def runner(command: tuple[str, ...], _cwd: Path) -> int:
        script_name = Path(command[-1]).name
        calls.append(script_name)
        if script_name == "single.py":
            stages[0].result_path.write_text(json.dumps(_result(port=53001)), encoding="utf-8")
            return 0
        return 7

    exit_code, summary = execute_release_gate(
        acceptance_stages=stages,
        command_runner=runner,
        port_checker=lambda _port: True,
        output=io.StringIO(),
    )

    assert exit_code == 1
    assert summary["passed"] is False
    assert summary["first_failure"]["stage"] == "multi_tu_blank"
    assert calls == ["single.py", "multi.py"]
    assert "pathway_blank" not in summary["stages"]
    assert "formal_pytest" not in summary["stages"]


def test_release_gate_fails_when_cleanup_or_port_rebind_check_fails(tmp_path: Path) -> None:
    stage = AcceptanceStage(
        "single_gene_blank", "single", tmp_path / "single.py", tmp_path / "single.json"
    )

    def runner(command: tuple[str, ...], _cwd: Path) -> int:
        if command[-1] == str(stage.script_path):
            result = _result(port=54001)
            result["process_cleanup_complete"] = False
            stage.result_path.write_text(json.dumps(result), encoding="utf-8")
        return 0

    exit_code, summary = execute_release_gate(
        acceptance_stages=(stage,),
        command_runner=runner,
        port_checker=lambda _port: False,
        output=io.StringIO(),
    )

    assert exit_code == 1
    assert summary["first_failure"]["stage"] == "single_gene_blank"
    assert "process_cleanup_complete was not true" in summary["first_failure"]["error"]
    assert "could not be rebound" in summary["first_failure"]["error"]


def test_release_gate_propagates_pytest_exit_code(tmp_path: Path) -> None:
    stage = AcceptanceStage(
        "single_gene_blank", "single", tmp_path / "single.py", tmp_path / "single.json"
    )
    calls = 0

    def runner(command: tuple[str, ...], _cwd: Path) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            stage.result_path.write_text(json.dumps(_result(port=55001)), encoding="utf-8")
            return 0
        return 5

    exit_code, summary = execute_release_gate(
        acceptance_stages=(stage,),
        command_runner=runner,
        port_checker=lambda _port: True,
        pytest_command=("python", "-m", "pytest", "-vv", "-s"),
        output=io.StringIO(),
    )

    assert exit_code == 1
    assert summary["passed"] is False
    assert summary["first_failure"] == {
        "stage": "formal_pytest",
        "error": "pytest command returned 5",
    }
    assert summary["stages"]["formal_pytest"]["returncode"] == 5
