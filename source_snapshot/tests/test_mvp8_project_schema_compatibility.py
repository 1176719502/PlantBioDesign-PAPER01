from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

import mvp_app
import services.mvp_single_gene_persistence as persistence
from services.mvp_company_review_package import build_company_review_package
from services.mvp_single_gene_persistence import (
    MVP_SINGLE_GENE_PERSISTENCE_KEY,
    MvpSingleGenePersistenceError,
    delete_mvp_single_gene_design,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository


def _repository(tmp_path: Path) -> PlantProjectDraftRepository:
    return PlantProjectDraftRepository(tmp_path / "shared_r224_drafts")


def _result() -> dict:
    return mvp_app.generate_complete_vector(mvp_app.load_real_case())


def _persisted_payload(repo: PlantProjectDraftRepository, project_id: str) -> tuple[Path, dict]:
    path = repo.storage_dir / f"{project_id}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return path, document


def test_new_save_records_project_version_source_fields_and_raw_zip_bytes(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    result = _result()
    saved = save_mvp_single_gene_design(result, repository=repo)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repo)
    _path, document = _persisted_payload(repo, saved.project_id)
    snapshot = document["manual_review_state"][MVP_SINGLE_GENE_PERSISTENCE_KEY]

    assert snapshot["project_schema_version"] == "1.0.0"
    assert snapshot["project_type"] == "single_gene"
    assert reopened["project_schema_version"] == "1.0.0"
    assert reopened["project_type"] == "single_gene"
    assert reopened["legacy_project_compatibility"] is False
    assert reopened["company_review_package"]["data"] == result["company_review_package"]["data"]
    assert reopened["company_review_package"]["sha256"] == result["company_review_package"]["sha256"]
    assert snapshot["company_review_package"]["data_b64"]
    for record in snapshot["source_provenance"].values():
        assert record["source_kind"]
        assert record["source_reference"]


def test_five_process_restarts_reopen_identical_zip_without_rebuilding(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    result = _result()
    saved = save_mvp_single_gene_design(result, repository=repo)
    script = (
        "from services.mvp_single_gene_persistence import open_mvp_single_gene_design; "
        f"r=open_mvp_single_gene_design({saved.project_id!r}); "
        "print(r['company_review_package']['sha256']); "
        "print(len(r['company_review_package']['data']))"
    )
    environment = dict(os.environ)
    environment["BIODESIGN_PLANT_PROJECT_DRAFT_DIR"] = str(repo.storage_dir)
    outputs = []
    for _ in range(5):
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(completed.stdout.splitlines())

    assert outputs == [outputs[0]] * 5
    assert outputs[0] == [
        result["company_review_package"]["sha256"],
        str(len(result["company_review_package"]["data"])),
    ]


def test_saved_package_reopen_never_calls_package_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repository(tmp_path)
    result = _result()
    saved = save_mvp_single_gene_design(result, repository=repo)
    monkeypatch.setattr(
        persistence,
        "build_company_review_package",
        lambda *_args, **_kwargs: pytest.fail("saved ZIP bytes must be restored, not rebuilt"),
    )

    for _ in range(5):
        reopened = open_mvp_single_gene_design(saved.project_id, repository=repo)
        assert reopened["company_review_package"]["data"] == result["company_review_package"]["data"]


def test_legacy_project_without_version_fields_still_opens(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    result = _result()
    saved = save_mvp_single_gene_design(result, repository=repo)
    path, document = _persisted_payload(repo, saved.project_id)
    snapshot = document["manual_review_state"][MVP_SINGLE_GENE_PERSISTENCE_KEY]
    snapshot.pop("project_schema_version")
    snapshot.pop("project_type")
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    reopened = open_mvp_single_gene_design(saved.project_id, repository=repo)

    assert reopened["project_schema_version"] == "1.0.0"
    assert reopened["project_type"] == "single_gene"
    assert reopened["legacy_project_compatibility"] is True
    assert reopened["company_review_package"]["data"] == result["company_review_package"]["data"]


def test_legacy_project_without_package_builds_deterministically_from_saved_exports(
    tmp_path: Path,
) -> None:
    repo = _repository(tmp_path)
    result = _result()
    saved = save_mvp_single_gene_design(result, repository=repo)
    path, document = _persisted_payload(repo, saved.project_id)
    snapshot = document["manual_review_state"][MVP_SINGLE_GENE_PERSISTENCE_KEY]
    snapshot.pop("project_schema_version")
    snapshot.pop("project_type")
    snapshot.pop("company_review_package")
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    reopened = [open_mvp_single_gene_design(saved.project_id, repository=repo) for _ in range(5)]

    assert all(item["legacy_project_compatibility"] is True for item in reopened)
    assert len({item["company_review_package"]["sha256"] for item in reopened}) == 1
    assert all(
        item["company_review_package"]["data"] == reopened[0]["company_review_package"]["data"]
        for item in reopened
    )


def test_legacy_source_aliases_are_saved_as_minimal_allowed_provenance(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    result = deepcopy(_result())
    result["input_records"]["promoter"].update(source_kind="paste", source_name="pasted-promoter")
    result["input_records"]["cds"].update(source_kind="paste", source_name="pasted-cds")
    result["cds_input"].update(source_kind="paste", source_name="pasted-cds")
    result["input_records"]["terminator"].update(source_kind="", source_name="")
    result["input_records"]["backbone"].update(
        source_kind="upload",
        source_name=r"C:\customer\inputs\uploaded_backbone.gb",
    )
    result["company_review_package"] = build_company_review_package(result)

    saved = save_mvp_single_gene_design(result, repository=repo)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repo)

    assert reopened["input_records"]["promoter"]["source_kind"] == "paste"
    assert reopened["input_records"]["backbone"]["source_kind"] == "upload"
    assert reopened["source_provenance"]["promoter"] == {
        "source_kind": "user_pasted",
        "source_reference": "not_provided",
    }
    assert reopened["source_provenance"]["cds"]["source_kind"] == "user_pasted"
    assert reopened["source_provenance"]["terminator"] == {
        "source_kind": "not_provided",
        "source_reference": "not_provided",
    }
    assert reopened["source_provenance"]["backbone"] == {
        "source_kind": "user_uploaded",
        "source_reference": "uploaded_backbone.gb",
    }


def test_future_project_version_is_rejected_without_changing_r224_schema(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    saved = save_mvp_single_gene_design(_result(), repository=repo)
    path, document = _persisted_payload(repo, saved.project_id)
    snapshot = document["manual_review_state"][MVP_SINGLE_GENE_PERSISTENCE_KEY]
    snapshot["project_schema_version"] = "2.0.0"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(MvpSingleGenePersistenceError, match="单基因项目版本不兼容"):
        open_mvp_single_gene_design(saved.project_id, repository=repo)


def test_corrupted_saved_zip_is_rejected(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    saved = save_mvp_single_gene_design(_result(), repository=repo)
    path, document = _persisted_payload(repo, saved.project_id)
    package = document["manual_review_state"][MVP_SINGLE_GENE_PERSISTENCE_KEY][
        "company_review_package"
    ]
    package["data_b64"] = package["data_b64"][:-8] + "AAAAAAAA"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(MvpSingleGenePersistenceError, match="公司审查包"):
        open_mvp_single_gene_design(saved.project_id, repository=repo)


def test_deleted_project_cannot_reopen_or_restore_old_package(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    saved = save_mvp_single_gene_design(_result(), repository=repo)
    delete_mvp_single_gene_design(saved.project_id, repository=repo)

    with pytest.raises(MvpSingleGenePersistenceError, match="不存在或无法读取"):
        open_mvp_single_gene_design(saved.project_id, repository=repo)
