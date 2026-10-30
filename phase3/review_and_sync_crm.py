
import sqlite3
from contextlib import closing
from pathlib import Path

from sync_hubspot_notes import sync_note
from sync_hubspot_tasks import sync_task


# --------------------------------------------
# 1. Database configuration
# --------------------------------------------

DB_PATH = (
    Path(__file__).resolve().parent
    / "meeting_intelligence.db"
)


# --------------------------------------------
# 2. Read human-review decisions
# --------------------------------------------

def get_review_summary(conn, table):
    rows = conn.execute(f"""
        SELECT review_status, COUNT(*)
        FROM {table}
        GROUP BY review_status
    """).fetchall()

    return dict(rows)


def get_approved_ids(conn, table, id_column):
    rows = conn.execute(f"""
        SELECT {id_column}
        FROM {table}
        WHERE review_status = 'approved'
        ORDER BY {id_column}
    """).fetchall()

    return [row[0] for row in rows]


# --------------------------------------------
# 3. Unified synchronization preview
# --------------------------------------------

def main():

    print("=" * 55)
    print("MEETING INTELLIGENCE - CRM REVIEW & SYNC")
    print("=" * 55)

    with closing(sqlite3.connect(DB_PATH)) as conn:

        note_summary = get_review_summary(
            conn, "crm_notes"
        )

        task_summary = get_review_summary(
            conn, "crm_tasks"
        )

        note_ids = get_approved_ids(
            conn, "crm_notes", "note_id"
        )

        task_ids = get_approved_ids(
            conn, "crm_tasks", "task_id"
        )

    print("\n--- HUMAN REVIEW STATUS ---")

    print("Notes:")
    print("  Approved:", note_summary.get("approved", 0))
    print("  Pending:", note_summary.get("pending", 0))
    print("  Rejected:", note_summary.get("rejected", 0))

    print("Tasks:")
    print("  Approved:", task_summary.get("approved", 0))
    print("  Pending:", task_summary.get("pending", 0))
    print("  Rejected:", task_summary.get("rejected", 0))

    eligible_notes = 0
    eligible_tasks = 0

    # ----------------------------------------
    # 4. Preview approved notes
    # ----------------------------------------

    print("\n--- APPROVED NOTE SYNC PREVIEW ---")

    if not note_ids:
        print("No approved notes.")

    for note_id in note_ids:

        result = sync_note(
            note_id,
            dry_run=True
        )

        print(f"Note {note_id}: {result}")

        if result.startswith("ELIGIBLE:"):
            eligible_notes += 1

    # ----------------------------------------
    # 5. Preview approved tasks
    # ----------------------------------------

    print("\n--- APPROVED TASK SYNC PREVIEW ---")

    if not task_ids:
        print("No approved tasks.")

    for task_id in task_ids:

        result = sync_task(
            task_id,
            dry_run=True
        )

        print(f"Task {task_id}: {result}")

        if result.startswith("ELIGIBLE:"):
            eligible_tasks += 1

    # ----------------------------------------
    # 6. Final summary
    # ----------------------------------------

    print("\n--- SYNCHRONIZATION SUMMARY ---")

    print("Approved notes checked:", len(note_ids))
    print("Approved tasks checked:", len(task_ids))

    print("Eligible notes:", eligible_notes)
    print("Eligible tasks:", eligible_tasks)

    print("\nDRY RUN COMPLETE")
    print("No HubSpot writes performed.")
    print("No SQLite records modified.")


if __name__ == "__main__":
    main()
