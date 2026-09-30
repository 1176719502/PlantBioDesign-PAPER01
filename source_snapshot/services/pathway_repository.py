from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any

from core.config import DB_PATH


PATHWAY_PROJECTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pathway_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target_product TEXT NOT NULL,
    host TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    documentation_review_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

PATHWAY_STEPS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pathway_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    step_name TEXT,
    reaction_name TEXT,
    substrate TEXT,
    product TEXT,
    enzyme_name TEXT,
    gene_name TEXT,
    gene_sequence TEXT,
    organism_source TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES pathway_projects(id) ON DELETE CASCADE
)
"""

PATHWAY_EXPRESSION_DESIGNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pathway_expression_designs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    step_id INTEGER NOT NULL,
    design_name TEXT,
    design_source TEXT NOT NULL DEFAULT 'expression_wizard',
    design_snapshot_json TEXT,
    validation_summary_json TEXT,
    linked_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES pathway_projects(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES pathway_steps(id) ON DELETE CASCADE
)
"""

PATHWAY_TESTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pathway_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    step_id INTEGER,
    sample_name TEXT NOT NULL,
    measured_product TEXT,
    titer TEXT,
    yield_value TEXT,
    productivity TEXT,
    intermediate_accumulation TEXT,
    enzyme_activity TEXT,
    growth_status TEXT,
    condition TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES pathway_projects(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES pathway_steps(id) ON DELETE SET NULL
)
"""

PATHWAY_DOCUMENTATION_SNAPSHOTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pathway_documentation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    snapshot_title TEXT NOT NULL,
    snapshot_note TEXT,
    snapshot_payload_json TEXT NOT NULL,
    report_config_json TEXT NOT NULL,
    generated_markdown_text TEXT,
    include_generated_markdown INTEGER NOT NULL DEFAULT 0,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES pathway_projects(id) ON DELETE CASCADE
)
"""

DOCUMENTATION_REVIEW_CHECKLIST_KEYS = (
    "pathway_description_reviewed",
    "gene_entries_reviewed",
    "linked_expression_designs_reviewed",
    "suggestions_reviewed",
    "test_records_reviewed",
    "markdown_documentation_report_reviewed",
    "unresolved_documentation_items_reviewed",
)

DOCUMENTATION_REVIEW_TEXT_FIELDS = (
    "reviewer_name_or_initials",
    "review_date",
    "review_notes",
    "follow_up_actions",
    "unresolved_items",
    "last_updated",
    "review_scope",
    "review_context",
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def get_default_documentation_review() -> dict[str, Any]:
    return {
        "review_items": {key: False for key in DOCUMENTATION_REVIEW_CHECKLIST_KEYS},
        "reviewer_name_or_initials": "",
        "review_date": "",
        "review_notes": "",
        "follow_up_actions": "",
        "unresolved_items": "",
        "last_updated": "",
        "review_scope": "",
        "review_context": "",
    }


def normalize_documentation_review(payload: Any) -> dict[str, Any]:
    normalized = get_default_documentation_review()
    source = payload if isinstance(payload, dict) else {}

    source_items = source.get("review_items")
    if not isinstance(source_items, dict):
        source_items = {}
    normalized["review_items"] = {
        key: bool(source_items.get(key, False))
        for key in DOCUMENTATION_REVIEW_CHECKLIST_KEYS
    }

    for field in DOCUMENTATION_REVIEW_TEXT_FIELDS:
        normalized[field] = str(source.get(field) or "").strip()
    return normalized


def _documentation_review_from_json(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return normalize_documentation_review(raw_value)
    if not raw_value:
        return get_default_documentation_review()
    try:
        parsed = json.loads(str(raw_value))
    except (TypeError, json.JSONDecodeError):
        return get_default_documentation_review()
    return normalize_documentation_review(parsed)


def _normalize_project_record(project: dict[str, Any]) -> dict[str, Any]:
    if not project:
        return {}
    normalized = dict(project)
    normalized["documentation_review"] = _documentation_review_from_json(
        normalized.pop("documentation_review_json", None)
    )
    return normalized


def init_pathway_tables() -> None:
    """Create additive pathway tables without modifying existing schema."""
    conn = _connect()
    try:
        conn.execute(PATHWAY_PROJECTS_TABLE_SQL)
        if not _has_column(conn, "pathway_projects", "documentation_review_json"):
            conn.execute(
                "ALTER TABLE pathway_projects ADD COLUMN documentation_review_json TEXT"
            )
        conn.execute(PATHWAY_STEPS_TABLE_SQL)
        conn.execute(PATHWAY_EXPRESSION_DESIGNS_TABLE_SQL)
        conn.execute(PATHWAY_TESTS_TABLE_SQL)
        conn.execute(PATHWAY_DOCUMENTATION_SNAPSHOTS_TABLE_SQL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pathway_documentation_snapshots_project "
            "ON pathway_documentation_snapshots (project_id, created_at DESC, id DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pathway_documentation_snapshots_project_updated "
            "ON pathway_documentation_snapshots (project_id, updated_at DESC, id DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pathway_steps_project "
            "ON pathway_steps (project_id, step_order)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pathway_designs_step "
            "ON pathway_expression_designs (project_id, step_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pathway_tests_project "
            "ON pathway_tests (project_id, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pathway_tests_step "
            "ON pathway_tests (project_id, step_id)"
        )
        conn.commit()
    finally:
        conn.close()


def create_pathway_project(
    *,
    name: str,
    target_product: str,
    host: str = "",
    description: str = "",
    status: str = "draft",
) -> tuple[bool, str, int | None]:
    init_pathway_tables()
    clean_name = str(name or "").strip()
    clean_target = str(target_product or "").strip()
    if not clean_name:
        return False, "Project name is required.", None
    if not clean_target:
        return False, "Target product is required.", None

    timestamp = _now()
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO pathway_projects
                (name, target_product, host, description, status,
                 documentation_review_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_name,
                clean_target,
                str(host or "").strip(),
                str(description or "").strip(),
                str(status or "draft").strip() or "draft",
                safe_json_dumps(get_default_documentation_review()),
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        return True, "Pathway project created.", int(cursor.lastrowid)
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to create pathway project: {exc}", None
    finally:
        conn.close()


def list_pathway_projects() -> list[dict[str, Any]]:
    init_pathway_tables()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, name, target_product, host, description, status,
                   documentation_review_json, created_at, updated_at
            FROM pathway_projects
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
        return [_normalize_project_record(row) for row in _rows_to_dicts(rows)]
    finally:
        conn.close()


def get_pathway_project(project_id: int | str | None) -> dict[str, Any]:
    init_pathway_tables()
    try:
        resolved_id = int(project_id) if project_id is not None else 0
    except (TypeError, ValueError):
        return {}
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT id, name, target_product, host, description, status,
                   documentation_review_json, created_at, updated_at
            FROM pathway_projects
            WHERE id = ?
            """,
            (resolved_id,),
        ).fetchone()
        return _normalize_project_record(_row_to_dict(row))
    finally:
        conn.close()


def update_pathway_documentation_review(
    project_id: int | str | None,
    review_payload: dict[str, Any] | None,
) -> tuple[bool, str]:
    init_pathway_tables()
    try:
        resolved_id = int(project_id) if project_id is not None else 0
    except (TypeError, ValueError):
        return False, "Invalid project id."
    if resolved_id <= 0:
        return False, "Invalid project id."

    normalized_review = normalize_documentation_review(review_payload)
    timestamp = _now()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id FROM pathway_projects WHERE id = ?",
            (resolved_id,),
        ).fetchone()
        if row is None:
            return False, "Pathway project was not found."
        conn.execute(
            """
            UPDATE pathway_projects
            SET documentation_review_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (safe_json_dumps(normalized_review), timestamp, resolved_id),
        )
        conn.commit()
        return True, "Pathway documentation review updated."
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to update pathway documentation review: {exc}"
    finally:
        conn.close()


def delete_pathway_project(project_id: int | str | None) -> tuple[bool, str]:
    init_pathway_tables()
    try:
        resolved_id = int(project_id) if project_id is not None else 0
    except (TypeError, ValueError):
        return False, "Invalid project id."
    conn = _connect()
    try:
        conn.execute("DELETE FROM pathway_expression_designs WHERE project_id = ?", (resolved_id,))
        conn.execute("DELETE FROM pathway_tests WHERE project_id = ?", (resolved_id,))
        conn.execute("DELETE FROM pathway_steps WHERE project_id = ?", (resolved_id,))
        cursor = conn.execute("DELETE FROM pathway_projects WHERE id = ?", (resolved_id,))
        conn.commit()
        if cursor.rowcount:
            return True, "Pathway project deleted."
        return False, "Pathway project was not found."
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to delete pathway project: {exc}"
    finally:
        conn.close()


def create_pathway_step(
    *,
    project_id: int,
    step_order: int,
    step_name: str = "",
    reaction_name: str = "",
    substrate: str = "",
    product: str = "",
    enzyme_name: str = "",
    gene_name: str = "",
    gene_sequence: str = "",
    organism_source: str = "",
    notes: str = "",
) -> tuple[bool, str, int | None]:
    init_pathway_tables()
    try:
        resolved_project_id = int(project_id)
        resolved_order = int(step_order)
    except (TypeError, ValueError):
        return False, "Project id and step order are required.", None
    if resolved_project_id <= 0:
        return False, "A valid pathway project is required.", None
    if resolved_order <= 0:
        return False, "Step order must be greater than zero.", None

    timestamp = _now()
    conn = _connect()
    try:
        project_row = conn.execute(
            "SELECT id FROM pathway_projects WHERE id = ?",
            (resolved_project_id,),
        ).fetchone()
        if project_row is None:
            return False, "Pathway project was not found.", None

        cursor = conn.execute(
            """
            INSERT INTO pathway_steps
                (project_id, step_order, step_name, reaction_name, substrate, product,
                 enzyme_name, gene_name, gene_sequence, organism_source, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_project_id,
                resolved_order,
                str(step_name or "").strip(),
                str(reaction_name or "").strip(),
                str(substrate or "").strip(),
                str(product or "").strip(),
                str(enzyme_name or "").strip(),
                str(gene_name or "").strip(),
                str(gene_sequence or "").strip().upper(),
                str(organism_source or "").strip(),
                str(notes or "").strip(),
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            "UPDATE pathway_projects SET updated_at = ? WHERE id = ?",
            (timestamp, resolved_project_id),
        )
        conn.commit()
        return True, "Pathway step added.", int(cursor.lastrowid)
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to add pathway step: {exc}", None
    finally:
        conn.close()


def list_pathway_steps(project_id: int | str | None) -> list[dict[str, Any]]:
    init_pathway_tables()
    try:
        resolved_id = int(project_id) if project_id is not None else 0
    except (TypeError, ValueError):
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, project_id, step_order, step_name, reaction_name, substrate, product,
                   enzyme_name, gene_name, gene_sequence, organism_source, notes, created_at, updated_at
            FROM pathway_steps
            WHERE project_id = ?
            ORDER BY step_order ASC, id ASC
            """,
            (resolved_id,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def update_pathway_step(step_id: int | str | None, fields: dict[str, Any]) -> tuple[bool, str]:
    init_pathway_tables()
    try:
        resolved_step_id = int(step_id) if step_id is not None else 0
    except (TypeError, ValueError):
        return False, "Invalid step id."
    allowed_fields = {
        "step_order",
        "step_name",
        "reaction_name",
        "substrate",
        "product",
        "enzyme_name",
        "gene_name",
        "gene_sequence",
        "organism_source",
        "notes",
    }
    cleaned: dict[str, Any] = {}
    for key, value in (fields or {}).items():
        if key not in allowed_fields:
            continue
        if key == "step_order":
            try:
                cleaned[key] = int(value)
            except (TypeError, ValueError):
                return False, "Step order must be a number."
        elif key == "gene_sequence":
            cleaned[key] = str(value or "").strip().upper()
        else:
            cleaned[key] = str(value or "").strip()
    if not cleaned:
        return False, "No editable fields were provided."

    timestamp = _now()
    cleaned["updated_at"] = timestamp
    set_clause = ", ".join(f"{key} = ?" for key in cleaned)
    values = list(cleaned.values())
    values.append(resolved_step_id)

    conn = _connect()
    try:
        row = conn.execute(
            "SELECT project_id FROM pathway_steps WHERE id = ?",
            (resolved_step_id,),
        ).fetchone()
        if row is None:
            return False, "Pathway step was not found."
        conn.execute(f"UPDATE pathway_steps SET {set_clause} WHERE id = ?", values)
        conn.execute(
            "UPDATE pathway_projects SET updated_at = ? WHERE id = ?",
            (timestamp, row["project_id"]),
        )
        conn.commit()
        return True, "Pathway step updated."
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to update pathway step: {exc}"
    finally:
        conn.close()


def delete_pathway_step(step_id: int | str | None) -> tuple[bool, str]:
    init_pathway_tables()
    try:
        resolved_step_id = int(step_id) if step_id is not None else 0
    except (TypeError, ValueError):
        return False, "Invalid step id."
    timestamp = _now()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT project_id FROM pathway_steps WHERE id = ?",
            (resolved_step_id,),
        ).fetchone()
        if row is None:
            return False, "Pathway step was not found."
        project_id = row["project_id"]
        conn.execute("DELETE FROM pathway_expression_designs WHERE step_id = ?", (resolved_step_id,))
        conn.execute("UPDATE pathway_tests SET step_id = NULL, updated_at = ? WHERE step_id = ?", (timestamp, resolved_step_id))
        cursor = conn.execute("DELETE FROM pathway_steps WHERE id = ?", (resolved_step_id,))
        conn.execute(
            "UPDATE pathway_projects SET updated_at = ? WHERE id = ?",
            (timestamp, project_id),
        )
        conn.commit()
        if cursor.rowcount:
            return True, "Pathway step deleted."
        return False, "Pathway step was not found."
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to delete pathway step: {exc}"
    finally:
        conn.close()


def link_expression_design_to_step(
    *,
    project_id: int | str | None,
    step_id: int | str | None,
    design_name: str,
    design_snapshot_json: str,
    validation_summary_json: str,
    design_source: str = "expression_wizard",
) -> tuple[bool, str, int | None]:
    init_pathway_tables()
    try:
        resolved_project_id = int(project_id) if project_id is not None else 0
        resolved_step_id = int(step_id) if step_id is not None else 0
    except (TypeError, ValueError):
        return False, "Invalid project or step id.", None
    if resolved_project_id <= 0 or resolved_step_id <= 0:
        return False, "Invalid project or step id.", None

    clean_design_name = str(design_name or "").strip()
    if not clean_design_name:
        return False, "Design name is required.", None

    try:
        json.loads(str(design_snapshot_json or ""))
    except (TypeError, json.JSONDecodeError):
        return False, "Design snapshot JSON is invalid.", None

    try:
        json.loads(str(validation_summary_json or ""))
    except (TypeError, json.JSONDecodeError):
        return False, "Validation summary JSON is invalid.", None

    timestamp = _now()
    conn = _connect()
    try:
        project_row = conn.execute(
            "SELECT id FROM pathway_projects WHERE id = ?",
            (resolved_project_id,),
        ).fetchone()
        if project_row is None:
            return False, "Pathway project was not found.", None

        step_row = conn.execute(
            "SELECT id, project_id FROM pathway_steps WHERE id = ?",
            (resolved_step_id,),
        ).fetchone()
        if step_row is None:
            return False, "Pathway step was not found.", None
        if int(step_row["project_id"]) != resolved_project_id:
            return False, "Pathway step does not belong to the project.", None

        conn.execute(
            """
            DELETE FROM pathway_expression_designs
            WHERE project_id = ? AND step_id = ?
            """,
            (resolved_project_id, resolved_step_id),
        )
        cursor = conn.execute(
            """
            INSERT INTO pathway_expression_designs
                (project_id, step_id, design_name, design_source,
                 design_snapshot_json, validation_summary_json, linked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_project_id,
                resolved_step_id,
                clean_design_name,
                str(design_source or "expression_wizard").strip() or "expression_wizard",
                str(design_snapshot_json),
                str(validation_summary_json),
                timestamp,
            ),
        )
        conn.execute(
            "UPDATE pathway_projects SET updated_at = ? WHERE id = ?",
            (timestamp, resolved_project_id),
        )
        conn.commit()
        return True, "Expression design linked to pathway step.", int(cursor.lastrowid)
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to link expression design: {exc}", None
    finally:
        conn.close()


def list_expression_design_links(project_id: int | str | None) -> list[dict[str, Any]]:
    init_pathway_tables()
    try:
        resolved_id = int(project_id) if project_id is not None else 0
    except (TypeError, ValueError):
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, project_id, step_id, design_name, design_source,
                   design_snapshot_json, validation_summary_json, linked_at
            FROM pathway_expression_designs
            WHERE project_id = ?
            ORDER BY linked_at DESC, id DESC
            """,
            (resolved_id,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def _resolve_optional_step_id(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    return int(value)


def _validate_project_and_optional_step(
    conn: sqlite3.Connection,
    project_id: int,
    step_id: int | None,
) -> tuple[bool, str]:
    project_row = conn.execute(
        "SELECT id FROM pathway_projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if project_row is None:
        return False, "Pathway project was not found."
    if step_id is None:
        return True, ""

    step_row = conn.execute(
        "SELECT id, project_id FROM pathway_steps WHERE id = ?",
        (step_id,),
    ).fetchone()
    if step_row is None:
        return False, "Pathway step was not found."
    if int(step_row["project_id"]) != project_id:
        return False, "Pathway step does not belong to the project."
    return True, ""


def create_pathway_test_record(
    *,
    project_id: int | str | None,
    step_id: int | str | None = None,
    sample_name: str = "",
    measured_product: str = "",
    titer: str = "",
    yield_value: str = "",
    productivity: str = "",
    intermediate_accumulation: str = "",
    enzyme_activity: str = "",
    growth_status: str = "",
    condition: str = "",
    notes: str = "",
) -> tuple[bool, str, int | None]:
    init_pathway_tables()
    try:
        resolved_project_id = int(project_id) if project_id is not None else 0
        resolved_step_id = _resolve_optional_step_id(step_id)
    except (TypeError, ValueError):
        return False, "Invalid project or step id.", None
    if resolved_project_id <= 0:
        return False, "Invalid project or step id.", None

    clean_sample_name = str(sample_name or "").strip()
    if not clean_sample_name:
        return False, "Sample name is required.", None

    timestamp = _now()
    conn = _connect()
    try:
        ok, message = _validate_project_and_optional_step(conn, resolved_project_id, resolved_step_id)
        if not ok:
            return False, message, None

        cursor = conn.execute(
            """
            INSERT INTO pathway_tests
                (project_id, step_id, sample_name, measured_product, titer, yield_value,
                 productivity, intermediate_accumulation, enzyme_activity, growth_status,
                 condition, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_project_id,
                resolved_step_id,
                clean_sample_name,
                str(measured_product or "").strip(),
                str(titer or "").strip(),
                str(yield_value or "").strip(),
                str(productivity or "").strip(),
                str(intermediate_accumulation or "").strip(),
                str(enzyme_activity or "").strip(),
                str(growth_status or "").strip(),
                str(condition or "").strip(),
                str(notes or "").strip(),
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            "UPDATE pathway_projects SET updated_at = ? WHERE id = ?",
            (timestamp, resolved_project_id),
        )
        conn.commit()
        return True, "Pathway test record added.", int(cursor.lastrowid)
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to add pathway test record: {exc}", None
    finally:
        conn.close()


def list_pathway_test_records(project_id: int | str | None) -> list[dict[str, Any]]:
    init_pathway_tables()
    try:
        resolved_id = int(project_id) if project_id is not None else 0
    except (TypeError, ValueError):
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT tests.id, tests.project_id, tests.step_id, tests.sample_name,
                   tests.measured_product, tests.titer, tests.yield_value, tests.productivity,
                   tests.intermediate_accumulation, tests.enzyme_activity, tests.growth_status,
                   tests.condition, tests.notes, tests.created_at, tests.updated_at,
                   steps.step_order, steps.step_name, steps.reaction_name
            FROM pathway_tests AS tests
            LEFT JOIN pathway_steps AS steps ON tests.step_id = steps.id
            WHERE tests.project_id = ?
            ORDER BY tests.created_at DESC, tests.id DESC
            """,
            (resolved_id,),
        ).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def update_pathway_test_record(test_id: int | str | None, fields: dict[str, Any]) -> tuple[bool, str]:
    init_pathway_tables()
    try:
        resolved_test_id = int(test_id) if test_id is not None else 0
    except (TypeError, ValueError):
        return False, "Invalid test record id."

    allowed_fields = {
        "step_id",
        "sample_name",
        "measured_product",
        "titer",
        "yield_value",
        "productivity",
        "intermediate_accumulation",
        "enzyme_activity",
        "growth_status",
        "condition",
        "notes",
    }
    cleaned: dict[str, Any] = {}
    try:
        for key, value in (fields or {}).items():
            if key not in allowed_fields:
                continue
            if key == "step_id":
                cleaned[key] = _resolve_optional_step_id(value)
            else:
                cleaned[key] = str(value or "").strip()
    except (TypeError, ValueError):
        return False, "Invalid step id."

    if not cleaned:
        return False, "No editable fields were provided."
    if "sample_name" in cleaned and not cleaned["sample_name"]:
        return False, "Sample name is required."

    timestamp = _now()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, project_id, sample_name FROM pathway_tests WHERE id = ?",
            (resolved_test_id,),
        ).fetchone()
        if row is None:
            return False, "Pathway test record was not found."

        final_sample_name = cleaned.get("sample_name", row["sample_name"])
        if not str(final_sample_name or "").strip():
            return False, "Sample name is required."

        if "step_id" in cleaned:
            ok, message = _validate_project_and_optional_step(conn, int(row["project_id"]), cleaned["step_id"])
            if not ok:
                return False, message

        cleaned["updated_at"] = timestamp
        set_clause = ", ".join(f"{key} = ?" for key in cleaned)
        values = list(cleaned.values())
        values.append(resolved_test_id)
        conn.execute(f"UPDATE pathway_tests SET {set_clause} WHERE id = ?", values)
        conn.execute(
            "UPDATE pathway_projects SET updated_at = ? WHERE id = ?",
            (timestamp, row["project_id"]),
        )
        conn.commit()
        return True, "Pathway test record updated."
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to update pathway test record: {exc}"
    finally:
        conn.close()


def delete_pathway_test_record(test_id: int | str | None) -> tuple[bool, str]:
    init_pathway_tables()
    try:
        resolved_test_id = int(test_id) if test_id is not None else 0
    except (TypeError, ValueError):
        return False, "Invalid test record id."

    timestamp = _now()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT project_id FROM pathway_tests WHERE id = ?",
            (resolved_test_id,),
        ).fetchone()
        if row is None:
            return False, "Pathway test record was not found."
        cursor = conn.execute("DELETE FROM pathway_tests WHERE id = ?", (resolved_test_id,))
        conn.execute(
            "UPDATE pathway_projects SET updated_at = ? WHERE id = ?",
            (timestamp, row["project_id"]),
        )
        conn.commit()
        if cursor.rowcount:
            return True, "Pathway test record deleted."
        return False, "Pathway test record was not found."
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to delete pathway test record: {exc}"
    finally:
        conn.close()


DOCUMENTATION_SNAPSHOT_SCHEMA_VERSION = "1.0"
DOCUMENTATION_SNAPSHOT_DEFAULT_TITLE = "Untitled Documentation Snapshot"
DOCUMENTATION_SNAPSHOT_BOUNDARY_STATEMENT = (
    "Documentation snapshots are user-created local workspace records for traceability only. They do not approve, "
    "validate, certify, sign, lock, or make the project ready for experimental use. Snapshot contents do not change "
    "Wizard validation, Step 6 export recommendations, primer-risk status, completeness score semantics, Suggestions "
    "semantics, Review Notes semantics, or downstream handoff behavior."
)


def _safe_json_loads(raw_value: Any, default: Any) -> Any:
    if isinstance(raw_value, (dict, list)):
        return raw_value
    if raw_value in (None, ""):
        return default
    try:
        return json.loads(str(raw_value))
    except (TypeError, json.JSONDecodeError):
        return default


def _normalize_snapshot_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _normalize_snapshot_payload(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _normalize_snapshot_record(row: sqlite3.Row | None) -> dict[str, Any]:
    raw = _row_to_dict(row)
    if not raw:
        return {}
    raw["snapshot_payload"] = _safe_json_loads(raw.get("snapshot_payload_json"), {})
    raw["report_config"] = _safe_json_loads(raw.get("report_config_json"), {})
    raw["include_generated_markdown"] = bool(raw.get("include_generated_markdown"))
    return raw


def create_pathway_documentation_snapshot(
    *,
    project_id: int | str | None,
    snapshot_title: str = "",
    snapshot_note: str = "",
    snapshot_payload: dict[str, Any] | None = None,
    report_config: dict[str, Any] | None = None,
    generated_markdown_text: str | None = None,
    include_generated_markdown: bool = False,
    schema_version: str = DOCUMENTATION_SNAPSHOT_SCHEMA_VERSION,
) -> tuple[bool, str, int | None]:
    init_pathway_tables()
    try:
        resolved_project_id = int(project_id) if project_id is not None else 0
    except (TypeError, ValueError):
        return False, "Invalid project id.", None
    if resolved_project_id <= 0:
        return False, "Invalid project id.", None

    clean_title = _normalize_snapshot_text(snapshot_title, DOCUMENTATION_SNAPSHOT_DEFAULT_TITLE)
    clean_note = _normalize_snapshot_text(snapshot_note)
    clean_schema_version = _normalize_snapshot_text(schema_version, DOCUMENTATION_SNAPSHOT_SCHEMA_VERSION)
    payload_dict = _normalize_snapshot_payload(snapshot_payload)
    report_config_dict = _normalize_snapshot_payload(report_config)
    markdown_text = _normalize_snapshot_text(generated_markdown_text)
    include_markdown_flag = bool(include_generated_markdown or markdown_text)
    stored_markdown_text = markdown_text if include_markdown_flag else None
    timestamp = _now()

    if not payload_dict:
        return False, "Snapshot payload is required.", None

    conn = _connect()
    try:
        project_row = conn.execute(
            "SELECT id FROM pathway_projects WHERE id = ?",
            (resolved_project_id,),
        ).fetchone()
        if project_row is None:
            return False, "Pathway project was not found.", None

        cursor = conn.execute(
            """
            INSERT INTO pathway_documentation_snapshots
                (project_id, snapshot_title, snapshot_note, snapshot_payload_json,
                 report_config_json, generated_markdown_text, include_generated_markdown,
                 schema_version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_project_id,
                clean_title,
                clean_note,
                safe_json_dumps(payload_dict),
                safe_json_dumps(report_config_dict),
                stored_markdown_text,
                1 if include_markdown_flag else 0,
                clean_schema_version,
                timestamp,
                timestamp,
            ),
        )
        conn.commit()
        return True, "Pathway documentation snapshot created.", int(cursor.lastrowid)
    except Exception as exc:
        conn.rollback()
        return False, f"Failed to create pathway documentation snapshot: {exc}", None
    finally:
        conn.close()


def list_pathway_documentation_snapshots(project_id: int | str | None) -> list[dict[str, Any]]:
    init_pathway_tables()
    try:
        resolved_id = int(project_id) if project_id is not None else 0
    except (TypeError, ValueError):
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, project_id, snapshot_title, snapshot_note, snapshot_payload_json,
                   report_config_json, generated_markdown_text, include_generated_markdown,
                   schema_version, created_at, updated_at
            FROM pathway_documentation_snapshots
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (resolved_id,),
        ).fetchall()
        return [_normalize_snapshot_record(row) for row in rows]
    finally:
        conn.close()


def get_pathway_documentation_snapshot(snapshot_id: int | str | None) -> dict[str, Any]:
    init_pathway_tables()
    try:
        resolved_id = int(snapshot_id) if snapshot_id is not None else 0
    except (TypeError, ValueError):
        return {}
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT id, project_id, snapshot_title, snapshot_note, snapshot_payload_json,
                   report_config_json, generated_markdown_text, include_generated_markdown,
                   schema_version, created_at, updated_at
            FROM pathway_documentation_snapshots
            WHERE id = ?
            """,
            (resolved_id,),
        ).fetchone()
        return _normalize_snapshot_record(row)
    finally:
        conn.close()


def safe_json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
