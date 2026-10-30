
import sqlite3
import tempfile

from pathlib import Path
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sync_hubspot_tasks


# ---------------------------------------------
# 1. Database configuration
# ---------------------------------------------

REAL_DB = (
    Path(__file__).resolve().parent
    / "meeting_intelligence.db"
)


# ---------------------------------------------
# 2. Create temporary database
# ---------------------------------------------

with tempfile.TemporaryDirectory() as folder:

    test_db = Path(folder) / "test_task_sync.db"

    # Copy original database without modifying it.
    with closing(sqlite3.connect(REAL_DB)) as source:
        with closing(sqlite3.connect(test_db)) as destination:
            source.backup(destination)

    # -----------------------------------------
    # 3. Create fictional test records
    # -----------------------------------------

    with closing(sqlite3.connect(test_db)) as conn:

        # Use an existing meeting ID from the copied database.
        meeting = conn.execute("""
            SELECT meeting_id
            FROM meetings
            LIMIT 1
        """).fetchone()

        if not meeting:
            raise RuntimeError("No meetings available for test")

        meeting_id = meeting[0]

        # Fictional contact: never sent to HubSpot.
        cursor = conn.execute("""
            INSERT INTO crm_contacts (
                full_name,
                email,
                hubspot_contact_id
            )
            VALUES (?, ?, ?)
        """, (
            "Temporary Test Contact",
            "task-sync-test@example.invalid",
            "DRY_RUN_CONTACT_ONLY"
        ))

        contact_id = cursor.lastrowid

        # Associate fictional contact with meeting.
        conn.execute("""
            INSERT OR IGNORE INTO crm_meeting_contacts (
                meeting_id,
                contact_id
            )
            VALUES (?, ?)
        """, (meeting_id, contact_id))

        # A valid future deadline.
        due_date = (
            datetime.now(timezone.utc).date()
            + timedelta(days=7)
        ).isoformat()

        # Create an approved non-demo test task.
        cursor = conn.execute("""
            INSERT INTO crm_tasks (
                meeting_id,
                contact_id,
                task_title,
                owner,
                due_date,
                task_status,
                review_status,
                sync_status,
                is_demo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meeting_id,
            contact_id,
            "TEST ONLY - Verify task sync eligibility",
            "Temporary Test Owner",
            due_date,
            "open",
            "approved",
            "not_synced",
            0
        ))

        test_task_id = cursor.lastrowid

        conn.commit()

    # -----------------------------------------
    # 4. Run safe dry-run verification
    # -----------------------------------------

    original_path = sync_hubspot_tasks.DB_PATH
    sync_hubspot_tasks.DB_PATH = test_db

    try:
        # Make unexpected API requests fail immediately.
        with patch.object(
            sync_hubspot_tasks.requests,
            "get",
            side_effect=AssertionError("Unexpected HubSpot GET")
        ), patch.object(
            sync_hubspot_tasks.requests,
            "post",
            side_effect=AssertionError("Unexpected HubSpot POST")
        ):

            result = sync_hubspot_tasks.sync_task(
                task_id=test_task_id,
                dry_run=True
            )

        print("Test result:", result)

        assert result.startswith("ELIGIBLE:"), result

        # Confirm that the dry run did not modify the task.
        with closing(sqlite3.connect(test_db)) as conn:
            status = conn.execute("""
                SELECT sync_status, hubspot_task_id
                FROM crm_tasks
                WHERE task_id = ?
            """, (test_task_id,)).fetchone()

        assert status == ("not_synced", None), status

        print("Eligibility test: PASS")
        print("Task synchronization state: Unchanged")
        print("No HubSpot API requests made.")

    finally:
        sync_hubspot_tasks.DB_PATH = original_path

# TemporaryDirectory has now removed the test database.
print("Temporary database removed.")
print("Real SQLite database unchanged.")
