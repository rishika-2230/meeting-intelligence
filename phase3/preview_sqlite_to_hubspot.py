
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

API_BASE = "https://api.hubapi.com/crm/objects/2026-03"


def get_hubspot_record(object_type, record_id, properties):
    response = requests.get(
        f"{API_BASE}/{object_type}/{record_id}",
        headers=headers,
        params={"properties": ",".join(properties)},
        timeout=30
    )
    response.raise_for_status()
    return response.json().get("properties") or {}


def clean(value):
    return (value or "").strip().casefold()


changes = 0

with sqlite3.connect(DB_PATH) as conn:
    contacts = conn.execute("""
        SELECT contact_id, full_name, email, hubspot_contact_id
        FROM crm_contacts
        WHERE hubspot_contact_id IS NOT NULL
    """).fetchall()

    companies = conn.execute("""
        SELECT company_id, company_name, domain, hubspot_company_id
        FROM crm_companies
        WHERE hubspot_company_id IS NOT NULL
    """).fetchall()

print("=== SQLITE TO HUBSPOT SYNC PREVIEW ===")

for local_id, name, email, remote_id in contacts:
    remote = get_hubspot_record(
        "contacts", remote_id,
        ["email", "firstname", "lastname"]
    )

    remote_name = " ".join(filter(None, [
        remote.get("firstname"),
        remote.get("lastname")
    ]))

    differences = []

    if clean(email) != clean(remote.get("email")):
        differences.append("email")

    if clean(name) != clean(remote_name):
        differences.append("name")

    print(
        f"Contact {local_id}:",
        "Differences: " + ", ".join(differences)
        if differences else "Already matches"
    )

    changes += bool(differences)

for local_id, name, domain, remote_id in companies:
    remote = get_hubspot_record(
        "companies", remote_id,
        ["name", "domain"]
    )

    differences = []

    if clean(name) != clean(remote.get("name")):
        differences.append("company name")

    if clean(domain) != clean(remote.get("domain")):
        differences.append("domain")

    print(
        f"Company {local_id}:",
        "Differences: " + ", ".join(differences)
        if differences else "Already matches"
    )

    changes += bool(differences)

print("\nContacts checked:", len(contacts))
print("Companies checked:", len(companies))
print("Records with differences:", changes)
print("No records modified in either system.")
