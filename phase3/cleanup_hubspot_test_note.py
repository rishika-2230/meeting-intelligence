
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("HUBSPOT_SERVICE_KEY")
id_path = BASE_DIR / "phase3" / "hubspot_test_note_id.txt"

if not api_key:
    raise ValueError("HubSpot Service Key missing")

if not id_path.exists():
    raise FileNotFoundError("Saved test note ID not found")

note_id = id_path.read_text(encoding="utf-8").strip()

if note_id != "412897402578":
    raise ValueError("Unexpected note ID. Cleanup cancelled.")

url = f"https://api.hubapi.com/crm/v3/objects/notes/{note_id}"

headers = {"Authorization": f"Bearer {api_key}"}

# Verify the note is our temporary test record.
response = requests.get(
    url,
    headers=headers,
    params={"properties": "hs_note_body"},
    timeout=30
)
response.raise_for_status()

body = response.json().get("properties", {}).get(
    "hs_note_body", ""
)

if not body.startswith(
    "TEST ONLY - Meeting Intelligence API integration."
):
    raise ValueError("Note is not the expected test note")

# Archive only the verified test note.
response = requests.delete(
    url,
    headers=headers,
    timeout=30
)

print("HTTP Status:", response.status_code)

if response.status_code == 204:
    id_path.unlink()
    print("Test note archived successfully.")
    print("Saved test ID file removed.")
else:
    print("Cleanup unsuccessful. ID file preserved.")
