import sqlite3, os
db = os.path.join('data', 'biodesign_unified.db')
conn = sqlite3.connect(db)
try:
    conn.execute("ALTER TABLE biological_parts ADD COLUMN organism TEXT NOT NULL DEFAULT ''")
    conn.commit()
    print('Migration OK: organism column added')
except sqlite3.OperationalError as e:
    print('Already exists or skipped:', e)
finally:
    conn.close()
