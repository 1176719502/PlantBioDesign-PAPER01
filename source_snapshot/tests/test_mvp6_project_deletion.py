from __future__ import annotations

from pathlib import Path

import pytest

import mvp_app
from services.mvp_single_gene_persistence import (
    MvpSingleGenePersistenceError,
    delete_mvp_single_gene_design,
    list_mvp_single_gene_designs,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.plant_project_draft_schema import PlantProjectDraftError


def _result(project_id: str, project_name: str):
    return mvp_app.generate_complete_vector(
        project_id=project_id,
        project_name=project_name,
        input_signature=(project_id[0] * 64),
    )


def test_repository_delete_removes_only_the_requested_file(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "drafts")
    first = repository.create_blank("First")
    first.project_id = "first-project"
    second = repository.create_blank("Second")
    second.project_id = "second-project"
    repository.save(first)
    repository.save(second)

    repository.delete(first.project_id)

    with pytest.raises(PlantProjectDraftError, match="not found"):
        repository.load(first.project_id)
    assert repository.load(second.project_id).project_name == "Second"


@pytest.mark.parametrize(
    "project_id",
    ["", ".", "..", "../outside", "..\\outside", "C:\\outside", "/outside"],
)
def test_repository_delete_rejects_ids_that_could_escape_storage(
    tmp_path: Path, project_id: str
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "drafts")
    outside = tmp_path / "outside.json"
    outside.write_text("keep", encoding="utf-8")

    with pytest.raises(PlantProjectDraftError, match="Invalid"):
        repository.delete(project_id)

    assert outside.read_text(encoding="utf-8") == "keep"


def test_delete_missing_mvp_project_returns_understandable_error(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "drafts")

    with pytest.raises(MvpSingleGenePersistenceError, match="不存在或无法删除"):
        delete_mvp_single_gene_design("missing-project", repository=repository)


def test_delete_rejects_non_mvp_draft_and_keeps_its_file(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "drafts")
    draft = repository.create_blank("Non-MVP draft")
    draft.project_id = "non-mvp-project"
    repository.save(draft)

    with pytest.raises(MvpSingleGenePersistenceError, match="不是单基因 MVP"):
        delete_mvp_single_gene_design(draft.project_id, repository=repository)

    assert repository.load(draft.project_id).project_name == "Non-MVP draft"


def test_delete_valid_mvp_project_does_not_affect_other_saved_project(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "drafts")
    first = _result("alpha-project", "Alpha")
    second = _result("beta-project", "Beta")
    save_mvp_single_gene_design(first, repository=repository)
    save_mvp_single_gene_design(second, repository=repository)

    delete_mvp_single_gene_design(first["project_id"], repository=repository)

    assert [item.project_id for item in list_mvp_single_gene_designs(repository=repository)] == [
        second["project_id"]
    ]
    with pytest.raises(MvpSingleGenePersistenceError, match="不存在"):
        open_mvp_single_gene_design(first["project_id"], repository=repository)
    reopened = open_mvp_single_gene_design(second["project_id"], repository=repository)
    assert reopened["exports"]["fasta"]["data"] == second["exports"]["fasta"]["data"]
    assert reopened["exports"]["genbank"]["data"] == second["exports"]["genbank"]["data"]
