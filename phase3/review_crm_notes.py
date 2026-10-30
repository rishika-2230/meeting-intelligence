
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"


def review_note():
    with sqlite3.connect(DB_PATH) as conn:
        notes = conn.execute("""
            SELECT note_id, meeting_id, review_status
            FROM crm_notes
            ORDER BY note_id
        """).fetchall()

        print("\n=== CRM NOTE REVIEW ===")

        for note_id, meeting_id, status in notes:
            print(f"{note_id}. Meeting {meeting_id} [{status}]")

        try:
            note_id = int(input("\nEnter Note ID: "))
        except ValueError:
            print("Invalid note ID.")
            return

        note = conn.execute("""
            SELECT note_text, review_status, sync_status, is_demo
            FROM crm_notes
            WHERE note_id = ?
        """, (note_id,)).fetchone()

        if not note:
            print("Note not found.")
            return

        text, status, sync_status, is_demo = note

        print("\nMeeting summary:")
        print(text)
        print("\nCurrent review status:", status)
        print("Demo only:", bool(is_demo))

        if sync_status != "not_synced":
            print("This note cannot be changed in its current sync state.")
            return

        print("\n1. Approve")
        print("2. Reject")
        print("3. Cancel")

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            new_status = "approved"
        elif choice == "2":
            new_status = "rejected"
        else:
            print("No changes made.")
            return

        conn.execute("""
            UPDATE crm_notes
            SET review_status = ?
            WHERE note_id = ?
              AND sync_status = 'not_synced'
        """, (new_status, note_id))

        conn.commit()

        print("\nUpdated review status:", new_status)

        if is_demo:
            print("Demo note: Not eligible for live HubSpot synchronization.")


if __name__ == "__main__":
    review_note()
