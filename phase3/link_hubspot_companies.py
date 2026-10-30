
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"

HUBSPOT_COMPANY_ID = "356543377107"
CONTACT_IDS = (2, 3)

with sqlite3.connect(DB_PATH) as conn:
    conn.execute("PRAGMA foreign_keys = ON")

    company = conn.execute("""
        SELECT company_id
        FROM crm_companies
        WHERE hubspot_company_id = ?
    """, (HUBSPOT_COMPANY_ID,)).fetchone()

    if not company:
        raise ValueError("Matching HubSpot company not found in SQLite")

    company_id = company[0]

    # Verify every contact before changing anything.
    for contact_id in CONTACT_IDS:
        contact = conn.execute("""
            SELECT hubspot_contact_id, company_id
            FROM crm_contacts
            WHERE contact_id = ?
        """, (contact_id,)).fetchone()

        if not contact or not contact[0]:
            raise ValueError(f"Contact {contact_id} is not linked to HubSpot")

        if contact[1] is not None and contact[1] != company_id:
            raise ValueError(f"Contact {contact_id} has a conflicting company")

    for contact_id in CONTACT_IDS:
        conn.execute("""
            UPDATE crm_contacts
            SET company_id = ?
            WHERE contact_id = ?
        """, (company_id, contact_id))

    conn.commit()

    print("Contact-company relationships saved successfully.")

    for contact_id, linked_company in conn.execute("""
        SELECT contact_id, company_id
        FROM crm_contacts
        WHERE contact_id IN (2, 3)
        ORDER BY contact_id
    """):
        print(
            f"Contact {contact_id} -> Company {linked_company}"
        )

    print(
        "Total meetings:",
        conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
    )
    print(
        "Total extracted items:",
        conn.execute("SELECT COUNT(*) FROM meeting_items").fetchone()[0]
    )
