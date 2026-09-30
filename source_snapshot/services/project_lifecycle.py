"""Minimal lifecycle operations for persisted formal project records.

The service deliberately owns backend selection and write behaviour so the
Project Center UI never needs to write project JSON or SQL directly.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Literal

from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    SqlitePlantProjectDraftRepository,
    normalized_project_lifecycle_status,
    require_active_project,
)
from services.plant_project_draft_schema import (
    PlantDesignProjectDraft,
    PlantProjectDraftError,
    new_project_id,
    utc_timestamp,
)


BACKEND_JSON = "json"
BACKEND_SQLITE = "sqlite"
ProjectBackend = Literal["json", "sqlite"]
MAX_PROJECT_NAME_LENGTH = 120
MAX_COPY_NAME_ATTEMPTS = 1_000


class ProjectLifecycleError(ValueError):
    """A lifecycle failure whose message is suitable for Project Center UI."""


class ProjectNotFound(ProjectLifecycleError):
    pass


class InvalidProjectName(ProjectLifecycleError):
    pass


class ProjectNameConflict(ProjectLifecycleError):
    pass


class UnsupportedProjectBackend(ProjectLifecycleError):
    pass


class ProjectLifecycleWriteError(ProjectLifecycleError):
    pass


class ProjectAlreadyArchived(ProjectLifecycleError):
    pass


class ProjectNotArchived(ProjectLifecycleError):
    pass


class ProjectHasUnsavedChanges(ProjectLifecycleError):
    pass


class UnknownProjectLifecycleStatus(ProjectLifecycleError):
    pass


@dataclass(frozen=True)
class ProjectLifecycleResult:
    success: bool
    project_id: str
    project_name: str
    backend: ProjectBackend
    operation: Literal["rename", "duplicate", "archive", "unarchive"]
    message: str


@dataclass(frozen=True)
class ProjectLifecycleState:
    """Read-only lifecycle metadata for a persisted project record."""

    project_id: str
    backend: ProjectBackend
    lifecycle_status: str
    archived_at: str
    updated_at: str


class ProjectLifecycleService:
    """Persist Project Center lifecycle changes through existing repositories."""

    def __init__(
        self,
        *,
        json_repository: PlantProjectDraftRepository | None = None,
        sqlite_repository: SqlitePlantProjectDraftRepository | None = None,
    ) -> None:
        self.json_repository = json_repository or PlantProjectDraftRepository()
        self.sqlite_repository = sqlite_repository or SqlitePlantProjectDraftRepository()

    def rename_project(
        self, project_id: object, project_name: object, *, backend: str | None = None
    ) -> ProjectLifecycleResult:
        clean_name = _validated_project_name(project_name)
        resolved_backend, repository, draft = self._project_record(project_id, backend=backend)
        try:
            require_active_project(draft)
        except PlantProjectDraftError as exc:
            raise UnknownProjectLifecycleStatus(str(exc)) from exc
        if clean_name != draft.project_name:
            self._ensure_name_available(clean_name, excluding_project_id=draft.project_id)

        if resolved_backend == BACKEND_JSON and _is_mvp_single_gene_draft(draft):
            renamed = _persist_single_gene_identity(
                draft,
                repository,
                project_id=draft.project_id,
                project_name=clean_name,
                duplicate=False,
            )
            return ProjectLifecycleResult(
                success=True,
                project_id=renamed.project_id,
                project_name=renamed.project_name,
                backend=resolved_backend,
                operation="rename",
                message="项目名称已更新。",
            )

        renamed = _copy_draft(draft)
        renamed.project_name = clean_name
        renamed.updated_at = utc_timestamp()
        _replace_embedded_project_identity(
            renamed.manual_review_state,
            source_project_id=draft.project_id,
            source_project_name=draft.project_name,
            project_id=draft.project_id,
            project_name=clean_name,
        )
        self._write_existing(resolved_backend, repository, renamed)
        return ProjectLifecycleResult(
            success=True,
            project_id=renamed.project_id,
            project_name=renamed.project_name,
            backend=resolved_backend,
            operation="rename",
            message="项目名称已更新。",
        )

    def duplicate_project(
        self, project_id: object, *, backend: str | None = None
    ) -> ProjectLifecycleResult:
        resolved_backend, repository, source = self._project_record(project_id, backend=backend)
        try:
            require_active_project(source)
        except PlantProjectDraftError as exc:
            raise UnknownProjectLifecycleStatus(str(exc)) from exc
        copied_name = self._next_copy_name(source.project_name)
        if resolved_backend == BACKEND_JSON and _is_mvp_single_gene_draft(source):
            duplicate = _persist_single_gene_identity(
                source,
                repository,
                project_id=new_project_id(),
                project_name=copied_name,
                duplicate=True,
            )
            return ProjectLifecycleResult(
                success=True,
                project_id=duplicate.project_id,
                project_name=duplicate.project_name,
                backend=resolved_backend,
                operation="duplicate",
                message="项目副本已创建。",
            )
        timestamp = utc_timestamp()
        duplicate = _copy_draft(source)
        duplicate.project_id = new_project_id()
        duplicate.project_name = copied_name
        duplicate.created_at = timestamp
        duplicate.updated_at = timestamp
        duplicate.extra_fields["duplicated_from"] = source.project_id
        _strip_nonpersistent_copy_values(duplicate.extra_fields)
        _replace_embedded_project_identity(
            duplicate.manual_review_state,
            source_project_id=source.project_id,
            source_project_name=source.project_name,
            project_id=duplicate.project_id,
            project_name=copied_name,
        )
        _strip_nonpersistent_copy_values(duplicate.manual_review_state)
        self._write_new(resolved_backend, repository, duplicate)
        return ProjectLifecycleResult(
            success=True,
            project_id=duplicate.project_id,
            project_name=duplicate.project_name,
            backend=resolved_backend,
            operation="duplicate",
            message="项目副本已创建。",
        )

    def project_lifecycle_state(
        self, project_id: object, *, backend: str | None = None
    ) -> ProjectLifecycleState:
        resolved_backend, _, draft = self._project_record(project_id, backend=backend)
        return ProjectLifecycleState(
            project_id=draft.project_id,
            backend=resolved_backend,
            lifecycle_status=_lifecycle_status(draft),
            archived_at=_text(draft.extra_fields.get("archived_at")),
            updated_at=draft.updated_at,
        )

    def archive_project(
        self, project_id: object, *, backend: str | None = None
    ) -> ProjectLifecycleResult:
        resolved_backend, repository, draft = self._project_record(project_id, backend=backend)
        status = _lifecycle_status(draft)
        if status == "archived":
            raise ProjectAlreadyArchived("项目已经归档。")
        if status != "active":
            raise UnknownProjectLifecycleStatus("项目生命周期状态未知，无法归档。")
        timestamp = utc_timestamp()
        archived = _copy_draft(draft)
        archived.updated_at = timestamp
        archived.extra_fields["lifecycle_status"] = "archived"
        archived.extra_fields["archived_at"] = timestamp
        self._transition_lifecycle(
            repository,
            project_id=draft.project_id,
            expected_status="active",
            target_status="archived",
            archived_at=timestamp,
        )
        return ProjectLifecycleResult(
            success=True,
            project_id=archived.project_id,
            project_name=archived.project_name,
            backend=resolved_backend,
            operation="archive",
            message="项目已归档。",
        )

    def unarchive_project(
        self, project_id: object, *, backend: str | None = None
    ) -> ProjectLifecycleResult:
        resolved_backend, repository, draft = self._project_record(project_id, backend=backend)
        status = _lifecycle_status(draft)
        if status == "active":
            raise ProjectNotArchived("项目当前未归档。")
        if status != "archived":
            raise UnknownProjectLifecycleStatus("项目生命周期状态未知，无法取消归档。")
        restored = _copy_draft(draft)
        restored.updated_at = utc_timestamp()
        restored.extra_fields["lifecycle_status"] = "active"
        # JSON saves merge retained unknown fields from the existing record, so
        # an explicit null is required to clear this known lifecycle field.
        restored.extra_fields["archived_at"] = None
        self._transition_lifecycle(
            repository,
            project_id=draft.project_id,
            expected_status="archived",
            target_status="active",
            archived_at=None,
        )
        return ProjectLifecycleResult(
            success=True,
            project_id=restored.project_id,
            project_name=restored.project_name,
            backend=resolved_backend,
            operation="unarchive",
            message="项目已取消归档。",
        )

    def _project_record(
        self, project_id: object, *, backend: str | None
    ) -> tuple[ProjectBackend, PlantProjectDraftRepository | SqlitePlantProjectDraftRepository, PlantDesignProjectDraft]:
        clean_project_id = str(project_id or "").strip()
        if not clean_project_id:
            raise ProjectNotFound("未找到项目。")
        requested = _validated_backend(backend)
        candidates: list[tuple[ProjectBackend, PlantProjectDraftRepository | SqlitePlantProjectDraftRepository, PlantDesignProjectDraft]] = []
        for candidate_backend, repository in self._repositories(requested):
            try:
                draft = repository.load(clean_project_id)
            except PlantProjectDraftError:
                continue
            candidates.append((candidate_backend, repository, draft))
        if not candidates:
            raise ProjectNotFound("未找到项目。")
        if len(candidates) != 1:
            raise UnsupportedProjectBackend("项目存储位置不明确，无法执行此操作。")
        return candidates[0]

    def _repositories(
        self, requested: ProjectBackend | None = None
    ) -> tuple[tuple[ProjectBackend, PlantProjectDraftRepository | SqlitePlantProjectDraftRepository], ...]:
        values = (
            (BACKEND_JSON, self.json_repository),
            (BACKEND_SQLITE, self.sqlite_repository),
        )
        return tuple(item for item in values if requested is None or item[0] == requested)

    def _all_project_names(self) -> list[tuple[str, str]]:
        names: list[tuple[str, str]] = []
        for _, repository in self._repositories():
            try:
                names.extend((summary.project_id, summary.project_name) for summary in repository.list_summaries())
            except PlantProjectDraftError:
                continue
        return names

    def _ensure_name_available(self, name: str, *, excluding_project_id: str = "") -> None:
        wanted = _normalized_name(name)
        for candidate_id, candidate_name in self._all_project_names():
            if candidate_id == excluding_project_id:
                continue
            if _normalized_name(candidate_name) == wanted:
                raise ProjectNameConflict("项目名称已存在。")

    def _next_copy_name(self, source_name: str) -> str:
        base = f"{source_name} - 副本"
        for index in range(1, MAX_COPY_NAME_ATTEMPTS + 1):
            candidate = base if index == 1 else f"{base} ({index})"
            if len(candidate) > MAX_PROJECT_NAME_LENGTH:
                raise InvalidProjectName("项目名称过长，无法创建副本。")
            try:
                self._ensure_name_available(candidate)
            except ProjectNameConflict:
                continue
            return candidate
        raise ProjectLifecycleWriteError("无法生成可用的副本名称。")

    def _write_existing(
        self,
        backend: ProjectBackend,
        repository: PlantProjectDraftRepository | SqlitePlantProjectDraftRepository,
        draft: PlantDesignProjectDraft,
    ) -> None:
        try:
            if backend == BACKEND_JSON:
                repository.save(draft)
            else:
                _sqlite_update_draft(repository, draft)
        except ProjectLifecycleError:
            raise
        except Exception as exc:
            raise ProjectLifecycleWriteError("项目无法保存，原记录未更改。") from exc

    def _transition_lifecycle(
        self,
        repository: PlantProjectDraftRepository | SqlitePlantProjectDraftRepository,
        *,
        project_id: str,
        expected_status: str,
        target_status: str,
        archived_at: str | None,
    ) -> None:
        try:
            repository.transition_project_lifecycle(
                project_id,
                expected_status,
                target_status,
                archived_at,
            )
        except ProjectLifecycleError:
            raise
        except Exception as exc:
            raise ProjectLifecycleWriteError("Project lifecycle transition could not be saved; the original record was unchanged.") from exc

    def _write_new(
        self,
        backend: ProjectBackend,
        repository: PlantProjectDraftRepository | SqlitePlantProjectDraftRepository,
        draft: PlantDesignProjectDraft,
    ) -> None:
        try:
            if backend == BACKEND_JSON:
                repository.save(draft)
            else:
                _sqlite_insert_draft(repository, draft)
        except ProjectLifecycleError:
            raise
        except Exception as exc:
            raise ProjectLifecycleWriteError("项目副本无法保存，原记录未更改。") from exc


def rename_project(project_id: object, project_name: object, **kwargs: Any) -> ProjectLifecycleResult:
    return ProjectLifecycleService(
        json_repository=kwargs.pop("json_repository", None),
        sqlite_repository=kwargs.pop("sqlite_repository", None),
    ).rename_project(project_id, project_name, **kwargs)


def duplicate_project(project_id: object, **kwargs: Any) -> ProjectLifecycleResult:
    return ProjectLifecycleService(
        json_repository=kwargs.pop("json_repository", None),
        sqlite_repository=kwargs.pop("sqlite_repository", None),
    ).duplicate_project(project_id, **kwargs)


def project_lifecycle_state(project_id: object, **kwargs: Any) -> ProjectLifecycleState:
    return ProjectLifecycleService(
        json_repository=kwargs.pop("json_repository", None),
        sqlite_repository=kwargs.pop("sqlite_repository", None),
    ).project_lifecycle_state(project_id, **kwargs)


def archive_project(project_id: object, **kwargs: Any) -> ProjectLifecycleResult:
    return ProjectLifecycleService(
        json_repository=kwargs.pop("json_repository", None),
        sqlite_repository=kwargs.pop("sqlite_repository", None),
    ).archive_project(project_id, **kwargs)


def unarchive_project(project_id: object, **kwargs: Any) -> ProjectLifecycleResult:
    return ProjectLifecycleService(
        json_repository=kwargs.pop("json_repository", None),
        sqlite_repository=kwargs.pop("sqlite_repository", None),
    ).unarchive_project(project_id, **kwargs)


def _validated_backend(value: str | None) -> ProjectBackend | None:
    if value is None:
        return None
    backend = str(value).strip().casefold()
    if backend not in {BACKEND_JSON, BACKEND_SQLITE}:
        raise UnsupportedProjectBackend("不支持该项目存储类型。")
    return backend  # type: ignore[return-value]


def _validated_project_name(value: object) -> str:
    name = str(value or "").strip()
    if not name:
        raise InvalidProjectName("项目名称不能为空。")
    if len(name) > MAX_PROJECT_NAME_LENGTH:
        raise InvalidProjectName(f"项目名称不能超过 {MAX_PROJECT_NAME_LENGTH} 个字符。")
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise InvalidProjectName("项目名称不能包含换行或控制字符。")
    return name


def _normalized_name(value: object) -> str:
    return str(value or "").strip().casefold()


def _text(value: object) -> str:
    return str(value or "").strip()


def _lifecycle_status(draft: PlantDesignProjectDraft) -> str:
    return normalized_project_lifecycle_status(draft)


def _copy_draft(draft: PlantDesignProjectDraft) -> PlantDesignProjectDraft:
    return PlantDesignProjectDraft.from_dict(copy.deepcopy(draft.to_dict()))


def _is_mvp_single_gene_draft(draft: PlantDesignProjectDraft) -> bool:
    return isinstance(draft.manual_review_state.get("mvp_single_gene_persistence"), dict)


def _persist_single_gene_identity(
    source: PlantDesignProjectDraft,
    repository: PlantProjectDraftRepository | SqlitePlantProjectDraftRepository,
    *,
    project_id: str,
    project_name: str,
    duplicate: bool,
) -> PlantDesignProjectDraft:
    """Regenerate the embedded review package when a single-gene name changes."""
    if not isinstance(repository, PlantProjectDraftRepository):
        raise UnsupportedProjectBackend("单基因项目不支持该项目存储类型。")
    try:
        from services.mvp_single_gene_persistence import (
            MvpSingleGenePersistenceError,
            open_mvp_single_gene_design,
            save_mvp_single_gene_design,
        )

        result = copy.deepcopy(open_mvp_single_gene_design(source.project_id, repository=repository))
        result["project_id"] = project_id
        result["project_name"] = project_name
        _replace_embedded_project_identity(
            result,
            source_project_id=source.project_id,
            source_project_name=source.project_name,
            project_id=project_id,
            project_name=project_name,
        )
        # The package root incorporates the display name. It is regenerated
        # from the same canonical runtime rather than copied as an old export.
        result.pop("company_review_package", None)
        saved = save_mvp_single_gene_design(result, repository=repository)
        persisted = repository.load(saved.project_id)
        persisted.extra_fields = copy.deepcopy(source.extra_fields)
        if duplicate:
            persisted.extra_fields["duplicated_from"] = source.project_id
            _strip_nonpersistent_copy_values(persisted.extra_fields)
            _strip_nonpersistent_copy_values(persisted.manual_review_state)
        repository.save(persisted)
        return repository.load(saved.project_id)
    except (PlantProjectDraftError, MvpSingleGenePersistenceError) as exc:
        if duplicate:
            try:
                repository.delete(project_id)
            except PlantProjectDraftError:
                pass
        raise ProjectLifecycleWriteError("项目无法保存，原记录未更改。") from exc


def _replace_embedded_project_identity(
    value: Any,
    *,
    source_project_id: str,
    source_project_name: str,
    project_id: str,
    project_name: str,
) -> None:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "project_id" and item == source_project_id:
                value[key] = project_id
            elif key == "project_name" and item == source_project_name:
                value[key] = project_name
            else:
                _replace_embedded_project_identity(
                    item,
                    source_project_id=source_project_id,
                    source_project_name=source_project_name,
                    project_id=project_id,
                    project_name=project_name,
                )
    elif isinstance(value, list):
        for item in value:
            _replace_embedded_project_identity(
                item,
                source_project_id=source_project_id,
                source_project_name=source_project_name,
                project_id=project_id,
                project_name=project_name,
            )


def _strip_nonpersistent_copy_values(value: Any) -> None:
    excluded_keys = {
        "cache",
        "runtime_cache",
        "temporary_file",
        "temporary_files",
        "temporary_path",
        "temp_files",
        "export_directory",
        "export_dir",
        "export_path",
        "export_paths",
        "report_path",
        "report_paths",
        "report_file",
        "report_files",
        "mvp_project_id",
        "formal_last_saved_mvp_project_id",
        "formal_last_saved_draft_id",
        "formal_last_saved_gate3_draft_id",
    }
    if isinstance(value, dict):
        for key in list(value):
            if str(key).casefold() in excluded_keys:
                value.pop(key, None)
            else:
                _strip_nonpersistent_copy_values(value[key])
    elif isinstance(value, list):
        for item in value:
            _strip_nonpersistent_copy_values(item)


def _sqlite_update_draft(repository: SqlitePlantProjectDraftRepository, draft: PlantDesignProjectDraft) -> None:
    connection = repository._connect()
    try:
        connection.execute("BEGIN")
        existing = repository._find_record(connection, draft.project_id)
        if existing is None:
            raise ProjectNotFound("未找到项目。")
        cursor = connection.execute(
            "UPDATE project_history SET project_name = ?, design_data = ? WHERE id = ?",
            (draft.project_name, repository._envelope(draft), existing[0]),
        )
        if cursor.rowcount != 1:
            raise ProjectNotFound("未找到项目。")
        connection.commit()
    except ProjectLifecycleError:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        raise PlantProjectDraftError("The formal project transaction could not be committed.") from exc
    finally:
        connection.close()


def _sqlite_insert_draft(repository: SqlitePlantProjectDraftRepository, draft: PlantDesignProjectDraft) -> None:
    connection = repository._connect()
    try:
        connection.execute("BEGIN")
        connection.execute(
            "INSERT INTO project_history "
            "(project_name, version, chassis, design_data, created_at, creator, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                draft.project_name,
                1,
                draft.workflow_type or "multi_tu",
                repository._envelope(draft),
                draft.created_at,
                "BioDesign Studio formal Multi-TU",
                draft.draft_status,
            ),
        )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        raise PlantProjectDraftError("The formal project transaction could not be committed.") from exc
    finally:
        connection.close()
