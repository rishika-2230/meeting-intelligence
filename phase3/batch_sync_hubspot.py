
import argparse
import sqlite3

from collections import Counter
from contextlib import closing
from pathlib import Path

from sync_hubspot_notes import sync_note
from sync_hubspot_tasks import sync_task


DB_PATH = (
    Path(__file__).resolve().parent
    / "meeting_intelligence.db"
)


# ------------------------------------------
# 1. Normalize text for duplicate detection
# ------------------------------------------

def normalize(value):
    return " ".join(
        str(value or "").split()
    ).casefold()


def signature(record, record_type):
    if record_type == "note":
        return (
            record["meeting_id"],
            record["contact_id"],
            normalize(record["note_text"])
        )

    return (
        record["meeting_id"],
        record["contact_id"],
        normalize(record["task_title"]),
        record["due_date"]
    )


# ------------------------------------------
# 2. Read SQLite records safely
# ------------------------------------------

def load_records():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row

        notes = [
            dict(row)
            for row in conn.execute("""
                SELECT note_id, meeting_id, contact_id,
                       note_text, review_status, is_demo
                FROM crm_notes
                ORDER BY note_id
            """)
        ]

        tasks = [
            dict(row)
            for row in conn.execute("""
                SELECT task_id, meeting_id, contact_id,
                       task_title, due_date,
                       review_status, is_demo
                FROM crm_tasks
                ORDER BY task_id
            """)
        ]

    return notes, tasks


# ------------------------------------------
# 3. Detect duplicate local records
# ------------------------------------------

def duplicate_signatures(records, record_type):
    counts = Counter(
        signature(record, record_type)
        for record in records
        if not record["is_demo"]
    )

    return {
        key for key, count in counts.items()
        if count > 1
    }


# ------------------------------------------
# 4. Batch synchronization controller
# ------------------------------------------

def run_batch(live=False, limit=5):
    notes, tasks = load_records()

    note_duplicates = duplicate_signatures(
        notes, "note"
    )
    task_duplicates = duplicate_signatures(
        tasks, "task"
    )

    approved_notes = [
        record for record in notes
        if record["review_status"] == "approved"
    ]

    approved_tasks = [
        record for record in tasks
        if record["review_status"] == "approved"
    ]

    print("=" * 55)
    print("MEETING INTELLIGENCE - HUBSPOT BATCH SYNC")
    print("=" * 55)
    print("Mode:", "LIVE" if live else "DRY RUN")
    print("Approved notes:", len(approved_notes))
    print("Approved tasks:", len(approved_tasks))
    print("Duplicate note groups:", len(note_duplicates))
    print("Duplicate task groups:", len(task_duplicates))

    eligible = 0
    blocked = 0
    synced = 0
    attempts = 0

    records = (
        [("note", record) for record in approved_notes]
        + [("task", record) for record in approved_tasks]
    )

    for record_type, record in records:
        id_column = (
            "note_id" if record_type == "note"
            else "task_id"
        )
        record_id = record[id_column]
        label = f"{record_type.title()} {record_id}"

        duplicates = (
            note_duplicates if record_type == "note"
            else task_duplicates
        )

        if signature(record, record_type) in duplicates:
            print(f"{label}: BLOCKED - Duplicate local record")
            blocked += 1
            continue

        # Always check eligibility without writes first.
        if record_type == "note":
            preview = sync_note(record_id, dry_run=True)
        else:
            preview = sync_task(record_id, dry_run=True)

        if not preview.startswith("ELIGIBLE:"):
            print(f"{label}: {preview}")
            blocked += 1
            continue

        eligible += 1

        if not live:
            print(f"{label}: ELIGIBLE - Dry run only")
            continue

        if attempts >= limit:
            print(f"{label}: SKIPPED - Live batch limit reached")
            continue

        attempts += 1

        try:
            if record_type == "note":
                result = sync_note(
                    record_id, dry_run=False
                )
            else:
                result = sync_task(
                    record_id, dry_run=False
                )

            print(f"{label}: {result}")

            if result.startswith("SYNCED:"):
                synced += 1
            else:
                blocked += 1

        except Exception as error:
            print(
                f"{label}: ERROR - "
                f"{type(error).__name__}"
            )
            print(
                "Batch stopped. Inspect the record's "
                "sync_status before retrying."
            )
            break

    print("\n--- BATCH SUMMARY ---")
    print("Eligible records:", eligible)
    print("Blocked records:", blocked)
    print("Successfully synced:", synced)

    if not live:
        print("DRY RUN COMPLETE")
        print("No HubSpot writes performed.")
        print("No SQLite records modified.")
    else:
        print("LIVE BATCH FINISHED")
        print("Check individual sync statuses.")


# ------------------------------------------
# 5. Command-line safety controls
# ------------------------------------------

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable HubSpot writes"
    )

    parser.add_argument(
        "--confirm",
        default="",
        help="Required confirmation for live mode"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum live synchronization attempts"
    )

    args = parser.parse_args()

    if not 1 <= args.limit <= 10:
        parser.error("--limit must be between 1 and 10")

    if args.live and args.confirm != "SYNC_APPROVED_CRM":
        parser.error(
            "Live mode requires "
            "--confirm SYNC_APPROVED_CRM"
        )

    run_batch(
        live=args.live,
        limit=args.limit
    )
