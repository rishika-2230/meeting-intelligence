
import argparse
import json
import sqlite3

from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


# ==================================================
# 1. CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "meeting_intelligence.db"

MEETING_ID = "manual_ef1595a5435980396085fb6c"


# ==================================================
# 2. ORIGINAL GEMINI EXTRACTION CONTENT
# ==================================================

# Text and evidence references reproduced from the
# extraction output for this specific test meeting.

EXPECTED_ITEMS = {
    "decisions": [
        {
            "text": "Launch the product on November 20, 2026.",
            "evidence": [0, 1],
            "owner": None,
        },
        {
            "text": (
                "Use a blue-and-white design "
                "for the product dashboard."
            ),
            "evidence": [4],
            "owner": None,
        },
    ],

    "commitments": [
        {
            "text": "Finish testing the application dashboard.",
            "evidence": [2],
            "owner": "Rahul",
        },
        {
            "text": (
                "Prepare the marketing campaign "
                "and submit the promotional materials."
            ),
            "evidence": [3],
            "owner": "Priya",
        },
    ],

    "action_items": [
        {
            "text": (
                "Review the payment integration progress "
                "during the next meeting."
            ),
            "evidence": [5, 6, 9],
            "owner": None,
        },
        {
            "text": (
                "Discuss the advertising budget "
                "in the next meeting."
            ),
            "evidence": [7, 8, 9],
            "owner": None,
        },
    ],

    "unanswered_questions": [
        {
            "text": "What is the final advertising budget?",
            "evidence": [7],
            "owner": None,
        },
    ],
}


# ==================================================
# 3. HELPER FUNCTIONS
# ==================================================

def normalize_evidence(value):
    if value is None:
        return []

    if isinstance(value, str):
        value = json.loads(value)

    if not isinstance(value, list):
        raise ValueError("Unexpected evidence format")

    return [int(item) for item in value]


def load_items(conn):
    conn.row_factory = sqlite3.Row

    return conn.execute(
        """
        SELECT
            rowid AS record_id,
            meeting_id,
            item_type,
            text,
            owner,
            deadline,
            confidence,
            evidence_turn_ids
        FROM meeting_items
        WHERE meeting_id = ?
        ORDER BY rowid
        """,
        (MEETING_ID,)
    ).fetchall()


def prepare_repairs(rows):
    if len(rows) != 8:
        raise RuntimeError(
            f"Expected 8 meeting items, found {len(rows)}. "
            "Repair cancelled."
        )

    counts = Counter(row["item_type"] for row in rows)

    expected_counts = {
        "decisions": 2,
        "commitments": 2,
        "action_items": 2,
        "risks": 1,
        "unanswered_questions": 1,
    }

    if counts != expected_counts:
        raise RuntimeError(
            "Extraction categories do not match the "
            "original test meeting. Repair cancelled."
        )

    grouped = defaultdict(list)

    for row in rows:
        grouped[row["item_type"]].append(row)

    # The existing risk text is already correct.
    if not str(grouped["risks"][0]["text"] or "").strip():
        raise RuntimeError(
            "Risk text is unexpectedly empty. "
            "Repair cancelled."
        )

    repairs = []

    for category, expected_records in EXPECTED_ITEMS.items():

        actual_records = grouped[category]

        for row, expected in zip(
            actual_records,
            expected_records
        ):

            actual_evidence = normalize_evidence(
                row["evidence_turn_ids"]
            )

            if actual_evidence != expected["evidence"]:
                raise RuntimeError(
                    f"Evidence mismatch in {category}, "
                    f"row {row['record_id']}. "
                    "Repair cancelled."
                )

            actual_owner = (
                str(row["owner"]).strip()
                if row["owner"] is not None
                else None
            )

            if actual_owner != expected["owner"]:
                raise RuntimeError(
                    f"Owner mismatch in {category}, "
                    f"row {row['record_id']}. "
                    "Repair cancelled."
                )

            current_text = str(row["text"] or "").strip()

            if current_text:
                if current_text != expected["text"]:
                    raise RuntimeError(
                        f"Existing text differs in "
                        f"row {row['record_id']}. "
                        "Repair cancelled."
                    )

                continue

            repairs.append((
                expected["text"],
                row["record_id"],
                category
            ))

    return repairs


# ==================================================
# 4. DATABASE BACKUP
# ==================================================

def backup_database():
    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S_%f")

    backup_path = BASE_DIR / (
        f"meeting_intelligence_before_repair_{timestamp}.db"
    )

    with closing(sqlite3.connect(DB_PATH)) as source:
        with closing(sqlite3.connect(backup_path)) as target:
            source.backup(target)

    return backup_path


# ==================================================
# 5. REPAIR PROCESS
# ==================================================

def main(apply_changes=False):

    print("=" * 55)
    print("MEETING INTELLIGENCE - SQLITE TEXT REPAIR")
    print("=" * 55)

    print("Meeting:", MEETING_ID)
    print("Mode:", "APPLY" if apply_changes else "DRY RUN")

    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)

    with closing(sqlite3.connect(DB_PATH)) as conn:
        repairs = prepare_repairs(load_items(conn))

    print("\n--- REPAIR PREVIEW ---")
    print("Empty text fields found:", len(repairs))

    for text, record_id, category in repairs:
        print(f"\nRow ID: {record_id}")
        print("Category:", category)
        print("Restore text:", text)

    if not repairs:
        print("\nAll expected text fields are present.")
        print("No repair needed.")
        return

    if len(repairs) != 7:
        raise RuntimeError(
            "Expected exactly 7 empty text fields. "
            "Repair cancelled to avoid partial changes."
        )

    if not apply_changes:
        print("\nDRY RUN COMPLETE")
        print("No database changes made.")
        print("Run with --apply to perform the repair.")
        return

    print("\n--- DATABASE BACKUP ---")

    backup_path = backup_database()

    print("Backup created:", backup_path.name)

    # Revalidate under a write transaction.
    with closing(sqlite3.connect(DB_PATH, timeout=30)) as conn:

        try:
            conn.execute("BEGIN IMMEDIATE")

            current_repairs = prepare_repairs(
                load_items(conn)
            )

            if current_repairs != repairs:
                raise RuntimeError(
                    "Database changed since preview. "
                    "Repair cancelled."
                )

            for text, record_id, category in repairs:

                cursor = conn.execute(
                    """
                    UPDATE meeting_items
                    SET text = ?
                    WHERE rowid = ?
                      AND meeting_id = ?
                      AND item_type = ?
                      AND (
                          text IS NULL
                          OR TRIM(text) = ''
                      )
                    """,
                    (
                        text,
                        record_id,
                        MEETING_ID,
                        category
                    )
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Could not update row {record_id}"
                    )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

    # Verify the final contents.
    with closing(sqlite3.connect(DB_PATH)) as conn:
        final_rows = load_items(conn)

    empty_count = sum(
        not str(row["text"] or "").strip()
        for row in final_rows
    )

    if empty_count:
        raise RuntimeError(
            f"Repair verification failed: "
            f"{empty_count} empty fields remain."
        )

    print("\n--- FINAL VERIFICATION ---")
    print("Meeting items:", len(final_rows))
    print("Text fields repaired:", len(repairs))
    print("Empty text fields remaining:", empty_count)

    print("\nSQLITE MEETING REPAIR: PASS")
    print("Other meetings unchanged.")
    print("No Gemini or HubSpot API requests made.")


# ==================================================
# 6. COMMAND LINE
# ==================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the verified repair to SQLite"
    )

    args = parser.parse_args()

    main(apply_changes=args.apply)
