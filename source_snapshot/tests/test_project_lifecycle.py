from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    SqlitePlantProjectDraftRepository,
    normalized_project_lifecycle_status,
)
from services.plant_project_draft_schema import PlantDesignProjectDraft
from services.project_lifecycle import (
    BACKEND_JSON,
    BACKEND_SQLITE,
    InvalidProjectName,
    ProjectAlreadyArchived,
    ProjectLifecycleService,
    ProjectLifecycleWriteError,
    ProjectNameConflict,
    ProjectNotArchived,
    ProjectNotFound,
    UnsupportedProjectBackend,
)
from services.project_center_query import normalized_lifecycle_status


def _sqlite_repository(tmp_path: Path) -> SqlitePlantProjectDraftRepository:
    database = tmp_path / "projects.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            CREATE TABLE project_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                version INTEGER NOT NULL,
                chassis TEXT,
                design_data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                creator TEXT,
                status TEXT
            )
            """
        )
        connection.commit()
    finally:
        connection.close()
    return SqlitePlantProjectDraftRepository(database)


def _draft(name: str, *, workflow_type: str = "single_gene") -> PlantDesignProjectDraft:
    draft = PlantDesignProjectDraft.blank(project_name=name)
    draft.workflow_type = workflow_type
    draft.draft_status = "draft"
    draft.manual_review_state = {
        "formal_project_workflow_v1": {
            "project_id": draft.project_id,
            "project_name": name,
            "project_definition": {"project_name": name, "plant_host": "rice"},
            "runtime_cache": {"ignored": True},
            "mvp_project_id": draft.project_id,
        },
        "cache": {"ignored": True},
    }
    draft.extra_fields = {
        "future_compatible_field": {"retained": True},
        "export_directory": "C:/old-output",
    }
    return draft


def _service(tmp_path: Path) -> tuple[ProjectLifecycleService, PlantProjectDraftRepository, SqlitePlantProjectDraftRepository]:
    json_repository = PlantProjectDraftRepository(tmp_path / "json")
    sqlite_repository = _sqlite_repository(tmp_path)
    return (
        ProjectLifecycleService(
            json_repository=json_repository,
            sqlite_repository=sqlite_repository,
        ),
        json_repository,
        sqlite_repository,
    )


def test_rename_json_preserves_identity_unknown_fields_and_updates_embedded_name(tmp_path: Path) -> None:
    service, json_repository, _ = _service(tmp_path)
    source = _draft("原始项目")
    source_payload = copy.deepcopy(source.to_dict())
    json_repository.save(source)

    result = service.rename_project(source.project_id, "  重命名项目  ")
    renamed = json_repository.load(source.project_id)

    assert result.backend == BACKEND_JSON
    assert result.project_name == "重命名项目"
    assert renamed.project_id == source.project_id
    assert renamed.created_at == source.created_at
    assert renamed.updated_at > source.updated_at
    assert renamed.extra_fields["future_compatible_field"] == {"retained": True}
    assert renamed.manual_review_state["formal_project_workflow_v1"]["project_name"] == "重命名项目"
    assert source.to_dict() == source_payload


def test_rename_sqlite_keeps_row_created_at_and_uses_the_existing_envelope(tmp_path: Path) -> None:
    service, _, sqlite_repository = _service(tmp_path)
    source = _draft("Multi-TU", workflow_type="multi_tu")
    sqlite_repository.save(source)
    connection = sqlite3.connect(sqlite_repository.database_path)
    try:
        before_created_at = connection.execute("SELECT created_at FROM project_history").fetchone()[0]
    finally:
        connection.close()

    result = service.rename_project(source.project_id, "Multi-TU 重命名")
    renamed = sqlite_repository.load(source.project_id)
    connection = sqlite3.connect(sqlite_repository.database_path)
    try:
        after_created_at = connection.execute("SELECT created_at FROM project_history").fetchone()[0]
    finally:
        connection.close()

    assert result.backend == BACKEND_SQLITE
    assert renamed.project_id == source.project_id
    assert renamed.created_at == source.created_at
    assert renamed.updated_at > source.updated_at
    assert before_created_at == after_created_at


def test_gate3_json_draft_rename_and_duplicate_keep_design_state(tmp_path: Path) -> None:
    service, json_repository, _ = _service(tmp_path)
    source = _draft("Gate 3 草稿", workflow_type="gate3_pathway")
    source.manual_review_state["gate3_pathway_draft"] = {
        "project_id": source.project_id,
        "project_name": source.project_name,
        "project_type": "dual_tu",
    }
    json_repository.save(source)

    service.rename_project(source.project_id, "Gate 3 已重命名")
    copied = service.duplicate_project(source.project_id)
    duplicate = json_repository.load(copied.project_id)

    assert duplicate.workflow_type == "gate3_pathway"
    assert duplicate.draft_status == source.draft_status
    assert duplicate.manual_review_state["gate3_pathway_draft"]["project_id"] == duplicate.project_id
    assert duplicate.manual_review_state["gate3_pathway_draft"]["project_name"] == copied.project_name


@pytest.mark.parametrize("bad_name", ["", "   ", "name\nnext", "name\x00next", "x" * 121])
def test_rename_rejects_invalid_names(tmp_path: Path, bad_name: str) -> None:
    service, json_repository, _ = _service(tmp_path)
    source = _draft("有效项目")
    json_repository.save(source)

    with pytest.raises(InvalidProjectName):
        service.rename_project(source.project_id, bad_name)
    assert json_repository.load(source.project_id).project_name == "有效项目"


def test_rename_rejects_casefolded_name_conflicts_across_backends(tmp_path: Path) -> None:
    service, json_repository, sqlite_repository = _service(tmp_path)
    json_source = _draft("First")
    sqlite_source = _draft("项目", workflow_type="multi_tu")
    json_repository.save(json_source)
    sqlite_repository.save(sqlite_source)

    with pytest.raises(ProjectNameConflict):
        service.rename_project(sqlite_source.project_id, "  first ")


def test_duplicate_json_creates_new_identity_without_copying_cache_or_paths(tmp_path: Path) -> None:
    service, json_repository, _ = _service(tmp_path)
    source = _draft("单基因项目")
    source_snapshot = copy.deepcopy(source.to_dict())
    json_repository.save(source)

    result = service.duplicate_project(source.project_id)
    duplicate = json_repository.load(result.project_id)
    original = json_repository.load(source.project_id)

    assert result.backend == BACKEND_JSON
    assert duplicate.project_id != source.project_id
    assert duplicate.created_at == duplicate.updated_at
    assert duplicate.created_at != source.created_at
    assert duplicate.project_name == "单基因项目 - 副本"
    assert duplicate.extra_fields["duplicated_from"] == source.project_id
    assert "export_directory" not in duplicate.extra_fields
    assert "cache" not in duplicate.manual_review_state
    assert "runtime_cache" not in duplicate.manual_review_state["formal_project_workflow_v1"]
    assert "mvp_project_id" not in duplicate.manual_review_state["formal_project_workflow_v1"]
    assert duplicate.manual_review_state["formal_project_workflow_v1"]["project_id"] == duplicate.project_id
    assert original.to_dict() == source_snapshot


def test_duplicate_sqlite_creates_independent_row_and_preserves_original(tmp_path: Path) -> None:
    service, _, sqlite_repository = _service(tmp_path)
    source = _draft("多转录单元", workflow_type="multi_tu")
    sqlite_repository.save(source)

    copied = service.duplicate_project(source.project_id)
    original = sqlite_repository.load(source.project_id)
    duplicate = sqlite_repository.load(copied.project_id)

    assert copied.backend == BACKEND_SQLITE
    assert original.to_dict() == source.to_dict()
    assert duplicate.project_id != original.project_id
    assert duplicate.project_name == "多转录单元 - 副本"
    assert duplicate.workflow_type == "multi_tu"
    assert duplicate.extra_fields["duplicated_from"] == original.project_id


def test_duplicate_name_suffixes_increment_and_do_not_loop_indefinitely(tmp_path: Path) -> None:
    service, json_repository, _ = _service(tmp_path)
    source = _draft("项目")
    json_repository.save(source)
    first = service.duplicate_project(source.project_id)
    second = service.duplicate_project(source.project_id)
    third = service.duplicate_project(source.project_id)

    assert [first.project_name, second.project_name, third.project_name] == [
        "项目 - 副本",
        "项目 - 副本 (2)",
        "项目 - 副本 (3)",
    ]


def test_single_gene_rename_and_duplicate_regenerate_the_embedded_review_package(tmp_path: Path) -> None:
    from mvp_app import generate_complete_vector, load_real_case
    from services.mvp_single_gene_persistence import (
        open_mvp_single_gene_design,
        save_mvp_single_gene_design,
    )

    service, json_repository, _ = _service(tmp_path)
    source = generate_complete_vector(
        load_real_case(), project_id="lifecycle-single-gene", project_name="原始单基因项目"
    )
    saved = save_mvp_single_gene_design(source, repository=json_repository)

    renamed = service.rename_project(saved.project_id, "重命名单基因项目")
    duplicate = service.duplicate_project(saved.project_id)

    assert open_mvp_single_gene_design(renamed.project_id, repository=json_repository)["project_name"] == renamed.project_name
    assert open_mvp_single_gene_design(duplicate.project_id, repository=json_repository)["project_name"] == duplicate.project_name
    assert json_repository.load(duplicate.project_id).extra_fields["duplicated_from"] == saved.project_id


def test_write_failures_preserve_json_source_and_surface_a_safe_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, json_repository, _ = _service(tmp_path)
    source = _draft("原项目")
    json_repository.save(source)
    before = (json_repository.storage_dir / f"{source.project_id}.json").read_bytes()

    def broken_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk failure")

    monkeypatch.setattr(json_repository, "_atomic_write_json", broken_write)
    with pytest.raises(ProjectLifecycleWriteError):
        service.rename_project(source.project_id, "不会保存")
    assert (json_repository.storage_dir / f"{source.project_id}.json").read_bytes() == before


def test_sqlite_failure_rolls_back_without_creating_a_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, _, sqlite_repository = _service(tmp_path)
    source = _draft("事务项目", workflow_type="multi_tu")
    sqlite_repository.save(source)

    def broken_envelope(_draft: PlantDesignProjectDraft) -> str:
        raise RuntimeError("serialization failure")

    monkeypatch.setattr(sqlite_repository, "_envelope", broken_envelope)
    with pytest.raises(ProjectLifecycleWriteError):
        service.duplicate_project(source.project_id)
    assert [summary.project_id for summary in sqlite_repository.list_summaries()] == [source.project_id]


def test_not_found_and_unsupported_backend_are_explicit(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)

    with pytest.raises(ProjectNotFound):
        service.rename_project("plant-draft-missing", "不存在")
    with pytest.raises(UnsupportedProjectBackend):
        service.rename_project("plant-draft-missing", "不存在", backend="memory")


def test_archive_and_unarchive_json_preserve_identity_business_status_and_unknown_fields(tmp_path: Path) -> None:
    service, json_repository, _ = _service(tmp_path)
    source = _draft("JSON 归档项目")
    source.draft_status = "completed"
    source_payload = copy.deepcopy(source.to_dict())
    json_repository.save(source)

    archived_result = service.archive_project(source.project_id)
    archived = json_repository.load(source.project_id)

    assert archived_result.operation == "archive"
    assert archived.project_id == source.project_id
    assert archived.created_at == source.created_at
    assert archived.draft_status == "completed"
    assert archived.extra_fields["lifecycle_status"] == "archived"
    assert archived.extra_fields["archived_at"]
    assert archived.extra_fields["future_compatible_field"] == {"retained": True}
    assert source.to_dict() == source_payload
    assert service.project_lifecycle_state(source.project_id).lifecycle_status == "archived"

    restored_result = service.unarchive_project(source.project_id)
    restored = json_repository.load(source.project_id)

    assert restored_result.operation == "unarchive"
    assert restored.project_id == source.project_id
    assert restored.created_at == source.created_at
    assert restored.draft_status == "completed"
    assert restored.extra_fields["lifecycle_status"] == "active"
    assert restored.extra_fields["archived_at"] is None


def test_archive_and_unarchive_sqlite_use_existing_envelope_transaction(tmp_path: Path) -> None:
    service, _, sqlite_repository = _service(tmp_path)
    source = _draft("SQLite 归档项目", workflow_type="multi_tu")
    source.draft_status = "blocked"
    sqlite_repository.save(source)

    service.archive_project(source.project_id, backend=BACKEND_SQLITE)
    archived = sqlite_repository.load(source.project_id)
    assert archived.project_id == source.project_id
    assert archived.created_at == source.created_at
    assert archived.draft_status == "blocked"
    assert archived.extra_fields["lifecycle_status"] == "archived"
    assert archived.extra_fields["archived_at"]

    service.unarchive_project(source.project_id, backend=BACKEND_SQLITE)
    restored = sqlite_repository.load(source.project_id)
    assert restored.extra_fields["lifecycle_status"] == "active"
    assert restored.extra_fields["archived_at"] is None


def test_archive_supports_gate3_json_drafts_and_legacy_records_default_to_active(tmp_path: Path) -> None:
    service, json_repository, _ = _service(tmp_path)
    source = _draft("Gate 3 草稿", workflow_type="gate3_pathway")
    source.extra_fields.pop("lifecycle_status", None)
    json_repository.save(source)

    assert service.project_lifecycle_state(source.project_id).lifecycle_status == "active"
    service.archive_project(source.project_id, backend=BACKEND_JSON)
    assert json_repository.load(source.project_id).extra_fields["lifecycle_status"] == "archived"


@pytest.mark.parametrize(
    ("present", "value", "expected"),
    [
        (False, None, "active"),
        (True, "active", "active"),
        (True, "archived", "archived"),
        (True, None, "unknown"),
        (True, "", "unknown"),
        (True, 0, "unknown"),
        (True, False, "unknown"),
        (True, [], "unknown"),
        (True, {}, "unknown"),
        (True, "invalid", "unknown"),
        (True, "ARCHIVED", "unknown"),
        (True, " active ", "unknown"),
        (True, "archived ", "unknown"),
    ],
)
def test_repository_summary_and_project_center_query_share_lifecycle_classification(
    tmp_path: Path, present: bool, value: object, expected: str
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "json")
    draft = _draft(f"lifecycle {expected}")
    repository.save(draft)
    if present:
        path = repository.storage_dir / f"{draft.project_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["lifecycle_status"] = value
        path.write_text(json.dumps(payload), encoding="utf-8")

    summary = repository.list_summaries()[0]
    assert summary.lifecycle_status == expected
    assert normalized_lifecycle_status(summary.lifecycle_status) == expected


def test_lifecycle_rejects_repeated_or_unknown_state_changes_without_writing(tmp_path: Path) -> None:
    service, json_repository, _ = _service(tmp_path)
    source = _draft("状态保护")
    json_repository.save(source)

    with pytest.raises(ProjectNotArchived):
        service.unarchive_project(source.project_id)
    service.archive_project(source.project_id)
    archived_at = json_repository.load(source.project_id).extra_fields["archived_at"]
    with pytest.raises(ProjectAlreadyArchived):
        service.archive_project(source.project_id)
    assert json_repository.load(source.project_id).extra_fields["archived_at"] == archived_at

    unknown = _draft("未知状态")
    json_repository.save(unknown)
    path = json_repository.storage_dir / f"{unknown.project_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["lifecycle_status"] = "held"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert service.project_lifecycle_state(unknown.project_id).lifecycle_status == "unknown"
    with pytest.raises(ValueError, match="生命周期状态未知"):
        service.archive_project(unknown.project_id)


def test_archive_write_failures_preserve_json_and_sqlite_source_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, json_repository, sqlite_repository = _service(tmp_path)
    json_source = _draft("JSON 写入失败")
    json_repository.save(json_source)
    json_before = (json_repository.storage_dir / f"{json_source.project_id}.json").read_bytes()

    monkeypatch.setattr(json_repository, "_atomic_write_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk failure")))
    with pytest.raises(ProjectLifecycleWriteError):
        service.archive_project(json_source.project_id)
    assert (json_repository.storage_dir / f"{json_source.project_id}.json").read_bytes() == json_before

    sqlite_source = _draft("SQLite 写入失败", workflow_type="multi_tu")
    sqlite_repository.save(sqlite_source)
    monkeypatch.setattr(sqlite_repository, "_envelope", lambda _draft: (_ for _ in ()).throw(RuntimeError("encode failure")))
    with pytest.raises(ProjectLifecycleWriteError):
        service.archive_project(sqlite_source.project_id, backend=BACKEND_SQLITE)
    assert sqlite_repository.load(sqlite_source.project_id).extra_fields.get("lifecycle_status") is None


@pytest.mark.parametrize("backend", [BACKEND_JSON, BACKEND_SQLITE])
def test_archived_repository_save_is_rejected_before_mutation(tmp_path: Path, backend: str) -> None:
    service, json_repository, sqlite_repository = _service(tmp_path)
    repository = json_repository if backend == BACKEND_JSON else sqlite_repository
    source = _draft(f"{backend} write guard", workflow_type="multi_tu")
    repository.save(source)
    service.archive_project(source.project_id, backend=backend)
    before = repository.load(source.project_id).to_dict()
    attempted = repository.load(source.project_id)
    attempted.project_name = "must not persist"

    with pytest.raises(ValueError, match="does not allow editing or saving"):
        repository.save(attempted)

    assert repository.load(source.project_id).to_dict() == before


def test_archived_single_gene_open_is_rejected_without_restoring_design(tmp_path: Path) -> None:
    from services.mvp_single_gene_persistence import (
        MvpSingleGenePersistenceError,
        open_mvp_single_gene_design,
        save_mvp_single_gene_design,
    )
    from mvp_app import generate_complete_vector, load_real_case

    repository = PlantProjectDraftRepository(tmp_path / "json")
    result = generate_complete_vector(load_real_case(), project_id="archived-open-guard", project_name="Archived open guard")
    saved = save_mvp_single_gene_design(result, repository=repository)
    service = ProjectLifecycleService(json_repository=repository, sqlite_repository=_sqlite_repository(tmp_path))
    service.archive_project(saved.project_id, backend=BACKEND_JSON)

    with pytest.raises(MvpSingleGenePersistenceError, match="does not allow editing or saving"):
        open_mvp_single_gene_design(saved.project_id, repository=repository)


def test_unarchive_then_open_and_save_remains_supported(tmp_path: Path) -> None:
    from services.mvp_single_gene_persistence import open_mvp_single_gene_design, save_mvp_single_gene_design
    from mvp_app import generate_complete_vector, load_real_case

    repository = PlantProjectDraftRepository(tmp_path / "json")
    result = generate_complete_vector(load_real_case(), project_id="unarchive-open-guard", project_name="Unarchive open guard")
    saved = save_mvp_single_gene_design(result, repository=repository)
    service = ProjectLifecycleService(json_repository=repository, sqlite_repository=_sqlite_repository(tmp_path))
    service.archive_project(saved.project_id, backend=BACKEND_JSON)
    service.unarchive_project(saved.project_id, backend=BACKEND_JSON)

    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)
    save_mvp_single_gene_design(reopened, repository=repository)
    assert repository.load(saved.project_id).project_name == "Unarchive open guard"


@pytest.mark.parametrize("invalid_status", [None, "", 0, False, [], {}, "invalid", "deleted", "ARCHIVED", " active "])
def test_present_invalid_lifecycle_values_fail_closed(invalid_status: object) -> None:
    draft = _draft("invalid lifecycle")
    draft.extra_fields["lifecycle_status"] = invalid_status

    assert normalized_project_lifecycle_status(draft) == "unknown"


@pytest.mark.parametrize("backend", [BACKEND_JSON, BACKEND_SQLITE])
def test_dedicated_transition_changes_only_lifecycle_metadata(tmp_path: Path, backend: str) -> None:
    _service_instance, json_repository, sqlite_repository = _service(tmp_path)
    repository = json_repository if backend == BACKEND_JSON else sqlite_repository
    source = _draft(f"{backend} transition", workflow_type="multi_tu")
    repository.save(source)
    before = repository.load(source.project_id).to_dict()

    archived = repository.transition_project_lifecycle(
        source.project_id,
        "active",
        "archived",
        "2026-08-07T00:00:00Z",
    )
    after_archive = archived.to_dict()
    for key in ("lifecycle_status", "archived_at", "updated_at"):
        before.pop(key, None)
        after_archive.pop(key, None)
    assert after_archive == before

    restored = repository.transition_project_lifecycle(
        source.project_id,
        "archived",
        "active",
        None,
    )
    assert restored.extra_fields["lifecycle_status"] == "active"
    assert restored.extra_fields["archived_at"] is None


@pytest.mark.parametrize("backend", [BACKEND_JSON, BACKEND_SQLITE])
def test_repository_transition_rejects_invalid_or_stale_state_without_mutation(tmp_path: Path, backend: str) -> None:
    _service_instance, json_repository, sqlite_repository = _service(tmp_path)
    repository = json_repository if backend == BACKEND_JSON else sqlite_repository
    source = _draft(f"{backend} invalid transition", workflow_type="multi_tu")
    repository.save(source)
    before = repository.load(source.project_id).to_dict()

    for expected, target, timestamp in (
        ("active", "active", None),
        ("archived", "archived", None),
        ("archived", "active", None),
        ("active", "archived", None),
    ):
        with pytest.raises(ValueError):
            repository.transition_project_lifecycle(source.project_id, expected, target, timestamp)
        assert repository.load(source.project_id).to_dict() == before


def test_public_save_has_no_lifecycle_bypass_parameter(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "json")
    source = _draft("no public lifecycle bypass")
    repository.save(source)
    with pytest.raises(TypeError):
        repository.save(source, allow_lifecycle_transition=True)  # type: ignore[call-arg]


@pytest.mark.parametrize("status", ["archived", "invalid", ""])
def test_controller_open_rejects_non_active_projects_without_session_changes(tmp_path: Path, status: str) -> None:
    from services.plant_project_draft_controller import PlantProjectDraftController

    repository = PlantProjectDraftRepository(tmp_path / "json")
    source = _draft("controller lifecycle guard")
    repository.save(source)
    if status == "archived":
        ProjectLifecycleService(json_repository=repository).archive_project(source.project_id, backend=BACKEND_JSON)
    else:
        path = repository.storage_dir / f"{source.project_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["lifecycle_status"] = status
        path.write_text(json.dumps(payload), encoding="utf-8")
    persisted_path = repository.storage_dir / f"{source.project_id}.json"
    persisted_before = persisted_path.read_bytes()
    session_state = {"unrelated": "retain"}

    result = PlantProjectDraftController(
        session_state=session_state,
        repository=repository,
    ).open_project(source.project_id)

    assert result.ok is False
    assert session_state == {"unrelated": "retain"}
    assert persisted_path.read_bytes() == persisted_before
