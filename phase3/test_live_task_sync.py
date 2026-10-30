
import json
import os
import sqlite3
import tempfile
import uuid

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

import sync_hubspot_tasks


BASE_DIR = Path(__file__).resolve().parent.parent
PHASE3_DIR = BASE_DIR / "phase3"
REAL_DB = PHASE3_DIR / "meeting_intelligence.db"
CHECKPOINT = PHASE3_DIR / "hubspot_task_sync_test.json"

load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("HUBSPOT_SERVICE_KEY")
if not api_key:
    raise ValueError("HUBSPOT_SERVICE_KEY missing")

if CHECKPOINT.exists():
    raise RuntimeError(
        "Previous test records may still exist. "
        "Do not run this test again before cleanup."
    )

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

API = "https://api.hubapi.com"


def save_checkpoint(data):
    CHECKPOINT.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )


# Check association support BEFORE creating test records.
labels_response = requests.get(
    f"{API}/crm/v4/associations/tasks/contacts/labels",
    headers=headers,
    timeout=30
)
labels_response.raise_for_status()

labels = labels_response.json().get("results", [])
default_label = next(
    (
        item for item in labels
        if item.get("category") == "HUBSPOT_DEFINED"
        and item.get("label") is None
    ),
    None
)

if not default_label:
    raise RuntimeError(
        "Default task/contact association not available."
    )

print("Association configuration: VERIFIED")


# Create an isolated, clearly labeled HubSpot test contact.
unique_code = uuid.uuid4().hex[:12]
test_email = f"mi-sync-test-{unique_code}@example.com"

contact_response = requests.post(
    f"{API}/crm/v3/objects/contacts",
    headers=headers,
    json={
        "properties": {
            "email": test_email,
            "firstname": "TEST ONLY",
            "lastname": "Meeting Intelligence Integration"
        }
    },
    timeout=30
)
contact_response.raise_for_status()

hubspot_contact_id = str(contact_response.json()["id"])

checkpoint_data = {
    "test_contact_id": hubspot_contact_id,
    "test_contact_email": test_email,
    "test_task_id": None
}
save_checkpoint(checkpoint_data)

print("Temporary HubSpot contact created:", hubspot_contact_id)


# Build a test in a temporary COPY of the SQLite database.
with tempfile.TemporaryDirectory() as folder:
    test_db = Path(folder) / "test_live_task_sync.db"

    with closing(sqlite3.connect(REAL_DB)) as source:
        with closing(sqlite3.connect(test_db)) as destination:
            source.backup(destination)

    with closing(sqlite3.connect(test_db)) as conn:
        # Meeting ID is used only as test metadata.
        meeting = conn.execute(
            "SELECT meeting_id FROM meetings LIMIT 1"
        ).fetchone()

        if meeting is None:
            raise RuntimeError("No meeting available in test copy")

        meeting_id = meeting[0]

        cursor = conn.execute("""
            INSERT INTO crm_contacts
                (full_name, email, hubspot_contact_id)
            VALUES (?, ?, ?)
        """, (
            "TEST ONLY - Meeting Intelligence",
            test_email,
            hubspot_contact_id
        ))
        local_contact_id = cursor.lastrowid

        conn.execute("""
            INSERT OR IGNORE INTO crm_meeting_contacts
                (meeting_id, contact_id)
            VALUES (?, ?)
        """, (meeting_id, local_contact_id))

        future_date = (
            datetime.now(timezone.utc).date()
            + timedelta(days=7)
        ).isoformat()

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
            local_contact_id,
            "TEST ONLY - Meeting Intelligence Live Task Sync",
            "Integration Test",
            future_date,
            "open",
            "approved",
            "not_synced",
            0
        ))
        local_task_id = cursor.lastrowid
        conn.commit()

    original_db_path = sync_hubspot_tasks.DB_PATH
    sync_hubspot_tasks.DB_PATH = test_db

    try:
        dry_result = sync_hubspot_tasks.sync_task(
            local_task_id,
            dry_run=True
        )
        print("Dry-run result:", dry_result)

        assert dry_result.startswith("ELIGIBLE:"), dry_result

        print("Executing controlled live synchronization...")

        live_result = sync_hubspot_tasks.sync_task(
            local_task_id,
            dry_run=False
        )
        print("Live result:", live_result)

        assert live_result.startswith("SYNCED:"), live_result

        with closing(sqlite3.connect(test_db)) as conn:
            saved = conn.execute("""
                SELECT sync_status, hubspot_task_id
                FROM crm_tasks
                WHERE task_id = ?
            """, (local_task_id,)).fetchone()

        assert saved is not None
        assert saved[0] == "synced"
        assert saved[1]

        hubspot_task_id = str(saved[1])

        checkpoint_data["test_task_id"] = hubspot_task_id
        save_checkpoint(checkpoint_data)

        print("SQLite synchronization status: VERIFIED")
        print("Temporary HubSpot task ID:", hubspot_task_id)

        # Verify the task actually exists in HubSpot.
        task_response = requests.get(
            f"{API}/crm/v3/objects/tasks/{hubspot_task_id}",
            headers=headers,
            params={"properties": "hs_task_subject"},
            timeout=30
        )
        task_response.raise_for_status()

        subject = task_response.json().get(
            "properties", {}
        ).get("hs_task_subject", "")

        assert subject == (
            "TEST ONLY - Meeting Intelligence Live Task Sync"
        ), "Unexpected HubSpot task subject"

        # Verify the remote task/contact association.
        association_response = requests.get(
            f"{API}/crm/v4/objects/tasks/"
            f"{hubspot_task_id}/associations/contacts",
            headers=headers,
            timeout=30
        )
        association_response.raise_for_status()

        associated_contacts = {
            str(item["toObjectId"])
            for item in association_response.json().get(
                "results", []
            )
        }

        assert hubspot_contact_id in associated_contacts, (
            "Task was created, but expected contact "
            "association was not verified."
        )

        print("HubSpot task creation: VERIFIED")
        print("HubSpot contact association: VERIFIED")
        print("LIVE SYNCHRONIZATION TEST: PASS")

    finally:
        sync_hubspot_tasks.DB_PATH = original_db_path

print("Temporary SQLite database removed.")
print("Original SQLite database unchanged.")
print("Test record IDs saved for Step 32 cleanup.")
