from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from core.config import DB_PATH
from services.catalog_asset_snapshot_builder import (
    SNAPSHOT_SCHEMA_VERSION,
    sanitize_catalog_asset_snapshot,
)
from services.project_asset_linkage_service import build_project_asset_link, list_project_asset_links


PROJECT_CATALOG_ASSET_LINKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS project_catalog_asset_links (
    link_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT '',
    asset_id TEXT NOT NULL,
    asset_label TEXT NOT NULL DEFAULT '',
    asset_version TEXT NOT NULL DEFAULT '',
    source_label TEXT NOT NULL DEFAULT '',
    documentation_status TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    linkage_role TEXT NOT NULL DEFAULT 'project_reference',
    source_context_snapshot_json TEXT NOT NULL DEFAULT '{}',
    review_status_snapshot_json TEXT NOT NULL DEFAULT '{}',
    snapshot_schema_version TEXT NOT NULL DEFAULT '',
    asset_snapshot_json TEXT NOT NULL DEFAULT '{}',
    snapshot_captured_at TEXT NOT NULL DEFAULT '',
    human_review_required INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, asset_id, linkage_role)
)
"""


def _connect() -> sqlite3.Connection:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _make_link_id() -> str:
    return f"pcal-{uuid4().hex[:12]}"


def _json_dumps(value: Any) -> str:
    if not isinstance(value, dict):
        value = {}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value in (None, ""):
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def init_project_catalog_asset_link_tables() -> None:
    conn = _connect()
    try:
        conn.execute(PROJECT_CATALOG_ASSET_LINKS_TABLE_SQL)
        existing_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(project_catalog_asset_links)").fetchall()
        }
        additive_columns = {
            "snapshot_schema_version": "TEXT NOT NULL DEFAULT ''",
            "asset_snapshot_json": "TEXT NOT NULL DEFAULT '{}'",
            "snapshot_captured_at": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in additive_columns.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE project_catalog_asset_links ADD COLUMN {column} {definition}")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_catalog_asset_links_project "
            "ON project_catalog_asset_links (project_id, asset_label COLLATE NOCASE, asset_id, linkage_role)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_catalog_asset_links_asset_type "
            "ON project_catalog_asset_links (asset_type, project_id)"
        )
        conn.commit()
    finally:
        conn.close()


def _normalize_link_payload(link: dict[str, Any]) -> dict[str, Any]:
    source_snapshot = (
        link.get("source_context_snapshot")
        if isinstance(link.get("source_context_snapshot"), dict)
        else {}
    )
    review_snapshot = (
        link.get("review_status_snapshot")
        if isinstance(link.get("review_status_snapshot"), dict)
        else {}
    )
    asset_snapshot = sanitize_catalog_asset_snapshot(link.get("asset_snapshot"))
    source_label = _clean_text(
        link.get("source_label")
        or asset_snapshot.get("source_label")
        or source_snapshot.get("source_labels")
        or source_snapshot.get("source_label")
        or source_snapshot.get("catalog")
        or source_snapshot.get("source_provenance_status")
    )
    documentation_status = _clean_text(
        link.get("documentation_status")
        or asset_snapshot.get("documentation_status")
        or review_snapshot.get("curation_statuses")
        or review_snapshot.get("review_status")
        or review_snapshot.get("human_review_status")
    )
    snapshot_schema_version = _clean_text(
        link.get("snapshot_schema_version")
        or (SNAPSHOT_SCHEMA_VERSION if asset_snapshot else "")
    )
    snapshot_captured_at = _clean_text(
        link.get("snapshot_captured_at")
        or link.get("linked_at")
    )
    return {
        "project_id": _clean_text(link.get("project_id")),
        "asset_id": _clean_text(link.get("asset_id")),
        "asset_label": _clean_text(
            link.get("asset_label")
            or link.get("asset_display_name")
            or asset_snapshot.get("asset_label")
        ),
        "asset_type": _clean_text(link.get("asset_type")),
        "asset_version": _clean_text(link.get("asset_version") or asset_snapshot.get("asset_version")),
        "source_label": source_label,
        "documentation_status": documentation_status,
        "notes": _clean_text(link.get("notes") or link.get("documentation_note")),
        "linkage_role": _clean_text(link.get("linkage_role") or "project_reference"),
        "source_context_snapshot": source_snapshot,
        "review_status_snapshot": review_snapshot,
        "snapshot_schema_version": snapshot_schema_version,
        "asset_snapshot": asset_snapshot,
        "snapshot_captured_at": snapshot_captured_at if asset_snapshot else "",
        "human_review_required": bool(link.get("human_review_required", True)),
    }


def _row_to_link(row: dict[str, Any]) -> dict[str, Any]:
    source_snapshot = _json_loads(row.get("source_context_snapshot_json"))
    review_snapshot = _json_loads(row.get("review_status_snapshot_json"))
    asset_snapshot = sanitize_catalog_asset_snapshot(_json_loads(row.get("asset_snapshot_json")))
    link = build_project_asset_link(
        project_id=row.get("project_id"),
        asset_id=row.get("asset_id"),
        asset_display_name=row.get("asset_label"),
        asset_type=row.get("asset_type"),
        linkage_role=row.get("linkage_role"),
        documentation_note=row.get("notes"),
        source_context_snapshot=source_snapshot,
        review_status_snapshot=review_snapshot,
        linked_at=row.get("created_at"),
        human_review_required=bool(row.get("human_review_required")),
    )
    link.update(
        {
            "link_id": row.get("link_id"),
            "asset_label": row.get("asset_label"),
            "asset_version": row.get("asset_version"),
            "source_label": row.get("source_label"),
            "documentation_status": row.get("documentation_status"),
            "notes": row.get("notes"),
            "snapshot_schema_version": row.get("snapshot_schema_version") or "",
            "asset_snapshot": asset_snapshot,
            "snapshot_captured_at": row.get("snapshot_captured_at") or "",
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
    )
    return link


def find_project_catalog_asset_link(
    project_id: Any,
    *,
    asset_id: Any,
    linkage_role: Any,
) -> dict[str, Any]:
    clean_project_id = _clean_text(project_id)
    clean_asset_id = _clean_text(asset_id)
    clean_role = _clean_text(linkage_role)
    if not clean_project_id or not clean_asset_id or not clean_role:
        return {}

    for row in list_project_catalog_asset_links(clean_project_id):
        if (
            _clean_text(row.get("asset_id")).lower() == clean_asset_id.lower()
            and _clean_text(row.get("linkage_role")).lower() == clean_role.lower()
        ):
            return row
    return {}


def add_project_catalog_asset_link(link: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    init_project_catalog_asset_link_tables()
    normalized = _normalize_link_payload(link if isinstance(link, dict) else {})
    if not _clean_text(
        normalized["source_context_snapshot"].get("project_documentation_context")
    ):
        project_context = _clean_text(
            link.get("project_documentation_context")
            if isinstance(link, dict)
            else ""
        )
        normalized["source_context_snapshot"]["project_documentation_context"] = (
            project_context or "Pathway Workspace linked catalog assets"
        )
    built_link = build_project_asset_link(
        project_id=normalized["project_id"],
        asset_id=normalized["asset_id"],
        asset_display_name=normalized["asset_label"],
        asset_type=normalized["asset_type"],
        linkage_role=normalized["linkage_role"],
        documentation_note=normalized["notes"] or "Documentation-only reference for project traceability.",
        source_context_snapshot=normalized["source_context_snapshot"],
        review_status_snapshot=normalized["review_status_snapshot"],
        linked_at=link.get("linked_at") if isinstance(link, dict) else "",
        human_review_required=normalized["human_review_required"],
    )
    normalized = _normalize_link_payload({**built_link, **normalized})
    timestamp = _utc_now()
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO project_catalog_asset_links
                (
                    link_id, project_id, asset_type, asset_id, asset_label, asset_version,
                    source_label, documentation_status, notes, linkage_role,
                    source_context_snapshot_json, review_status_snapshot_json,
                    snapshot_schema_version, asset_snapshot_json, snapshot_captured_at,
                    human_review_required, created_at, updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _make_link_id(),
                normalized["project_id"],
                normalized["asset_type"],
                normalized["asset_id"],
                normalized["asset_label"],
                normalized["asset_version"],
                normalized["source_label"],
                normalized["documentation_status"],
                normalized["notes"],
                normalized["linkage_role"],
                _json_dumps(normalized["source_context_snapshot"]),
                _json_dumps(normalized["review_status_snapshot"]),
                normalized["snapshot_schema_version"],
                _json_dumps(normalized["asset_snapshot"]),
                normalized["snapshot_captured_at"],
                1 if normalized["human_review_required"] else 0,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        if cursor.rowcount == 0:
            existing = list_project_catalog_asset_links(normalized["project_id"])
            duplicate = next(
                (
                    row
                    for row in existing
                    if _clean_text(row.get("asset_id")).lower() == normalized["asset_id"].lower()
                    and _clean_text(row.get("linkage_role")).lower() == normalized["linkage_role"].lower()
                ),
                {},
            )
            return False, "Catalog asset reference already exists for this project and role.", duplicate
        rows = list_project_catalog_asset_links(normalized["project_id"])
        added = next(
            (
                row
                for row in rows
                if _clean_text(row.get("asset_id")).lower() == normalized["asset_id"].lower()
                and _clean_text(row.get("linkage_role")).lower() == normalized["linkage_role"].lower()
            ),
            {},
        )
        return True, "Catalog asset documentation reference saved.", added
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to save catalog asset reference: {exc}", {}
    finally:
        conn.close()


def list_project_catalog_asset_links(project_id: Any) -> list[dict[str, Any]]:
    clean_project_id = _clean_text(project_id)
    if not clean_project_id:
        return []
    init_project_catalog_asset_link_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
                link_id, project_id, asset_type, asset_id, asset_label, asset_version,
                source_label, documentation_status, notes, linkage_role,
                source_context_snapshot_json, review_status_snapshot_json,
                snapshot_schema_version, asset_snapshot_json, snapshot_captured_at,
                human_review_required, created_at, updated_at
            FROM project_catalog_asset_links
            WHERE project_id = ?
            ORDER BY asset_label COLLATE NOCASE ASC, asset_id ASC, linkage_role ASC, created_at ASC, link_id ASC
            """,
            (clean_project_id,),
        ).fetchall()
        links = [_row_to_link(row) for row in _rows_to_dicts(rows)]
        return list_project_asset_links(links, project_id=clean_project_id)
    finally:
        conn.close()


def remove_project_catalog_asset_link(
    *,
    project_id: Any,
    link_id: Any | None = None,
    asset_id: Any | None = None,
    linkage_role: Any | None = None,
) -> tuple[bool, str]:
    clean_project_id = _clean_text(project_id)
    if not clean_project_id:
        return False, "Project id is required."
    clean_link_id = _clean_text(link_id)
    clean_asset_id = _clean_text(asset_id)
    clean_role = _clean_text(linkage_role)
    if not clean_link_id and not (clean_asset_id and clean_role):
        return False, "A link id or asset id plus role is required."

    init_project_catalog_asset_link_tables()
    conn = _connect()
    try:
        if clean_link_id:
            cursor = conn.execute(
                "DELETE FROM project_catalog_asset_links WHERE project_id = ? AND link_id = ?",
                (clean_project_id, clean_link_id),
            )
        else:
            cursor = conn.execute(
                """
                DELETE FROM project_catalog_asset_links
                WHERE project_id = ? AND asset_id = ? AND linkage_role = ?
                """,
                (clean_project_id, clean_asset_id, clean_role),
            )
        conn.commit()
        if cursor.rowcount:
            return True, "Catalog asset documentation reference removed."
        return False, "Catalog asset reference was not found."
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to remove catalog asset reference: {exc}"
    finally:
        conn.close()


def merge_with_persisted_project_catalog_links(
    project_id: Any,
    links: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    persisted = list_project_catalog_asset_links(project_id)
    return list_project_asset_links([*(links or []), *persisted], project_id=project_id)
