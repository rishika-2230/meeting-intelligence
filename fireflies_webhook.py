
import os
import sys
import json
import hmac
import hashlib
import logging
import re
import sqlite3
import subprocess
import threading

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks


# ============================================================
# 1. PROJECT CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
PHASE3_DIR = BASE_DIR / "phase3"

DB_PATH = PHASE3_DIR / "meeting_intelligence.db"

REFRESH_SCRIPT = PHASE3_DIR / "refresh_semantic_index.py"

METADATA_PATH = PHASE3_DIR / "embedding_metadata.jsonl"

INDEX_PATH = PHASE3_DIR / "meeting_search.index"

load_dotenv(BASE_DIR / ".env")

if str(PHASE3_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE3_DIR))

from fireflies_pipeline import process_fireflies_meeting


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(
    "meeting_intelligence_fireflies"
)

app = FastAPI(
    title="Meeting Intelligence Fireflies Webhook",
    version="2.0"
)

# Serialize processing and index rebuilding inside
# this single-server local deployment.
processing_lock = threading.Lock()

MAX_WEBHOOK_BYTES = 256 * 1024

MEETING_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{1,128}$"
)


# ============================================================
# 2. TIME AND DATABASE HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def connect_database():

    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"SQLite database not found: {DB_PATH}"
        )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA busy_timeout = 30000"
    )

    return conn


# ============================================================
# 3. WEBHOOK PROCESSING HISTORY TABLE
# ============================================================

def initialize_webhook_jobs():
    """
    Add an independent job-tracking table.

    Does not change existing meetings,
    meeting_items, CRM records, or approvals.
    """

    with closing(connect_database()) as conn:

        with conn:

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS
                fireflies_webhook_jobs (
                    meeting_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL
                        CHECK (
                            status IN (
                                'queued',
                                'processing',
                                'indexed',
                                'failed'
                            )
                        ),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )


def meeting_exists(meeting_id):

    with closing(connect_database()) as conn:

        row = conn.execute(
            """
            SELECT 1
            FROM meetings
            WHERE meeting_id = ?
            """,
            (meeting_id,)
        ).fetchone()

    return row is not None


# ============================================================
# 4. CHECK SEARCH METADATA
# ============================================================

def is_meeting_indexed(meeting_id):
    """
    Verify whether search metadata contains
    at least one passage for this meeting.

    This is a quick check, not full FAISS validation.
    """

    if not METADATA_PATH.is_file():
        return False

    if not INDEX_PATH.is_file():
        return False

    with METADATA_PATH.open(
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            if not line.strip():
                continue

            record = json.loads(line)

            if record.get("meeting_id") == meeting_id:
                return True

    return False


# ============================================================
# 5. VERIFY FIREFLIES WEBHOOK SIGNATURE
# ============================================================

def verify_webhook_signature(
    raw_body,
    received_signature,
    secret
):
    """
    Fireflies V2:
    X-Hub-Signature: sha256=<digest>

    HMAC is calculated over the original raw body.
    """

    if not secret:
        return False

    if not received_signature:
        return False

    expected_signature = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256
        ).hexdigest()
    )

    return hmac.compare_digest(
        received_signature,
        expected_signature
    )


# ============================================================
# 6. VALIDATE WEBHOOK PAYLOAD
# ============================================================

def validate_payload(raw_body):

    try:
        payload = json.loads(
            raw_body.decode("utf-8")
        )

    except (UnicodeDecodeError, ValueError):
        raise ValueError(
            "Invalid JSON payload"
        )

    if not isinstance(payload, dict):
        raise ValueError(
            "Webhook payload must be a JSON object"
        )

    event = payload.get("event")

    if not isinstance(event, str):
        raise ValueError(
            "Missing or invalid event"
        )

    if event != "meeting.transcribed":
        return {
            "event": event,
            "meeting_id": None,
            "ignored": True
        }

    meeting_id = payload.get("meeting_id")

    if not isinstance(meeting_id, str):
        raise ValueError(
            "Missing or invalid meeting_id"
        )

    meeting_id = meeting_id.strip()

    if not MEETING_ID_PATTERN.fullmatch(meeting_id):
        raise ValueError(
            "Meeting ID contains invalid characters"
        )

    return {
        "event": event,
        "meeting_id": meeting_id,
        "ignored": False
    }


# ============================================================
# 7. QUEUE A MEETING SAFELY
# ============================================================

def queue_meeting(meeting_id):
    """
    Prevent duplicate processing.

    If a meeting is already saved AND indexed,
    there is no need to process it again.

    Failed jobs can be queued again by a
    newly received signed webhook event.
    """

    initialize_webhook_jobs()

    with closing(connect_database()) as conn:

        try:

            conn.execute("BEGIN IMMEDIATE")

            job = conn.execute(
                """
                SELECT status, attempts
                FROM fireflies_webhook_jobs
                WHERE meeting_id = ?
                """,
                (meeting_id,)
            ).fetchone()

            saved = conn.execute(
                """
                SELECT 1
                FROM meetings
                WHERE meeting_id = ?
                """,
                (meeting_id,)
            ).fetchone() is not None

            indexed = (
                is_meeting_indexed(meeting_id)
                if saved
                else False
            )

            if saved and indexed:

                conn.rollback()

                return "already_indexed"

            if job is not None:

                if job["status"] in (
                    "queued",
                    "processing"
                ):

                    conn.rollback()

                    return "already_processing"

                conn.execute(
                    """
                    UPDATE fireflies_webhook_jobs
                    SET status = 'queued',
                        attempts = attempts + 1,
                        last_error = NULL,
                        updated_at = ?
                    WHERE meeting_id = ?
                    """,
                    (
                        utc_now(),
                        meeting_id
                    )
                )

            else:

                now = utc_now()

                conn.execute(
                    """
                    INSERT INTO fireflies_webhook_jobs (
                        meeting_id,
                        status,
                        attempts,
                        last_error,
                        created_at,
                        updated_at
                    )
                    VALUES (?, 'queued', 1, NULL, ?, ?)
                    """,
                    (
                        meeting_id,
                        now,
                        now
                    )
                )

            conn.commit()

            return "accepted"

        except Exception:

            conn.rollback()
            raise


# ============================================================
# 8. UPDATE WEBHOOK JOB STATUS
# ============================================================

def update_job_status(
    meeting_id,
    status,
    last_error=None
):

    allowed = {
        "processing",
        "indexed",
        "failed"
    }

    if status not in allowed:
        raise ValueError(
            "Invalid webhook processing status"
        )

    if last_error is not None:
        last_error = str(last_error)[:500]

    with closing(connect_database()) as conn:

        with conn:

            conn.execute(
                """
                UPDATE fireflies_webhook_jobs
                SET status = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE meeting_id = ?
                """,
                (
                    status,
                    last_error,
                    utc_now(),
                    meeting_id
                )
            )


# ============================================================
# 9. REBUILD SEMANTIC SEARCH INDEX
# ============================================================

def rebuild_semantic_index(meeting_id):
    """
    Reuse the previously tested full FAISS
    refresh pipeline.

    The pipeline handles:
    - Search document preparation
    - Text chunking
    - Sentence Transformer embeddings
    - FAISS index generation

    Verify the target meeting after rebuilding.
    """

    if not REFRESH_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Refresh script missing: {REFRESH_SCRIPT}"
        )

    logger.info(
        "Starting semantic search refresh for %s",
        meeting_id
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(REFRESH_SCRIPT)
        ],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=300,
        check=False
    )

    if completed.returncode != 0:

        logger.error(
            "Search refresh failed for %s; "
            "exit code: %s",
            meeting_id,
            completed.returncode
        )

        # Show diagnostic output only in local
        # server logs, not webhook responses.
        logger.error(
            "Refresh stderr (last 2000 chars): %s",
            completed.stderr[-2000:]
        )

        raise RuntimeError(
            "Semantic search refresh pipeline failed"
        )

    if not (
        METADATA_PATH.is_file()
        and INDEX_PATH.is_file()
    ):

        raise RuntimeError(
            "Search index or metadata is missing"
        )

    import faiss

    index = faiss.read_index(
        str(INDEX_PATH)
    )

    metadata_count = 0
    new_meeting_count = 0

    with METADATA_PATH.open(
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            if not line.strip():
                continue

            record = json.loads(line)

            metadata_count += 1

            if record.get("meeting_id") == meeting_id:
                new_meeting_count += 1

    if index.ntotal != metadata_count:
        raise RuntimeError(
            "FAISS index and metadata counts "
            "do not match"
        )

    if index.d != 384:
        raise RuntimeError(
            "Unexpected embedding dimension"
        )

    if new_meeting_count == 0:
        raise RuntimeError(
            "The new meeting was not included "
            "in the search index"
        )

    logger.info(
        "Index refresh completed: meeting=%s, "
        "new passages=%s, total passages=%s",
        meeting_id,
        new_meeting_count,
        metadata_count
    )

    return {
        "meeting_id": meeting_id,
        "new_meeting_passages": new_meeting_count,
        "total_passages": metadata_count
    }


# ============================================================
# 10. PROCESS FIREFLIES MEETING
# ============================================================

def process_meeting_background(meeting_id):
    """
    Complete end-to-end workflow:

    Fireflies API / Gemini -> SQLite -> FAISS

    Existing meetings are not extracted again.

    HubSpot synchronization is intentionally
    excluded from this process.
    """

    with processing_lock:

        try:

            update_job_status(
                meeting_id,
                "processing"
            )

            logger.info(
                "Processing Fireflies meeting: %s",
                meeting_id
            )

            # --------------------------------------------
            # STAGE 1: EXTRACT AND SAVE
            # --------------------------------------------

            if meeting_exists(meeting_id):

                logger.info(
                    "Meeting already exists in SQLite: %s",
                    meeting_id
                )

            else:

                result = process_fireflies_meeting(
                    meeting_id
                )

                logger.info(
                    "Fireflies pipeline returned "
                    "for meeting %s: %s",
                    meeting_id,
                    type(result).__name__
                )

                if not meeting_exists(meeting_id):
                    raise RuntimeError(
                        "Fireflies pipeline returned "
                        "without saving a meeting"
                    )

            # --------------------------------------------
            # STAGE 2: REFRESH FAISS
            # --------------------------------------------

            if is_meeting_indexed(meeting_id):

                logger.info(
                    "Meeting is already indexed: %s",
                    meeting_id
                )

            else:

                rebuild_semantic_index(
                    meeting_id
                )

            # --------------------------------------------
            # STAGE 3: FINAL VALIDATION
            # --------------------------------------------

            if not meeting_exists(meeting_id):
                raise RuntimeError(
                    "Meeting is missing from SQLite"
                )

            if not is_meeting_indexed(meeting_id):
                raise RuntimeError(
                    "Meeting is missing from "
                    "search metadata"
                )

            update_job_status(
                meeting_id,
                "indexed"
            )

            logger.info(
                "FIREFLIES AUTOMATION SUCCESS: %s",
                meeting_id
            )

        except Exception as error:

            logger.exception(
                "Fireflies automation failed: %s",
                meeting_id
            )

            # A successful SQLite save is preserved
            # even if search indexing fails.
            try:

                update_job_status(
                    meeting_id,
                    "failed",
                    type(error).__name__
                )

            except Exception:

                logger.exception(
                    "Unable to update job failure status"
                )


# ============================================================
# 11. HEALTH CHECK
# ============================================================

@app.get("/")
def health_check():

    return {
        "status": "online",
        "service": "Meeting Intelligence Fireflies Webhook",
        "version": "2.0"
    }


# ============================================================
# 12. FIREFLIES V2 WEBHOOK ENDPOINT
# ============================================================

@app.post("/webhook/fireflies", status_code=202)
async def fireflies_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):

    secret = os.getenv(
        "FIREFLIES_WEBHOOK_SECRET",
        ""
    )

    if not secret:

        logger.error(
            "Fireflies webhook signing secret missing"
        )

        raise HTTPException(
            status_code=500,
            detail="Webhook configuration missing"
        )

    # --------------------------------------------
    # READ ORIGINAL BODY
    # --------------------------------------------

    raw_body = await request.body()

    if len(raw_body) > MAX_WEBHOOK_BYTES:

        raise HTTPException(
            status_code=413,
            detail="Webhook payload too large"
        )

    # --------------------------------------------
    # VERIFY AUTHENTICITY
    # --------------------------------------------

    received_signature = request.headers.get(
        "X-Hub-Signature",
        ""
    )

    if not verify_webhook_signature(
        raw_body,
        received_signature,
        secret
    ):

        logger.warning(
            "Rejected webhook with invalid signature"
        )

        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature"
        )

    # --------------------------------------------
    # VALIDATE PAYLOAD
    # --------------------------------------------

    try:

        payload = validate_payload(
            raw_body
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    event = payload["event"]

    if payload["ignored"]:

        logger.info(
            "Ignoring Fireflies event: %s",
            event
        )

        return {
            "status": "ignored",
            "event": event
        }

    meeting_id = payload["meeting_id"]

    logger.info(
        "Verified Fireflies transcription event: %s",
        meeting_id
    )

    # --------------------------------------------
    # QUEUE OR SKIP DUPLICATE
    # --------------------------------------------

    try:

        status = queue_meeting(
            meeting_id
        )

    except Exception:

        logger.exception(
            "Could not queue Fireflies meeting"
        )

        raise HTTPException(
            status_code=503,
            detail="Meeting queue unavailable"
        )

    if status == "already_indexed":

        return {
            "status": "already_indexed",
            "meeting_id": meeting_id
        }

    if status == "already_processing":

        return {
            "status": "already_processing",
            "meeting_id": meeting_id
        }

    # --------------------------------------------
    # START BACKGROUND PROCESSING
    # --------------------------------------------

    background_tasks.add_task(
        process_meeting_background,
        meeting_id
    )

    logger.info(
        "Fireflies meeting queued: %s",
        meeting_id
    )

    return {
        "status": "accepted",
        "meeting_id": meeting_id,
        "message": (
            "Meeting queued for extraction, "
            "database saving and semantic indexing"
        )
    }


# ============================================================
# 13. LOCAL SELF-TEST
# ============================================================

def run_self_test():
    """
    Test webhook authentication and payload parsing.

    Does not:
    - Access the Fireflies API
    - Call Gemini
    - Update SQLite
    - Rebuild FAISS
    - Contact HubSpot
    """

    print("=" * 60)
    print("FIREFLIES WEBHOOK - LOCAL SAFETY TEST")
    print("=" * 60)

    test_secret = "local-test-secret-not-for-production"

    test_payload = {
        "event": "meeting.transcribed",
        "meeting_id": "TEST_MEETING_123",
        "timestamp": 1234567890
    }

    raw_body = json.dumps(
        test_payload
    ).encode("utf-8")

    signature = (
        "sha256="
        + hmac.new(
            test_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256
        ).hexdigest()
    )

    assert verify_webhook_signature(
        raw_body,
        signature,
        test_secret
    )

    print("Valid HMAC signature: PASS")

    assert not verify_webhook_signature(
        raw_body + b"x",
        signature,
        test_secret
    )

    print("Tampered body rejection: PASS")

    assert not verify_webhook_signature(
        raw_body,
        "sha256=invalid",
        test_secret
    )

    print("Invalid signature rejection: PASS")

    parsed = validate_payload(
        raw_body
    )

    assert (
        parsed["meeting_id"]
        == "TEST_MEETING_123"
    )

    assert parsed["ignored"] is False

    print("Meeting ID extraction: PASS")
    print("Transcription event validation: PASS")

    ignored_payload = json.dumps({
        "event": "meeting.summarized",
        "meeting_id": "TEST_MEETING_123"
    }).encode("utf-8")

    ignored_result = validate_payload(
        ignored_payload
    )

    assert ignored_result["ignored"] is True

    print("Unsubscribed event filtering: PASS")

    try:

        validate_payload(
            json.dumps({
                "event": "meeting.transcribed",
                "meeting_id": "../invalid"
            }).encode("utf-8")
        )

        raise AssertionError(
            "Invalid meeting ID was accepted"
        )

    except ValueError:
        pass

    print("Invalid meeting ID rejection: PASS")

    print("\nFIREFLIES WEBHOOK SELF-TEST: PASS")

    print("No Fireflies API requests made.")
    print("No Gemini API requests made.")
    print("SQLite database unchanged.")
    print("No HubSpot API requests made.")


# ============================================================
# 14. COMMAND LINE
# ============================================================

if __name__ == "__main__":

    if "--self-test" in sys.argv:

        run_self_test()

    else:

        print(
            "Start this webhook server using:"
        )

        print(
            "python -m uvicorn "
            "fireflies_webhook:app "
            "--host 127.0.0.1 --port 8000"
        )
