
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"

with sqlite3.connect(DB_PATH) as conn:
    conn.execute("PRAGMA foreign_keys = ON")

    # Link meetings to CRM contacts
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_meeting_contacts (
            meeting_id TEXT NOT NULL,
            contact_id INTEGER NOT NULL,
            PRIMARY KEY (meeting_id, contact_id),
            FOREIGN KEY (contact_id)
                REFERENCES crm_contacts(contact_id)
        )
    """)

    # Store meeting notes for review and HubSpot synchronization
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_notes (
            note_id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT NOT NULL,
            contact_id INTEGER,
            company_id INTEGER,
            note_text TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'pending',
            sync_status TEXT NOT NULL DEFAULT 'not_synced',
            hubspot_note_id TEXT UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id)
                REFERENCES crm_contacts(contact_id),
            FOREIGN KEY (company_id)
                REFERENCES crm_companies(company_id)
        )
    """)

    # Store CRM follow-up tasks
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT NOT NULL,
            contact_id INTEGER,
            task_title TEXT NOT NULL,
            owner TEXT,
            due_date TEXT,
            task_status TEXT NOT NULL DEFAULT 'open',
            review_status TEXT NOT NULL DEFAULT 'pending',
            sync_status TEXT NOT NULL DEFAULT 'not_synced',
            hubspot_task_id TEXT UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id)
                REFERENCES crm_contacts(contact_id)
        )
    """)

    conn.commit()

    for name in (
        "crm_meeting_contacts",
        "crm_notes",
        "crm_tasks"
    ):
        count = conn.execute(
            f"SELECT COUNT(*) FROM {name}"
        ).fetchone()[0]
        print(f"{name}: {count} records")

    print(
        "Existing meetings:",
        conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
    )
    print(
        "Existing items:",
        conn.execute("SELECT COUNT(*) FROM meeting_items").fetchone()[0]
    )

print("CRM workflow tables ready.")
