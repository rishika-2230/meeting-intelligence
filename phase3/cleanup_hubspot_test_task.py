
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("HUBSPOT_SERVICE_KEY")
id_path = BASE_DIR / "phase3" / "hubspot_test_task_id.txt"

if not api_key:
    raise ValueError("HUBSPOT_SERVICE_KEY missing")

if not id_path.exists():
    raise FileNotFoundError("Saved test task ID not found")

task_id = id_path.read_text(encoding="utf-8").strip()

# Protect against accidentally archiving another task.
if task_id != "412872392380":
    raise ValueError("Unexpected task ID. Cleanup cancelled.")

url = f"https://api.hubapi.com/crm/v3/objects/tasks/{task_id}"

headers = {
    "Authorization": f"Bearer {api_key}"
}

# Verify that this is the temporary test task.
response = requests.get(
    url,
    headers=headers,
    params={
        "properties": "hs_task_subject,hs_task_body"
    },
    timeout=30
)

response.raise_for_status()

properties = response.json().get("properties", {})

subject = properties.get("hs_task_subject", "")
body = properties.get("hs_task_body", "")

if (
    subject != "TEST ONLY - Meeting Intelligence API"
    or "Temporary integration test." not in body
):
    raise ValueError(
        "Task does not match the expected test record. "
        "Cleanup cancelled."
    )

# Archive the verified temporary test task.
response = requests.delete(
    url,
    headers=headers,
    timeout=30
)

print("HTTP Status:", response.status_code)

if response.status_code == 204:
    id_path.unlink()
    print("Test task archived successfully.")
    print("Saved test ID file removed.")
else:
    print("Cleanup unsuccessful.")
    print("Saved ID file preserved.")
    print("Response:", response.text[:300])
