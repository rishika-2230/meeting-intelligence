
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"

with sqlite3.connect(DB_PATH) as conn:
    # Add a demo flag without changing existing task data.
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(crm_tasks)")
    }

    if "is_demo" not in columns:
        conn.execute(
            "ALTER TABLE crm_tasks "
            "ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0"
        )

    # The five existing tasks came from historical QMSum meetings.
    conn.execute("""
        UPDATE crm_tasks
        SET is_demo = 1
        WHERE meeting_id IN ('Bdb001', 'Bed002', 'Bed006', 'Bmr003')
          AND hubspot_task_id IS NULL
    """)

    conn.commit()

    tasks = conn.execute("""
        SELECT task_id, meeting_id, task_title, owner,
               due_date, review_status, is_demo
        FROM crm_tasks
        ORDER BY task_id
    """).fetchall()

    for task in tasks:
        task_id, meeting_id, title, owner, due, status, demo = task

        print("\n" + "=" * 55)
        print("Task ID:", task_id)
        print("Meeting:", meeting_id)
        print("Task:", title)
        print("Owner:", owner or "Unassigned")
        print("Deadline:", due or "Not specified")
        print("Review:", status)
        print("Demo only:", bool(demo))

    print("\nTotal tasks:", len(tasks))
    print(
        "Pending review:",
        sum(task[5] == "pending" for task in tasks)
    )
    print(
        "Demo tasks:",
        sum(bool(task[6]) for task in tasks)
    )
