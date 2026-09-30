# -*- coding: utf-8 -*-
"""Save/load helpers for Expression Wizard designs."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

from core.config import DB_PATH


def format_saved_at_display(value: object) -> str:
    """Format saved timestamps for UI display without changing stored values."""
    text = str(value or "").strip()
    if not text:
        return ""

    normalized = text.replace("Z", "").replace("T", " ")
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(normalized[:26], fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue

    if len(normalized) >= 16:
        return normalized[:16]
    return normalized

if TYPE_CHECKING:
    from core.design_session import DesignSession

logger = logging.getLogger(__name__)


class SaveWizardDesignResult(str):
    """Backward-compatible save result: string display name plus identity fields."""

    def __new__(cls, display_name: str, design_id: str):
        obj = str.__new__(cls, display_name)
        obj.design_id = design_id
        obj.display_name = display_name
        obj.name = display_name
        return obj

    def __getitem__(self, key: str) -> str:
        if isinstance(key, int):
            return str.__getitem__(self, key)
        if key == "design_id":
            return self.design_id
        if key in {"display_name", "name"}:
            return self.display_name
        raise KeyError(key)

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default


PROJECT_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS project_history (
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

SEQUENCES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sequence TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _safe_json_loads(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _coerce_saved_step(value: object) -> int | None:
    try:
        step = int(value)
    except (TypeError, ValueError):
        return None
    return step if 1 <= step <= 6 else None


def _artifact_safe_max_step(data: dict) -> int:
    if not str(data.get("original_seq") or "").strip():
        return 1
    if not str(data.get("host") or "").strip():
        return 2
    frame = data.get("frame")
    if not (isinstance(frame, dict) and frame.get("success")):
        return 3
    validation_results = data.get("validation_results")
    if isinstance(validation_results, list) and validation_results:
        return 6
    primers = data.get("primers")
    if not (isinstance(primers, list) and primers):
        return 4
    return 5


def _resolve_resume_step(data: dict) -> int:
    if data.get("_sequence_only_fallback"):
        return 1
    safe_max = _artifact_safe_max_step(data)
    if safe_max == 6:
        return 6
    saved_step = _coerce_saved_step(data.get("step_reached"))
    return safe_max if saved_step is None else min(saved_step, safe_max)


def _payload_saved_identity(data: dict, fallback_name: str) -> dict:
    metadata = data.get("saved_design_metadata") if isinstance(data.get("saved_design_metadata"), dict) else {}
    design_id = str(data.get("design_id") or metadata.get("design_id") or "").strip()
    display_name = str(data.get("display_name") or metadata.get("display_name") or fallback_name or "").strip()
    saved_at = str(data.get("saved_at") or metadata.get("saved_at") or "").strip()
    if design_id:
        return {
            "design_id": design_id,
            "display_name": display_name,
            "saved_design_version": data.get("saved_design_version") or metadata.get("saved_design_version") or 1,
            "saved_at": saved_at,
            "identity_source": "immutable_design_id",
        }
    return {
        "design_id": "",
        "display_name": display_name,
        "saved_design_version": data.get("saved_design_version") or metadata.get("saved_design_version"),
        "saved_at": saved_at,
        "identity_source": "legacy_name",
    }


def resolve_saved_design_identity(
    *,
    name: str,
    source: str,
    data: dict | None = None,
    sequences_name: str | None = None,
    project_history_project_name: str | None = None,
    sequence_date_added: str | None = None,
    project_history_created_at: str | None = None,
) -> dict:
    """Resolve saved-design identity with immutable IDs and legacy-name fallback."""
    resolved_name = str(name or "")
    payload = _payload_saved_identity(data or {}, resolved_name)
    immutable_id = payload["design_id"]
    identity_source = payload["identity_source"]
    db_refs = {
        "sequences_name": sequences_name or "",
        "project_history_project_name": project_history_project_name or "",
        "sequence_date_added": sequence_date_added or "",
        "project_history_created_at": project_history_created_at or "",
        "source": source,
    }
    stable_key = immutable_id or resolved_name
    return {
        "design_id": stable_key,
        "saved_design_id": immutable_id,
        "name": payload["display_name"] or resolved_name,
        "display_name": payload["display_name"] or resolved_name,
        "load_key": stable_key,
        "delete_key": stable_key,
        "identity_source": identity_source,
        "saved_design_version": payload["saved_design_version"],
        "source": source,
        "db_refs": db_refs,
    }


def saved_design_load_key(identity: dict | str) -> str:
    if isinstance(identity, dict):
        return str(identity.get("load_key") or identity.get("design_id") or identity.get("name") or "")
    return str(identity or "")


def saved_design_delete_key(identity: dict | str) -> str:
    if isinstance(identity, dict):
        return str(identity.get("delete_key") or identity.get("design_id") or identity.get("name") or "")
    return str(identity or "")


def _identity_summary_fields(identity: dict) -> dict:
    return {
        "design_id": identity["design_id"],
        "saved_design_id": identity.get("saved_design_id", ""),
        "name": identity["name"],
        "display_name": identity.get("display_name", identity["name"]),
        "load_key": identity["load_key"],
        "delete_key": identity["delete_key"],
        "identity_source": identity.get("identity_source", "legacy_name"),
        "saved_design_version": identity.get("saved_design_version"),
        "source": identity["source"],
        "db_refs": identity["db_refs"],
    }


def _metadata_with_db_refs(data: dict, db_refs: dict) -> dict:
    metadata = _saved_design_metadata(data)
    metadata["db_refs"] = db_refs
    return metadata


def _connect() -> sqlite3.Connection:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(PROJECT_HISTORY_TABLE_SQL)
    conn.execute(SEQUENCES_TABLE_SQL)
    return conn


def _extract_saved_features(data: dict) -> list:
    frame = data.get("frame")
    if isinstance(frame, dict) and isinstance(frame.get("features"), list):
        return frame.get("features", [])
    features = data.get("features")
    return features if isinstance(features, list) else []


def _build_elements(data: dict) -> dict:
    return {
        "promoter_name": data.get("promoter", "") or "",
        "promoter_seq": data.get("promoter_seq", "") or "",
        "rbs_name": data.get("rbs", "") or "",
        "rbs_seq": data.get("rbs_seq", "") or "",
        "terminator_name": data.get("terminator", "") or "",
        "terminator_seq": data.get("terminator_seq", "") or "",
    }


def _project_history_summary_lookup(cursor: sqlite3.Cursor) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    rows = cursor.execute(
        "SELECT project_name, created_at, design_data, status FROM project_history ORDER BY id DESC"
    ).fetchall()
    for project_name, created_at, design_data, status in rows:
        if project_name not in lookup:
            lookup[project_name] = {
                "created_at": created_at or "",
                "data": _safe_json_loads(design_data),
                "status": status or "",
            }
    return lookup


def _infer_sequence_design_type(category: str, sequence_length: int) -> str:
    category_norm = category.lower()
    if "vector" in category_norm or "plasmid" in category_norm:
        return "Vector"
    if "expression wizard" in category_norm:
        return "Expression Design"
    if sequence_length > 5000:
        return "Design"
    return "Sequence"


def _saved_design_metadata(data: dict) -> dict:
    gc = data.get("gc_content")
    identity = _payload_saved_identity(data, str(data.get("display_name") or data.get("gene_name") or ""))
    return {
        "design_id": identity["design_id"],
        "saved_design_version": identity["saved_design_version"],
        "display_name": identity["display_name"],
        "saved_at": identity["saved_at"],
        "identity_source": identity["identity_source"],
        "gc_content": gc,
        "features": _extract_saved_features(data),
        "step": _resolve_resume_step(data) if data else 1,
        "cloning_method": data.get("cloning_method", "") or "",
        "vector": data.get("vector", "") or "",
        "n_primers": data.get("n_primers"),
        "n_issues": data.get("n_issues"),
        "method": data.get("method", "") or "",
    }


def _build_saved_design_summary_from_sequence_row(row: pd.Series, history: dict) -> dict:
    data = history.get("data", {}) if history else {}
    sequence = str(row["sequence"] or "")
    category = str(row["category"] or "Sequence")
    date_added = row["date_added"] or ""
    name = str(row["name"] or "")
    identity = resolve_saved_design_identity(
        name=name,
        source="sequences",
        data=data,
        sequences_name=name,
        project_history_project_name=name if history else "",
        sequence_date_added=date_added,
        project_history_created_at=history.get("created_at", "") if history else "",
    )
    return {
        **_identity_summary_fields(identity),
        "gene": data.get("gene_name", "") or "",
        "host": data.get("host", "") or "",
        "type": _infer_sequence_design_type(category, len(sequence)),
        "saved_at": data.get("saved_at") or date_added,
        "created_at": date_added,
        "updated_at": None,
        "sequence_length": len(sequence),
        "status": history.get("status", "") if history else "",
        "metadata": _metadata_with_db_refs(data, identity["db_refs"]),
        "raw": {
            "sequence": sequence,
            "category": category,
            "date_added": date_added,
            "project_history_created_at": history.get("created_at", "") if history else "",
            "project_history_data": data,
        },
    }


def _build_saved_design_summary_from_project_history_row(record: tuple) -> dict:
    project_name, created_at, design_data, status = record
    data = _safe_json_loads(design_data)
    sequence = data.get("sequence", "") or ""
    identity = resolve_saved_design_identity(
        name=project_name,
        source="project_history",
        data=data,
        project_history_project_name=project_name,
        project_history_created_at=created_at or "",
    )
    return {
        **_identity_summary_fields(identity),
        "gene": data.get("gene_name", "") or "",
        "host": data.get("host", "") or "",
        "type": data.get("method", "Design") or "Design",
        "saved_at": data.get("saved_at") or created_at or "",
        "created_at": created_at or "",
        "updated_at": None,
        "sequence_length": data.get("seq_len", 0),
        "status": status or "",
        "metadata": _metadata_with_db_refs(data, identity["db_refs"]),
        "raw": {
            "sequence": sequence,
            "created_at": created_at or "",
            "project_history_data": data,
        },
    }


def _saved_design_summary_to_dashboard_row(summary: dict) -> dict:
    metadata = summary.get("metadata") if isinstance(summary.get("metadata"), dict) else {}
    raw = summary.get("raw") if isinstance(summary.get("raw"), dict) else {}
    gc = metadata.get("gc_content")
    return {
        "Name": summary.get("display_name") or summary.get("name", ""),
        "Gene": summary.get("gene", "") or "--",
        "Host": summary.get("host", "") or "--",
        "Length (bp)": summary.get("sequence_length", 0),
        "GC%": f"{gc:.1f}%" if gc is not None else "--",
        "Type": summary.get("type", "Design") or "Design",
        "Saved": format_saved_at_display(summary.get("created_at") or summary.get("saved_at") or ""),
        "_sequence": raw.get("sequence", ""),
        "_features": metadata.get("features", []),
        "_source": summary.get("source", ""),
        "_load_key": summary.get("load_key", summary.get("name", "")),
        "_delete_key": summary.get("delete_key", summary.get("name", "")),
        "_gene": summary.get("gene", ""),
        "_host": summary.get("host", ""),
        "_cloning": metadata.get("cloning_method", ""),
        "_step": metadata.get("step"),
        "_vector": metadata.get("vector", ""),
        "_n_primers": metadata.get("n_primers"),
        "_n_issues": metadata.get("n_issues"),
        "_gc": gc,
    }


def _build_sequence_summaries(conn: sqlite3.Connection, ph_lookup: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    df = pd.read_sql_query(
        "SELECT name, category, date_added, sequence FROM sequences ORDER BY date_added DESC LIMIT 100",
        conn,
    )
    for _, row in df.iterrows():
        rows.append(_build_saved_design_summary_from_sequence_row(row, ph_lookup.get(row["name"], {})))
    return rows


def _build_project_history_fallback_summaries(cursor: sqlite3.Cursor) -> list[dict]:
    records = cursor.execute(
        "SELECT project_name, created_at, design_data, status FROM project_history ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    return [_build_saved_design_summary_from_project_history_row(record) for record in records]


def _normalize_query_text(value: object) -> str:
    return str(value or "").strip().lower()


def _normalize_type_filter(types: object) -> set[str]:
    if types is None:
        return set()
    if isinstance(types, str):
        normalized = types.strip()
        return {normalized} if normalized else set()
    if isinstance(types, (list, tuple, set)):
        return {str(value).strip() for value in types if str(value or "").strip()}
    normalized = str(types or "").strip()
    return {normalized} if normalized else set()


def _summary_matches_search(summary: dict, search: str | None) -> bool:
    query = _normalize_query_text(search)
    if not query:
        return True
    values = [
        summary.get("name"),
        summary.get("gene"),
        summary.get("host"),
        summary.get("type"),
    ]
    return any(query in _normalize_query_text(value) for value in values)


def _sort_saved_design_summaries(summaries: list[dict], sort_by: str, sort_order: str) -> list[dict]:
    if sort_by != "saved_at":
        sort_by = "saved_at"
    order = _normalize_query_text(sort_order)
    reverse = order not in {"asc", "oldest first", "oldest"}
    return sorted(summaries, key=lambda summary: _normalize_query_text(summary.get(sort_by)), reverse=reverse)


def _filter_saved_design_summaries(
    summaries: list[dict],
    *,
    search: str | None = None,
    types: object = None,
    sort_by: str = "saved_at",
    sort_order: str = "desc",
) -> list[dict]:
    allowed_types = _normalize_type_filter(types)
    filtered = [summary for summary in summaries if _summary_matches_search(summary, search)]
    if allowed_types:
        filtered = [summary for summary in filtered if str(summary.get("type") or "").strip() in allowed_types]
    return _sort_saved_design_summaries(filtered, sort_by, sort_order)


def query_saved_design_summaries(
    search: str | None = None,
    types: object = None,
    sort_by: str = "saved_at",
    sort_order: str = "desc",
) -> list[dict]:
    try:
        if not os.path.exists(DB_PATH):
            return []
        conn = _connect()
        try:
            cursor = conn.cursor()
            ph_lookup = _project_history_summary_lookup(cursor)
            sequence_rows = _build_sequence_summaries(conn, ph_lookup)
            project_history_rows = _build_project_history_fallback_summaries(cursor)
            sequence_name_counts: dict[str, int] = {}
            for row in sequence_rows:
                sequence_name_counts[row.get("name", "")] = sequence_name_counts.get(row.get("name", ""), 0) + 1
            duplicate_names = {name for name, count in sequence_name_counts.items() if count > 1}
            sequence_rows = [row for row in sequence_rows if row.get("name") not in duplicate_names]
            sequence_names = {row.get("name") for row in sequence_rows}
            project_history_only_rows = [row for row in project_history_rows if row.get("name") not in sequence_names]
            summaries = [*sequence_rows, *project_history_only_rows]
            return _filter_saved_design_summaries(
                summaries,
                search=search,
                types=types,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        finally:
            conn.close()
    except Exception as exc:
        logger.error("[design_saver] query_saved_design_summaries failed: %s", exc)
        return []


def _sequence_only_fallback_payload(project_name: str, sequence: str) -> dict:
    return {
        "step": 1,
        "gene_name": project_name,
        "original_seq": sequence,
        "optimized_seq": sequence,
        "host": "",
        "tag": "",
        "cloning_method": "",
        "primers": [],
        "validation_results": [],
        "codon_report": {},
        "frame": {
            "success": True,
            "final_sequence": sequence,
            "total_length": len(sequence),
            "features": [],
        },
        "sequence": sequence,
        "_sequence_only_fallback": True,
    }


def _detail_sequence(data: dict) -> str:
    frame = data.get("frame") if isinstance(data.get("frame"), dict) else {}
    return str(
        data.get("sequence")
        or frame.get("final_sequence")
        or data.get("optimized_seq")
        or data.get("original_seq")
        or ""
    )


def _build_saved_design_detail(summary: dict, data: dict, load_warnings: list[str] | None = None) -> dict:
    frame = data.get("frame") if isinstance(data.get("frame"), dict) else {}
    validation_results = data.get("validation_results") if isinstance(data.get("validation_results"), list) else []
    primers = data.get("primers") if isinstance(data.get("primers"), list) else []
    db_refs = summary.get("db_refs") if isinstance(summary.get("db_refs"), dict) else {}
    return {
        "summary": summary,
        "design_id": summary.get("design_id", ""),
        "load_key": summary.get("load_key", ""),
        "name": summary.get("name", ""),
        "source": summary.get("source", ""),
        "design_data": data,
        "sequence": _detail_sequence(data),
        "frame": frame,
        "validation_results": validation_results,
        "primers": primers,
        "metadata": _metadata_with_db_refs(data, db_refs),
        "db_refs": db_refs,
        "can_load": bool(data),
        "load_warnings": load_warnings or [],
    }


def _fetch_sequence_detail_row(cursor: sqlite3.Cursor, load_key: str) -> tuple | None:
    return cursor.execute(
        "SELECT name, category, date_added, sequence FROM sequences "
        "WHERE name = ? ORDER BY date_added DESC, id DESC LIMIT 1",
        (load_key,),
    ).fetchone()


def _fetch_project_history_detail_row(cursor: sqlite3.Cursor, load_key: str) -> tuple | None:
    return cursor.execute(
        "SELECT project_name, created_at, design_data, status FROM project_history "
        "WHERE project_name = ? ORDER BY id DESC LIMIT 1",
        (load_key,),
    ).fetchone()


def _fetch_project_history_detail_row_by_design_id(cursor: sqlite3.Cursor, design_id: str) -> tuple | None:
    rows = cursor.execute(
        "SELECT project_name, created_at, design_data, status FROM project_history ORDER BY id DESC"
    ).fetchall()
    for row in rows:
        data = _safe_json_loads(row[2])
        identity = _payload_saved_identity(data, str(row[0] or ""))
        if identity.get("design_id") == design_id:
            return row
    return None


def query_saved_design_detail(load_key: dict | str) -> dict:
    resolved_load_key = saved_design_load_key(load_key)
    try:
        if not resolved_load_key or not os.path.exists(DB_PATH):
            return {}
        conn = _connect()
        try:
            cursor = conn.cursor()
            history_row = _fetch_project_history_detail_row_by_design_id(cursor, resolved_load_key)
            sequence_row = None
            if history_row:
                sequence_row = _fetch_sequence_detail_row(cursor, str(history_row[0] or ""))
            else:
                # Legacy fallback: name-based lookup may select the newest record when duplicate names exist.
                history_row = _fetch_project_history_detail_row(cursor, resolved_load_key)
                sequence_row = _fetch_sequence_detail_row(cursor, resolved_load_key)

            if history_row:
                project_name, created_at, design_data, status = history_row
                data = _safe_json_loads(design_data)
                if sequence_row:
                    name, category, date_added, sequence = sequence_row
                    sequence_summary_row = pd.Series(
                        {
                            "name": name,
                            "category": category,
                            "date_added": date_added,
                            "sequence": sequence,
                        }
                    )
                    history = {
                        "created_at": created_at or "",
                        "data": data,
                        "status": status or "",
                    }
                    summary = _build_saved_design_summary_from_sequence_row(sequence_summary_row, history)
                else:
                    summary = _build_saved_design_summary_from_project_history_row(history_row)
                return _build_saved_design_detail(summary, data)

            if sequence_row:
                name, category, date_added, sequence = sequence_row
                sequence_text = str(sequence or "")
                data = _sequence_only_fallback_payload(str(name or resolved_load_key), sequence_text)
                sequence_summary_row = pd.Series(
                    {
                        "name": name,
                        "category": category,
                        "date_added": date_added,
                        "sequence": sequence_text,
                    }
                )
                summary = _build_saved_design_summary_from_sequence_row(sequence_summary_row, {})
                return _build_saved_design_detail(
                    summary,
                    data,
                    ["Sequence-only fallback; full design metadata is unavailable."],
                )
            return {}
        finally:
            conn.close()
    except Exception as exc:
        logger.error("[design_saver] query_saved_design_detail failed for %s: %s", resolved_load_key, exc)
        return {}


def _fetch_project_data(cursor: sqlite3.Cursor, project_name: str) -> dict:
    detail = query_saved_design_detail(project_name)
    data = detail.get("design_data") if isinstance(detail, dict) else {}
    return data if isinstance(data, dict) else {}


def get_saved_design_rows(
    search: str | None = None,
    types: object = None,
    sort_by: str = "saved_at",
    sort_order: str = "desc",
) -> list[dict]:
    return [
        _saved_design_summary_to_dashboard_row(summary)
        for summary in query_saved_design_summaries(
            search=search,
            types=types,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    ]


def save_wizard_design(ds: "DesignSession") -> tuple[bool, str]:
    gene = (ds.gene_name or "").strip()
    host = (ds.host or "").strip()
    now = datetime.now()
    label = gene or "Untitled"
    stamp = now.strftime("%Y-%m-%d %H:%M")
    name = f"{label} ({host}) — {stamp}" if host else f"{label} — {stamp}"
    design_id = str(uuid.uuid4())
    saved_at = now.isoformat()
    frame = ds.frame if isinstance(ds.frame, dict) else {}
    elems = ds.elements if isinstance(ds.elements, dict) else {}
    seq = frame.get("final_sequence") or ds.optimized_seq or ds.original_seq or ""
    payload = {
        "gene_name": gene,
        "host": host,
        "tag": ds.tag or "",
        "promoter": elems.get("promoter_name", ""),
        "promoter_seq": elems.get("promoter_seq", ""),
        "rbs": elems.get("rbs_name", ""),
        "rbs_seq": elems.get("rbs_seq", ""),
        "terminator": elems.get("terminator_name", ""),
        "terminator_seq": elems.get("terminator_seq", ""),
        "cloning_method": ds.cloning_method or "",
        "primer_context_host": ds.primer_context_host or "",
        "primer_context_seq_hash": ds.primer_context_seq_hash or "",
        "vector": frame.get("vector_suggestion", ""),
        "seq_len": len(seq),
        "gc_content": frame.get("gc_content", 0.0),
        "n_primers": len(ds.primers or []),
        "n_issues": len(ds.validation_results or []),
        "sequence": seq,
        "original_seq": ds.original_seq or "",
        "optimized_seq": ds.optimized_seq or "",
        "frame": frame,
        "features": frame.get("features", []) if isinstance(frame.get("features"), list) else [],
        "primers": ds.primers if isinstance(ds.primers, list) else [],
        "codon_report": ds.codon_report if isinstance(ds.codon_report, dict) else {},
        "validation_results": ds.validation_results if isinstance(ds.validation_results, list) else [],
        "method": "Expression Wizard",
        "step_reached": ds.step,
        "design_id": design_id,
        "saved_design_version": 1,
        "display_name": name,
        "saved_at": saved_at,
        "identity_source": "immutable_design_id",
        "saved_design_metadata": {
            "design_id": design_id,
            "saved_design_version": 1,
            "display_name": name,
            "saved_at": saved_at,
            "identity_source": "immutable_design_id",
        },
    }
    try:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
                (name, seq, "Expression Wizard", f"Saved Expression Wizard design for {label}", now.strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.execute(
                "INSERT INTO project_history (project_name, version, chassis, design_data, created_at, creator, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, 1, host, json.dumps(payload), now.strftime("%Y-%m-%d %H:%M:%S"), "Expression Wizard", "saved"),
            )
            conn.commit()
            return True, SaveWizardDesignResult(name, design_id)
        finally:
            conn.close()
    except Exception as exc:
        logger.error("[design_saver] save_wizard_design failed: %s", exc)
        return False, str(exc)


def load_wizard_design(project_name: str):
    load_key = saved_design_load_key(project_name)
    try:
        if not os.path.exists(DB_PATH):
            return False, f"Project not found: {load_key}"
        detail = query_saved_design_detail(load_key)
        data = detail.get("design_data") if isinstance(detail, dict) else {}
        if not isinstance(data, dict) or not data:
            return False, f"Project not found: {load_key}"

        from core.design_session import DesignSession

        return True, DesignSession(
            step=_resolve_resume_step(data),
            gene_name=data.get("gene_name", "") or "",
            original_seq=data.get("original_seq", "") or "",
            optimized_seq=data.get("optimized_seq", "") or "",
            host=data.get("host", "") or "",
            tag=data.get("tag", "") or "",
            elements=_build_elements(data),
            frame=data.get("frame") if isinstance(data.get("frame"), dict) else {},
            primers=data.get("primers") if isinstance(data.get("primers"), list) else [],
            validation_results=data.get("validation_results") if isinstance(data.get("validation_results"), list) else [],
            cloning_method=data.get("cloning_method", "") or "",
            codon_report=data.get("codon_report") if isinstance(data.get("codon_report"), dict) else {},
            primer_context_host=data.get("primer_context_host", "") or "",
            primer_context_seq_hash=data.get("primer_context_seq_hash", "") or "",
            source_saved_design_id=detail.get("design_id", ""),
            saved_design_metadata=detail.get("metadata", {}),
        )
    except Exception as exc:
        logger.error("[design_saver] load_wizard_design failed for %s: %s", load_key, exc)
        return False, str(exc)


def delete_wizard_design(project_name: str):
    delete_key = saved_design_delete_key(project_name)
    try:
        if not os.path.exists(DB_PATH):
            return False, f"Project not found: {delete_key}"
        conn = _connect()
        try:
            cur = conn.cursor()
            history_row = _fetch_project_history_detail_row_by_design_id(cur, delete_key)
            if history_row:
                rowid = cur.execute(
                    "SELECT id FROM project_history WHERE project_name = ? AND created_at = ? AND design_data = ? ORDER BY id DESC LIMIT 1",
                    (history_row[0], history_row[1], history_row[2]),
                ).fetchone()
                if not rowid:
                    return False, f"Project not found: {delete_key}"
                cur.execute("DELETE FROM project_history WHERE id = ?", (rowid[0],))
                deleted_history = cur.rowcount
                cur.execute(
                    "DELETE FROM sequences WHERE name = ? AND date_added = ?",
                    (history_row[0], history_row[1]),
                )
                deleted_sequences = cur.rowcount
            else:
                # Legacy fallback: name-based delete keeps existing behavior and may remove duplicate legacy names.
                cur.execute("DELETE FROM project_history WHERE project_name = ?", (delete_key,))
                deleted_history = cur.rowcount
                cur.execute("DELETE FROM sequences WHERE name = ?", (delete_key,))
                deleted_sequences = cur.rowcount
            conn.commit()
        finally:
            conn.close()
        return (True, delete_key) if (deleted_history or deleted_sequences) else (False, f"Project not found: {delete_key}")
    except Exception as exc:
        logger.error("[design_saver] delete_wizard_design failed for %s: %s", delete_key, exc)
        return False, str(exc)
