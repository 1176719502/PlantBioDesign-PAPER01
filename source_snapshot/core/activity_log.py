# [DORMANT — V1 FREEZE]
# Not part of the active V1 wizard path. Retained for future reuse.
# Do not extend or modify unless this module is intentionally reactivated.
"""
Activity Log Manager
Records and queries user operation history.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List

from core.config import DB_PATH


def log_activity(action_type: str, message: str, sub_message: str = "", 
                 module: str = "", color: str = "#2563eb") -> bool:
    """
    Log a user activity to the activity_log table.

    Args:
        action_type: Operation type (create, update, delete, import, export, analyze)
        message: Primary message
        sub_message: Secondary message (optional)
        module: Module name (Design, Build, Test, Data, Analysis)
        color: Display color (hex string)

    Returns:
        True if the record was written successfully, False otherwise.

    Example:
        log_activity("create", "New project Maize_v2", "Design Module · draft saved", "Design", "#7c3aed")
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Ensure table exists
        c.execute('''CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            message TEXT NOT NULL,
            sub_message TEXT,
            module TEXT,
            color TEXT,
            created_at TEXT NOT NULL
        )''')
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""INSERT INTO activity_log 
                     (action_type, message, sub_message, module, color, created_at)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                 (action_type, message, sub_message, module, color, now))
        
        conn.commit()
        conn.close()
        return True
    
    except Exception as e:
        print(f"[Activity Log] Error: {e}")
        return False


def get_recent_activities(limit: int = 10) -> List[Dict]:
    """
    Retrieve the most recent activity log entries.

    Args:
        limit: Number of entries to return

    Returns:
        List of activity dicts, each containing: action_type, message, sub_message, module, color, time
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Ensure table exists
        c.execute('''CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            message TEXT NOT NULL,
            sub_message TEXT,
            module TEXT,
            color TEXT,
            created_at TEXT NOT NULL
        )''')
        
        c.execute("""SELECT action_type, message, sub_message, module, color, created_at 
                     FROM activity_log 
                     ORDER BY created_at DESC 
                     LIMIT ?""", (limit,))
        
        activities = []
        for row in c.fetchall():
            # Format time display
            created_at = row[5]
            try:
                dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                now = datetime.now()
                diff = now - dt
                
                if diff.days == 0:
                    time_str = dt.strftime("%H:%M")
                elif diff.days == 1:
                    time_str = "Yesterday"
                elif diff.days < 7:
                    time_str = f"{diff.days} days ago"
                else:
                    time_str = dt.strftime("%b %d")
            except:
                time_str = created_at[:10]
            
            activities.append({
                "action_type": row[0],
                "message": row[1],
                "sub_message": row[2] or "",
                "module": row[3] or "",
                "color": row[4] or "#2563eb",
                "time": time_str
            })
        
        conn.close()
        return activities
    
    except Exception as e:
        print(f"[Activity Log] Query error: {e}")
        return []


def clear_old_activities(days: int = 30) -> int:
    """
    Remove activity log entries older than the specified number of days.

    Args:
        days: Number of days of history to retain

    Returns:
        Number of deleted rows
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("DELETE FROM activity_log WHERE created_at < ?", (cutoff_date,))
        deleted = c.rowcount
        
        conn.commit()
        conn.close()
        return deleted
    
    except Exception as e:
        print(f"[Activity Log] Clear error: {e}")
        return 0


# Predefined activity type colors
ACTIVITY_COLORS = {
    "create":  "#16a34a",   # green  - create
    "update":  "#2563eb",   # blue   - update
    "delete":  "#dc2626",   # red    - delete
    "import":  "#d97706",   # orange - import
    "export":  "#7c3aed",   # purple - export
    "analyze": "#2563eb",   # blue   - analyze
    "build":   "#16a34a",   # green  - build
    "test":    "#d97706",   # orange - test
    "warning": "#dc2626",   # red    - warning
}




def log_design_activity(message: str, sub_message: str = ""):
    """Shortcut: log a Design module activity."""
    return log_activity("create", message, sub_message, "Design", ACTIVITY_COLORS["create"])


def log_build_activity(message: str, sub_message: str = ""):
    """Shortcut: log a Build module activity."""
    return log_activity("build", message, sub_message, "Build", ACTIVITY_COLORS["build"])


def log_data_activity(message: str, sub_message: str = ""):
    """Shortcut: log a Data module activity."""
    return log_activity("import", message, sub_message, "Data", ACTIVITY_COLORS["import"])


def log_analysis_activity(message: str, sub_message: str = ""):
    """Shortcut: log an Analysis module activity."""
    return log_activity("analyze", message, sub_message, "Analysis", ACTIVITY_COLORS["analyze"])


def log_test_activity(message: str, sub_message: str = ""):
    """Shortcut: log a Test module activity."""
    return log_activity("test", message, sub_message, "Test", ACTIVITY_COLORS["test"])




def get_dbtl_progress() -> dict:
    """
    Returns DBTL four-phase activity counts for Dashboard progress ring.
    Keys: Design, Build, Test, Learn, total, last_active_module
    """
    try:
        conn = __import__('sqlite3').connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activity_log'")
        if not c.fetchone():
            conn.close()
            return _empty_dbtl()
        c.execute("SELECT module, COUNT(*) FROM activity_log GROUP BY module")
        counts = {row[0]: row[1] for row in c.fetchall()}
        c.execute("SELECT module FROM activity_log ORDER BY created_at DESC LIMIT 1")
        row = c.fetchone()
        last = row[0] if row else ""
        conn.close()
        return {
            "Design": counts.get("Design", 0),
            "Build":  counts.get("Build",  0),
            "Test":   counts.get("Test",   0),
            "Learn":  counts.get("Analysis", 0) + counts.get("Data", 0),
            "total":  sum(counts.values()),
            "last_active_module": last,
        }
    except Exception as e:
        print(f"[Activity Log] get_dbtl_progress error: {e}")
        return _empty_dbtl()


def _empty_dbtl() -> dict:
    return {"Design": 0, "Build": 0, "Test": 0, "Learn": 0,
            "total": 0, "last_active_module": ""}


if __name__ == "__main__":
    # Test code
    print("Activity Log Module Test")
    print("=" * 60)
    
    # Add test log entries
    log_design_activity("New project Test_Project", "Design Module · draft saved")
    log_build_activity("Primer design complete", "PCR primers generated ×2")
    log_data_activity("Part imported: 35S-Promoter", "Parts Library → Promoter")
    
    # Query log
    print("\nRecent Activities:")
    activities = get_recent_activities(5)
    for act in activities:
        print(f"  [{act['time']}] {act['message']}")
        print(f"    {act['sub_message']}")
    
    print("\n" + "=" * 60)
