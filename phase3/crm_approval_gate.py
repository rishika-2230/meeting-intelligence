
import sqlite3

from collections import Counter
from contextlib import closing
from pathlib import Path


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "meeting_intelligence.db"

CRM_TABLES = {
    "note": {
        "table": "crm_notes",
        "id_column": "note_id",
        "hubspot_column": "hubspot_note_id",
    },
    "task": {
        "table": "crm_tasks",
        "id_column": "task_id",
        "hubspot_column": "hubspot_task_id",
    },
}


# ============================================================
# 2. DATABASE CONNECTION
# ============================================================

def connect_database(db_path=DB_PATH):

    if not Path(db_path).is_file():
        raise FileNotFoundError(
            f"SQLite database not found: {db_path}"
        )

    connection = sqlite3.connect(
        db_path,
        timeout=30
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA query_only = ON"
    )

    return connection


# ============================================================
# 3. LOAD LATEST MEETING REVIEW DECISION
# ============================================================

def get_meeting_review_status(
    conn,
    meeting_id
):

    if not meeting_id:
        return "pending"

    row = conn.execute(
        """
        SELECT status
        FROM meeting_review_history
        WHERE meeting_id = ?
        ORDER BY review_id DESC
        LIMIT 1
        """,
        (meeting_id,)
    ).fetchone()

    if row is None:
        return "pending"

    return str(
        row["status"] or "pending"
    ).strip().lower()


# ============================================================
# 4. CHECK WHETHER ONE CRM RECORD IS ELIGIBLE
# ============================================================

def check_crm_record(
    conn,
    record_type,
    record_id
):
    """
    Read-only eligibility check.

    This function does not:
    - Update SQLite
    - Create HubSpot notes
    - Create HubSpot tasks
    - Change approval decisions
    """

    if record_type not in CRM_TABLES:
        raise ValueError(
            "record_type must be 'note' or 'task'"
        )

    config = CRM_TABLES[record_type]

    table = config["table"]
    id_column = config["id_column"]
    hubspot_column = config["hubspot_column"]

    record = conn.execute(
        f"""
        SELECT
            {id_column} AS record_id,
            meeting_id,
            review_status,
            sync_status,
            is_demo,
            {hubspot_column} AS hubspot_id
        FROM {table}
        WHERE {id_column} = ?
        """,
        (record_id,)
    ).fetchone()

    if record is None:
        return {
            "record_type": record_type,
            "record_id": record_id,
            "meeting_id": None,
            "meeting_review": "unknown",
            "record_review": "unknown",
            "eligible": False,
            "reasons": ["CRM record does not exist"],
        }

    meeting_id = record["meeting_id"]

    meeting_review = (
        get_meeting_review_status(
            conn,
            meeting_id
        )
    )

    record_review = str(
        record["review_status"] or ""
    ).strip().lower()

    sync_status = str(
        record["sync_status"] or ""
    ).strip().lower()

    hubspot_id = record["hubspot_id"]

    reasons = []

    # ------------------------------------------
    # Meeting-level approval
    # ------------------------------------------

    if not meeting_id:
        reasons.append(
            "CRM record has no meeting ID"
        )

    if meeting_review != "approved":
        reasons.append(
            "Meeting is not approved"
        )

    # ------------------------------------------
    # Individual CRM record approval
    # ------------------------------------------

    if record_review != "approved":
        reasons.append(
            "CRM record is not approved"
        )

    # ------------------------------------------
    # Demo data protection
    # ------------------------------------------

    demo_value = record["is_demo"]

    # Only explicitly non-demo records qualify.
    if demo_value is None:
        reasons.append(
            "Demo flag is not verified"
        )

    else:
        try:
            is_demo = int(demo_value)
        except (ValueError, TypeError):
            is_demo = 1

        if is_demo != 0:
            reasons.append(
                "Demo record: synchronization blocked"
            )

    # ------------------------------------------
    # Existing sync protection
    # ------------------------------------------

    if sync_status == "synced":
        reasons.append(
            "Record already marked as synced"
        )

    if hubspot_id is not None and str(
        hubspot_id
    ).strip():
        reasons.append(
            "Record already has a HubSpot ID"
        )

    # Do not permit arbitrary or unknown states.
    allowed_unsynced_statuses = {
        "",
        "pending",
        "not_synced",
        "unsynced",
        "ready",
    }

    if sync_status not in allowed_unsynced_statuses:
        reasons.append(
            f"Sync status not eligible: {sync_status}"
        )

    return {
        "record_type": record_type,
        "record_id": record["record_id"],
        "meeting_id": meeting_id,
        "meeting_review": meeting_review,
        "record_review": record_review,
        "sync_status": sync_status,
        "eligible": len(reasons) == 0,
        "reasons": reasons,
    }


# ============================================================
# 5. AUDIT ALL CRM RECORDS
# ============================================================

def audit_crm_records(db_path=DB_PATH):

    results = []

    with closing(
        connect_database(db_path)
    ) as conn:

        for record_type, config in CRM_TABLES.items():

            table = config["table"]
            id_column = config["id_column"]

            records = conn.execute(
                f"""
                SELECT {id_column}
                FROM {table}
                ORDER BY {id_column}
                """
            ).fetchall()

            for record in records:

                result = check_crm_record(
                    conn,
                    record_type,
                    record[id_column]
                )

                results.append(result)

    return results


# ============================================================
# 6. DISPLAY THE AUDIT RESULTS
# ============================================================

def print_audit():

    print("=" * 60)
    print("MEETING INTELLIGENCE - CRM APPROVAL SAFETY GATE")
    print("=" * 60)

    results = audit_crm_records()

    total = len(results)

    eligible = sum(
        result["eligible"]
        for result in results
    )

    blocked = total - eligible

    types = Counter(
        result["record_type"]
        for result in results
    )

    print("\n--- CRM RECORD COUNTS ---")

    print(
        "CRM notes:",
        types.get("note", 0)
    )

    print(
        "CRM tasks:",
        types.get("task", 0)
    )

    print(
        "Total records:",
        total
    )

    print("\n--- ELIGIBILITY ---")

    print(
        "Eligible records:",
        eligible
    )

    print(
        "Blocked records:",
        blocked
    )

    print("\n--- RECORD DETAILS ---")

    for result in results:

        print("\n" + "-" * 50)

        print(
            "Record type:",
            result["record_type"]
        )

        print(
            "Record ID:",
            result["record_id"]
        )

        print(
            "Meeting ID:",
            result["meeting_id"]
        )

        print(
            "Meeting approval:",
            result["meeting_review"]
        )

        print(
            "CRM record approval:",
            result["record_review"]
        )

        print(
            "Eligible:",
            "YES" if result["eligible"] else "NO"
        )

        if result["reasons"]:

            print("Blocking reasons:")

            for reason in result["reasons"]:
                print(" -", reason)

    print("\n" + "=" * 60)

    if eligible == 0:

        print(
            "RESULT: NO CRM RECORDS CURRENTLY "
            "QUALIFY FOR SYNCHRONIZATION"
        )

    else:

        print(
            f"RESULT: {eligible} RECORD(S) PASS "
            "THE APPROVAL SAFETY CHECK"
        )

    print("\nRead-only verification completed.")
    print("SQLite records unchanged.")
    print("No HubSpot API requests made.")
    print(
        "Actual synchronization is NOT "
        "enabled by this script."
    )


# ============================================================
# 7. EXECUTION
# ============================================================

if __name__ == "__main__":
    print_audit()
