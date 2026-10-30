
import json
import sqlite3
import tempfile
import uuid

from contextlib import closing
from pathlib import Path


# ==================================================
# 1. DATABASE CONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "meeting_intelligence.db"


# ==================================================
# 2. EXTRACTION FIELD MAPPING
# ==================================================

# Gemini uses different field names for different
# extraction categories.

ITEM_TEXT_FIELDS = {
    "decisions": (
        "decision",
        "text",
        "description",
    ),
    "commitments": (
        "commitment",
        "text",
        "description",
    ),
    "action_items": (
        "action",
        "text",
        "description",
    ),
    "risks": (
        "text",
        "risk",
        "description",
    ),
    "objections": (
        "objection",
        "text",
        "description",
    ),
    "unanswered_questions": (
        "question",
        "text",
        "description",
    ),
}


# ==================================================
# 3. VALUE NORMALIZATION
# ==================================================

def clean_text(value):
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def clean_confidence(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_item_text(item, category):
    """
    Extract the actual content for each category.

    Supports both category-specific keys and the
    generic 'text' key.
    """

    if isinstance(item, str):
        return clean_text(item)

    if not isinstance(item, dict):
        return None

    for field in ITEM_TEXT_FIELDS[category]:
        value = clean_text(item.get(field))

        if value:
            return value

    return None


def format_evidence(value):
    """
    Store evidence references as JSON text.
    """

    if value is None:
        return json.dumps([])

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError:
            return json.dumps([value], ensure_ascii=False)

    return json.dumps(value, ensure_ascii=False)


# ==================================================
# 4. NORMALIZE MEETING SUMMARY
# ==================================================

def prepare_summary(prediction):

    summary = prediction.get("summary", {})

    if isinstance(summary, dict):
        summary_text = clean_text(
            summary.get("text")
            or summary.get("summary")
        )

        summary_confidence = clean_confidence(
            summary.get("confidence")
        )

    else:
        summary_text = clean_text(summary)

        summary_confidence = clean_confidence(
            prediction.get("summary_confidence")
        )

    overall_confidence = clean_confidence(
        prediction.get("overall_confidence")
    )

    requires_review = int(
        bool(prediction.get("requires_human_review", False))
    )

    return (
        summary_text,
        summary_confidence,
        overall_confidence,
        requires_review,
    )


# ==================================================
# 5. PREPARE EXTRACTED ITEMS
# ==================================================

def prepare_items(meeting_id, prediction):

    rows = []

    for category in ITEM_TEXT_FIELDS:

        extracted = prediction.get(category, [])

        if extracted is None:
            continue

        if not isinstance(extracted, list):
            raise ValueError(
                f"Expected a list for category: {category}"
            )

        for position, item in enumerate(extracted):

            text = extract_item_text(item, category)

            # Never silently save an empty extraction.
            if not text:
                raise ValueError(
                    f"Missing text in {category} "
                    f"at position {position}. "
                    "Meeting was not saved."
                )

            if isinstance(item, dict):

                owner = clean_text(
                    item.get("owner")
                    or item.get("assigned_to")
                    or item.get("raised_by")
                )

                deadline = clean_text(
                    item.get("deadline")
                    or item.get("due_date")
                )

                confidence = clean_confidence(
                    item.get("confidence")
                )

                evidence = format_evidence(
                    item.get("evidence_turn_ids", [])
                )

            else:

                owner = None
                deadline = None
                confidence = None
                evidence = format_evidence([])

            rows.append((
                meeting_id,
                category,
                text,
                owner,
                deadline,
                confidence,
                evidence,
            ))

    return rows


# ==================================================
# 6. SAVE MEETING TO SQLITE
# ==================================================

def save_meeting_to_db(meeting_id, prediction):
    """
    Save a newly extracted meeting atomically.

    Safety:
    - Checks meeting ID
    - Prevents duplicate meetings
    - Validates extracted text before writing
    - Uses one SQLite transaction
    - Does not modify existing meeting records
    """

    meeting_id = clean_text(meeting_id)

    if not meeting_id:
        raise ValueError("Meeting ID cannot be empty")

    if not isinstance(prediction, dict):
        raise TypeError(
            "Prediction must be a dictionary"
        )

    summary_data = prepare_summary(prediction)

    item_rows = prepare_items(
        meeting_id,
        prediction
    )

    with closing(
        sqlite3.connect(DB_PATH, timeout=30)
    ) as conn:

        with conn:

            conn.execute("BEGIN IMMEDIATE")

            existing = conn.execute(
                """
                SELECT 1
                FROM meetings
                WHERE meeting_id = ?
                """,
                (meeting_id,)
            ).fetchone()

            if existing:
                return {
                    "status": "already_exists",
                    "meeting_id": meeting_id,
                    "items_saved": 0,
                }

            conn.execute(
                """
                INSERT INTO meetings (
                    meeting_id,
                    summary,
                    summary_confidence,
                    overall_confidence,
                    requires_human_review
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    meeting_id,
                    *summary_data,
                )
            )

            if item_rows:

                conn.executemany(
                    """
                    INSERT INTO meeting_items (
                        meeting_id,
                        item_type,
                        text,
                        owner,
                        deadline,
                        confidence,
                        evidence_turn_ids
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    item_rows
                )

    return {
        "status": "saved",
        "meeting_id": meeting_id,
        "items_saved": len(item_rows),
    }


# ==================================================
# 7. SAFE SELF-TEST ON A TEMPORARY DATABASE COPY
# ==================================================

def self_test():

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    print("=" * 55)
    print("SQLITE MEETING SAVE - FIELD MAPPING TEST")
    print("=" * 55)

    test_prediction = {
        "summary": {
            "text": "A fictional product planning meeting.",
            "confidence": 0.95,
        },
        "overall_confidence": 0.90,
        "requires_human_review": False,

        "decisions": [
            {
                "decision": "Approve the product design.",
                "confidence": 0.95,
                "evidence_turn_ids": [1],
            }
        ],

        "commitments": [
            {
                "commitment": "Finish dashboard testing.",
                "owner": "Rahul",
                "deadline": "November 5, 2026",
                "confidence": 0.90,
                "evidence_turn_ids": [2],
            }
        ],

        "action_items": [
            {
                "action": "Review payment integration.",
                "confidence": 0.90,
                "evidence_turn_ids": [3],
            }
        ],

        "risks": [
            {
                "text": "Payment integration may be delayed.",
                "confidence": 0.85,
                "evidence_turn_ids": [4],
            }
        ],

        "objections": [
            {
                "objection": "The proposed launch is too early.",
                "confidence": 0.90,
                "evidence_turn_ids": [5],
            }
        ],

        "unanswered_questions": [
            {
                "question": "What is the advertising budget?",
                "confidence": 0.95,
                "evidence_turn_ids": [6],
            }
        ],
    }

    # Copy the real database; never write test data to it.
    with tempfile.TemporaryDirectory() as folder:

        test_db = Path(folder) / "save_test.db"

        with closing(sqlite3.connect(DB_PATH)) as source:
            with closing(sqlite3.connect(test_db)) as target:
                source.backup(target)

        global_path = globals()["DB_PATH"]

        globals()["DB_PATH"] = test_db

        try:
            test_id = "SAVE_TEST_" + uuid.uuid4().hex[:12]

            result = save_meeting_to_db(
                test_id,
                test_prediction
            )

            assert result["status"] == "saved"
            assert result["items_saved"] == 6

            # Verify saved text, not only row counts.
            with closing(sqlite3.connect(test_db)) as conn:
                rows = conn.execute(
                    """
                    SELECT item_type, text
                    FROM meeting_items
                    WHERE meeting_id = ?
                    ORDER BY item_type
                    """,
                    (test_id,)
                ).fetchall()

            assert len(rows) == 6

            for category, text in rows:
                assert text and text.strip(), (
                    f"Empty text found in {category}"
                )

            # Verify duplicate protection.
            second_result = save_meeting_to_db(
                test_id,
                test_prediction
            )

            assert (
                second_result["status"] == "already_exists"
            )

            print("Meeting insertion: PASS")
            print("Six extraction categories: PASS")
            print("Nonempty item text: 6 of 6")
            print("Duplicate prevention: PASS")
            print("SQLite transaction test: PASS")

        finally:
            globals()["DB_PATH"] = global_path

    print("\nSAVE FUNCTION TEST: PASS")
    print("Temporary database removed.")
    print("Original SQLite database unchanged.")
    print("No Gemini or HubSpot requests made.")


# ==================================================
# 8. COMMAND LINE TEST
# ==================================================

if __name__ == "__main__":
    self_test()
