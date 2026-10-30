
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"

with sqlite3.connect(DB_PATH) as conn:
    conn.row_factory = sqlite3.Row

    notes = conn.execute("""
        SELECT
            n.note_id,
            n.meeting_id,
            n.review_status,
            n.sync_status,
            n.is_demo,
            n.hubspot_note_id,
            c.hubspot_contact_id,
            co.hubspot_company_id
        FROM crm_notes n
        LEFT JOIN crm_contacts c
            ON n.contact_id = c.contact_id
        LEFT JOIN crm_companies co
            ON n.company_id = co.company_id
        ORDER BY n.note_id
    """).fetchall()

    eligible = 0

    for note in notes:
        reasons = []

        if note["review_status"] != "approved":
            reasons.append("Not approved")

        if note["is_demo"]:
            reasons.append("Historical demo note")

        if note["sync_status"] != "not_synced":
            reasons.append("Not in unsynced state")

        if note["hubspot_note_id"]:
            reasons.append("Already linked to HubSpot")

        if not (
            note["hubspot_contact_id"]
            or note["hubspot_company_id"]
        ):
            reasons.append("No verified HubSpot destination")

        print("\nNote ID:", note["note_id"])
        print("Meeting:", note["meeting_id"])

        if reasons:
            print("Eligible: NO")
            print("Reasons:", ", ".join(reasons))
        else:
            print("Eligible: YES")
            eligible += 1

    print("\nNotes checked:", len(notes))
    print("Eligible for synchronization:", eligible)
    print("No database changes or HubSpot requests made.")
