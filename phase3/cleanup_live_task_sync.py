
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
CHECKPOINT = (
    BASE_DIR / "phase3" / "hubspot_task_sync_test.json"
)

load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("HUBSPOT_SERVICE_KEY")

if not api_key:
    raise ValueError("HUBSPOT_SERVICE_KEY missing")

if not CHECKPOINT.exists():
    raise FileNotFoundError(
        "Test checkpoint not found. Cleanup cancelled."
    )

data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))

task_id = str(data.get("test_task_id") or "")
contact_id = str(data.get("test_contact_id") or "")
test_email = data.get("test_contact_email") or ""

# Restrict cleanup to the exact records created in Step 31.
if task_id != "412910318313":
    raise ValueError("Unexpected task ID. Cleanup cancelled.")

if contact_id != "579855445720":
    raise ValueError("Unexpected contact ID. Cleanup cancelled.")

if not (
    test_email.startswith("mi-sync-test-")
    and test_email.endswith("@example.com")
):
    raise ValueError("Unexpected test email. Cleanup cancelled.")

HEADERS = {
    "Authorization": f"Bearer {api_key}"
}

API = "https://api.hubapi.com"


def save_checkpoint():
    CHECKPOINT.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )


# --------------------------------------------------
# 1. Verify temporary task
# --------------------------------------------------

if not data.get("task_archived", False):

    task_url = f"{API}/crm/v3/objects/tasks/{task_id}"

    response = requests.get(
        task_url,
        headers=HEADERS,
        params={"properties": "hs_task_subject"},
        timeout=30
    )
    response.raise_for_status()

    subject = response.json().get(
        "properties", {}
    ).get("hs_task_subject")

    if subject != (
        "TEST ONLY - Meeting Intelligence Live Task Sync"
    ):
        raise ValueError(
            "Task subject does not match. Cleanup cancelled."
        )

    # Verify the task is linked to our test contact.
    response = requests.get(
        f"{API}/crm/v4/objects/tasks/"
        f"{task_id}/associations/contacts",
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    associated_ids = {
        str(item["toObjectId"])
        for item in response.json().get("results", [])
    }

    if contact_id not in associated_ids:
        raise ValueError(
            "Expected task/contact association missing."
        )

    print("Temporary task verified.")


# --------------------------------------------------
# 2. Verify temporary contact
# --------------------------------------------------

if not data.get("contact_archived", False):

    contact_url = (
        f"{API}/crm/v3/objects/contacts/{contact_id}"
    )

    response = requests.get(
        contact_url,
        headers=HEADERS,
        params={"properties": "email,firstname,lastname"},
        timeout=30
    )
    response.raise_for_status()

    properties = response.json().get("properties", {})

    if properties.get("email") != test_email:
        raise ValueError(
            "Contact email does not match. Cleanup cancelled."
        )

    if properties.get("firstname") != "TEST ONLY":
        raise ValueError(
            "Contact is not the expected test contact."
        )

    if properties.get("lastname") != (
        "Meeting Intelligence Integration"
    ):
        raise ValueError(
            "Contact name does not match. Cleanup cancelled."
        )

    print("Temporary contact verified.")


# --------------------------------------------------
# 3. Archive temporary task
# --------------------------------------------------

if not data.get("task_archived", False):

    response = requests.delete(
        f"{API}/crm/v3/objects/tasks/{task_id}",
        headers=HEADERS,
        timeout=30
    )

    print("Task archive HTTP status:", response.status_code)
    response.raise_for_status()

    if response.status_code != 204:
        raise RuntimeError("Unexpected task archive response")

    data["task_archived"] = True
    save_checkpoint()

    print("Temporary task archived successfully.")

else:
    print("Temporary task already marked archived.")


# --------------------------------------------------
# 4. Archive temporary contact
# --------------------------------------------------

if not data.get("contact_archived", False):

    response = requests.delete(
        f"{API}/crm/v3/objects/contacts/{contact_id}",
        headers=HEADERS,
        timeout=30
    )

    print(
        "Contact archive HTTP status:",
        response.status_code
    )
    response.raise_for_status()

    if response.status_code != 204:
        raise RuntimeError("Unexpected contact archive response")

    data["contact_archived"] = True
    save_checkpoint()

    print("Temporary contact archived successfully.")

else:
    print("Temporary contact already marked archived.")


# --------------------------------------------------
# 5. Complete cleanup
# --------------------------------------------------

if (
    data.get("task_archived")
    and data.get("contact_archived")
):
    CHECKPOINT.unlink()

    print("\nLIVE TEST CLEANUP: PASS")
    print("Both temporary HubSpot records archived.")
    print("Checkpoint file removed.")
    print("Original SQLite database unchanged.")
