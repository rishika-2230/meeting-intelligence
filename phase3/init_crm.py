
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"

with sqlite3.connect(DB_PATH) as conn:
    conn.execute("PRAGMA foreign_keys = ON")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_companies (
            company_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            domain TEXT,
            hubspot_company_id TEXT UNIQUE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_contacts (
            contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE,
            company_id INTEGER,
            hubspot_contact_id TEXT UNIQUE,
            FOREIGN KEY (company_id)
                REFERENCES crm_companies(company_id)
        )
    """)

    conn.commit()

    tables = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type = 'table'
        AND name IN ('crm_companies', 'crm_contacts')
        ORDER BY name
    """).fetchall()

    print("CRM tables created successfully:")
    for table in tables:
        print("-", table[0])

    print("Existing meetings:",
          conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0])
    print("Existing items:",
          conn.execute("SELECT COUNT(*) FROM meeting_items").fetchone()[0])
