from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import mvp_app
from services.mvp_multi_tu_persistence import (
    MVP_MULTI_TU_PERSISTENCE_KEY,
    MvpMultiTuPersistenceError,
    list_mvp_multi_tu_designs,
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.mvp_single_gene_persistence import (
    MvpSingleGenePersistenceError,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_repository import (
    SQLITE_DRAFT_ENVELOPE_KIND,
    PlantProjectDraftRepository,
)
from services.mvp_multi_tu_runtime import MULTI_TU_EXPRESSION_ASSEMBLY, generate_multi_tu_combined_construct
from tests.test_mvp9_multi_tu_runtime import DATA, _generate, _units_for_case


def _repo(tmp_path: Path) -> PlantProjectDraftRepository:
    return PlantProjectDraftRepository(tmp_path / "mvp9_projects")


def _initialize_project_history_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE project_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                version INTEGER,
                chassis TEXT,
                design_data TEXT,
                created_at TEXT,
                creator TEXT,
                status TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_multi_tu_save_and_reopen_preserves_runtime_inputs_and_export_bytes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _generate(DATA["cases"][7])
    saved = save_mvp_multi_tu_design(result, repository=repo)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repo)

    assert saved.draft_status == "draft"
    assert saved.workflow_type == ""
    assert saved.canonical_available is False
    assert reopened["project_type"] == "multi_tu"
    assert reopened["original_input"] == result["original_input"]
    assert reopened["unit_order"] == result["unit_order"]
    assert reopened["expression_units"] == result["expression_units"]
    assert reopened["combined_construct"] == result["combined_construct"]
    assert reopened["complete_plasmid"] == result["complete_plasmid"]
    assert reopened["runtime"] == result["runtime"]
    for export_key in (
        "combined_construct_fasta",
        "complete_plasmid_fasta",
        "complete_plasmid_genbank",
    ):
        assert reopened["exports"][export_key]["data"] == result["exports"][export_key]["data"]

    document = json.loads((repo.storage_dir / f"{saved.project_id}.json").read_text(encoding="utf-8"))
    snapshot = document["manual_review_state"][MVP_MULTI_TU_PERSISTENCE_KEY]
    assert document["draft_status"] == "draft"
    assert document["workflow_type"] == ""
    assert document["canonical_available"] is False
    assert snapshot["vector_asset_admission"]["legacy_project_read_only"] is True
    assert snapshot["vector_asset_admission"]["completed_design_allowed"] is False
    assert reopened["vector_asset_admission"]["legacy_project_read_only"] is True
    assert snapshot["project_type"] == "multi_tu"
    assert len(snapshot["original_input"]["expression_units"]) == 2
    assert snapshot["runtime_sha256"]
    assert all(
        snapshot["exports"][key]["data_b64"]
        for key in ("combined_construct_fasta", "complete_plasmid_fasta", "complete_plasmid_genbank")
    )
    assert all(item["data_b64"] for item in snapshot["exports"]["unit_fastas"].values())


def test_five_process_style_reopens_do_not_call_generation(monkeypatch, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _generate(DATA["cases"][1])
    saved = save_mvp_multi_tu_design(result, repository=repo)

    def _unexpected_generation(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("reopen must not call a generation entry point")

    monkeypatch.setattr(
        "services.mvp_multi_tu_runtime.generate_multi_tu_construct",
        _unexpected_generation,
    )
    reopened = [open_mvp_multi_tu_design(saved.project_id, repository=repo) for _ in range(5)]

    assert all(item["runtime"] == result["runtime"] for item in reopened)
    assert len(
        {
            item["exports"]["complete_plasmid_genbank"]["data"]
            for item in reopened
        }
    ) == 1


def test_multi_tu_and_single_gene_project_types_cannot_be_cross_opened(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    multi_result = _generate(DATA["cases"][0])
    multi_saved = save_mvp_multi_tu_design(multi_result, repository=repo)
    with pytest.raises(MvpSingleGenePersistenceError):
        open_mvp_single_gene_design(multi_saved.project_id, repository=repo)

    single_result = mvp_app.generate_complete_vector(mvp_app.load_real_case())
    single_saved = save_mvp_single_gene_design(single_result, repository=repo)
    with pytest.raises(MvpMultiTuPersistenceError, match="single_gene"):
        open_mvp_multi_tu_design(single_saved.project_id, repository=repo)


def test_single_gene_project_cannot_be_overwritten_as_multi_tu(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    single_result = mvp_app.generate_complete_vector(mvp_app.load_real_case())
    saved = save_mvp_single_gene_design(single_result, repository=repo)
    multi_result = _generate(DATA["cases"][0])
    multi_result["project_id"] = saved.project_id
    multi_result["runtime"]["project_id"] = saved.project_id

    with pytest.raises(MvpMultiTuPersistenceError, match="cannot be overwritten"):
        save_mvp_multi_tu_design(multi_result, repository=repo)


def test_corrupted_saved_export_bytes_are_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _generate(DATA["cases"][0])
    saved = save_mvp_multi_tu_design(result, repository=repo)
    path = repo.storage_dir / f"{saved.project_id}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    export = document["manual_review_state"][MVP_MULTI_TU_PERSISTENCE_KEY]["exports"][
        "complete_plasmid_genbank"
    ]
    export["data_b64"] = export["data_b64"][:-8] + "AAAAAAAA"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(MvpMultiTuPersistenceError, match="checksum|corrupted"):
        open_mvp_multi_tu_design(saved.project_id, repository=repo)


def test_multi_tu_listing_excludes_single_gene_projects(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    multi_saved = save_mvp_multi_tu_design(_generate(DATA["cases"][5]), repository=repo)
    single_saved = save_mvp_single_gene_design(
        mvp_app.generate_complete_vector(mvp_app.load_real_case()),
        repository=repo,
    )

    ids = {summary.project_id for summary in list_mvp_multi_tu_designs(repository=repo)}
    assert multi_saved.project_id in ids
    assert single_saved.project_id not in ids


def test_assembly_only_save_and_cold_reopen_preserve_contract_boundaries_and_exports(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = generate_multi_tu_combined_construct(
        project_id="assembly-only-cold-reopen",
        project_name="Assembly only cold reopen",
        expression_units=_units_for_case(DATA["cases"][1]),
    )
    result["project_type"] = "dual_tu"
    result["formal_project_context"] = {"current_step": 6, "design_scenario": "standard_plant_expression_vector"}
    saved = save_mvp_multi_tu_design(result, repository=repo)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repo)

    assert reopened["result_kind"] == MULTI_TU_EXPRESSION_ASSEMBLY
    assert reopened["workflow_kind"] == "generic_multi_tu"
    assert reopened["contains_vector"] is False
    assert reopened["complete_plasmid"] == {}
    assert reopened["unit_order"] == result["unit_order"]
    assert reopened["expression_units"] == result["expression_units"]
    assert reopened["combined_construct"] == result["combined_construct"]
    assert reopened["capability_limits"] == result["capability_limits"]
    assert reopened["vector_asset_admission"]["status"] == "not_applicable_without_vector"
    assert reopened["vector_asset_admission"]["legacy_project_read_only"] is False
    for key in ("combined_construct_fasta", "combined_construct_genbank"):
        assert reopened["exports"][key]["data"] == result["exports"][key]["data"]

    command = (
        "import json; "
        "from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design; "
        f"r=open_mvp_multi_tu_design({saved.project_id!r}); "
        "print(json.dumps({'sha':r['combined_construct']['sequence_sha256'],'order':r['unit_order'],"
        "'kind':r['result_kind'],'contains_vector':r['contains_vector']},sort_keys=True))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(repo.storage_dir)},
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == {
        "contains_vector": False,
        "kind": MULTI_TU_EXPRESSION_ASSEMBLY,
        "order": result["unit_order"],
        "sha": result["combined_construct"]["sequence_sha256"],
    }


def test_generic_multi_tu_default_save_commits_to_biodesign_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "db" / "biodesign_unified.db"
    json_draft_dir = tmp_path / "must-not-be-used"
    _initialize_project_history_database(database_path)
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(database_path))
    monkeypatch.setenv("BIODESIGN_PLANT_PROJECT_DRAFT_DIR", str(json_draft_dir))
    result = generate_multi_tu_combined_construct(
        project_id="sqlite-case-01-forward-forward",
        project_name="case_01_forward_forward",
        expression_units=_units_for_case(DATA["cases"][0]),
    )
    result["project_type"] = "dual_tu"
    result["formal_project_context"] = {
        "current_step": 6,
        "design_scenario": "standard_plant_expression_vector",
    }

    saved = save_mvp_multi_tu_design(result)

    assert saved.project_id == result["project_id"]
    assert not json_draft_dir.exists()
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            "SELECT project_name, chassis, design_data, status FROM project_history"
        ).fetchall()
    finally:
        connection.close()
    assert len(rows) == 1
    project_name, chassis, raw_payload, status = rows[0]
    envelope = json.loads(raw_payload)
    snapshot = envelope["draft"]["manual_review_state"][MVP_MULTI_TU_PERSISTENCE_KEY]
    assert envelope["storage_kind"] == SQLITE_DRAFT_ENVELOPE_KIND
    assert project_name == "case_01_forward_forward"
    assert chassis == "multi_tu"
    assert status == "draft"
    assert snapshot["workflow_kind"] == "generic_multi_tu"
    assert snapshot["result_kind"] == MULTI_TU_EXPRESSION_ASSEMBLY
    assert snapshot["contains_vector"] is False
    assert snapshot["topology"] == "linear"
    assert snapshot["combined_construct"]["sequence_sha256"] == result["combined_construct"]["sequence_sha256"]
    assert snapshot["unit_order"] == result["unit_order"]
    assert [unit["range"] for unit in snapshot["expression_units"]] == [
        unit["range"] for unit in result["expression_units"]
    ]

    reopened = open_mvp_multi_tu_design(saved.project_id)
    assert reopened["topology"] == "linear"
    assert reopened["contains_vector"] is False
    assert reopened["combined_construct"]["sequence_sha256"] == result["combined_construct"]["sequence_sha256"]
    assert saved.project_id in {item.project_id for item in list_mvp_multi_tu_designs()}


def test_generic_multi_tu_database_reopens_and_lists_in_fresh_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "db" / "biodesign_unified.db"
    _initialize_project_history_database(database_path)
    monkeypatch.setenv("BIODESIGN_DB_PATH", str(database_path))
    result = generate_multi_tu_combined_construct(
        project_id="sqlite-cold-reopen",
        project_name="SQLite cold reopen",
        expression_units=_units_for_case(DATA["cases"][0]),
    )
    result["project_type"] = "dual_tu"
    result["formal_project_context"] = {
        "current_step": 6,
        "design_scenario": "standard_plant_expression_vector",
    }
    saved = save_mvp_multi_tu_design(result)
    command = (
        "import json; "
        "from services.mvp_multi_tu_persistence import list_mvp_multi_tu_designs,open_mvp_multi_tu_design; "
        f"r=open_mvp_multi_tu_design({saved.project_id!r}); "
        "print(json.dumps({'ids':[s.project_id for s in list_mvp_multi_tu_designs()],"
        "'sha':r['combined_construct']['sequence_sha256'],'order':r['unit_order'],"
        "'ranges':[u['range'] for u in r['expression_units']],"
        "'kind':r['result_kind'],'contains_vector':r['contains_vector'],'topology':r['topology']}))"
    )
    environment = {
        **os.environ,
        "BIODESIGN_DB_PATH": str(database_path),
        "LOCALAPPDATA": str(tmp_path / "different-process-local-app-data"),
        "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(tmp_path / "different-json-drafts"),
    }
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    cold = json.loads(completed.stdout)
    assert saved.project_id in cold["ids"]
    assert cold["sha"] == result["combined_construct"]["sequence_sha256"]
    assert cold["order"] == result["unit_order"]
    assert cold["ranges"] == [unit["range"] for unit in result["expression_units"]]
    assert cold["kind"] == MULTI_TU_EXPRESSION_ASSEMBLY
    assert cold["contains_vector"] is False
    assert cold["topology"] == "linear"
