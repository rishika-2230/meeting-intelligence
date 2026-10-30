
import sqlite3
import tempfile

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "meeting_intelligence.db"

VALID_STATUSES = {
    "pending",
    "approved",
    "rejected",
}


# ============================================================
# 2. INITIALIZE REVIEW HISTORY
# ============================================================

def initialize_review_store(db_path=DB_PATH):
    """
    Creates a separate review-history table.

    Existing meeting records, extracted items,
    and HubSpot data are not changed.
    """

    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"Meeting database not found: {db_path}"
        )

    with closing(sqlite3.connect(db_path)) as conn:
        with conn:

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS
                meeting_review_history (
                    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meeting_id TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (
                            status IN (
                                'pending',
                                'approved',
                                'rejected'
                            )
                        ),
                    reviewer TEXT NOT NULL,
                    review_note TEXT,
                    reviewed_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_review_history_meeting
                ON meeting_review_history (
                    meeting_id,
                    review_id
                )
                """
            )


# ============================================================
# 3. GET LATEST REVIEW STATUS FOR EVERY MEETING
# ============================================================

def get_latest_review_map(db_path=DB_PATH):

    initialize_review_store(db_path)

    query = """
        SELECT
            h.review_id,
            h.meeting_id,
            h.status,
            h.reviewer,
            h.review_note,
            h.reviewed_at
        FROM meeting_review_history AS h
        INNER JOIN (
            SELECT
                meeting_id,
                MAX(review_id) AS latest_id
            FROM meeting_review_history
            GROUP BY meeting_id
        ) AS latest
            ON h.review_id = latest.latest_id
        ORDER BY h.meeting_id
    """

    with closing(sqlite3.connect(db_path)) as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(query).fetchall()

    return {
        row["meeting_id"]: dict(row)
        for row in rows
    }


# ============================================================
# 4. GET REVIEW HISTORY FOR A MEETING
# ============================================================

def get_review_history(meeting_id, db_path=DB_PATH):

    initialize_review_store(db_path)

    with closing(sqlite3.connect(db_path)) as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT
                review_id,
                meeting_id,
                status,
                reviewer,
                review_note,
                reviewed_at
            FROM meeting_review_history
            WHERE meeting_id = ?
            ORDER BY review_id DESC
            """,
            (meeting_id,)
        ).fetchall()

    return [dict(row) for row in rows]


# ============================================================
# 5. SAVE A REVIEW DECISION
# ============================================================

def save_review_decision(
    meeting_id,
    status,
    reviewer,
    note="",
    db_path=DB_PATH
):
    """
    Append an immutable audit-history event.

    Does not modify:
    - meetings
    - meeting_items
    - crm_notes
    - crm_tasks
    - HubSpot
    """

    meeting_id = str(meeting_id or "").strip()
    status = str(status or "").strip().lower()
    reviewer = str(reviewer or "").strip()
    note = str(note or "").strip()

    if not meeting_id:
        raise ValueError("Meeting ID is required.")

    if status not in VALID_STATUSES:
        raise ValueError(
            "Review status must be pending, "
            "approved, or rejected."
        )

    if not reviewer:
        raise ValueError(
            "Reviewer name is required."
        )

    if len(reviewer) > 80:
        raise ValueError(
            "Reviewer name is too long."
        )

    if len(note) > 2000:
        raise ValueError(
            "Review note exceeds 2000 characters."
        )

    if status == "rejected" and not note:
        raise ValueError(
            "A rejection reason is required."
        )

    initialize_review_store(db_path)

    reviewed_at = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    with closing(
        sqlite3.connect(db_path, timeout=30)
    ) as conn:

        try:

            conn.execute("BEGIN IMMEDIATE")

            exists = conn.execute(
                """
                SELECT 1
                FROM meetings
                WHERE meeting_id = ?
                """,
                (meeting_id,)
            ).fetchone()

            if exists is None:
                raise ValueError(
                    "Meeting does not exist."
                )

            cursor = conn.execute(
                """
                INSERT INTO meeting_review_history (
                    meeting_id,
                    status,
                    reviewer,
                    review_note,
                    reviewed_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    meeting_id,
                    status,
                    reviewer,
                    note,
                    reviewed_at
                )
            )

            review_id = cursor.lastrowid

            conn.commit()

        except Exception:
            conn.rollback()
            raise

    return {
        "review_id": review_id,
        "meeting_id": meeting_id,
        "status": status,
        "reviewer": reviewer,
        "review_note": note,
        "reviewed_at": reviewed_at
    }


# ============================================================
# 6. SELF-TEST USING A TEMPORARY DATABASE
# ============================================================

def self_test():

    print("=" * 55)
    print("MEETING INTELLIGENCE - HUMAN REVIEW TEST")
    print("=" * 55)

    with tempfile.TemporaryDirectory() as folder:

        test_db = Path(folder) / "review_test.db"

        # A temporary database with the relevant
        # existing meetings schema.
        with closing(sqlite3.connect(test_db)) as conn:

            with conn:

                conn.execute(
                    """
                    CREATE TABLE meetings (
                        meeting_id TEXT,
                        summary TEXT,
                        summary_confidence REAL,
                        overall_confidence REAL,
                        requires_human_review INTEGER
                    )
                    """
                )

                conn.execute(
                    """
                    INSERT INTO meetings (
                        meeting_id,
                        summary,
                        overall_confidence,
                        requires_human_review
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        "TEST_REVIEW_MEETING",
                        "Fictional meeting.",
                        0.85,
                        1
                    )
                )

        initialize_review_store(test_db)

        save_review_decision(
            "TEST_REVIEW_MEETING",
            "approved",
            "Test Reviewer",
            "Content verified.",
            test_db
        )

        save_review_decision(
            "TEST_REVIEW_MEETING",
            "rejected",
            "Test Reviewer",
            "An incorrect owner was identified.",
            test_db
        )

        save_review_decision(
            "TEST_REVIEW_MEETING",
            "pending",
            "Test Reviewer",
            "Returned for another review.",
            test_db
        )

        history = get_review_history(
            "TEST_REVIEW_MEETING",
            test_db
        )

        latest = get_latest_review_map(test_db)

        assert len(history) == 3

        assert (
            latest["TEST_REVIEW_MEETING"]["status"]
            == "pending"
        )

        # Rejecting without a reason must fail.
        try:

            save_review_decision(
                "TEST_REVIEW_MEETING",
                "rejected",
                "Test Reviewer",
                "",
                test_db
            )

            raise AssertionError(
                "Empty rejection reason was accepted."
            )

        except ValueError:
            pass

        # A review cannot be attached to an
        # unknown meeting.
        try:

            save_review_decision(
                "NONEXISTENT_MEETING",
                "approved",
                "Test Reviewer",
                "Test",
                test_db
            )

            raise AssertionError(
                "Unknown meeting was accepted."
            )

        except ValueError:
            pass

        print("Review table creation: PASS")
        print("Approve decision: PASS")
        print("Reject decision: PASS")
        print("Return to pending: PASS")
        print("Persistent review history: PASS")
        print("Rejection note validation: PASS")
        print("Meeting existence validation: PASS")
        print("Review history records: 3")

    print("\nHUMAN REVIEW BACKEND TEST: PASS")
    print("Original SQLite database unchanged.")
    print("No HubSpot API requests made.")


if __name__ == "__main__":
    self_test()
