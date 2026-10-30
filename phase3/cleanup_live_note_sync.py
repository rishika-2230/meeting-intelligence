
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


# ---------------------------------------------
# 1. Configuration
# ---------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
CHECKPOINT = (
    BASE_DIR / "phase3" / "hubspot_note_sync_test.json"
)

load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("HUBSPOT_SERVICE_KEY")

if not api_key:
    raise ValueError("HUBSPOT_SERVICE_KEY missing")

if not CHECKPOINT.exists():
    raise FileNotFoundError(
        "Test checkpoint not found. Cleanup cancelled."
    )

data = json.loads(
    CHECKPOINT.read_text(encoding="utf-8")
)

note_id = str(data.get("test_note_id") or "")
contact_id = str(data.get("test_contact_id") or "")
test_email = data.get("test_contact_email") or ""
expected_body = data.get("test_note_body") or ""

# Only allow cleanup of the exact Step 33 records.
if note_id != "412846921431":
    raise ValueError("Unexpected note ID. Cleanup cancelled.")

if contact_id != "579991424701":
    raise ValueError("Unexpected contact ID. Cleanup cancelled.")

if not (
    test_email.startswith("mi-note-test-")
    and test_email.endswith("@example.com")
):
    raise ValueError("Unexpected test email. Cleanup cancelled.")

if not expected_body.startswith(
    "TEST ONLY - Meeting Intelligence live note"
):
    raise ValueError("Unexpected note body. Cleanup cancelled.")


API = "https://api.hubapi.com"

headers = {
    "Authorization": f"Bearer {api_key}"
}


def save_checkpoint():
    CHECKPOINT.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )


# ---------------------------------------------
# 2. Verify the test note
# ---------------------------------------------

if not data.get("note_archived", False):

    response = requests.get(
        f"{API}/crm/v3/objects/notes/{note_id}",
        headers=headers,
        params={"properties": "hs_note_body"},
        timeout=30
    )

    response.raise_for_status()

    actual_body = (
        response.json()
        .get("properties", {})
        .get("hs_note_body", "")
    )

    if actual_body != expected_body:
        raise ValueError(
            "Note body mismatch. Cleanup cancelled."
        )

    # Confirm association with our temporary contact.
    response = requests.get(
        f"{API}/crm/v4/objects/notes/"
        f"{note_id}/associations/contacts",
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    associated_contacts = {
        str(item["toObjectId"])
        for item in response.json().get("results", [])
    }

    if contact_id not in associated_contacts:
        raise ValueError(
            "Expected note/contact association missing."
        )

    print("Temporary note verified.")


# ---------------------------------------------
# 3. Verify the test contact
# ---------------------------------------------

if not data.get("contact_archived", False):

    response = requests.get(
        f"{API}/crm/v3/objects/contacts/{contact_id}",
        headers=headers,
        params={
            "properties": "email,firstname,lastname"
        },
        timeout=30
    )

    response.raise_for_status()

    properties = response.json().get("properties", {})

    if properties.get("email") != test_email:
        raise ValueError(
            "Contact email mismatch. Cleanup cancelled."
        )

    if properties.get("firstname") != "TEST ONLY":
        raise ValueError(
            "Unexpected contact firstname."
        )

    if properties.get("lastname") != "MI Note Integration":
        raise ValueError(
            "Unexpected contact lastname."
        )

    print("Temporary contact verified.")


# ---------------------------------------------
# 4. Archive the temporary note
# ---------------------------------------------

if not data.get("note_archived", False):

    response = requests.delete(
        f"{API}/crm/v3/objects/notes/{note_id}",
        headers=headers,
        timeout=30
    )

    print("Note archive HTTP status:", response.status_code)

    response.raise_for_status()

    if response.status_code != 204:
        raise RuntimeError(
            "Unexpected note archive response"
        )

    data["note_archived"] = True
    save_checkpoint()

    print("Temporary note archived successfully.")

else:
    print("Temporary note already marked archived.")


# ---------------------------------------------
# 5. Archive the temporary contact
# ---------------------------------------------

if not data.get("contact_archived", False):

    response = requests.delete(
        f"{API}/crm/v3/objects/contacts/{contact_id}",
        headers=headers,
        timeout=30
    )

    print(
        "Contact archive HTTP status:",
        response.status_code
    )

    response.raise_for_status()

    if response.status_code != 204:
        raise RuntimeError(
            "Unexpected contact archive response"
        )

    data["contact_archived"] = True
    save_checkpoint()

    print("Temporary contact archived successfully.")

else:
    print("Temporary contact already marked archived.")


# ---------------------------------------------
# 6. Finish cleanup
# ---------------------------------------------

if (
    data.get("note_archived")
    and data.get("contact_archived")
):
    CHECKPOINT.unlink()

    print("\nLIVE NOTE TEST CLEANUP: PASS")
    print("Both temporary HubSpot records archived.")
    print("Checkpoint file removed.")
    print("Original SQLite database unchanged.")
