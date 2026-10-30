
import os
import sqlite3
import requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "phase3" / "meeting_intelligence.db"
BACKUP_PATH = BASE_DIR / "phase3" / "meeting_intelligence_before_hubspot_import.db"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("HUBSPOT_SERVICE_KEY")

if not API_KEY:
    raise ValueError("HUBSPOT_SERVICE_KEY missing from .env")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


def fetch_records(object_type, properties):
    records = []
    after = None

    while True:
        params = {
            "limit": 100,
            "properties": ",".join(properties)
        }

        if after:
            params["after"] = after

        response = requests.get(
            f"https://api.hubapi.com/crm/objects/2026-03/{object_type}",
            headers=HEADERS,
            params=params,
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

        records.extend(data.get("results", []))

        after = (
            data.get("paging", {})
            .get("next", {})
            .get("after")
        )

        if not after:
            break

    return records


def normalize(value):
    return (value or "").strip().lower()


if not DB_PATH.exists():
    raise FileNotFoundError(f"SQLite database not found: {DB_PATH}")


# Fetch HubSpot data before writing to SQLite
companies = fetch_records("companies", ["name", "domain"])
contacts = fetch_records(
    "contacts", ["email", "firstname", "lastname"]
)


# Create a database backup before importing
if not BACKUP_PATH.exists():
    with sqlite3.connect(DB_PATH) as source:
        with sqlite3.connect(BACKUP_PATH) as backup:
            source.backup(backup)

    print("Database backup created.")


companies_added = 0
contacts_added = 0
records_skipped = 0

with sqlite3.connect(DB_PATH) as conn:

    for company in companies:
        props = company.get("properties") or {}

        name = (props.get("name") or "").strip()
        domain = normalize(props.get("domain"))
        hubspot_id = str(company["id"])

        if not name or not domain or domain == "example.com":
            records_skipped += 1
            continue

        existing = conn.execute("""
            SELECT company_id
            FROM crm_companies
            WHERE hubspot_company_id = ?
               OR LOWER(TRIM(domain)) = ?
            LIMIT 1
        """, (hubspot_id, domain)).fetchone()

        if existing:
            records_skipped += 1
            continue

        conn.execute("""
            INSERT INTO crm_companies
            (company_name, domain, hubspot_company_id)
            VALUES (?, ?, ?)
        """, (name, domain, hubspot_id))

        companies_added += 1

    for contact in contacts:
        props = contact.get("properties") or {}

        email = normalize(props.get("email"))
        hubspot_id = str(contact["id"])

        if not email or email.endswith("@example.com"):
            records_skipped += 1
            continue

        first_name = (props.get("firstname") or "").strip()
        last_name = (props.get("lastname") or "").strip()
        full_name = f"{first_name} {last_name}".strip() or email

        existing = conn.execute("""
            SELECT contact_id
            FROM crm_contacts
            WHERE hubspot_contact_id = ?
               OR LOWER(TRIM(email)) = ?
            LIMIT 1
        """, (hubspot_id, email)).fetchone()

        if existing:
            records_skipped += 1
            continue

        conn.execute("""
            INSERT INTO crm_contacts
            (full_name, email, hubspot_contact_id)
            VALUES (?, ?, ?)
        """, (full_name, email, hubspot_id))

        contacts_added += 1

    conn.commit()

    print("\n=== HUBSPOT IMPORT RESULTS ===")
    print("New companies imported:", companies_added)
    print("New contacts imported:", contacts_added)
    print("Records skipped:", records_skipped)

    print(
        "Total SQLite companies:",
        conn.execute("SELECT COUNT(*) FROM crm_companies").fetchone()[0]
    )
    print(
        "Total SQLite contacts:",
        conn.execute("SELECT COUNT(*) FROM crm_contacts").fetchone()[0]
    )
    print(
        "Existing meetings:",
        conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
    )
    print(
        "Existing intelligence items:",
        conn.execute("SELECT COUNT(*) FROM meeting_items").fetchone()[0]
    )

print("\nHubSpot-to-SQLite import completed.")
print("No HubSpot records were modified.")
