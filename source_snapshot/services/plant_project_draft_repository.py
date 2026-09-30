from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import resolve_biodesign_db_path

from services.plant_project_draft_schema import (
    PlantDesignProjectDraft,
    PlantProjectDraftError,
    utc_timestamp,
    update_plant_project_draft,
)


PLANT_PROJECT_DRAFT_STORAGE_ENV = "BIODESIGN_PLANT_PROJECT_DRAFT_DIR"
PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
SQLITE_DRAFT_ENVELOPE_KIND = "biodesign.formal_plant_project_draft.v1"
LIFECYCLE_ACTIVE = "active"
LIFECYCLE_ARCHIVED = "archived"
LIFECYCLE_UNKNOWN = "unknown"

_MISSING = object()


def normalized_project_lifecycle_status(
    value: PlantDesignProjectDraft | object = _MISSING,
) -> str:
    """Read lifecycle state without promoting present invalid values to active."""
    if isinstance(value, PlantDesignProjectDraft):
        value = value.extra_fields.get("lifecycle_status", _MISSING)
    if value is _MISSING:
        return LIFECYCLE_ACTIVE
    if value == LIFECYCLE_ACTIVE:
        return LIFECYCLE_ACTIVE
    if value == LIFECYCLE_ARCHIVED:
        return LIFECYCLE_ARCHIVED
    return LIFECYCLE_UNKNOWN


def require_active_project(draft: PlantDesignProjectDraft) -> None:
    """Reject writes or editable restoration unless the durable record is active."""
    status = normalized_project_lifecycle_status(draft)
    if status != "active":
        raise PlantProjectDraftError(
            "Project lifecycle status does not allow editing or saving."
        )


def _assert_lifecycle_fields_unchanged(
    current: PlantDesignProjectDraft, resolved: PlantDesignProjectDraft
) -> None:
    """Keep lifecycle metadata owned by the dedicated transition API."""
    for key in ("lifecycle_status", "archived_at"):
        if key in resolved.extra_fields and resolved.extra_fields[key] != current.extra_fields.get(key, _MISSING):
            raise PlantProjectDraftError(
                "Lifecycle metadata can only be changed through the lifecycle transition API."
            )


def _transition_lifecycle_draft(
    current: PlantDesignProjectDraft,
    expected_status: str,
    target_status: str,
    archived_at: str | None,
) -> PlantDesignProjectDraft:
    if expected_status not in {"active", "archived"} or target_status not in {"active", "archived"}:
        raise PlantProjectDraftError("Lifecycle transitions require active or archived statuses.")
    if expected_status == target_status:
        raise PlantProjectDraftError("Lifecycle transition must change status.")
    if target_status == "archived" and (not isinstance(archived_at, str) or not archived_at):
        raise PlantProjectDraftError("Archived lifecycle transitions require archived_at.")
    if target_status == "active" and archived_at is not None:
        raise PlantProjectDraftError("Active lifecycle transitions must clear archived_at.")
    current_status = normalized_project_lifecycle_status(current)
    if current_status != expected_status:
        raise PlantProjectDraftError("Project lifecycle status did not match the expected transition state.")
    updated = current
    updated.extra_fields = dict(current.extra_fields)
    updated.extra_fields["lifecycle_status"] = target_status
    updated.extra_fields["archived_at"] = archived_at if target_status == "archived" else None
    updated.updated_at = archived_at if target_status == "archived" else utc_timestamp()
    return updated


@dataclass(frozen=True)
class PlantProjectDraftSummary:
    project_id: str
    project_name: str
    updated_at: str
    created_at: str
    draft_status: str
    record_origin: str = "user"
    workflow_type: str = ""
    canonical_available: bool = False
    lifecycle_status: str = ""
    archived_at: str = ""

    def display_label(self) -> str:
        name = self.project_name or "Untitled plant design draft"
        return f"{name} ({self.project_id[-8:]})"


def default_plant_project_draft_storage_dir() -> Path:
    override = os.environ.get(PLANT_PROJECT_DRAFT_STORAGE_ENV)
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if root:
            return Path(root) / "BioDesignStudio" / "plant_design_project_drafts"
    return Path.home() / ".biodesign_studio" / "plant_design_project_drafts"


class PlantProjectDraftRepository:
    def __init__(self, storage_dir: str | os.PathLike[str] | None = None):
        self.storage_dir = Path(storage_dir) if storage_dir is not None else default_plant_project_draft_storage_dir()

    def _ensure_dir(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, project_id: str) -> Path:
        clean_project_id = str(project_id or "").strip()
        if (
            not clean_project_id
            or clean_project_id in {".", ".."}
            or not PROJECT_ID_PATTERN.fullmatch(clean_project_id)
        ):
            raise PlantProjectDraftError("Invalid plant project draft id.")
        storage_root = self.storage_dir.resolve(strict=False)
        path = storage_root / f"{clean_project_id}.json"
        if path.resolve(strict=False).parent != storage_root:
            raise PlantProjectDraftError("Invalid plant project draft path.")
        return path

    def create_blank(self, project_name: str = "") -> PlantDesignProjectDraft:
        return PlantDesignProjectDraft.blank(project_name=project_name)

    def save(
        self,
        draft: PlantDesignProjectDraft | dict[str, Any],
    ) -> PlantDesignProjectDraft:
        resolved = draft if isinstance(draft, PlantDesignProjectDraft) else PlantDesignProjectDraft.from_dict(draft)
        if not resolved.project_name:
            raise PlantProjectDraftError("Project name is required before saving.")
        self._ensure_dir()
        current = None
        target = self._path_for(resolved.project_id)
        if target.exists():
            current = self.load(resolved.project_id)
        if current is not None:
            require_active_project(current)
            _assert_lifecycle_fields_unchanged(current, resolved)
            resolved.extra_fields = {**current.extra_fields, **resolved.extra_fields}
            resolved = update_plant_project_draft(
                resolved,
                project_name=resolved.project_name,
                plant_design_goal=resolved.plant_design_goal,
                host_context=resolved.host_context,
                expression_context=resolved.expression_context,
                construct_slot_updates={
                    slot.slot_key: {
                        "component_name": slot.component_name,
                        "source_reference": slot.source_reference,
                        "evidence_reference": slot.evidence_reference,
                        "notes": slot.notes,
                    }
                    for slot in resolved.construct_slots
                },
                evidence_references=[record.to_dict() for record in resolved.evidence_references],
                canonical_construct_runtime=dict(resolved.canonical_construct_runtime),
                draft_status=resolved.draft_status,
                workflow_type=resolved.workflow_type,
                canonical_available=resolved.canonical_available,
            )
            resolved.created_at = current.created_at
        else:
            require_active_project(resolved)
        self._atomic_write_json(target, resolved.to_dict())
        return resolved

    def restore_exact(
        self,
        snapshot: PlantDesignProjectDraft | dict[str, Any],
    ) -> PlantDesignProjectDraft:
        """Restore an existing record exactly for compensating transactions."""
        resolved = (
            snapshot
            if isinstance(snapshot, PlantDesignProjectDraft)
            else PlantDesignProjectDraft.from_dict(snapshot)
        )
        if not resolved.project_name:
            raise PlantProjectDraftError("Project name is required before restoring.")
        self._ensure_dir()
        target = self._path_for(resolved.project_id)
        if not target.exists():
            raise PlantProjectDraftError("Plant project draft file was not found.")
        current = self.load(resolved.project_id)
        if current.project_id != resolved.project_id:
            raise PlantProjectDraftError("Plant project draft identity changed before restore.")
        self._atomic_write_json(target, resolved.to_dict())
        return self.load(resolved.project_id)

    def transition_project_lifecycle(
        self,
        project_id: str,
        expected_status: str,
        target_status: str,
        archived_at: str | None,
    ) -> PlantDesignProjectDraft:
        current = self.load(project_id)
        updated = _transition_lifecycle_draft(current, expected_status, target_status, archived_at)
        self._atomic_write_json(self._path_for(project_id), updated.to_dict())
        return updated

    def load(self, project_id: str) -> PlantDesignProjectDraft:
        path = self._path_for(project_id)
        if not path.exists():
            raise PlantProjectDraftError("Plant project draft file was not found.")
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise PlantProjectDraftError(f"Plant project draft file is malformed: {exc}") from exc
        except OSError as exc:
            raise PlantProjectDraftError(f"Plant project draft file could not be read: {exc}") from exc
        return PlantDesignProjectDraft.from_dict(payload)

    def delete(self, project_id: str) -> None:
        """Delete one project draft file after validating its identifier."""
        path = self._path_for(project_id)
        if not path.exists():
            raise PlantProjectDraftError("Plant project draft file was not found.")
        try:
            path.unlink()
        except OSError as exc:
            raise PlantProjectDraftError(f"Plant project draft file could not be deleted: {exc}") from exc

    def list_summaries(self) -> list[PlantProjectDraftSummary]:
        if not self.storage_dir.exists():
            return []
        summaries: list[PlantProjectDraftSummary] = []
        for path in self.storage_dir.glob("*.json"):
            try:
                draft = self.load(path.stem)
            except PlantProjectDraftError:
                continue
            summaries.append(
                PlantProjectDraftSummary(
                    project_id=draft.project_id,
                    project_name=draft.project_name,
                    updated_at=draft.updated_at,
                    created_at=draft.created_at,
                    draft_status=draft.draft_status,
                    record_origin=draft.record_origin,
                    workflow_type=draft.workflow_type,
                    canonical_available=draft.canonical_available,
                    lifecycle_status=normalized_project_lifecycle_status(draft),
                    archived_at=(
                        ""
                        if "archived_at" not in draft.extra_fields
                        else str(draft.extra_fields.get("archived_at"))
                    ),
                )
            )
        return sorted(summaries, key=lambda summary: (summary.updated_at, summary.project_id), reverse=True)

    def _atomic_write_json(self, target: Path, payload: dict[str, Any]) -> None:
        tmp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(target.parent),
                prefix=f".{target.stem}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                tmp_name = handle.name
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        except Exception:
            if tmp_name:
                try:
                    Path(tmp_name).unlink(missing_ok=True)
                except OSError:
                    pass
            raise


class SqlitePlantProjectDraftRepository:
    """Store formal project drafts in the existing project_history table."""

    def __init__(self, database_path: str | os.PathLike[str] | None = None):
        self.database_path = Path(database_path or resolve_biodesign_db_path()).resolve(
            strict=False
        )

    def create_blank(self, project_name: str = "") -> PlantDesignProjectDraft:
        return PlantDesignProjectDraft.blank(project_name=project_name)

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise PlantProjectDraftError(
                "The BioDesign Studio database is not initialized for project persistence."
            )
        try:
            connection = sqlite3.connect(str(self.database_path))
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project_history'"
            ).fetchone()
        except sqlite3.Error as exc:
            raise PlantProjectDraftError(
                f"The BioDesign Studio database could not be opened: {exc}"
            ) from exc
        if table is None:
            connection.close()
            raise PlantProjectDraftError(
                "The existing database schema cannot express formal project records."
            )
        return connection

    @staticmethod
    def _decode_envelope(raw: str) -> PlantDesignProjectDraft | None:
        try:
            envelope = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(envelope, dict) or envelope.get("storage_kind") != SQLITE_DRAFT_ENVELOPE_KIND:
            return None
        payload = envelope.get("draft")
        if not isinstance(payload, dict):
            return None
        try:
            return PlantDesignProjectDraft.from_dict(payload)
        except (PlantProjectDraftError, TypeError, ValueError):
            return None

    def _find_record(
        self, connection: sqlite3.Connection, project_id: str
    ) -> tuple[int, PlantDesignProjectDraft] | None:
        for row_id, raw in connection.execute(
            "SELECT id, design_data FROM project_history ORDER BY id DESC"
        ):
            draft = self._decode_envelope(raw)
            if draft is not None and draft.project_id == project_id:
                return int(row_id), draft
        return None

    @staticmethod
    def _envelope(draft: PlantDesignProjectDraft) -> str:
        payload = {
            "storage_kind": SQLITE_DRAFT_ENVELOPE_KIND,
            "design_id": draft.project_id,
            "display_name": draft.project_name,
            "saved_at": draft.updated_at,
            "method": "Formal Multi-TU",
            "draft": draft.to_dict(),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def save(
        self,
        draft: PlantDesignProjectDraft | dict[str, Any],
    ) -> PlantDesignProjectDraft:
        resolved = draft if isinstance(draft, PlantDesignProjectDraft) else PlantDesignProjectDraft.from_dict(draft)
        if not resolved.project_name:
            raise PlantProjectDraftError("Project name is required before saving.")
        connection = self._connect()
        try:
            existing = self._find_record(connection, resolved.project_id)
            if existing is not None:
                require_active_project(existing[1])
                _assert_lifecycle_fields_unchanged(existing[1], resolved)
                resolved.created_at = existing[1].created_at
            else:
                require_active_project(resolved)
            encoded = self._envelope(resolved)
            if existing is None:
                connection.execute(
                    "INSERT INTO project_history "
                    "(project_name, version, chassis, design_data, created_at, creator, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        resolved.project_name,
                        1,
                        resolved.workflow_type or "multi_tu",
                        encoded,
                        resolved.updated_at,
                        "BioDesign Studio formal Multi-TU",
                        resolved.draft_status,
                    ),
                )
            else:
                connection.execute(
                    "UPDATE project_history SET project_name = ?, version = ?, chassis = ?, "
                    "design_data = ?, created_at = ?, creator = ?, status = ? WHERE id = ?",
                    (
                        resolved.project_name,
                        1,
                        resolved.workflow_type or "multi_tu",
                        encoded,
                        resolved.updated_at,
                        "BioDesign Studio formal Multi-TU",
                        resolved.draft_status,
                        existing[0],
                    ),
                )
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise PlantProjectDraftError(
                f"The formal project transaction could not be committed: {exc}"
            ) from exc
        finally:
            connection.close()
        return resolved

    def transition_project_lifecycle(
        self,
        project_id: str,
        expected_status: str,
        target_status: str,
        archived_at: str | None,
    ) -> PlantDesignProjectDraft:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            existing = self._find_record(connection, project_id)
            if existing is None:
                raise PlantProjectDraftError("Plant project draft database row was not found.")
            updated = _transition_lifecycle_draft(existing[1], expected_status, target_status, archived_at)
            connection.execute(
                "UPDATE project_history SET design_data = ? WHERE id = ?",
                (self._envelope(updated), existing[0]),
            )
            connection.commit()
            return updated
        except PlantProjectDraftError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise PlantProjectDraftError(
                f"The formal project transaction could not be committed: {exc}"
            ) from exc
        finally:
            connection.close()

    def load(self, project_id: str) -> PlantDesignProjectDraft:
        clean_project_id = str(project_id or "").strip()
        if not PROJECT_ID_PATTERN.fullmatch(clean_project_id):
            raise PlantProjectDraftError("Invalid plant project draft id.")
        connection = self._connect()
        try:
            record = self._find_record(connection, clean_project_id)
        finally:
            connection.close()
        if record is None:
            raise PlantProjectDraftError("Plant project draft database row was not found.")
        return record[1]

    def list_summaries(self) -> list[PlantProjectDraftSummary]:
        connection = self._connect()
        drafts: dict[str, PlantDesignProjectDraft] = {}
        try:
            rows = connection.execute(
                "SELECT design_data FROM project_history ORDER BY id DESC"
            ).fetchall()
        finally:
            connection.close()
        for (raw,) in rows:
            draft = self._decode_envelope(raw)
            if draft is not None and draft.project_id not in drafts:
                drafts[draft.project_id] = draft
        summaries = [
            PlantProjectDraftSummary(
                project_id=draft.project_id,
                project_name=draft.project_name,
                updated_at=draft.updated_at,
                created_at=draft.created_at,
                draft_status=draft.draft_status,
                record_origin=draft.record_origin,
                workflow_type=draft.workflow_type,
                canonical_available=draft.canonical_available,
                lifecycle_status=normalized_project_lifecycle_status(draft),
                archived_at=(
                    ""
                    if "archived_at" not in draft.extra_fields
                    else str(draft.extra_fields.get("archived_at"))
                ),
            )
            for draft in drafts.values()
        ]
        return sorted(
            summaries,
            key=lambda summary: (summary.updated_at, summary.project_id),
            reverse=True,
        )

    def delete(self, project_id: str) -> None:
        connection = self._connect()
        try:
            record = self._find_record(connection, project_id)
            if record is None:
                raise PlantProjectDraftError("Plant project draft database row was not found.")
            connection.execute("DELETE FROM project_history WHERE id = ?", (record[0],))
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise PlantProjectDraftError(
                f"The formal project delete transaction could not be committed: {exc}"
            ) from exc
        finally:
            connection.close()
