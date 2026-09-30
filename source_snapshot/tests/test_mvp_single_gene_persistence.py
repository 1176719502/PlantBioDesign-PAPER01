from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mvp_app import generate_complete_vector, load_real_case
from services.mvp_single_gene_persistence import (
    MVP_SINGLE_GENE_PERSISTENCE_KEY,
    MvpSingleGenePersistenceError,
    list_mvp_single_gene_designs,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository


def _repository(tmp_path: Path) -> PlantProjectDraftRepository:
    return PlantProjectDraftRepository(tmp_path / "shared_r224_drafts")


def _generated_result() -> dict:
    return generate_complete_vector(load_real_case())


def test_save_and_reopen_preserve_the_exact_complete_vector_and_exports(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    before = _generated_result()
    saved = save_mvp_single_gene_design(before, repository=repo)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repo)

    assert saved.draft_status == "draft"
    assert saved.workflow_type == ""
    assert saved.canonical_available is False
    assert reopened["project_id"] == saved.project_id
    assert reopened["project_name"] == saved.project_name
    assert reopened["input_lengths"] == {"promoter": 640, "cds": 900, "terminator": 210, "backbone": 4200}
    assert reopened["cassette_length"] == 1750
    assert reopened["plasmid_length"] == 5950
    assert reopened["plasmid_sha256"] == "a65a617e31e54b2a2e91ad00294aa21d8d83fe8ec0e44dd2dc7c6f39cb0c69fb"
    assert reopened["source_inputs"] == before["source_inputs"]
    assert reopened["exports"]["fasta"]["data"] == before["exports"]["fasta"]["data"]
    assert reopened["exports"]["genbank"]["data"] == before["exports"]["genbank"]["data"]
    assert reopened["runtime"] == before["runtime"]
    backbone_asset = next(asset for asset in reopened["runtime"]["sequence_assets"] if asset["asset_role"] == "backbone")
    assert "LOCUS" in reopened["source_inputs"]["backbone"]
    assert backbone_asset["imported_feature_records"]

    persisted = json.loads((repo.storage_dir / f"{saved.project_id}.json").read_text(encoding="utf-8"))
    snapshot = persisted["manual_review_state"][MVP_SINGLE_GENE_PERSISTENCE_KEY]
    assert persisted["draft_status"] == "draft"
    assert persisted["workflow_type"] == ""
    assert persisted["canonical_available"] is False
    assert snapshot["vector_asset_admission"]["legacy_project_read_only"] is True
    assert snapshot["vector_asset_admission"]["completed_design_allowed"] is False
    assert snapshot["runtime_schema_version"] == reopened["runtime"]["schema_version"]
    assert snapshot["sequence_sha256"] == {
        "plasmid": reopened["plasmid_sha256"],
        "fasta": reopened["plasmid_sha256"],
        "genbank": reopened["plasmid_sha256"],
    }


def test_repeated_save_updates_the_same_stable_project_without_duplicates(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    first = save_mvp_single_gene_design(_generated_result(), repository=repo)
    second = save_mvp_single_gene_design(open_mvp_single_gene_design(first.project_id, repository=repo), repository=repo)

    assert second.project_id == first.project_id
    assert len(repo.list_summaries()) == 1
    assert [summary.project_id for summary in list_mvp_single_gene_designs(repository=repo)] == [first.project_id]


def test_non_hsa_formal_context_survives_list_and_cross_process_reopen(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    before = _generated_result()
    before["project_id"] = "formal-general-user-project"
    before["project_name"] = "非HSA单基因用户输入回归项目"
    before["formal_project_context"] = {
        "host_key": "Arabidopsis thaliana",
        "expression_target": "用户表达目标",
        "current_step": 6,
    }
    # The package is generated from the saved project identity, independently
    # of the project-backup JSON download surface.
    before.pop("company_review_package", None)

    saved = save_mvp_single_gene_design(before, repository=repo)

    assert [summary.project_id for summary in list_mvp_single_gene_designs(repository=repo)] == [saved.project_id]
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repo)
    assert reopened["formal_project_context"] == before["formal_project_context"]
    assert reopened["project_name"] == before["project_name"]
    assert reopened["cassette_input_signature"] == before["cassette_input_signature"]

    script = (
        "from services.mvp_single_gene_persistence import open_mvp_single_gene_design; "
        f"record=open_mvp_single_gene_design({saved.project_id!r}); "
        "print(record['formal_project_context']['host_key']); "
        "print(record['project_name'])"
    )
    environment = dict(os.environ)
    environment["BIODESIGN_PLANT_PROJECT_DRAFT_DIR"] = str(repo.storage_dir)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.splitlines() == ["Arabidopsis thaliana", "非HSA单基因用户输入回归项目"]


def test_complete_python_process_restart_can_read_the_same_saved_design(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    saved = save_mvp_single_gene_design(_generated_result(), repository=repo)
    script = (
        "from services.mvp_single_gene_persistence import open_mvp_single_gene_design; "
        f"record = open_mvp_single_gene_design({saved.project_id!r}); "
        "print(record['plasmid_length']); "
        "print(record['plasmid_sha256']); "
        "print(record['exports']['fasta']['data'] == record['exports']['genbank']['data'])"
    )
    environment = dict(os.environ)
    environment["BIODESIGN_PLANT_PROJECT_DRAFT_DIR"] = str(repo.storage_dir)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.splitlines() == [
        "5950",
        "a65a617e31e54b2a2e91ad00294aa21d8d83fe8ec0e44dd2dc7c6f39cb0c69fb",
        "False",
    ]


def test_missing_saved_design_fails_with_a_safe_message(tmp_path: Path) -> None:
    with pytest.raises(MvpSingleGenePersistenceError, match="不存在或无法读取"):
        open_mvp_single_gene_design("mvp-single-gene-rescue", repository=_repository(tmp_path))


def test_corrupted_saved_design_fails_with_a_safe_message(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    saved = save_mvp_single_gene_design(_generated_result(), repository=repo)
    path = repo.storage_dir / f"{saved.project_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["manual_review_state"][MVP_SINGLE_GENE_PERSISTENCE_KEY]["exports"]["fasta"]["data"] = ">broken\nAAAA\n"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MvpSingleGenePersistenceError, match="FASTA 文件已损坏"):
        open_mvp_single_gene_design(saved.project_id, repository=repo)


def test_incompatible_saved_design_version_fails_with_a_safe_message(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    saved = save_mvp_single_gene_design(_generated_result(), repository=repo)
    path = repo.storage_dir / f"{saved.project_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["manual_review_state"][MVP_SINGLE_GENE_PERSISTENCE_KEY]["persistence_schema_version"] = "future-version"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MvpSingleGenePersistenceError, match="版本不兼容"):
        open_mvp_single_gene_design(saved.project_id, repository=repo)


def test_reopened_fasta_and_genbank_bytes_are_identical_to_the_saved_downloads(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    before = _generated_result()
    saved = save_mvp_single_gene_design(before, repository=repo)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repo)

    assert reopened["exports"]["fasta"]["data"].encode("utf-8") == before["exports"]["fasta"]["data"].encode("utf-8")
    assert reopened["exports"]["genbank"]["data"].encode("utf-8") == before["exports"]["genbank"]["data"].encode("utf-8")
