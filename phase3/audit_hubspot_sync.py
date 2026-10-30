
import os
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

import requests
from dotenv import load_dotenv


# --------------------------------------------------
# 1. Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "phase3" / "meeting_intelligence.db"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("HUBSPOT_SERVICE_KEY")
API_BASE = "https://api.hubapi.com"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}"
} if API_KEY else {}


# --------------------------------------------------
# 2. Load synchronization records
# --------------------------------------------------

def load_records():
    records = []

    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row

        for row in conn.execute("""
            SELECT
                note_id AS record_id,
                meeting_id,
                review_status,
                sync_status,
                is_demo,
                hubspot_note_id AS hubspot_id
            FROM crm_notes
        """):
            records.append({
                **dict(row),
                "type": "note"
            })

        for row in conn.execute("""
            SELECT
                task_id AS record_id,
                meeting_id,
                review_status,
                sync_status,
                is_demo,
                hubspot_task_id AS hubspot_id
            FROM crm_tasks
        """):
            records.append({
                **dict(row),
                "type": "task"
            })

    return records


# --------------------------------------------------
# 3. Verify remote HubSpot records
# --------------------------------------------------

def check_hubspot_record(record_type, hubspot_id):

    if not API_KEY:
        return "NOT_CHECKED - Missing API key"

    endpoint = "notes" if record_type == "note" else "tasks"

    try:
        response = requests.get(
            f"{API_BASE}/crm/v3/objects/"
            f"{endpoint}/{hubspot_id}",
            headers=HEADERS,
            timeout=20
        )

        if response.status_code == 200:
            return "VERIFIED"

        if response.status_code == 404:
            return "NOT_FOUND"

        if response.status_code in (401, 403):
            return "ACCESS_ERROR"

        if response.status_code == 429:
            return "RATE_LIMITED"

        return f"HTTP_{response.status_code}"

    except requests.RequestException:
        return "NETWORK_ERROR"


# --------------------------------------------------
# 4. Audit records
# --------------------------------------------------

def audit_record(record):
    issues = []

    sync_status = record["sync_status"]
    remote_id = record["hubspot_id"]
    is_demo = bool(record["is_demo"])

    if sync_status == "needs_review":
        issues.append(
            "API outcome uncertain - manual reconciliation required"
        )

    if sync_status == "syncing":
        issues.append(
            "Synchronization in progress or interrupted"
        )

    if sync_status == "synced" and not remote_id:
        issues.append(
            "Marked synced but HubSpot ID missing"
        )

    if sync_status == "not_synced" and remote_id:
        issues.append(
            "HubSpot ID exists but status says not_synced"
        )

    if is_demo and sync_status == "synced":
        issues.append(
            "Demo record marked synced - investigate"
        )

    allowed_statuses = {
        "not_synced",
        "syncing",
        "synced",
        "needs_review"
    }

    if sync_status not in allowed_statuses:
        issues.append(
            f"Unexpected synchronization status: {sync_status}"
        )

    remote_check = "NOT_APPLICABLE"

    if remote_id:
        remote_check = check_hubspot_record(
            record["type"],
            remote_id
        )

        if remote_check == "NOT_FOUND":
            issues.append(
                "Saved HubSpot record not found"
            )

        elif remote_check != "VERIFIED":
            issues.append(
                f"Remote verification incomplete: {remote_check}"
            )

    return issues, remote_check


# --------------------------------------------------
# 5. Main audit
# --------------------------------------------------

def main():
    records = load_records()

    print("=" * 55)
    print("MEETING INTELLIGENCE - HUBSPOT SYNC AUDIT")
    print("=" * 55)

    print("\nTotal CRM records:", len(records))

    note_count = sum(
        r["type"] == "note" for r in records
    )

    task_count = sum(
        r["type"] == "task" for r in records
    )

    print("Notes:", note_count)
    print("Tasks:", task_count)

    print("\n--- SYNC STATUS SUMMARY ---")

    for record_type in ("note", "task"):
        counts = Counter(
            r["sync_status"]
            for r in records
            if r["type"] == record_type
        )

        print(f"\n{record_type.upper()}S")

        for status in (
            "not_synced",
            "syncing",
            "synced",
            "needs_review"
        ):
            print(
                f"  {status}: {counts.get(status, 0)}"
            )

    print("\n--- RECORD AUDIT ---")

    issue_count = 0
    verified_count = 0

    for record in records:
        issues, remote_check = audit_record(record)

        label = (
            f"{record['type'].title()} "
            f"{record['record_id']}"
        )

        print(f"\n{label}")
        print("  Meeting:", record["meeting_id"])
        print("  Review:", record["review_status"])
        print("  Sync:", record["sync_status"])
        print("  Demo:", bool(record["is_demo"]))
        print("  HubSpot ID:", record["hubspot_id"])
        print("  Remote check:", remote_check)

        if remote_check == "VERIFIED":
            verified_count += 1

        if issues:
            issue_count += 1

            for issue in issues:
                print("  ATTENTION:", issue)

        else:
            print("  Audit: OK")

    print("\n--- FINAL SUMMARY ---")

    print("Records checked:", len(records))
    print("Records requiring attention:", issue_count)
    print("Remote records verified:", verified_count)

    if issue_count:
        print(
            "\nSome records require manual investigation."
        )
        print(
            "Do not automatically retry uncertain syncs."
        )
    else:
        print("\nSYNC AUDIT: PASS")

    print("\nNo HubSpot writes performed.")
    print("No SQLite records modified.")


if __name__ == "__main__":
    main()
