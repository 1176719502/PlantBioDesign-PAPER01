"""
Unified database manager for the local BioDesign Studio workspace.

This module keeps the legacy unified SQLite bootstrap logic in one place and
exposes lightweight helpers used by older data-management flows.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import pandas as pd

from core.config import DB_PATH  # single source of truth; no side effects


# ----------------------------------------------------------------
# Unified database bootstrap
# ----------------------------------------------------------------

def init_unified_database():
    """
    Initialize the unified SQLite database.

    The schema combines legacy component tables and legacy laboratory record
    tables without changing the historical table definitions.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ----------------------------------------------------------------
    # 1. Standard component tables
    # ----------------------------------------------------------------

    # 1.1 Promoters table
    c.execute('''CREATE TABLE IF NOT EXISTS promoters (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT DEFAULT 'Promoter',
        sequence TEXT,
        length INTEGER,
        chassis_compatibility TEXT,
        tissue_specificity TEXT,
        inducible TEXT,
        strength TEXT,
        description TEXT,
        source_id TEXT,
        evidence_level TEXT,
        color TEXT,
        overhangs_5 TEXT,
        overhangs_3 TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')

    # 1.2 Genes table
    c.execute('''CREATE TABLE IF NOT EXISTS genes (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT,
        sequence TEXT,
        length INTEGER,
        chassis_compatibility TEXT,
        function_category TEXT,
        description TEXT,
        source_id TEXT,
        evidence_level TEXT,
        color TEXT,
        overhangs_5 TEXT,
        overhangs_3 TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')

    # 1.3 Terminators table
    c.execute('''CREATE TABLE IF NOT EXISTS terminators (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT DEFAULT 'Terminator',
        sequence TEXT,
        length INTEGER,
        chassis_compatibility TEXT,
        efficiency TEXT,
        description TEXT,
        source_id TEXT,
        evidence_level TEXT,
        color TEXT,
        overhangs_5 TEXT,
        overhangs_3 TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')

    # 1.4 Tags table
    c.execute('''CREATE TABLE IF NOT EXISTS tags (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT,
        sequence TEXT,
        length INTEGER,
        chassis_compatibility TEXT,
        function_type TEXT,
        description TEXT,
        source_id TEXT,
        evidence_level TEXT,
        color TEXT,
        overhangs_5 TEXT,
        overhangs_3 TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')

    # ----------------------------------------------------------------
    # 2. Legacy record tables
    # ----------------------------------------------------------------

    # 2.1 Primers table
    c.execute('''CREATE TABLE IF NOT EXISTS primers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        sequence TEXT NOT NULL,
        tm REAL,
        gc_content REAL,
        species TEXT,
        design_date TEXT,
        status TEXT,
        notes TEXT
    )''')

    # 2.2 Plasmids table
    c.execute('''CREATE TABLE IF NOT EXISTS plasmids (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        sequence TEXT,
        backbone TEXT,
        size_bp INTEGER,
        antibiotic_marker TEXT,
        species TEXT,
        entry_date TEXT,
        status TEXT,
        notes TEXT
    )''')

    # 2.3 Strains table
    c.execute('''CREATE TABLE IF NOT EXISTS strains (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        species TEXT,
        genotype TEXT,
        storage_location TEXT,
        entry_date TEXT,
        notes TEXT
    )''')

    # 2.4 ELN records table
    c.execute('''CREATE TABLE IF NOT EXISTS eln_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_name TEXT,
        experiment_date TEXT,
        researcher TEXT,
        protocol TEXT,
        markdown_content TEXT,
        attachments TEXT,
        created_at TEXT,
        modified_at TEXT
    )''')

    # 2.5 Project history table
    c.execute('''CREATE TABLE IF NOT EXISTS project_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_name TEXT,
        version INTEGER,
        chassis TEXT,
        design_data TEXT,
        created_at TEXT,
        creator TEXT,
        status TEXT
    )''')

    # ----------------------------------------------------------------
    # 3. Design module sequences table
    #    Previously in bio_studio.db / biodesign_local.db, now unified.
    #    Dashboard._get_projects_from_db() reads this table.
    # ----------------------------------------------------------------

    c.execute('''CREATE TABLE IF NOT EXISTS sequences (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        sequence    TEXT NOT NULL,
        category    TEXT NOT NULL,
        description TEXT,
        date_added  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # ----------------------------------------------------------------
    # 4. Activity log table
    #    Previously created on-demand by activity_log.py.
    # ----------------------------------------------------------------

    c.execute('''CREATE TABLE IF NOT EXISTS activity_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        action_type TEXT NOT NULL,
        message     TEXT NOT NULL,
        sub_message TEXT,
        module      TEXT,
        color       TEXT,
        created_at  TEXT NOT NULL
    )''')

    # ----------------------------------------------------------------
    # 5. Biological parts registry table
    #    Managed by core/database.py; created here so it exists in the
    #    unified DB from the very first startup.
    # ----------------------------------------------------------------

    c.execute('''CREATE TABLE IF NOT EXISTS biological_parts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL UNIQUE,
        part_type   TEXT    NOT NULL,
        sequence    TEXT    NOT NULL,
        length_bp   INTEGER NOT NULL,
        gc_content  REAL    NOT NULL,
        description TEXT    NOT NULL DEFAULT '',
        created_at  TEXT    NOT NULL
    )''')
    c.execute(
        'CREATE INDEX IF NOT EXISTS idx_bp_type ON biological_parts (part_type)'
    )
    c.execute(
        'CREATE INDEX IF NOT EXISTS idx_bp_name ON biological_parts (name)'
    )

    # ----------------------------------------------------------------
    # 6. Metadata table
    # ----------------------------------------------------------------

    c.execute('''CREATE TABLE IF NOT EXISTS database_meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    )''')

    # Record schema version only when the stored value is absent or outdated.
    current_version = c.execute(
        "SELECT value FROM database_meta WHERE key = 'version'"
    ).fetchone()
    if current_version is None:
        c.execute(
            "INSERT INTO database_meta (key, value) VALUES ('version', '1.2')"
        )
    elif current_version[0] != "1.2":
        c.execute(
            "UPDATE database_meta SET value = '1.2' WHERE key = 'version'"
        )
    created_at = c.execute(
        "SELECT value FROM database_meta WHERE key = 'created_at'"
    ).fetchone()
    if created_at is None:
        c.execute(
            "INSERT INTO database_meta (key, value) VALUES ('created_at', ?)",
            ("2026-07-22T00:00:00+00:00",),
        )

    conn.commit()
    conn.close()


# ----------------------------------------------------------------
# Standard component helpers
# ----------------------------------------------------------------

_ALLOWED_COMPONENT_TABLES = {"promoters", "genes", "terminators", "tags"}


def _validate_component_table(table: str) -> str:
    clean_table = str(table or "").strip()
    if clean_table not in _ALLOWED_COMPONENT_TABLES:
        raise ValueError(f"Invalid component table: {clean_table}")
    return clean_table


def add_component(table: str, data: Dict) -> Tuple[bool, str]:
    """
    Add one component record to a supported component table.

    Args:
        table: One of 'promoters', 'genes', 'terminators', or 'tags'.
        data: Column/value mapping for the INSERT statement.

    Returns:
        Tuple of success flag and status message.
    """
    try:
        table = _validate_component_table(table)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Stamp creation and update timestamps on insert.
        now = datetime.now().isoformat()
        data['created_at'] = now
        data['updated_at'] = now

        # Build a parameterised INSERT statement from the provided mapping.
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        c.execute(sql, list(data.values()))
        conn.commit()
        conn.close()
        return True, "Component added"

    except sqlite3.IntegrityError:
        return False, "ID already exists"
    except Exception as e:
        return False, f"Database error: {str(e)}"


def get_all_components(table: str) -> pd.DataFrame:
    """Return all rows from a supported component table."""
    try:
        table = _validate_component_table(table)
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        conn.close()
        return df
    except Exception as e:
        pass  # Read failed
        return pd.DataFrame()


def get_component_by_id(table: str, component_id: str) -> Optional[Dict]:
    """Return one component row by ID from a supported component table."""
    try:
        table = _validate_component_table(table)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(f"SELECT * FROM {table} WHERE id = ?", (component_id,))
        row = c.fetchone()
        conn.close()

        if row:
            columns = [desc[0] for desc in c.description]
            return dict(zip(columns, row))
        return None
    except Exception as e:
        pass  # Query failed
        return None


def update_component(table: str, component_id: str, data: Dict) -> Tuple[bool, str]:
    """Update one component row by ID in a supported component table."""
    try:
        table = _validate_component_table(table)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Refresh the update timestamp on write.
        data['updated_at'] = datetime.now().isoformat()

        # Build the SET clause from the provided mapping.
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE id = ?"

        c.execute(sql, list(data.values()) + [component_id])
        conn.commit()
        conn.close()
        return True, "Updated successfully"

    except Exception as e:
        return False, f"Update failed: {str(e)}"


def delete_component(table: str, component_id: str) -> Tuple[bool, str]:
    """Delete one component row by ID from a supported component table."""
    try:
        table = _validate_component_table(table)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(f"DELETE FROM {table} WHERE id = ?", (component_id,))
        conn.commit()
        conn.close()
        return True, "Deleted successfully"
    except Exception as e:
        return False, f"Delete failed: {str(e)}"


def search_components(table: str, keyword: str) -> pd.DataFrame:
    """Search a supported component table by name, description, or ID."""
    try:
        table = _validate_component_table(table)
        conn = sqlite3.connect(DB_PATH)
        like_val = f"%{keyword}%"
        sql = f"""SELECT * FROM {table}
                  WHERE name LIKE ? OR description LIKE ? OR id LIKE ?"""
        df = pd.read_sql_query(sql, conn, params=(like_val, like_val, like_val))
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


# ----------------------------------------------------------------
# Legacy record helpers
# ----------------------------------------------------------------

def add_primer(name: str, sequence: str, tm: float, gc: float,
               species: str = "Bacteria", status: str = "Designed") -> Tuple[bool, str]:
    """Insert one primer record."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT INTO primers
                     (name, sequence, tm, gc_content, species, design_date, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                 (name, sequence, tm, gc, species,
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status))
        conn.commit()
        conn.close()
        return True, "Primer added"
    except sqlite3.IntegrityError:
        return False, "Primer name already exists"
    except Exception as e:
        return False, f"Database error: {str(e)}"


def get_all_primers() -> pd.DataFrame:
    """Return all primer rows."""
    return get_all_components('primers')


def add_plasmid(name: str, sequence: str, backbone: str, size_bp: int,
                marker: str, species: str = "Plant", status: str = "Available") -> Tuple[bool, str]:
    """Insert one plasmid record."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT INTO plasmids
                     (name, sequence, backbone, size_bp, antibiotic_marker, species, entry_date, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                 (name, sequence, backbone, size_bp, marker, species,
                  datetime.now().strftime("%Y-%m-%d"), status))
        conn.commit()
        conn.close()
        return True, "Plasmid added"
    except sqlite3.IntegrityError:
        return False, "Plasmid name already exists"
    except Exception as e:
        return False, f"Database error: {str(e)}"


def get_all_plasmids() -> pd.DataFrame:
    """Return all plasmid rows."""
    return get_all_components('plasmids')


def add_strain(name: str, species: str, genotype: str,
               location: str, notes: str = "") -> Tuple[bool, str]:
    """Insert one strain record."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT INTO strains
                     (name, species, genotype, storage_location, entry_date, notes)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                 (name, species, genotype, location,
                  datetime.now().strftime("%Y-%m-%d"), notes))
        conn.commit()
        conn.close()
        return True, "Strain added"
    except sqlite3.IntegrityError:
        return False, "Strain name already exists"
    except Exception as e:
        return False, f"Database error: {str(e)}"


def get_all_strains() -> pd.DataFrame:
    """Return all strain rows."""
    return get_all_components('strains')


def save_eln_record(project_name: str, experiment_date: str, researcher: str,
                    protocol: str, markdown_content: str) -> Tuple[bool, str]:
    """Insert one ELN record."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""INSERT INTO eln_records
                     (project_name, experiment_date, researcher, protocol,
                      markdown_content, created_at, modified_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                 (project_name, experiment_date, researcher, protocol,
                  markdown_content, now, now))
        conn.commit()
        conn.close()
        return True, "ELN record saved"
    except Exception as e:
        return False, f"Save error: {str(e)}"


def get_all_eln_records() -> pd.DataFrame:
    """Return all ELN records ordered by creation time descending."""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM eln_records ORDER BY created_at DESC", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()


# ----------------------------------------------------------------
# Database diagnostics
# ----------------------------------------------------------------

def get_database_stats() -> Dict:
    """Return row counts for the legacy unified database tables."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        stats = {}
        for table in ['promoters', 'genes', 'terminators', 'tags',
                      'primers', 'plasmids', 'strains', 'eln_records']:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            stats[f"{table}_count"] = c.fetchone()[0]

        conn.close()
        return stats
    except Exception as e:
        pass  # Stats failed
        return {}


# ----------------------------------------------------------------
# JSON migration helper
# ----------------------------------------------------------------

def migrate_from_json(json_path: str) -> Tuple[bool, str]:
    """
    Import legacy component data from a JSON file into SQLite.

    Args:
        json_path: Path to the source JSON file.

    Returns:
        Tuple of success flag and summary message.
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        migrated = {'promoters': 0, 'genes': 0, 'terminators': 0, 'tags': 0}

        # Migrate promoter records.
        for comp_id, comp_data in data.get('Promoters', {}).items():
            try:
                c.execute("""INSERT OR IGNORE INTO promoters
                             (id, name, type, sequence, length, chassis_compatibility,
                              description, source_id, color, overhangs_5, overhangs_3,
                              created_at, updated_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (comp_id, comp_data.get('name'), comp_data.get('type', 'Promoter'),
                          comp_data.get('sequence'), comp_data.get('length'),
                          ','.join(comp_data.get('chassis_compatibility', [])),
                          comp_data.get('description'), comp_data.get('source_id'),
                          comp_data.get('color'),
                          comp_data.get('overhangs', {}).get('5_prime'),
                          comp_data.get('overhangs', {}).get('3_prime'),
                          datetime.now().isoformat(), datetime.now().isoformat()))
                migrated['promoters'] += 1
            except Exception as e:
                pass  # Skipped

        # Migrate gene records.
        for comp_id, comp_data in data.get('Genes', {}).items():
            try:
                c.execute("""INSERT OR IGNORE INTO genes
                             (id, name, type, sequence, length, chassis_compatibility,
                              description, source_id, color, overhangs_5, overhangs_3,
                              created_at, updated_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (comp_id, comp_data.get('name'), comp_data.get('type'),
                          comp_data.get('sequence'), comp_data.get('length'),
                          ','.join(comp_data.get('chassis_compatibility', [])),
                          comp_data.get('description'), comp_data.get('source_id'),
                          comp_data.get('color'),
                          comp_data.get('overhangs', {}).get('5_prime'),
                          comp_data.get('overhangs', {}).get('3_prime'),
                          datetime.now().isoformat(), datetime.now().isoformat()))
                migrated['genes'] += 1
            except Exception as e:
                pass  # Skipped

        # Migrate terminator records.
        for comp_id, comp_data in data.get('Terminators', {}).items():
            try:
                c.execute("""INSERT OR IGNORE INTO terminators
                             (id, name, type, sequence, length, chassis_compatibility,
                              description, source_id, color, overhangs_5, overhangs_3,
                              created_at, updated_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (comp_id, comp_data.get('name'), comp_data.get('type', 'Terminator'),
                          comp_data.get('sequence'), comp_data.get('length'),
                          ','.join(comp_data.get('chassis_compatibility', [])),
                          comp_data.get('description'), comp_data.get('source_id'),
                          comp_data.get('color'),
                          comp_data.get('overhangs', {}).get('5_prime'),
                          comp_data.get('overhangs', {}).get('3_prime'),
                          datetime.now().isoformat(), datetime.now().isoformat()))
                migrated['terminators'] += 1
            except Exception as e:
                pass  # Skipped

        # Migrate tag records.
        for comp_id, comp_data in data.get('Tags', {}).items():
            try:
                c.execute("""INSERT OR IGNORE INTO tags
                             (id, name, type, sequence, length, chassis_compatibility,
                              description, source_id, color, overhangs_5, overhangs_3,
                              created_at, updated_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (comp_id, comp_data.get('name'), comp_data.get('type'),
                          comp_data.get('sequence'), comp_data.get('length'),
                          ','.join(comp_data.get('chassis_compatibility', [])),
                          comp_data.get('description'), comp_data.get('source_id'),
                          comp_data.get('color'),
                          comp_data.get('overhangs', {}).get('5_prime'),
                          comp_data.get('overhangs', {}).get('3_prime'),
                          datetime.now().isoformat(), datetime.now().isoformat()))
                migrated['tags'] += 1
            except Exception as e:
                pass  # Skipped

        conn.commit()
        conn.close()

        summary = f"Migration completed: {migrated['promoters']} promoters, {migrated['genes']} genes, {migrated['terminators']} terminators, {migrated['tags']} tags"
        return True, summary

    except Exception as e:
        return False, f"Migration failed: {str(e)}"


# ----------------------------------------------------------------
# Startup initialization
# ----------------------------------------------------------------

def ensure_database_exists():
    """Ensure the versioned user database is ready through the lifecycle coordinator."""
    from core.database_lifecycle import ensure_database_ready

    return str(ensure_database_ready(DB_PATH).database_path)


def initialize_database_on_startup() -> str:
    """Validate, create, or migrate the user database before app startup."""
    return ensure_database_exists()


if __name__ == "__main__":
    initialize_database_on_startup()
    print("\nDatabase stats:")
    stats = get_database_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
