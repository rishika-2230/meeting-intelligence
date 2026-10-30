
import os
import sqlite3
import requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "phase3" / "meeting_intelligence.db"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("HUBSPOT_SERVICE_KEY")

if not API_KEY:
    raise ValueError("HUBSPOT_SERVICE_KEY missing")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


def fetch_records(object_type, properties):
    results = []
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
        results.extend(data.get("results", []))

        after = (
            data.get("paging", {})
            .get("next", {})
            .get("after")
        )

        if not after:
            break

    return results


def normalize(value):
    return (value or "").strip().lower()


contacts = fetch_records(
    "contacts", ["email", "firstname", "lastname"]
)

companies = fetch_records(
    "companies", ["name", "domain"]
)

hubspot_emails = {
    normalize(r.get("properties", {}).get("email")): r["id"]
    for r in contacts
    if normalize(r.get("properties", {}).get("email"))
}

hubspot_domains = {
    normalize(r.get("properties", {}).get("domain")): r["id"]
    for r in companies
    if normalize(r.get("properties", {}).get("domain"))
}

with sqlite3.connect(DB_PATH) as conn:
    local_contacts = conn.execute("""
        SELECT email FROM crm_contacts
        WHERE email IS NOT NULL
        AND LOWER(email) != 'demo.contact@example.com'
    """).fetchall()

    local_companies = conn.execute("""
        SELECT domain FROM crm_companies
        WHERE domain IS NOT NULL
        AND company_name NOT LIKE 'DEMO - %'
    """).fetchall()

contact_matches = sum(
    normalize(email) in hubspot_emails
    for (email,) in local_contacts
)

company_matches = sum(
    normalize(domain) in hubspot_domains
    for (domain,) in local_companies
)

print("HubSpot contacts:", len(contacts))
print("HubSpot companies:", len(companies))
print("Local non-demo contacts:", len(local_contacts))
print("Local non-demo companies:", len(local_companies))
print("Contact matches:", contact_matches)
print("Company matches:", company_matches)
print("Matching test complete. No records modified.")
