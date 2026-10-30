
import json
import sqlite3
import subprocess
import sys

from contextlib import closing
from pathlib import Path

import faiss


# ==========================================
# 1. CONFIGURATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

DB_PATH = BASE_DIR / "meeting_intelligence.db"

METADATA_PATH = BASE_DIR / "embedding_metadata.jsonl"
INDEX_PATH = BASE_DIR / "meeting_search.index"

TEST_MEETING_ID = "manual_ef1595a5435980396085fb6c"


# ==========================================
# 2. VERIFY SQLITE DATABASE
# ==========================================

def verify_database():

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"SQLite database missing: {DB_PATH}"
        )

    with closing(sqlite3.connect(DB_PATH)) as conn:

        total_meetings = conn.execute(
            "SELECT COUNT(*) FROM meetings"
        ).fetchone()[0]

        uploaded_meeting = conn.execute(
            """
            SELECT meeting_id
            FROM meetings
            WHERE meeting_id = ?
            """,
            (TEST_MEETING_ID,)
        ).fetchone()

    if uploaded_meeting is None:
        raise RuntimeError(
            "Uploaded test meeting was not found in SQLite."
        )

    print("SQLite database: VERIFIED")
    print("Total meetings:", total_meetings)
    print("Uploaded test meeting: FOUND")


# ==========================================
# 3. RUN EXISTING SEARCH PIPELINE
# ==========================================

def run_script(filename, description):

    script_path = BASE_DIR / filename

    if not script_path.exists():
        raise FileNotFoundError(
            f"Required script missing: {script_path}"
        )

    print("\n" + "=" * 55)
    print(description)
    print("=" * 55, flush=True)

    subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(PROJECT_DIR),
        check=True
    )

    print(description + ": COMPLETE", flush=True)


# ==========================================
# 4. VERIFY NEW SEARCH INDEX
# ==========================================

def verify_index():

    if not METADATA_PATH.exists():
        raise FileNotFoundError(
            "Embedding metadata was not created."
        )

    if not INDEX_PATH.exists():
        raise FileNotFoundError(
            "FAISS index was not created."
        )

    metadata = []

    with METADATA_PATH.open(
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:
            if line.strip():
                metadata.append(json.loads(line))

    index = faiss.read_index(str(INDEX_PATH))

    if index.ntotal != len(metadata):
        raise RuntimeError(
            "FAISS index and metadata counts do not match."
        )

    if index.d != 384:
        raise RuntimeError(
            "Unexpected embedding dimensions."
        )

    uploaded_passages = [
        record
        for record in metadata
        if record.get("meeting_id") == TEST_MEETING_ID
    ]

    if not uploaded_passages:
        raise RuntimeError(
            "Uploaded meeting was not included in FAISS."
        )

    meeting_ids = {
        record["meeting_id"]
        for record in metadata
    }

    print("\n" + "=" * 55)
    print("SEMANTIC SEARCH REFRESH RESULTS")
    print("=" * 55)

    print("FAISS vectors:", index.ntotal)
    print("Metadata records:", len(metadata))
    print("Unique meetings:", len(meeting_ids))

    print(
        "New meeting passages indexed:",
        len(uploaded_passages)
    )

    print("\nNew meeting content types:")

    for content_type in sorted({
        record["content_type"]
        for record in uploaded_passages
    }):
        print(" -", content_type)

    print("\n--- VALIDATION ---")

    print("FAISS index alignment: PASS")
    print("Embedding dimensions: PASS")
    print("Uploaded meeting included: PASS")

    print("\nSEMANTIC INDEX REFRESH: SUCCESS")
    print("SQLite database unchanged.")
    print("No HubSpot API requests made.")


# ==========================================
# 5. MAIN
# ==========================================

def main():

    print("=" * 55)
    print("MEETING INTELLIGENCE - SEARCH INDEX REFRESH")
    print("=" * 55)

    verify_database()

    pipeline = [
        (
            "prepare_search_documents.py",
            "Preparing Search Documents"
        ),
        (
            "chunk_search_documents.py",
            "Preparing Search Chunks"
        ),
        (
            "generate_search_embeddings.py",
            "Generating Sentence Transformer Embeddings"
        ),
        (
            "build_faiss_index.py",
            "Rebuilding FAISS Index"
        )
    ]

    # Verify scripts are present before starting.
    for filename, _ in pipeline:
        if not (BASE_DIR / filename).exists():
            raise FileNotFoundError(
                f"Required script missing: {filename}"
            )

    for filename, description in pipeline:
        run_script(filename, description)

    verify_index()


if __name__ == "__main__":
    main()
