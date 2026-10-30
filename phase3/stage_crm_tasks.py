
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"

with sqlite3.connect(DB_PATH) as conn:

    rows = conn.execute("""
        SELECT meeting_id, text, owner, deadline
        FROM meeting_items
        WHERE item_type IN ('commitments', 'action_items')
        AND text IS NOT NULL
        AND TRIM(text) != ''
        ORDER BY rowid
    """).fetchall()

    seen = set()
    selected = []

    for meeting_id, text, owner, deadline in rows:
        key = (meeting_id, " ".join(text.lower().split()))

        if key in seen:
            continue

        seen.add(key)
        selected.append((meeting_id, text, owner, deadline))

        if len(selected) == 5:
            break

    added = 0

    for meeting_id, text, owner, deadline in selected:

        existing = conn.execute("""
            SELECT 1
            FROM crm_tasks
            WHERE meeting_id = ?
            AND LOWER(TRIM(task_title)) = LOWER(TRIM(?))
            LIMIT 1
        """, (meeting_id, text)).fetchone()

        if existing:
            print("Already staged:", text[:60])
            continue

        conn.execute("""
            INSERT INTO crm_tasks
            (
                meeting_id,
                task_title,
                owner,
                due_date,
                review_status,
                sync_status
            )
            VALUES (?, ?, ?, ?, 'pending', 'not_synced')
        """, (meeting_id, text, owner, deadline))

        added += 1
        print("Staged:", meeting_id, "-", text[:70])

    conn.commit()

    print("\nNew tasks added:", added)

    total = conn.execute(
        "SELECT COUNT(*) FROM crm_tasks"
    ).fetchone()[0]

    print("Total CRM tasks:", total)
    print("Review status: pending")
    print("HubSpot sync: not_synced")
