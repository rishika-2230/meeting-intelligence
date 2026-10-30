
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import requests
from dotenv import load_dotenv

import sync_hubspot_notes
import sync_hubspot_tasks


# -------------------------------------------
# 1. Configuration
# -------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
REAL_DB = BASE_DIR / "phase3" / "meeting_intelligence.db"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("HUBSPOT_SERVICE_KEY")

if not API_KEY:
    raise ValueError("HUBSPOT_SERVICE_KEY missing")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}"
}

API = "https://api.hubapi.com"


def get_hubspot(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()
    return response.json()


print("=" * 55)
print("FINAL HUBSPOT INTEGRATION VERIFICATION")
print("=" * 55)


# -------------------------------------------
# 2. Work with an isolated SQLite copy
# -------------------------------------------

with tempfile.TemporaryDirectory() as folder:

    test_db = Path(folder) / "final_integration_test.db"

    with closing(sqlite3.connect(REAL_DB)) as source:
        with closing(sqlite3.connect(test_db)) as target:
            source.backup(target)

    with closing(sqlite3.connect(test_db)) as conn:
        conn.row_factory = sqlite3.Row

        companies = [
            dict(row)
            for row in conn.execute("""
                SELECT company_id, hubspot_company_id
                FROM crm_companies
                WHERE hubspot_company_id IS NOT NULL
            """)
        ]

        contacts = [
            dict(row)
            for row in conn.execute("""
                SELECT
                    c.contact_id,
                    c.hubspot_contact_id,
                    co.hubspot_company_id
                        AS linked_company_id
                FROM crm_contacts c
                LEFT JOIN crm_companies co
                    ON c.company_id = co.company_id
                WHERE c.hubspot_contact_id IS NOT NULL
            """)
        ]

        notes = [
            dict(row)
            for row in conn.execute("""
                SELECT note_id, review_status, sync_status,
                       is_demo, hubspot_note_id
                FROM crm_notes
            """)
        ]

        tasks = [
            dict(row)
            for row in conn.execute("""
                SELECT task_id, review_status, sync_status,
                       is_demo, hubspot_task_id
                FROM crm_tasks
            """)
        ]

    print("\nSQLite database copy: CREATED")
    print("Imported HubSpot contacts:", len(contacts))
    print("Imported HubSpot companies:", len(companies))
    print("CRM notes:", len(notes))
    print("CRM tasks:", len(tasks))

    assert contacts, "No imported HubSpot contacts"
    assert companies, "No imported HubSpot companies"

    # ---------------------------------------
    # 3. Verify imported HubSpot companies
    # ---------------------------------------

    for company in companies:
        remote_id = str(company["hubspot_company_id"])

        result = get_hubspot(
            f"{API}/crm/v3/objects/companies/{remote_id}"
        )

        assert str(result["id"]) == remote_id

    print("\nHubSpot company verification: PASS")

    # ---------------------------------------
    # 4. Verify contacts and associations
    # ---------------------------------------

    association_checks = 0

    for contact in contacts:
        contact_id = str(contact["hubspot_contact_id"])

        result = get_hubspot(
            f"{API}/crm/v3/objects/contacts/{contact_id}"
        )

        assert str(result["id"]) == contact_id

        if contact["linked_company_id"]:
            associations = get_hubspot(
                f"{API}/crm/v4/objects/contacts/"
                f"{contact_id}/associations/companies"
            )

            remote_company_ids = {
                str(item["toObjectId"])
                for item in associations.get("results", [])
            }

            assert (
                str(contact["linked_company_id"])
                in remote_company_ids
            ), "Contact/company association mismatch"

            association_checks += 1

    print("HubSpot contact verification: PASS")
    print("Contact/company associations verified:",
          association_checks)

    # ---------------------------------------
    # 5. Validate local synchronization state
    # ---------------------------------------

    for record in notes + tasks:
        status = record["sync_status"]

        assert status in {
            "not_synced",
            "syncing",
            "synced",
            "needs_review"
        }, "Unexpected sync status"

        assert status not in {
            "syncing",
            "needs_review"
        }, "Unresolved synchronization state"

        remote_id = (
            record.get("hubspot_note_id")
            or record.get("hubspot_task_id")
        )

        if status == "synced":
            assert remote_id, "Synced record missing HubSpot ID"

        if status == "not_synced":
            assert not remote_id, (
                "Unsynced record unexpectedly has HubSpot ID"
            )

        if record["is_demo"]:
            assert status != "synced", (
                "Historical demo record marked synced"
            )

    print("Synchronization state verification: PASS")

    # ---------------------------------------
    # 6. Test review-to-sync integration
    # ---------------------------------------

    original_notes_path = sync_hubspot_notes.DB_PATH
    original_tasks_path = sync_hubspot_tasks.DB_PATH

    sync_hubspot_notes.DB_PATH = test_db
    sync_hubspot_tasks.DB_PATH = test_db

    approved_checked = 0

    try:
        # No external HTTP requests are permitted
        # during synchronization dry runs.
        with patch(
            "requests.get",
            side_effect=AssertionError(
                "Unexpected HTTP GET in dry run"
            )
        ), patch(
            "requests.post",
            side_effect=AssertionError(
                "Unexpected HTTP POST in dry run"
            )
        ), patch(
            "requests.delete",
            side_effect=AssertionError(
                "Unexpected HTTP DELETE in dry run"
            )
        ):

            for note in notes:
                if note["review_status"] != "approved":
                    continue

                result = sync_hubspot_notes.sync_note(
                    note["note_id"],
                    dry_run=True
                )

                print(
                    f"Note {note['note_id']}: {result}"
                )

                assert result.startswith(
                    ("BLOCKED:", "ELIGIBLE:")
                ), result

                if note["is_demo"]:
                    assert result.startswith("BLOCKED:")

                approved_checked += 1

            for task in tasks:
                if task["review_status"] != "approved":
                    continue

                result = sync_hubspot_tasks.sync_task(
                    task["task_id"],
                    dry_run=True
                )

                print(
                    f"Task {task['task_id']}: {result}"
                )

                assert result.startswith(
                    ("BLOCKED:", "ELIGIBLE:")
                ), result

                if task["is_demo"]:
                    assert result.startswith("BLOCKED:")

                approved_checked += 1

    finally:
        sync_hubspot_notes.DB_PATH = original_notes_path
        sync_hubspot_tasks.DB_PATH = original_tasks_path

    print("\nHuman-review integration: PASS")
    print("Approved records checked:", approved_checked)
    print("Dry-run HTTP write protection: PASS")

    # Verify no synchronization states changed.
    with closing(sqlite3.connect(test_db)) as conn:
        current_notes = conn.execute("""
            SELECT note_id, review_status, sync_status,
                   is_demo, hubspot_note_id
            FROM crm_notes
        """).fetchall()

        current_tasks = conn.execute("""
            SELECT task_id, review_status, sync_status,
                   is_demo, hubspot_task_id
            FROM crm_tasks
        """).fetchall()

    expected_notes = [
        tuple(record.values()) for record in notes
    ]
    expected_tasks = [
        tuple(record.values()) for record in tasks
    ]

    assert current_notes == expected_notes
    assert current_tasks == expected_tasks

    print("SQLite synchronization states unchanged: PASS")

print("\n" + "=" * 55)
print("FINAL HUBSPOT INTEGRATION TEST: PASS")
print("=" * 55)
print("Temporary database removed.")
print("Original SQLite database unchanged.")
print("No HubSpot records created, updated, or archived.")
