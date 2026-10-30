
import sqlite3

from contextlib import closing

from fireflies_client import fetch_fireflies_transcript
from convert_fireflies_transcript import normalize_fireflies_transcript
from run_fireflies_meeting import extract_meeting_intelligence
from save_fireflies_to_db import save_meeting_to_db


# ============================================================
# 1. CHECK WHETHER MEETING EXISTS
# ============================================================

def meeting_exists(meeting_id):
    """
    Check SQLite for a previously processed meeting.

    The connection is explicitly closed to avoid
    Windows file-locking errors.
    """

    from save_fireflies_to_db import DB_PATH

    with closing(
        sqlite3.connect(DB_PATH, timeout=30)
    ) as conn:

        existing = conn.execute(
            """
            SELECT 1
            FROM meetings
            WHERE meeting_id = ?
            LIMIT 1
            """,
            (meeting_id,)
        ).fetchone()

    return existing is not None


# ============================================================
# 2. PROCESS FIREFLIES MEETING
# ============================================================

def process_fireflies_meeting(meeting_id):
    """
    Retrieve a Fireflies meeting, extract intelligence
    using Gemini, and save the results to SQLite.

    Duplicate meetings are not processed again.

    This function does not:
    - Update FAISS directly
    - Synchronize records to HubSpot

    Those operations are handled separately.
    """

    # --------------------------------------------------------
    # VALIDATE MEETING ID
    # --------------------------------------------------------

    if not isinstance(meeting_id, str):
        raise ValueError(
            "Meeting ID must be a string."
        )

    meeting_id = meeting_id.strip()

    if not meeting_id:
        raise ValueError(
            "Meeting ID is required."
        )

    # --------------------------------------------------------
    # CHECK FOR DUPLICATES
    # --------------------------------------------------------

    if meeting_exists(meeting_id):

        return {
            "status": "already_exists",
            "meeting_id": meeting_id,
            "items_added": 0
        }

    # --------------------------------------------------------
    # FETCH FIREFLIES TRANSCRIPT
    # --------------------------------------------------------

    meeting = fetch_fireflies_transcript(
        meeting_id
    )

    if meeting is None:
        raise RuntimeError(
            "Fireflies did not return a transcript."
        )

    # --------------------------------------------------------
    # NORMALIZE TRANSCRIPT
    # --------------------------------------------------------

    transcript_text = normalize_fireflies_transcript(
        meeting
    )

    if (
        not isinstance(transcript_text, str)
        or not transcript_text.strip()
    ):
        raise ValueError(
            "Meeting transcript is empty or invalid."
        )

    # --------------------------------------------------------
    # EXTRACT MEETING INTELLIGENCE
    # --------------------------------------------------------

    prediction = extract_meeting_intelligence(
        meeting_id,
        transcript_text
    )

    if not isinstance(prediction, dict):
        raise ValueError(
            "Gemini returned an invalid extraction format."
        )

    # --------------------------------------------------------
    # SAVE RESULTS TO SQLITE
    # --------------------------------------------------------

    result = save_meeting_to_db(
        meeting_id,
        prediction
    )

    # --------------------------------------------------------
    # VERIFY DATABASE PERSISTENCE
    # --------------------------------------------------------

    if not meeting_exists(meeting_id):
        raise RuntimeError(
            "Meeting extraction completed, "
            "but SQLite saving could not be verified."
        )

    return result


# ============================================================
# 3. MODULE INFORMATION
# ============================================================

if __name__ == "__main__":

    print(
        "Fireflies processing pipeline loaded successfully."
    )

    print(
        "This module is called by fireflies_webhook.py."
    )

    print(
        "Run test_fireflies_pipeline_integration.py "
        "to verify the complete processing workflow."
    )
