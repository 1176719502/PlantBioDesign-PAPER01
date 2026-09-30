from __future__ import annotations

import copy
import hashlib
from io import StringIO
from pathlib import Path
from typing import Any

from Bio import SeqIO
import pytest

from services.formal_results_report_contract import (
    FormalResultsReportContractError,
    build_formal_results_report_contract,
    validate_report_artifact_manifest,
)
from services.mvp_multi_tu_persistence import (
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from tests.test_generic_pathway_vector_route import FIXTURE_PATH, _pathway_result
from tests.test_v1_runtime_evidence_contract import (
    _errors,
    _reseal,
    _valid_package,
)


PATHWAY_WORKFLOW = "gate3_pathway"
PATHWAY_MULTI_TU_SHA256 = (
    "07a587c0d73868e7bdc187a412c18a5d0918bdc9dcb5ef7d8d380ee314d390bc"
)
PATHWAY_PLASMID_SHA256 = (
    "f6321f529bfbfb45de661476c62cf5a7a46446631e59954c5c97c70dd12f2e61"
)


def _fresh_reopen(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    result, _combined, _backbone = _pathway_result()
    repository = PlantProjectDraftRepository(tmp_path / "pathway-projects")
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(
        saved.project_id,
        repository=PlantProjectDraftRepository(repository.storage_dir),
    )
    return result, reopened


def _canonical_artifact_bytes(record: dict[str, Any]) -> dict[str, bytes]:
    complete = record["complete_plasmid"]
    exports = record["exports"]
    canonical = str(complete["dna"]).upper()
    fasta_text = str(exports["complete_plasmid_fasta"]["data"])
    genbank_text = str(exports["complete_plasmid_genbank"]["data"])
    fasta = next(SeqIO.parse(StringIO(fasta_text), "fasta"))
    genbank = next(SeqIO.parse(StringIO(genbank_text), "genbank"))
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == canonical
    return {
        "canonical_sequence": canonical.encode("ascii"),
        "fasta": fasta_text.encode("utf-8"),
        "genbank": genbank_text.encode("utf-8"),
    }


def _replace_artifact(
    payload: dict[str, Any],
    package_root: Path,
    *,
    artifact_id: str,
    data: bytes,
) -> str:
    artifact = next(
        item for item in payload["artifacts"] if item["id"] == artifact_id
    )
    (package_root / artifact["path"]).write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    artifact["sha256"] = digest
    artifact["bytes"] = len(data)
    return digest


def test_pathway_final_report_r2_is_deterministic_across_fresh_reopen(
    tmp_path: Path,
) -> None:
    result, reopened = _fresh_reopen(tmp_path)
    result_with_transient_state = copy.deepcopy(result)
    result_with_transient_state["_transient"] = {
        "workflow_kind": "forged",
        "canonical_sha256": "0" * 64,
    }

    first = build_formal_results_report_contract(result)
    repeated = build_formal_results_report_contract(result_with_transient_state)
    after_reopen = build_formal_results_report_contract(reopened)
    validate_report_artifact_manifest(
        after_reopen["artifact_manifest"], after_reopen["report_snapshot"]
    )

    assert first == repeated
    assert (
        first["report_snapshot"]["snapshot_id"]
        == after_reopen["report_snapshot"]["snapshot_id"]
    )
    assert (
        first["artifact_manifest"]["manifest_id"]
        == after_reopen["artifact_manifest"]["manifest_id"]
    )
    assert reopened["workflow_kind"] == PATHWAY_WORKFLOW
    assert reopened["combined_construct"]["sequence_sha256"] == PATHWAY_MULTI_TU_SHA256
    assert reopened["complete_plasmid"]["sequence_sha256"] == PATHWAY_PLASMID_SHA256
    assert first["artifact_manifest"]["canonical_sequence_identity"] == {
        "sha256": PATHWAY_PLASMID_SHA256,
        "length_bp": 11819,
        "topology": "circular",
        "input_signature": result["input_signature"],
    }

    tampered = copy.deepcopy(after_reopen["artifact_manifest"])
    tampered["canonical_sequence_identity"]["sha256"] = "0" * 64
    with pytest.raises(FormalResultsReportContractError):
        validate_report_artifact_manifest(tampered, after_reopen["report_snapshot"])


def test_current_runtime_evidence_contract_accepts_pathway_bytes_and_fails_closed(
    tmp_path: Path,
) -> None:
    result, reopened = _fresh_reopen(tmp_path)
    package_root = tmp_path / "runtime-evidence"
    payload = _valid_package(package_root)

    fixture_bytes = FIXTURE_PATH.read_bytes()
    fixture_id = str(payload["fixture"]["artifact_id"])
    fixture_sha = _replace_artifact(
        payload,
        package_root,
        artifact_id=fixture_id,
        data=fixture_bytes,
    )
    payload["fixture"].update(
        {
            "id": "generic-pathway-pbi121-r3",
            "project_ids": [result["project_id"]],
            "sha256": fixture_sha,
            "description": "Deterministic documentation-only gate3_pathway fixture.",
        }
    )

    phase_records = {"pre_stop": result, "cold_reopen": reopened}
    for run in payload["runs"]:
        for lane in ("desktop", "mobile"):
            run["browser"][lane]["workflow_ids"] = [PATHWAY_WORKFLOW]
        for phase_name, record in phase_records.items():
            assert record["workflow_kind"] == PATHWAY_WORKFLOW
            artifact_bytes = _canonical_artifact_bytes(record)
            for binding_name, data in artifact_bytes.items():
                binding = run["canonical_artifacts"][phase_name][binding_name]
                binding["sha256"] = _replace_artifact(
                    payload,
                    package_root,
                    artifact_id=str(binding["artifact_id"]),
                    data=data,
                )

    _reseal(payload)
    assert _errors(payload, package_root) == []

    malformed = copy.deepcopy(payload)
    malformed["runs"][0]["canonical_artifacts"]["cold_reopen"][
        "canonical_sequence"
    ]["sha256"] = "0" * 64
    _reseal(malformed)
    errors = _errors(malformed, package_root)
    assert any("canonical_sequence hash does not match its artifact" in item for item in errors)
    assert any("canonical_sequence changed after cold reopen" in item for item in errors)
