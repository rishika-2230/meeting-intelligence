
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"


def valid_date(value):
    if not value:
        return False

    try:
        date.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def check_sync_eligibility():
    with sqlite3.connect(DB_PATH) as conn:

        rows = conn.execute("""
            SELECT
                t.task_id,
                t.task_title,
                t.review_status,
                t.sync_status,
                t.is_demo,
                t.due_date,
                t.hubspot_task_id,
                c.hubspot_contact_id
            FROM crm_tasks t
            LEFT JOIN crm_contacts c
                ON t.contact_id = c.contact_id
            ORDER BY t.task_id
        """).fetchall()

        eligible_count = 0

        for row in rows:
            (
                task_id,
                title,
                review_status,
                sync_status,
                is_demo,
                due_date,
                hubspot_task_id,
                hubspot_contact_id
            ) = row

            reasons = []

            if review_status != "approved":
                reasons.append("Not approved")

            if is_demo:
                reasons.append("Demo task")

            if sync_status != "not_synced" or hubspot_task_id:
                reasons.append("Already synced or ineligible sync state")

            if not hubspot_contact_id:
                reasons.append("No linked HubSpot contact")

            if not valid_date(due_date):
                reasons.append("Missing or invalid deadline")

            print("\nTask ID:", task_id)
            print("Title:", title)

            if reasons:
                print("Eligible: NO")
                print("Reasons:", ", ".join(reasons))
            else:
                print("Eligible: YES")
                eligible_count += 1

        print("\n" + "=" * 45)
        print("Tasks checked:", len(rows))
        print("Eligible for HubSpot sync:", eligible_count)
        print("No HubSpot API requests were made.")


if __name__ == "__main__":
    check_sync_eligibility()
