"""
db_utils.py  --  SQLite helpers for the Design module.
No Streamlit UI calls. No session_state access.

NOTE (P0 fix): All reads/writes now use core/unified_database.py uniformly.
  DB_PATH (data/biodesign_unified.db); bio_studio.db is no longer maintained separately.
  The sequences table is created by unified_database.ensure_database_exists().

Exports:
    init_db()              -- ensure unified DB exists and seed standard parts
    save_sequence()        -- insert a new sequence row
    get_all_sequences()    -- return full table as DataFrame
    get_sequence_by_name() -- look up one sequence by name
"""
import sqlite3
import logging
from typing import Optional

import pandas as pd

from .static_data import BIO_DB
# P0 fix: unified path and initialization from core/unified_database
from core.unified_database import DB_PATH, ensure_database_exists

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Ensure the unified DB and sequences table exist; seed standard parts if empty."""
    ensure_database_exists()   # idempotent: skip if exists, auto-create on fresh install
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT count(*) FROM sequences')
    if c.fetchone()[0] == 0:
        for p in BIO_DB['parts']:
            c.execute(
                'INSERT INTO sequences (name, sequence, category, description) VALUES (?,?,?,?)',
                (p['Name'], p['Seq'], 'Standard Part', 'From Standard Library'),
            )
        conn.commit()
    conn.close()


def save_sequence(name: str, seq: str, cat: str, desc: str) -> None:
    """Insert one sequence row into the unified database."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO sequences (name, sequence, category, description) VALUES (?,?,?,?)',
        (name, seq, cat, desc),
    )
    conn.commit()
    conn.close()


def get_all_sequences() -> pd.DataFrame:
    """Return all rows as a DataFrame (id, name, category, sequence, description)."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        'SELECT id, name, category, sequence, description FROM sequences', conn
    )
    conn.close()
    return df


def get_sequence_by_name(project_name: str) -> Optional[str]:
    """Return sequence string for *project_name*, or None if not found."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT sequence FROM sequences WHERE name = ? LIMIT 1', (project_name,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        logger.exception('get_sequence_by_name failed')
        return None
