
import hashlib
import sqlite3
import requests

from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from crm_approval_gate import audit_crm_records
from sync_hubspot_notes import sync_note
from sync_hubspot_tasks import sync_task


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "meeting_intelligence.db"


# ============================================================
# 2. DATABASE SNAPSHOT
# ============================================================

def database_snapshot():
    """
    Calculate a fingerprint of every user table.

    Used to verify that the synchronization tests
    do not modify existing database records.
    """

    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)

    with closing(sqlite3.connect(DB_PATH)) as conn:

        tables = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        digest = hashlib.sha256()

        for (table_name,) in tables:

            safe_name = (
                '"' + table_name.replace('"', '""') + '"'
            )

            rows = conn.execute(
                f"SELECT * FROM {safe_name}"
            ).fetchall()

            digest.update(
                repr((table_name, rows)).encode(
                    "utf-8"
                )
            )

    return digest.hexdigest()


# ============================================================
# 3. GET CRM RECORD IDS
# ============================================================

def get_record_ids():

    with closing(sqlite3.connect(DB_PATH)) as conn:

        note_ids = [
            row[0]
            for row in conn.execute(
                "SELECT note_id FROM crm_notes ORDER BY note_id"
            )
        ]

        task_ids = [
            row[0]
            for row in conn.execute(
                "SELECT task_id FROM crm_tasks ORDER BY task_id"
            )
        ]

    return note_ids, task_ids


# ============================================================
# 4. TEST ALL CRM SYNCHRONIZATION PATHS
# ============================================================

def verify_all_records():

    print("=" * 60)
    print("HUBSPOT CRM - COMBINED SAFETY VERIFICATION")
    print("=" * 60)

    before = database_snapshot()

    note_ids, task_ids = get_record_ids()

    audit = audit_crm_records()

    eligible = [
        record
        for record in audit
        if record["eligible"]
    ]

    print("\n--- DATABASE RECORDS ---")
    print("CRM notes:", len(note_ids))
    print("CRM tasks:", len(task_ids))
    print("Total records:", len(audit))
    print("Records passing approval gate:", len(eligible))

    if eligible:
        raise AssertionError(
            "Unexpected eligible CRM records. "
            "Review the database before continuing."
        )

    results = []

    # Both requests.get and requests.post are patched.
    # Any accidental HTTP request will fail immediately.

    def block_http(*args, **kwargs):
        raise AssertionError(
            "Unexpected HTTP request during safety test"
        )

    with (
        patch.object(
            requests,
            "get",
            side_effect=block_http
        ) as mock_get,
        patch.object(
            requests,
            "post",
            side_effect=block_http
        ) as mock_post
    ):

        print("\n--- NOTES ---")

        for note_id in note_ids:

            result = sync_note(
                note_id=note_id,
                dry_run=True
            )

            print(f"Note {note_id}: {result}")

            results.append(result)

        print("\n--- TASKS ---")

        for task_id in task_ids:

            result = sync_task(
                task_id=task_id,
                dry_run=True
            )

            print(f"Task {task_id}: {result}")

            results.append(result)

        if mock_get.called or mock_post.called:
            raise AssertionError(
                "An HTTP request was attempted."
            )

    # Every existing demo record should be blocked.
    if not all(
        result.startswith("BLOCKED:")
        for result in results
    ):
        raise AssertionError(
            "One or more records were not blocked."
        )

    after = database_snapshot()

    if before != after:
        raise AssertionError(
            "SQLite data changed during the test."
        )

    print("\n" + "=" * 60)
    print("FINAL VERIFICATION RESULTS")
    print("=" * 60)

    print("CRM records tested:", len(results))
    print("CRM records blocked:", len(results))
    print("HubSpot GET requests: 0")
    print("HubSpot POST requests: 0")
    print("SQLite modifications: 0")

    print("\nMeeting approval gate: PASS")
    print("CRM record protection: PASS")
    print("Dry-run isolation: PASS")
    print("Database integrity check: PASS")

    print("\nCOMBINED HUBSPOT SAFETY TEST: PASS")

    print(
        "\nLive HubSpot synchronization has "
        "not been tested or enabled."
    )


# ============================================================
# 5. ENTRY POINT
# ============================================================

if __name__ == "__main__":
    verify_all_records()
