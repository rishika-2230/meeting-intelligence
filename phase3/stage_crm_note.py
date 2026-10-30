
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"

MEETING_ID = "Bdb001"

with sqlite3.connect(DB_PATH) as conn:

    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(crm_notes)")
    }

    if "is_demo" not in columns:
        conn.execute("""
            ALTER TABLE crm_notes
            ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0
        """)

    meeting = conn.execute("""
        SELECT summary
        FROM meetings
        WHERE meeting_id = ?
    """, (MEETING_ID,)).fetchone()

    if not meeting or not meeting[0]:
        raise ValueError("Meeting summary not found")

    summary = meeting[0]

    existing = conn.execute("""
        SELECT note_id
        FROM crm_notes
        WHERE meeting_id = ?
          AND is_demo = 1
        LIMIT 1
    """, (MEETING_ID,)).fetchone()

    if existing:
        print("Demo note already staged:", existing[0])
    else:
        cursor = conn.execute("""
            INSERT INTO crm_notes
            (
                meeting_id,
                note_text,
                review_status,
                sync_status,
                is_demo
            )
            VALUES (?, ?, 'pending', 'not_synced', 1)
        """, (MEETING_ID, summary))

        print("New CRM note ID:", cursor.lastrowid)

    conn.commit()

    print("Meeting:", MEETING_ID)
    print("Review status: pending")
    print("Demo only: True")
    print("HubSpot synchronization: Not started")
