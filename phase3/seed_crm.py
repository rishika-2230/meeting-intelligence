
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"

with sqlite3.connect(DB_PATH) as conn:

    # Create a demo company only if it doesn't exist
    company = conn.execute(
        "SELECT company_id FROM crm_companies WHERE domain = ?",
        ("example.com",)
    ).fetchone()

    if company:
        company_id = company[0]
    else:
        cursor = conn.execute(
            """
            INSERT INTO crm_companies (company_name, domain)
            VALUES (?, ?)
            """,
            ("DEMO - Example Analytics", "example.com")
        )
        company_id = cursor.lastrowid

    # Create a demo contact only if it doesn't exist
    contact = conn.execute(
        "SELECT contact_id FROM crm_contacts WHERE email = ?",
        ("demo.contact@example.com",)
    ).fetchone()

    if contact:
        contact_id = contact[0]
    else:
        cursor = conn.execute(
            """
            INSERT INTO crm_contacts (full_name, email, company_id)
            VALUES (?, ?, ?)
            """,
            ("Demo Contact", "demo.contact@example.com", company_id)
        )
        contact_id = cursor.lastrowid

    conn.commit()

    print("Demo company ID:", company_id)
    print("Demo contact ID:", contact_id)

    print(
        "Total CRM companies:",
        conn.execute("SELECT COUNT(*) FROM crm_companies").fetchone()[0]
    )
    print(
        "Total CRM contacts:",
        conn.execute("SELECT COUNT(*) FROM crm_contacts").fetchone()[0]
    )

print("CRM demo data ready.")
