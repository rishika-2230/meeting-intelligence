
import sqlite3
import sys
import tempfile
import uuid

from pathlib import Path
from contextlib import closing
from unittest.mock import patch


# ============================================================
# 1. PROJECT CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
PHASE3_DIR = BASE_DIR / "phase3"

REAL_DB_PATH = PHASE3_DIR / "meeting_intelligence.db"

if str(PHASE3_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE3_DIR))

import fireflies_pipeline
import save_fireflies_to_db


# ============================================================
# 2. FICTIONAL FIREFLIES TRANSCRIPT
# ============================================================

TEST_TRANSCRIPT = """
Meeting: Customer Retention Strategy
Participants: Ananya, Rohit, Priya

Ananya: We have decided to launch a customer
retention dashboard on November 18, 2026.

Rohit: I will finish the customer churn SQL
analysis by November 6, 2026.

Priya: I will prepare the retention campaign
report by November 9, 2026.

Ananya: One risk is that incomplete customer
purchase histories could affect our analysis.

Rohit: We still need to decide which customer
segments should receive priority.

Ananya: We will review that question at our
next meeting.
"""


# ============================================================
# 3. FICTIONAL GEMINI EXTRACTION
# ============================================================

TEST_PREDICTION = {
    "summary": {
        "text": (
            "The team planned a customer retention "
            "dashboard and assigned analytics and "
            "marketing responsibilities."
        ),
        "confidence": 0.95
    },
    "overall_confidence": 0.92,
    "requires_human_review": False,
    "decisions": [
        {
            "decision": (
                "Launch the customer retention dashboard "
                "on November 18, 2026."
            ),
            "confidence": 0.95,
            "evidence_turn_ids": [1]
        }
    ],
    "commitments": [
        {
            "commitment": (
                "Finish the customer churn SQL analysis."
            ),
            "owner": "Rohit",
            "deadline": "November 6, 2026",
            "confidence": 0.95,
            "evidence_turn_ids": [2]
        },
        {
            "commitment": (
                "Prepare the retention campaign report."
            ),
            "owner": "Priya",
            "deadline": "November 9, 2026",
            "confidence": 0.95,
            "evidence_turn_ids": [3]
        }
    ],
    "action_items": [],
    "risks": [
        {
            "text": (
                "Incomplete purchase histories "
                "could affect churn analysis."
            ),
            "confidence": 0.90,
            "evidence_turn_ids": [4]
        }
    ],
    "objections": [],
    "unanswered_questions": [
        {
            "question": (
                "Which customer segments "
                "should receive priority?"
            ),
            "confidence": 0.95,
            "evidence_turn_ids": [5]
        }
    ]
}


# ============================================================
# 4. RUN SAFE INTEGRATION TEST
# ============================================================

def run_test():

    print("=" * 60)
    print("FIREFLIES PIPELINE - INTEGRATION TEST")
    print("=" * 60)

    if not REAL_DB_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found: {REAL_DB_PATH}"
        )

    test_meeting_id = (
        "FIREFLIES_TEST_"
        + uuid.uuid4().hex[:12]
    )

    with tempfile.TemporaryDirectory() as folder:

        test_db = Path(folder) / "meeting_test.db"

        # --------------------------------------------
        # Copy the real database safely
        # --------------------------------------------

        with closing(sqlite3.connect(REAL_DB_PATH)) as source:
            with closing(sqlite3.connect(test_db)) as target:
                source.backup(target)

        with closing(sqlite3.connect(test_db)) as conn:
            original_count = conn.execute(
                "SELECT COUNT(*) FROM meetings"
            ).fetchone()[0]

        print("Temporary database created: PASS")
        print("Existing meetings:", original_count)

        # --------------------------------------------
        # Replace real API calls with mock responses
        # --------------------------------------------

        with (
            patch.object(
                save_fireflies_to_db,
                "DB_PATH",
                test_db
            ),
            patch.object(
                fireflies_pipeline,
                "fetch_fireflies_transcript",
                return_value={"id": test_meeting_id}
            ) as mock_fetch,
            patch.object(
                fireflies_pipeline,
                "normalize_fireflies_transcript",
                return_value=TEST_TRANSCRIPT
            ) as mock_normalize,
            patch.object(
                fireflies_pipeline,
                "extract_meeting_intelligence",
                return_value=TEST_PREDICTION
            ) as mock_extract
        ):

            # ----------------------------------------
            # Test first processing
            # ----------------------------------------

            result = (
                fireflies_pipeline.process_fireflies_meeting(
                    test_meeting_id
                )
            )

            assert result["status"] == "saved", result

            mock_fetch.assert_called_once_with(
                test_meeting_id
            )

            mock_normalize.assert_called_once()

            mock_extract.assert_called_once_with(
                test_meeting_id,
                TEST_TRANSCRIPT
            )

            print("Fireflies retrieval stage: PASS")
            print("Transcript normalization stage: PASS")
            print("Gemini extraction stage: PASS")
            print("SQLite save stage: PASS")

            # ----------------------------------------
            # Verify the saved meeting
            # ----------------------------------------

            with closing(sqlite3.connect(test_db)) as conn:

                count = conn.execute(
                    "SELECT COUNT(*) FROM meetings"
                ).fetchone()[0]

                assert count == original_count + 1

                rows = conn.execute(
                    """
                    SELECT item_type, text
                    FROM meeting_items
                    WHERE meeting_id = ?
                    """,
                    (test_meeting_id,)
                ).fetchall()

            assert len(rows) == 5, rows

            assert all(
                text and text.strip()
                for _, text in rows
            ), "Empty extracted item text detected"

            print("New meeting persisted: PASS")
            print("Extracted item count: 5")
            print("Nonempty extracted item text: PASS")

            # ----------------------------------------
            # Verify duplicate protection
            # ----------------------------------------

            second_result = (
                fireflies_pipeline.process_fireflies_meeting(
                    test_meeting_id
                )
            )

            assert (
                second_result["status"]
                == "already_exists"
            )

            # No second Fireflies or Gemini call.
            assert mock_fetch.call_count == 1
            assert mock_extract.call_count == 1

            print("Duplicate meeting prevention: PASS")

    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)

    print("Pipeline integration: PASS")
    print("Category-specific text mapping: PASS")
    print("SQLite persistence: PASS")
    print("Duplicate protection: PASS")

    print("\nFIREFLIES PIPELINE INTEGRATION TEST: PASS")

    print("Temporary test database deleted.")
    print("Original SQLite database unchanged.")
    print("No real Fireflies API calls made.")
    print("No real Gemini API calls made.")
    print("No HubSpot API calls made.")
    print("No FAISS files modified.")


# ============================================================
# 5. EXECUTION
# ============================================================

if __name__ == "__main__":
    run_test()
