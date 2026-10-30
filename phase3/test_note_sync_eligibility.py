
import sqlite3
import tempfile
from pathlib import Path
from contextlib import closing

import sync_hubspot_notes

REAL_DB = Path(__file__).resolve().parent / "meeting_intelligence.db"

with tempfile.TemporaryDirectory() as folder:
    test_db = Path(folder) / "test_meeting_intelligence.db"

    # Copy the real database safely into a temporary test database
    with closing(sqlite3.connect(REAL_DB)) as source:
        with closing(sqlite3.connect(test_db)) as destination:
            source.backup(destination)

    with closing(sqlite3.connect(test_db)) as conn:
        # Create a fictional meeting
        conn.execute("""
            INSERT INTO meetings
            (meeting_id, summary, requires_human_review)
            VALUES (?, ?, ?)
        """, (
            "SYNC_TEST_ONLY",
            "Fictional meeting used for dry-run testing.",
            0
        ))

        # Create a fictional CRM contact
        cursor = conn.execute("""
            INSERT INTO crm_contacts
            (full_name, email, hubspot_contact_id)
            VALUES (?, ?, ?)
        """, (
            "Test Contact",
            "sync-test@example.invalid",
            "DRY_RUN_CONTACT_ONLY"
        ))

        contact_id = cursor.lastrowid

        # Establish a meeting-contact relationship
        conn.execute("""
            INSERT INTO crm_meeting_contacts
            (meeting_id, contact_id)
            VALUES (?, ?)
        """, ("SYNC_TEST_ONLY", contact_id))

        # Stage an approved non-demo note
        cursor = conn.execute("""
            INSERT INTO crm_notes
            (meeting_id, contact_id, note_text,
             review_status, sync_status, is_demo)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "SYNC_TEST_ONLY",
            contact_id,
            "TEST ONLY - Approved fictional meeting note.",
            "approved",
            "not_synced",
            0
        ))

        test_note_id = cursor.lastrowid
        conn.commit()

    # Temporarily point the sync function to the test database
    original_path = sync_hubspot_notes.DB_PATH
    sync_hubspot_notes.DB_PATH = test_db

    try:
        result = sync_hubspot_notes.sync_note(
            test_note_id,
            dry_run=True
        )
        print("Test result:", result)

        assert result.startswith("ELIGIBLE:"), result

    finally:
        sync_hubspot_notes.DB_PATH = original_path

print("Eligibility test: PASS")
print("Temporary database removed.")
print("Real SQLite database unchanged.")
print("No HubSpot API requests made.")
