
import json
import hmac
import hashlib
import sqlite3
import tempfile

from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from fastapi.testclient import TestClient

import fireflies_webhook as webhook


# ============================================================
# 1. TEST CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

REAL_DB = (
    BASE_DIR / "phase3" / "meeting_intelligence.db"
)

TEST_SECRET = "local-test-secret-2026"

TEST_MEETING_ID = "FIREFLIES_ENDPOINT_TEST_2026"


# ============================================================
# 2. GENERATE A VALID SIGNATURE
# ============================================================

def generate_signature(raw_body):

    digest = hmac.new(
        TEST_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    return "sha256=" + digest


# ============================================================
# 3. SEND A SIGNED TEST EVENT
# ============================================================

def signed_request(client, payload):

    raw_body = json.dumps(
        payload
    ).encode("utf-8")

    return client.post(
        "/webhook/fireflies",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature": generate_signature(
                raw_body
            )
        }
    )


# ============================================================
# 4. RUN ENDPOINT TESTS
# ============================================================

def run_tests():

    print("=" * 60)
    print("FIREFLIES WEBHOOK - SIGNED ENDPOINT TEST")
    print("=" * 60)

    if not REAL_DB.is_file():
        raise FileNotFoundError(
            f"Database missing: {REAL_DB}"
        )

    # Test against a temporary copy of SQLite.
    # The real database is never written to.

    with tempfile.TemporaryDirectory() as folder:

        temporary_db = (
            Path(folder) / "test_webhook.db"
        )

        with closing(
            sqlite3.connect(REAL_DB)
        ) as source:

            with closing(
                sqlite3.connect(temporary_db)
            ) as destination:

                source.backup(destination)

        # Redirect webhook database connections to
        # the temporary database.

        with (
            patch.object(
                webhook,
                "DB_PATH",
                temporary_db
            ),
            patch.dict(
                webhook.os.environ,
                {
                    "FIREFLIES_WEBHOOK_SECRET":
                        TEST_SECRET
                }
            ),
            patch.object(
                webhook,
                "process_meeting_background"
            ) as mock_background
        ):

            client = TestClient(webhook.app)

            # ------------------------------------------
            # TEST 1: Health check
            # ------------------------------------------

            response = client.get("/")

            assert response.status_code == 200
            assert response.json()["status"] == "online"

            print("Health endpoint: PASS")

            # ------------------------------------------
            # TEST 2: Valid signed transcription
            # ------------------------------------------

            payload = {
                "event": "meeting.transcribed",
                "meeting_id": TEST_MEETING_ID
            }

            response = signed_request(
                client,
                payload
            )

            assert response.status_code == 202, (
                response.text
            )

            assert (
                response.json()["status"]
                == "accepted"
            )

            assert (
                response.json()["meeting_id"]
                == TEST_MEETING_ID
            )

            print("Valid signed webhook accepted: PASS")

            # Background worker is mocked. No Gemini,
            # Fireflies or FAISS processing is run.

            mock_background.assert_called_once_with(
                TEST_MEETING_ID
            )

            print("Background task scheduled: PASS")

            # ------------------------------------------
            # TEST 3: Duplicate webhook
            # ------------------------------------------

            response = signed_request(
                client,
                payload
            )

            assert response.status_code == 202

            assert (
                response.json()["status"]
                == "already_processing"
            )

            assert mock_background.call_count == 1

            print("Duplicate event protection: PASS")

            # ------------------------------------------
            # TEST 4: Invalid signature
            # ------------------------------------------

            response = client.post(
                "/webhook/fireflies",
                json=payload,
                headers={
                    "X-Hub-Signature": "sha256=invalid"
                }
            )

            assert response.status_code == 401

            print("Invalid signature blocked: PASS")

            # ------------------------------------------
            # TEST 5: Unrelated event
            # ------------------------------------------

            response = signed_request(
                client,
                {
                    "event": "meeting.summarized",
                    "meeting_id": "IGNORED_MEETING"
                }
            )

            assert response.status_code == 202

            assert (
                response.json()["status"]
                == "ignored"
            )

            print("Unrelated event ignored: PASS")

            # ------------------------------------------
            # TEST 6: Missing meeting ID
            # ------------------------------------------

            response = signed_request(
                client,
                {
                    "event": "meeting.transcribed"
                }
            )

            assert response.status_code == 400

            print("Missing meeting ID rejected: PASS")

            # ------------------------------------------
            # TEST 7: Verify queued job in SQLite
            # ------------------------------------------

            with closing(
                sqlite3.connect(temporary_db)
            ) as conn:

                row = conn.execute(
                    """
                    SELECT
                        status,
                        attempts
                    FROM fireflies_webhook_jobs
                    WHERE meeting_id = ?
                    """,
                    (TEST_MEETING_ID,)
                ).fetchone()

            assert row is not None
            assert row[0] == "queued"
            assert row[1] == 1

            print("Webhook job history created: PASS")

    # Temporary database is now automatically
    # deleted. Original SQLite is unchanged.

    print("\n" + "=" * 60)
    print("FINAL TEST RESULTS")
    print("=" * 60)

    print("Signed HTTP endpoint: PASS")
    print("Background task scheduling: PASS")
    print("Duplicate prevention: PASS")
    print("Job history persistence: PASS")
    print("Request validation: PASS")

    print("\nFIREFLIES ENDPOINT TEST: PASS")

    print("\nReal SQLite database unchanged.")
    print("No Fireflies API requests made.")
    print("No Gemini API requests made.")
    print("No FAISS index rebuild performed.")
    print("No HubSpot API requests made.")


# ============================================================
# 5. EXECUTION
# ============================================================

if __name__ == "__main__":
    run_tests()
