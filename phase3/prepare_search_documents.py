
import json
import sqlite3
from pathlib import Path
from contextlib import closing


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "meeting_intelligence.db"
OUTPUT_PATH = BASE_DIR / "search_documents.jsonl"


def prepare_documents():

    documents = []
    summary_count = 0
    item_count = 0

    # Read existing SQLite data without modifying it.
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row

        # -----------------------------------------
        # 1. Prepare meeting summaries
        # -----------------------------------------

        meetings = conn.execute("""
            SELECT
                meeting_id,
                summary,
                summary_confidence,
                overall_confidence
            FROM meetings
            ORDER BY meeting_id
        """).fetchall()

        for meeting in meetings:
            text = str(meeting["summary"] or "").strip()

            if not text:
                continue

            documents.append({
                "document_id": (
                    f"summary:{meeting['meeting_id']}"
                ),
                "meeting_id": meeting["meeting_id"],
                "content_type": "summary",
                "text": text,
                "confidence": meeting["summary_confidence"],
                "overall_confidence": meeting["overall_confidence"],
                "owner": None,
                "deadline": None,
                "evidence_turn_ids": None
            })

            summary_count += 1

        # -----------------------------------------
        # 2. Prepare extracted meeting items
        # -----------------------------------------

        items = conn.execute("""
            SELECT
                rowid AS source_rowid,
                meeting_id,
                item_type,
                text,
                owner,
                deadline,
                confidence,
                evidence_turn_ids
            FROM meeting_items
            ORDER BY meeting_id, rowid
        """).fetchall()

        for item in items:
            text = str(item["text"] or "").strip()

            if not text:
                continue

            documents.append({
                "document_id": (
                    f"item:{item['source_rowid']}"
                ),
                "meeting_id": item["meeting_id"],
                "content_type": item["item_type"],
                "text": text,
                "confidence": item["confidence"],
                "owner": item["owner"],
                "deadline": item["deadline"],
                "evidence_turn_ids": item["evidence_turn_ids"]
            })

            item_count += 1

    # ---------------------------------------------
    # 3. Save searchable documents
    # ---------------------------------------------

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8"
    ) as file:

        for document in documents:
            file.write(
                json.dumps(
                    document,
                    ensure_ascii=False
                ) + "\n"
            )

    # ---------------------------------------------
    # 4. Verify output
    # ---------------------------------------------

    print("=" * 50)
    print("SEMANTIC SEARCH - DOCUMENT PREPARATION")
    print("=" * 50)

    print("Meeting summaries:", summary_count)
    print("Extracted items:", item_count)
    print("Total searchable documents:", len(documents))

    print("\nOutput file:", OUTPUT_PATH.name)
    print("Document preparation: COMPLETE")
    print("SQLite database unchanged.")

    if documents:
        print("\nSample document:")
        sample = documents[0]

        print("Document ID:", sample["document_id"])
        print("Meeting ID:", sample["meeting_id"])
        print("Content type:", sample["content_type"])
        print("Text preview:", sample["text"][:150])


if __name__ == "__main__":
    prepare_documents()
