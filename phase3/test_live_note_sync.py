
import json
import os
import sqlite3
import tempfile
import uuid

from contextlib import closing
from pathlib import Path

import requests
from dotenv import load_dotenv

import sync_hubspot_notes


BASE_DIR = Path(__file__).resolve().parent.parent
PHASE3_DIR = BASE_DIR / "phase3"
REAL_DB = PHASE3_DIR / "meeting_intelligence.db"
CHECKPOINT = PHASE3_DIR / "hubspot_note_sync_test.json"

load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("HUBSPOT_SERVICE_KEY")

if not api_key:
    raise ValueError("HUBSPOT_SERVICE_KEY missing")

if CHECKPOINT.exists():
    raise RuntimeError(
        "A previous live note test may have records "
        "requiring cleanup. Do not run again."
    )

API = "https://api.hubapi.com"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}


def save_checkpoint(data):
    CHECKPOINT.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )


# Verify association support before creating anything.
response = requests.get(
    f"{API}/crm/v4/associations/notes/contacts/labels",
    headers=headers,
    timeout=30
)
response.raise_for_status()

default_association = next(
    (
        item
        for item in response.json().get("results", [])
        if item.get("category") == "HUBSPOT_DEFINED"
        and item.get("label") is None
    ),
    None
)

if not default_association:
    raise RuntimeError(
        "Default note/contact association unavailable"
    )

print("Note/contact association: VERIFIED")


# Create a temporary HubSpot contact.
unique_code = uuid.uuid4().hex[:12]
test_email = f"mi-note-test-{unique_code}@example.com"

response = requests.post(
    f"{API}/crm/v3/objects/contacts",
    headers=headers,
    json={
        "properties": {
            "email": test_email,
            "firstname": "TEST ONLY",
            "lastname": "MI Note Integration"
        }
    },
    timeout=30
)
response.raise_for_status()

hubspot_contact_id = str(response.json()["id"])

checkpoint = {
    "test_contact_id": hubspot_contact_id,
    "test_contact_email": test_email,
    "test_note_id": None,
    "test_note_body": (
        "TEST ONLY - Meeting Intelligence live note "
        "synchronization. Fictional data; safe to archive."
    )
}
save_checkpoint(checkpoint)

print("Temporary HubSpot contact:", hubspot_contact_id)


# Work exclusively in a temporary copy of SQLite.
with tempfile.TemporaryDirectory() as folder:

    test_db = Path(folder) / "test_live_note_sync.db"

    with closing(sqlite3.connect(REAL_DB)) as source:
        with closing(sqlite3.connect(test_db)) as target:
            source.backup(target)

    with closing(sqlite3.connect(test_db)) as conn:

        # Create a fictional meeting.
        meeting_id = f"NOTE_TEST_{unique_code}"

        conn.execute("""
            INSERT INTO meetings (
                meeting_id,
                summary,
                requires_human_review
            )
            VALUES (?, ?, ?)
        """, (
            meeting_id,
            "Fictional integration-test meeting.",
            0
        ))

        # Match temporary contact with fictional meeting.
        cursor = conn.execute("""
            INSERT INTO crm_contacts (
                full_name,
                email,
                hubspot_contact_id
            )
            VALUES (?, ?, ?)
        """, (
            "TEST ONLY - MI Note Integration",
            test_email,
            hubspot_contact_id
        ))

        contact_id = cursor.lastrowid

        conn.execute("""
            INSERT INTO crm_meeting_contacts (
                meeting_id,
                contact_id
            )
            VALUES (?, ?)
        """, (
            meeting_id,
            contact_id
        ))

        # Approved, non-demo note for this test only.
        cursor = conn.execute("""
            INSERT INTO crm_notes (
                meeting_id,
                contact_id,
                note_text,
                review_status,
                sync_status,
                is_demo
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            meeting_id,
            contact_id,
            checkpoint["test_note_body"],
            "approved",
            "not_synced",
            0
        ))

        local_note_id = cursor.lastrowid
        conn.commit()

    original_path = sync_hubspot_notes.DB_PATH
    sync_hubspot_notes.DB_PATH = test_db

    try:
        # Check eligibility without writing.
        dry_result = sync_hubspot_notes.sync_note(
            local_note_id,
            dry_run=True
        )

        print("Dry-run result:", dry_result)

        assert dry_result.startswith("ELIGIBLE:"), (
            dry_result
        )

        # Execute one controlled live sync.
        print("Executing live note synchronization...")

        live_result = sync_hubspot_notes.sync_note(
            local_note_id,
            dry_run=False
        )

        print("Live result:", live_result)

        # Read back the local synchronization result.
        with closing(sqlite3.connect(test_db)) as conn:
            saved = conn.execute("""
                SELECT sync_status, hubspot_note_id
                FROM crm_notes
                WHERE note_id = ?
            """, (local_note_id,)).fetchone()

        if saved and saved[1]:
            checkpoint["test_note_id"] = str(saved[1])
            save_checkpoint(checkpoint)

        assert live_result.startswith("SYNCED:"), live_result
        assert saved is not None
        assert saved[0] == "synced"
        assert saved[1]

        hubspot_note_id = str(saved[1])

        print("SQLite synchronization status: VERIFIED")
        print("Temporary HubSpot note ID:", hubspot_note_id)

        # Verify the note content in HubSpot.
        response = requests.get(
            f"{API}/crm/v3/objects/notes/{hubspot_note_id}",
            headers=headers,
            params={"properties": "hs_note_body"},
            timeout=30
        )
        response.raise_for_status()

        remote_body = response.json().get(
            "properties", {}
        ).get("hs_note_body", "")

        assert remote_body == checkpoint["test_note_body"], (
            "HubSpot note content mismatch"
        )

        print("HubSpot note creation: VERIFIED")

        # Verify that the correct contact is associated.
        response = requests.get(
            f"{API}/crm/v4/objects/notes/"
            f"{hubspot_note_id}/associations/contacts",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()

        associated_contacts = {
            str(item["toObjectId"])
            for item in response.json().get("results", [])
        }

        assert hubspot_contact_id in associated_contacts, (
            "Expected contact association not found"
        )

        print("HubSpot contact association: VERIFIED")
        print("LIVE NOTE SYNCHRONIZATION TEST: PASS")

    finally:
        sync_hubspot_notes.DB_PATH = original_path

print("Temporary SQLite database removed.")
print("Original SQLite database unchanged.")
print("Test record IDs saved for Step 34 cleanup.")
