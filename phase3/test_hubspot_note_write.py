
import os
import requests
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("HUBSPOT_SERVICE_KEY")

if not api_key:
    raise ValueError("HUBSPOT_SERVICE_KEY missing")

id_path = BASE_DIR / "phase3" / "hubspot_test_note_id.txt"

if id_path.exists():
    raise RuntimeError(
        "A test note ID is already saved. "
        "Do not create another test note yet."
    )

payload = {
    "properties": {
        "hs_timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "hs_note_body": (
            "TEST ONLY - Meeting Intelligence API integration. "
            "This is a temporary test note. "
            "No real customer or meeting data."
        )
    }
}

response = requests.post(
    "https://api.hubapi.com/crm/v3/objects/notes",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json=payload,
    timeout=30
)

print("HTTP Status:", response.status_code)

if response.status_code == 201:
    note_id = str(response.json()["id"])
    id_path.write_text(note_id, encoding="utf-8")
    print("HubSpot Note WRITE: SUCCESS")
    print("Test note ID:", note_id)
    print("Saved ID for later cleanup.")

elif response.status_code == 403:
    print("HubSpot Note WRITE: PERMISSION DENIED")

else:
    print("HubSpot Note WRITE: Not successful")
    print("Review API permissions or request validation.")
