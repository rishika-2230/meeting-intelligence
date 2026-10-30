
import os
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("HUBSPOT_SERVICE_KEY")

if not api_key:
    raise ValueError("HUBSPOT_SERVICE_KEY missing")

id_path = BASE_DIR / "phase3" / "hubspot_test_task_id.txt"

if id_path.exists():
    raise RuntimeError(
        "A test task ID already exists. "
        "Cleanup is required before creating another."
    )

# Use a future timestamp for the temporary test task.
due_date = datetime.now(timezone.utc) + timedelta(days=7)

payload = {
    "properties": {
        "hs_timestamp": str(int(due_date.timestamp() * 1000)),
        "hs_task_subject": "TEST ONLY - Meeting Intelligence API",
        "hs_task_body": (
            "Temporary integration test. "
            "No real customer or meeting data."
        ),
        "hs_task_status": "NOT_STARTED",
        "hs_task_priority": "LOW",
        "hs_task_type": "TODO"
    }
}

response = requests.post(
    "https://api.hubapi.com/crm/v3/objects/tasks",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json=payload,
    timeout=30
)

print("HTTP Status:", response.status_code)

if response.status_code in (200, 201):
    task_id = str(response.json()["id"])
    id_path.write_text(task_id, encoding="utf-8")

    print("HubSpot Task WRITE: SUCCESS")
    print("Test task ID:", task_id)
    print("Saved ID for cleanup.")

elif response.status_code == 403:
    print("HubSpot Task WRITE: PERMISSION DENIED")

else:
    print("HubSpot Task WRITE: FAILED")
    print("Error details:", response.text[:500])
