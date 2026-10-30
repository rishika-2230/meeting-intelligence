
import os
import sqlite3
import requests

from pathlib import Path
from datetime import datetime, timezone
from contextlib import closing

from dotenv import load_dotenv

from crm_approval_gate import (
    check_crm_record,
    get_meeting_review_status
)


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = (
    BASE_DIR
    / "phase3"
    / "meeting_intelligence.db"
)

load_dotenv(BASE_DIR / ".env")

HUBSPOT_API = "https://api.hubapi.com"


def live_sync_enabled():
    """
    Live HubSpot writes are disabled unless explicitly
    enabled through the environment configuration.
    """

    return (
        os.getenv(
            "ENABLE_HUBSPOT_LIVE_SYNC",
            "false"
        ).strip().lower()
        == "true"
    )


# ============================================================
# 2. DATABASE CONNECTION
# ============================================================

def connect_database():

    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"Meeting database not found: {DB_PATH}"
        )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    return conn


# ============================================================
# 3. CHECK NOTE ELIGIBILITY
# ============================================================

def check_note(conn, note_id):
    """
    Validate one CRM note before synchronization.

    Includes:
    - Meeting-level approval
    - CRM note approval
    - Demo record protection
    - Duplicate synchronization protection
    - Verified HubSpot contact
    - Meeting-contact association

    This function is read-only.
    """

    note = conn.execute(
        """
        SELECT
            n.note_id,
            n.meeting_id,
            n.contact_id,
            n.company_id,
            n.note_text,
            n.review_status,
            n.sync_status,
            n.is_demo,
            n.hubspot_note_id,
            c.hubspot_contact_id
        FROM crm_notes AS n
        LEFT JOIN crm_contacts AS c
            ON n.contact_id = c.contact_id
        WHERE n.note_id = ?
        """,
        (note_id,)
    ).fetchone()

    if note is None:
        return None, ["Note not found"]

    reasons = []

    # --------------------------------------------------------
    # MEETING + CRM RECORD APPROVAL GATE
    # --------------------------------------------------------

    gate_result = check_crm_record(
        conn,
        record_type="note",
        record_id=note_id
    )

    if not gate_result["eligible"]:
        reasons.extend(
            gate_result["reasons"]
        )

    # --------------------------------------------------------
    # NOTE-SPECIFIC VALIDATION
    # --------------------------------------------------------

    if note["sync_status"] != "not_synced":
        reasons.append(
            "Note is not in the 'not_synced' state"
        )

    body = note["note_text"]

    if (
        body is None
        or not str(body).strip()
    ):
        reasons.append("Empty note body")

    # --------------------------------------------------------
    # CONTACT VALIDATION
    # --------------------------------------------------------

    if note["contact_id"] is None:
        reasons.append(
            "No local contact linked"
        )

    if not note["hubspot_contact_id"]:
        reasons.append(
            "No verified HubSpot contact"
        )

    # --------------------------------------------------------
    # MEETING-CONTACT RELATIONSHIP
    # --------------------------------------------------------

    if (
        note["meeting_id"] is not None
        and note["contact_id"] is not None
    ):

        matched = conn.execute(
            """
            SELECT 1
            FROM crm_meeting_contacts
            WHERE meeting_id = ?
              AND contact_id = ?
            """,
            (
                note["meeting_id"],
                note["contact_id"]
            )
        ).fetchone()

        if matched is None:
            reasons.append(
                "Contact not matched to meeting"
            )

    # Remove duplicate blocking reasons.
    reasons = list(
        dict.fromkeys(reasons)
    )

    return note, reasons


# ============================================================
# 4. GET VERIFIED HUBSPOT ASSOCIATION TYPE
# ============================================================

def get_note_contact_association(headers):
    """
    Retrieve HubSpot's default note-to-contact
    association type.

    GET request only; no HubSpot data is modified.
    """

    url = (
        f"{HUBSPOT_API}"
        "/crm/v4/associations/notes/contacts/labels"
    )

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    labels = response.json().get(
        "results",
        []
    )

    default_association = next(
        (
            item
            for item in labels
            if item.get("category")
            == "HUBSPOT_DEFINED"
            and item.get("label") is None
        ),
        None
    )

    if (
        default_association is None
        or default_association.get("typeId") is None
    ):
        raise RuntimeError(
            "Default HubSpot note-to-contact "
            "association is unavailable."
        )

    return default_association["typeId"]


# ============================================================
# 5. RESERVE NOTE SAFELY
# ============================================================

def reserve_note(note_id):
    """
    Recheck all conditions inside a SQLite write
    transaction before reserving the note.

    The write transaction is committed before the
    external HubSpot request.
    """

    with closing(
        connect_database()
    ) as conn:

        try:

            conn.execute(
                "BEGIN IMMEDIATE"
            )

            note, reasons = check_note(
                conn,
                note_id
            )

            if reasons:
                conn.rollback()
                return None, reasons

            cursor = conn.execute(
                """
                UPDATE crm_notes
                SET sync_status = 'syncing'
                WHERE note_id = ?
                  AND sync_status = 'not_synced'
                  AND review_status = 'approved'
                  AND is_demo = 0
                  AND (
                      hubspot_note_id IS NULL
                      OR TRIM(hubspot_note_id) = ''
                  )
                """,
                (note_id,)
            )

            if cursor.rowcount != 1:

                conn.rollback()

                return None, [
                    "Note could not be reserved safely"
                ]

            details = {
                "note_id": note["note_id"],
                "meeting_id": note["meeting_id"],
                "contact_id": note["contact_id"],
                "note_text": note["note_text"],
                "hubspot_contact_id": note[
                    "hubspot_contact_id"
                ]
            }

            conn.commit()

            return details, []

        except Exception:

            conn.rollback()
            raise


# ============================================================
# 6. RECHECK APPROVAL IMMEDIATELY BEFORE API CREATION
# ============================================================

def recheck_reserved_note(details):
    """
    Verify approval and critical record details
    after reservation, before the HubSpot POST.

    This reduces the risk of sending a record
    whose approval or association was changed.

    A SQLite check cannot completely eliminate
    races with an external API request.
    """

    note_id = details["note_id"]

    with closing(
        connect_database()
    ) as conn:

        note = conn.execute(
            """
            SELECT
                note_id,
                meeting_id,
                contact_id,
                note_text,
                review_status,
                sync_status,
                is_demo,
                hubspot_note_id
            FROM crm_notes
            WHERE note_id = ?
            """,
            (note_id,)
        ).fetchone()

        if note is None:
            return False

        # Meeting approval is mandatory.
        meeting_status = get_meeting_review_status(
            conn,
            note["meeting_id"]
        )

        if meeting_status != "approved":
            return False

        # Individual note approval is mandatory.
        if note["review_status"] != "approved":
            return False

        # Only explicitly non-demo records.
        if note["is_demo"] != 0:
            return False

        # The record must still be reserved.
        if note["sync_status"] != "syncing":
            return False

        # It must not have an existing remote ID.
        if note["hubspot_note_id"]:
            return False

        # Ensure the same meeting, contact, and note
        # will be sent as the reserved record.
        if note["meeting_id"] != details["meeting_id"]:
            return False

        if note["contact_id"] != details["contact_id"]:
            return False

        if note["note_text"] != details["note_text"]:
            return False

        contact = conn.execute(
            """
            SELECT hubspot_contact_id
            FROM crm_contacts
            WHERE contact_id = ?
            """,
            (details["contact_id"],)
        ).fetchone()

        if contact is None:
            return False

        if (
            str(contact["hubspot_contact_id"] or "")
            != str(details["hubspot_contact_id"])
        ):
            return False

        matched = conn.execute(
            """
            SELECT 1
            FROM crm_meeting_contacts
            WHERE meeting_id = ?
              AND contact_id = ?
            """,
            (
                details["meeting_id"],
                details["contact_id"]
            )
        ).fetchone()

        if matched is None:
            return False

    return True


# ============================================================
# 7. MARK UNCERTAIN SYNCHRONIZATION FOR REVIEW
# ============================================================

def mark_needs_review(note_id):
    """
    Prevent blind retries when a HubSpot operation
    has an uncertain outcome.
    """

    with closing(
        connect_database()
    ) as conn:

        with conn:

            conn.execute(
                """
                UPDATE crm_notes
                SET sync_status = 'needs_review'
                WHERE note_id = ?
                  AND sync_status = 'syncing'
                """,
                (note_id,)
            )


# ============================================================
# 8. FINALIZE SUCCESSFUL HUBSPOT SYNC
# ============================================================

def finalize_note_sync(
    note_id,
    remote_note_id
):
    """
    Save the remote HubSpot note ID only if
    the local note remains reserved.
    """

    with closing(
        connect_database()
    ) as conn:

        with conn:

            cursor = conn.execute(
                """
                UPDATE crm_notes
                SET
                    hubspot_note_id = ?,
                    sync_status = 'synced'
                WHERE note_id = ?
                  AND sync_status = 'syncing'
                  AND (
                      hubspot_note_id IS NULL
                      OR TRIM(hubspot_note_id) = ''
                  )
                """,
                (
                    str(remote_note_id),
                    note_id
                )
            )

            if cursor.rowcount != 1:

                raise RuntimeError(
                    "HubSpot note was created, but "
                    "the local synchronization record "
                    "could not be finalized. Manual "
                    "reconciliation is required."
                )


# ============================================================
# 9. SYNCHRONIZE ONE NOTE
# ============================================================

def sync_note(note_id, dry_run=True):
    """
    Synchronize one CRM note with HubSpot.

    Default behavior:
        dry_run=True

    Live synchronization requires:
        - dry_run=False
        - ENABLE_HUBSPOT_LIVE_SYNC=true
        - Approved meeting
        - Approved CRM note
        - Non-demo record
        - Unsynced state
        - Valid HubSpot contact
        - Verified meeting-contact association

    A dry run performs no API calls and makes
    no SQLite modifications.
    """

    # --------------------------------------------------------
    # INITIAL READ-ONLY SAFETY CHECK
    # --------------------------------------------------------

    with closing(
        connect_database()
    ) as conn:

        note, reasons = check_note(
            conn,
            note_id
        )

    if reasons:

        return (
            "BLOCKED: "
            + ", ".join(reasons)
        )

    # --------------------------------------------------------
    # DRY RUN: STOP BEFORE ALL API REQUESTS
    # --------------------------------------------------------

    if dry_run:

        return (
            "ELIGIBLE: Dry run only. "
            "Nothing sent to HubSpot."
        )

    # --------------------------------------------------------
    # EXPLICIT LIVE-SYNC ENVIRONMENT GATE
    # --------------------------------------------------------

    if not live_sync_enabled():

        return (
            "BLOCKED: Live HubSpot synchronization "
            "is disabled in the environment."
        )

    api_key = os.getenv(
        "HUBSPOT_SERVICE_KEY",
        ""
    ).strip()

    if not api_key:

        raise ValueError(
            "HUBSPOT_SERVICE_KEY is missing."
        )

    headers = {
        "Authorization": (
            f"Bearer {api_key}"
        ),
        "Content-Type": "application/json"
    }

    # --------------------------------------------------------
    # FETCH ASSOCIATION BEFORE RESERVING
    # --------------------------------------------------------

    association_type_id = (
        get_note_contact_association(headers)
    )

    # --------------------------------------------------------
    # RECHECK CONDITIONS AND RESERVE RECORD
    # --------------------------------------------------------

    details, reserve_reasons = reserve_note(
        note_id
    )

    if reserve_reasons:

        return (
            "BLOCKED: "
            + ", ".join(reserve_reasons)
        )

    # --------------------------------------------------------
    # VERIFY APPROVAL AGAIN BEFORE POST
    # --------------------------------------------------------

    try:

        still_eligible = recheck_reserved_note(
            details
        )

    except Exception:

        mark_needs_review(note_id)
        raise

    if not still_eligible:

        mark_needs_review(note_id)

        return (
            "BLOCKED: Approval or note details "
            "changed after reservation. "
            "Manual review required."
        )

    # --------------------------------------------------------
    # BUILD HUBSPOT NOTE PAYLOAD
    # --------------------------------------------------------

    payload = {
        "properties": {
            "hs_timestamp": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            "hs_note_body": details[
                "note_text"
            ]
        },
        "associations": [
            {
                "to": {
                    "id": str(
                        details["hubspot_contact_id"]
                    )
                },
                "types": [
                    {
                        "associationCategory": (
                            "HUBSPOT_DEFINED"
                        ),
                        "associationTypeId": (
                            association_type_id
                        )
                    }
                ]
            }
        ]
    }

    # --------------------------------------------------------
    # CREATE HUBSPOT NOTE
    # --------------------------------------------------------

    # Never blindly retry a failed POST. The remote
    # note might have been created even if the
    # response was not received.

    try:

        response = requests.post(
            (
                f"{HUBSPOT_API}"
                "/crm/v3/objects/notes"
            ),
            headers=headers,
            json=payload,
            timeout=30
        )

        response.raise_for_status()

        remote_note_id = (
            response.json().get("id")
        )

        if not remote_note_id:

            raise RuntimeError(
                "HubSpot did not return a note ID."
            )

    except Exception:

        mark_needs_review(note_id)
        raise

    # --------------------------------------------------------
    # RECORD SUCCESSFUL SYNCHRONIZATION
    # --------------------------------------------------------

    try:

        finalize_note_sync(
            note_id,
            remote_note_id
        )

    except Exception:

        mark_needs_review(note_id)
        raise

    return (
        "SYNCED: HubSpot note ID "
        + str(remote_note_id)
    )


# ============================================================
# 10. SAFE LOCAL TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("HUBSPOT NOTE SYNCHRONIZATION - SAFETY TEST")
    print("=" * 60)

    result = sync_note(
        note_id=1,
        dry_run=True
    )

    print("\nNote 1:", result)

    print("\nDry run completed.")
    print("No HubSpot API requests made.")
    print("No SQLite records modified.")
