"""Local documentation artifact storage for tool previews.

Artifacts are computational preview / review records only. They do not certify
experimental readiness, provide wet-lab protocols, predict yield, or optimize pathways.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any

from core.config import DB_PATH


TOOL_ARTIFACT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tool_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_type TEXT NOT NULL,
    title TEXT NOT NULL,
    source_module TEXT NOT NULL,
    summary TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    boundary_label TEXT NOT NULL,
    notes TEXT,
    project_id INTEGER,
    created_at TEXT NOT NULL
)
"""

VALID_ARTIFACT_TYPES = {
    "protein_structure_analysis",
    "lab_tools_cloning_preview",
    "lab_tools_pcr_preview",
    "lab_tools_virtual_gel_preview",
    "lab_tools_sequence_export_preview",
}

TOOL_ARTIFACT_BOUNDARY_LABEL = (
    "Documentation artifact / computational preview record only. Not an experimental conclusion, "
    "not experimental readiness certification, not yield prediction, not pathway optimization, "
    "and not a wet-lab protocol."
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def _connect() -> sqlite3.Connection:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(TOOL_ARTIFACT_TABLE_SQL)
    if not _has_column(conn, "tool_artifacts", "project_id"):
        conn.execute("ALTER TABLE tool_artifacts ADD COLUMN project_id INTEGER")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tool_artifacts_created "
        "ON tool_artifacts (created_at DESC, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tool_artifacts_project "
        "ON tool_artifacts (project_id, created_at DESC, id DESC)"
    )
    return conn


def _safe_json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _safe_json_loads(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row_to_artifact(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    record = dict(row)
    record["artifact_id"] = int(record.pop("id"))
    record["payload_json"] = _safe_json_loads(record.get("payload_json"))
    return record


def _normalize_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _normalize_optional_project_id(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def create_tool_artifact(
    *,
    artifact_type: str,
    title: str,
    source_module: str,
    summary: str,
    payload_json: dict[str, Any] | None,
    boundary_label: str = TOOL_ARTIFACT_BOUNDARY_LABEL,
    notes: str = "",
    project_id: int | str | None = None,
) -> tuple[bool, str, int | None]:
    clean_type = _normalize_text(artifact_type)
    if clean_type not in VALID_ARTIFACT_TYPES:
        return False, "Invalid artifact type.", None
    clean_title = _normalize_text(title)
    if not clean_title:
        return False, "Artifact title is required.", None
    clean_source = _normalize_text(source_module)
    if not clean_source:
        return False, "Source module is required.", None
    clean_summary = _normalize_text(summary)
    if not clean_summary:
        return False, "Artifact summary is required.", None
    payload = dict(payload_json) if isinstance(payload_json, dict) else {}
    if not payload:
        return False, "Artifact payload is required.", None
    clean_boundary = _normalize_text(boundary_label, TOOL_ARTIFACT_BOUNDARY_LABEL)
    clean_project_id = _normalize_optional_project_id(project_id)
    timestamp = _now()

    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO tool_artifacts
                (artifact_type, title, source_module, summary, payload_json,
                 boundary_label, notes, project_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_type,
                clean_title,
                clean_source,
                clean_summary,
                _safe_json_dumps(payload),
                clean_boundary,
                _normalize_text(notes),
                clean_project_id,
                timestamp,
            ),
        )
        conn.commit()
        return True, "Tool documentation artifact created.", int(cursor.lastrowid)
    except Exception as exc:
        conn.rollback()
        return False, f"Could not create tool artifact: {exc}", None
    finally:
        conn.close()


def list_tool_artifacts(
    artifact_type: str | None = None,
    source_module: str | None = None,
    project_id: int | str | None = None,
) -> list[dict[str, Any]]:
    clean_type = _normalize_text(artifact_type)
    clean_source = _normalize_text(source_module)
    clean_project_id = _normalize_optional_project_id(project_id)
    clauses: list[str] = []
    params: list[Any] = []
    if clean_type:
        clauses.append("artifact_type = ?")
        params.append(clean_type)
    if clean_source:
        clauses.append("source_module = ?")
        params.append(clean_source)
    if clean_project_id is not None:
        clauses.append("project_id = ?")
        params.append(clean_project_id)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            SELECT id, artifact_type, title, source_module, summary, payload_json,
                   boundary_label, notes, project_id, created_at
            FROM tool_artifacts
            {where_sql}
            ORDER BY created_at DESC, id DESC
            """,
            tuple(params),
        ).fetchall()
        return [_row_to_artifact(row) for row in rows]
    finally:
        conn.close()


def get_tool_artifact(artifact_id: int | str | None) -> dict[str, Any]:
    try:
        resolved_id = int(artifact_id) if artifact_id is not None else 0
    except (TypeError, ValueError):
        return {}
    if resolved_id <= 0:
        return {}
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT id, artifact_type, title, source_module, summary, payload_json,
                   boundary_label, notes, project_id, created_at
            FROM tool_artifacts
            WHERE id = ?
            """,
            (resolved_id,),
        ).fetchone()
        return _row_to_artifact(row)
    finally:
        conn.close()


def _stringify_preview_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value[:8])
    if isinstance(value, dict):
        return ", ".join(f"{key}: {val}" for key, val in list(value.items())[:8])
    return str(value)


def readable_payload_summary(payload: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Return concise, UI-friendly payload details without dumping raw JSON."""
    if not isinstance(payload, dict) or not payload:
        return [("Payload summary", "No payload summary is available.")]

    artifact_type = str(payload.get("artifact_type") or "")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    rows: list[tuple[str, str]] = []

    def add(label: str, value: Any) -> None:
        text = _stringify_preview_value(value)
        if text:
            rows.append((label, text))

    if artifact_type == "protein_structure_analysis":
        props = payload.get("sequence_properties") if isinstance(payload.get("sequence_properties"), dict) else {}
        source = payload.get("structure_source") if isinstance(payload.get("structure_source"), dict) else {}
        add("Sequence length", f"{props.get('length')} aa" if props.get("length") is not None else "")
        add("Structure source", source.get("source"))
        add("PDB ID", source.get("pdb_id"))
        add("Molecular weight estimate", f"{props.get('molecular_weight')} Da" if props.get("molecular_weight") is not None else "")
        add("Source status", source.get("message"))
    elif artifact_type == "lab_tools_cloning_preview":
        add("Cloning method", summary.get("assembly_method"))
        add("Insert name", summary.get("insert_name"))
        add("Insert length", f"{summary.get('insert_length_bp')} bp" if summary.get("insert_length_bp") is not None else "")
        add("Vector", summary.get("vector"))
    elif artifact_type == "lab_tools_pcr_preview":
        add("Forward primer", summary.get("forward_primer_name"))
        add("Reverse primer", summary.get("reverse_primer_name"))
        add("Forward primer length", f"{summary.get('forward_primer_length_bp')} bp" if summary.get("forward_primer_length_bp") is not None else "")
        add("Reverse primer length", f"{summary.get('reverse_primer_length_bp')} bp" if summary.get("reverse_primer_length_bp") is not None else "")
        add("Target length", f"{summary.get('target_length_bp')} bp" if summary.get("target_length_bp") is not None else "")
        add("Amplicon preview", summary.get("expected_amplicon_summary"))
    elif artifact_type == "lab_tools_virtual_gel_preview":
        add("Fragment count", summary.get("fragment_count"))
        add("Fragment sizes", summary.get("fragment_sizes_bp"))
        add("Gel preview", summary.get("textual_gel_preview"))
    elif artifact_type == "lab_tools_sequence_export_preview":
        add("Sequence name", summary.get("sequence_name"))
        add("Sequence length", f"{summary.get('sequence_length_bp')} bp" if summary.get("sequence_length_bp") is not None else "")
        add("Export format", summary.get("format"))
        add("Sequence source", inputs.get("sequence_source"))
    else:
        for key in ("preview_status", "structure_source", "sequence_properties", "inputs"):
            add(key.replace("_", " ").title(), payload.get(key))

    add("Preview type", summary.get("preview_type"))
    return rows or [("Payload summary", "No concise payload summary is available.")]


def raw_payload_preview(payload: dict[str, Any] | None, max_chars: int = 2000) -> tuple[str, bool]:
    """Return a truncated raw payload preview and whether truncation occurred."""
    text = _safe_json_dumps(payload if isinstance(payload, dict) else {})
    if len(text) > max_chars:
        return text[:max_chars].rstrip(), True
    return text, False


def delete_tool_artifact(artifact_id: int | str | None) -> tuple[bool, str]:
    try:
        resolved_id = int(artifact_id) if artifact_id is not None else 0
    except (TypeError, ValueError):
        return False, "Invalid artifact id."
    if resolved_id <= 0:
        return False, "Invalid artifact id."
    conn = _connect()
    try:
        cursor = conn.execute("DELETE FROM tool_artifacts WHERE id = ?", (resolved_id,))
        conn.commit()
        if cursor.rowcount:
            return True, "Tool documentation artifact deleted."
        return False, "Tool documentation artifact was not found."
    except Exception as exc:
        conn.rollback()
        return False, f"Could not delete tool artifact: {exc}"
    finally:
        conn.close()
