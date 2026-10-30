
import os
import sqlite3
import requests

from pathlib import Path
from contextlib import closing
from datetime import date, datetime, time, timezone

from dotenv import load_dotenv

from crm_approval_gate import check_crm_record


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = (
    BASE_DIR / "phase3" / "meeting_intelligence.db"
)

load_dotenv(BASE_DIR / ".env")

HUBSPOT_API = "https://api.hubapi.com"

# Live synchronization is explicitly disabled by default.
LIVE_SYNC_ENABLED = (
    os.getenv("ENABLE_HUBSPOT_LIVE_SYNC", "false")
    .strip()
    .lower()
    == "true"
)


# ============================================================
# 2. VALIDATE TASK DUE DATE
# ============================================================

def parse_due_date(value):
    """
    Accept date-only values in YYYY-MM-DD format.

    Never invent a deadline.
    Reject invalid or past dates.
    """

    if not value:
        return None

    try:
        parsed = date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        return None

    if parsed < datetime.now(timezone.utc).date():
        return None

    due_datetime = datetime.combine(
        parsed,
        time(12, 0),
        tzinfo=timezone.utc
    )

    return str(int(due_datetime.timestamp() * 1000))


# ============================================================
# 3. DATABASE CONNECTION
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
# 4. CHECK TASK ELIGIBILITY
# ============================================================

def check_task(conn, task_id):
    """
    Verify every requirement before synchronization.

    Includes the new meeting-level approval gate.

    Returns:
        task, blocking_reasons, due_timestamp
    """

    task = conn.execute(
        """
        SELECT
            t.task_id,
            t.meeting_id,
            t.contact_id,
            t.task_title,
            t.owner,
            t.due_date,
            t.task_status,
            t.review_status,
            t.sync_status,
            t.is_demo,
            t.hubspot_task_id,
            c.hubspot_contact_id
        FROM crm_tasks AS t
        LEFT JOIN crm_contacts AS c
            ON t.contact_id = c.contact_id
        WHERE t.task_id = ?
        """,
        (task_id,)
    ).fetchone()

    if task is None:
        return None, ["Task not found"], None

    reasons = []

    # --------------------------------------------------------
    # MEETING + RECORD APPROVAL SAFETY GATE
    # --------------------------------------------------------

    gate_result = check_crm_record(
        conn,
        record_type="task",
        record_id=task_id
    )

    if not gate_result["eligible"]:
        reasons.extend(gate_result["reasons"])

    # --------------------------------------------------------
    # TASK-SPECIFIC VALIDATION
    # --------------------------------------------------------

    if task["sync_status"] != "not_synced":
        if not any(
            "sync status" in reason.lower()
            or "synced" in reason.lower()
            for reason in reasons
        ):
            reasons.append(
                "Task is not in the 'not_synced' state"
            )

    task_title = task["task_title"]

    if not task_title or not str(task_title).strip():
        reasons.append("Empty task title")

    if task["task_status"] != "open":
        reasons.append("Task is not open")

    due_timestamp = parse_due_date(task["due_date"])

    if due_timestamp is None:
        reasons.append(
            "Missing, invalid, or past due date"
        )

    if task["contact_id"] is None:
        reasons.append("No local contact linked")

    if not task["hubspot_contact_id"]:
        reasons.append("No verified HubSpot contact")

    # --------------------------------------------------------
    # VERIFY CONTACT BELONGS TO THE MEETING
    # --------------------------------------------------------

    if (
        task["contact_id"] is not None
        and task["meeting_id"] is not None
    ):

        matching_contact = conn.execute(
            """
            SELECT 1
            FROM crm_meeting_contacts
            WHERE meeting_id = ?
              AND contact_id = ?
            """,
            (
                task["meeting_id"],
                task["contact_id"]
            )
        ).fetchone()

        if matching_contact is None:
            reasons.append(
                "Contact not matched to meeting"
            )

    # Remove duplicated reasons while preserving order.
    reasons = list(dict.fromkeys(reasons))

    return task, reasons, due_timestamp


# ============================================================
# 5. VERIFY HUBSPOT ASSOCIATION TYPE
# ============================================================

def get_task_contact_association(headers):
    """
    Retrieve the HubSpot-defined association type.

    This is a GET request and does not create records.
    """

    response = requests.get(
        (
            f"{HUBSPOT_API}/crm/v4/associations/"
            "tasks/contacts/labels"
        ),
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    associations = response.json().get(
        "results",
        []
    )

    default_association = next(
        (
            item
            for item in associations
            if item.get("category") == "HUBSPOT_DEFINED"
            and item.get("label") is None
        ),
        None
    )

    if (
        default_association is None
        or default_association.get("typeId") is None
    ):
        raise RuntimeError(
            "Default HubSpot task-to-contact "
            "association is unavailable."
        )

    return default_association["typeId"]


# ============================================================
# 6. RESERVE TASK AFTER RECHECKING APPROVAL
# ============================================================

def reserve_task(task_id):
    """
    Recheck every condition in a SQLite write transaction.

    Reserve only if meeting approval, record approval,
    demo protection, and all task checks still pass.
    """

    with closing(connect_database()) as conn:

        try:

            conn.execute("BEGIN IMMEDIATE")

            task, reasons, due_timestamp = check_task(
                conn,
                task_id
            )

            if reasons:
                conn.rollback()
                return None, reasons

            cursor = conn.execute(
                """
                UPDATE crm_tasks
                SET sync_status = 'syncing'
                WHERE task_id = ?
                  AND sync_status = 'not_synced'
                  AND review_status = 'approved'
                  AND is_demo = 0
                  AND hubspot_task_id IS NULL
                """,
                (task_id,)
            )

            if cursor.rowcount != 1:
                conn.rollback()
                return None, [
                    "Task could not be reserved safely"
                ]

            details = {
                "task_id": task["task_id"],
                "meeting_id": task["meeting_id"],
                "task_title": task["task_title"],
                "hubspot_contact_id": task[
                    "hubspot_contact_id"
                ],
                "due_timestamp": due_timestamp
            }

            conn.commit()

            return details, []

        except Exception:
            conn.rollback()
            raise


# ============================================================
# 7. HANDLE UNCERTAIN API OUTCOMES
# ============================================================

def mark_needs_review(task_id):
    """
    Prevent automatic retries after an uncertain
    HubSpot request or failed local finalization.
    """

    with closing(connect_database()) as conn:

        with conn:

            conn.execute(
                """
                UPDATE crm_tasks
                SET sync_status = 'needs_review'
                WHERE task_id = ?
                  AND sync_status = 'syncing'
                """,
                (task_id,)
            )


# ============================================================
# 8. SAVE SUCCESSFUL HUBSPOT SYNCHRONIZATION
# ============================================================

def finalize_task_sync(task_id, remote_task_id):

    with closing(connect_database()) as conn:

        with conn:

            cursor = conn.execute(
                """
                UPDATE crm_tasks
                SET
                    hubspot_task_id = ?,
                    sync_status = 'synced'
                WHERE task_id = ?
                  AND sync_status = 'syncing'
                  AND hubspot_task_id IS NULL
                """,
                (
                    str(remote_task_id),
                    task_id
                )
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "HubSpot task was created, but "
                    "the SQLite sync record could "
                    "not be finalized. Reconciliation "
                    "is required before any retry."
                )


# ============================================================
# 9. SYNCHRONIZE ONE APPROVED TASK
# ============================================================

def sync_task(task_id, dry_run=True):
    """
    Synchronize one task with HubSpot.

    DEFAULT:
        dry_run=True

    Live synchronization requires:
        - dry_run=False
        - ENABLE_HUBSPOT_LIVE_SYNC=true
        - meeting-level approval
        - CRM-record approval
        - non-demo record
        - all remaining task checks

    No API writes are performed during a dry run.
    """

    # --------------------------------------------------------
    # INITIAL READ-ONLY APPROVAL CHECK
    # --------------------------------------------------------

    with closing(connect_database()) as conn:

        task, reasons, due_timestamp = check_task(
            conn,
            task_id
        )

    if reasons:
        return "BLOCKED: " + ", ".join(reasons)

    if dry_run:
        return (
            "ELIGIBLE: Dry run only. "
            "Nothing sent to HubSpot."
        )

    # --------------------------------------------------------
    # EXPLICIT LIVE-SYNC PERMISSION
    # --------------------------------------------------------

    if not LIVE_SYNC_ENABLED:
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
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # --------------------------------------------------------
    # LOOK UP ASSOCIATION BEFORE RESERVING TASK
    # --------------------------------------------------------

    association_type_id = (
        get_task_contact_association(headers)
    )

    # --------------------------------------------------------
    # SECOND APPROVAL CHECK + ATOMIC RESERVATION
    # --------------------------------------------------------

    details, reserve_reasons = reserve_task(
        task_id
    )

    if reserve_reasons:
        return (
            "BLOCKED: "
            + ", ".join(reserve_reasons)
        )

    # --------------------------------------------------------
    # PREPARE HUBSPOT TASK
    # --------------------------------------------------------

    payload = {
        "properties": {
            "hs_timestamp": details[
                "due_timestamp"
            ],
            "hs_task_subject": details[
                "task_title"
            ],
            "hs_task_body": (
                "Meeting Intelligence follow-up. "
                "Source meeting: "
                + str(details["meeting_id"])
            ),
            "hs_task_status": "NOT_STARTED",
            "hs_task_priority": "MEDIUM",
            "hs_task_type": "TODO"
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
    # CREATE HUBSPOT TASK
    # --------------------------------------------------------

    # Do not blindly retry this POST if the response
    # is lost: the remote task might already exist.

    try:

        response = requests.post(
            (
                f"{HUBSPOT_API}/crm/v3/"
                "objects/tasks"
            ),
            headers=headers,
            json=payload,
            timeout=30
        )

        response.raise_for_status()

        response_data = response.json()

        remote_task_id = response_data.get(
            "id"
        )

        if not remote_task_id:
            raise RuntimeError(
                "HubSpot did not return a task ID."
            )

    except Exception:

        mark_needs_review(task_id)
        raise

    # --------------------------------------------------------
    # SAVE REMOTE TASK ID
    # --------------------------------------------------------

    try:

        finalize_task_sync(
            task_id,
            remote_task_id
        )

    except Exception:

        mark_needs_review(task_id)
        raise

    return (
        "SYNCED: HubSpot task ID "
        + str(remote_task_id)
    )


# ============================================================
# 10. SAFE LOCAL DRY RUN
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("HUBSPOT TASK SYNCHRONIZATION - SAFETY TEST")
    print("=" * 60)

    result = sync_task(
        task_id=1,
        dry_run=True
    )

    print("\nTask 1:", result)

    print("\nDry run completed.")
    print("No HubSpot API requests made.")
    print("No SQLite records modified.")
