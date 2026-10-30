
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

headers = {"Authorization": f"Bearer {api_key}"}

with sqlite3.connect(DB_PATH) as conn:
    contacts = conn.execute("""
        SELECT contact_id, hubspot_contact_id
        FROM crm_contacts
        WHERE hubspot_contact_id IS NOT NULL
    """).fetchall()

    companies = {
        str(hubspot_id): local_id
        for local_id, hubspot_id in conn.execute("""
            SELECT company_id, hubspot_company_id
            FROM crm_companies
            WHERE hubspot_company_id IS NOT NULL
        """)
    }

print("Contacts to inspect:", len(contacts))

for local_contact_id, hubspot_contact_id in contacts:
    url = (
        "https://api.hubapi.com/crm/v4/objects/"
        f"contacts/{hubspot_contact_id}/associations/companies"
    )

    response = requests.get(
        url, headers=headers, timeout=30
    )

    print("\nLocal contact ID:", local_contact_id)
    print("HTTP Status:", response.status_code)

    if response.status_code != 200:
        print("Association lookup unavailable")
        continue

    associations = response.json().get("results", [])

    if not associations:
        print("No HubSpot company association found")
        continue

    for association in associations:
        remote_company_id = str(association["toObjectId"])
        local_company_id = companies.get(remote_company_id)

        print("HubSpot company ID:", remote_company_id)
        print("Matching SQLite company ID:", local_company_id)

print("\nRead-only association check completed.")
