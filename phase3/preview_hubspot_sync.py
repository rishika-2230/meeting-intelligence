
import os
import sqlite3
import requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "phase3" / "meeting_intelligence.db"

load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("HUBSPOT_SERVICE_KEY")

if not api_key:
    raise ValueError("HUBSPOT_SERVICE_KEY missing")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json"
}


def get_records(object_type, properties):
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
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        records.extend(data.get("results", []))

        after = data.get("paging", {}).get("next", {}).get("after")

        if not after:
            break

    return records


contacts = get_records(
    "contacts", ["email", "firstname", "lastname"]
)

companies = get_records(
    "companies", ["name", "domain"]
)

with sqlite3.connect(DB_PATH) as conn:
    local_emails = {
        (row[0] or "").strip().lower()
        for row in conn.execute("SELECT email FROM crm_contacts")
    }

    local_domains = {
        (row[0] or "").strip().lower()
        for row in conn.execute("SELECT domain FROM crm_companies")
    }

    contact_candidates = 0
    company_candidates = 0

    for contact in contacts:
        email = (
            contact.get("properties", {}).get("email") or ""
        ).strip().lower()

        if email and email not in local_emails:
            contact_candidates += 1

    for company in companies:
        domain = (
            company.get("properties", {}).get("domain") or ""
        ).strip().lower()

        if domain and domain not in local_domains:
            company_candidates += 1

print("\n=== HUBSPOT SYNC PREVIEW ===")
print("HubSpot contacts:", len(contacts))
print("HubSpot companies:", len(companies))
print("Contacts available for import:", contact_candidates)
print("Companies available for import:", company_candidates)
print("\nPreview complete.")
print("No SQLite records modified.")
print("No HubSpot records modified.")
