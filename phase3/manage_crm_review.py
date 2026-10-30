
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "meeting_intelligence.db"


def review_task():
    with sqlite3.connect(DB_PATH) as conn:

        tasks = conn.execute("""
            SELECT task_id, task_title, review_status
            FROM crm_tasks
            ORDER BY task_id
        """).fetchall()

        print("\n=== CRM HUMAN REVIEW ===")

        for task_id, title, status in tasks:
            print(f"{task_id}. [{status}] {title}")

        try:
            task_id = int(input("\nEnter Task ID: "))
        except ValueError:
            print("Invalid task ID.")
            return

        task = conn.execute("""
            SELECT task_title, owner, due_date,
                   review_status, is_demo
            FROM crm_tasks
            WHERE task_id = ?
        """, (task_id,)).fetchone()

        if not task:
            print("Task not found.")
            return

        title, owner, due_date, status, is_demo = task

        print("\nSelected Task:", title)
        print("Owner:", owner or "Unassigned")
        print("Deadline:", due_date or "Not specified")
        print("Current Status:", status)
        print("Demo Only:", bool(is_demo))

        print("\nChoose an action:")
        print("1. Approve")
        print("2. Reject")
        print("3. Edit")

        choice = input("\nEnter choice (1/2/3): ").strip()

        if choice == "1":
            conn.execute("""
                UPDATE crm_tasks
                SET review_status = 'approved'
                WHERE task_id = ?
                  AND sync_status = 'not_synced'
            """, (task_id,))
            if conn.total_changes == 0:
                print("Task was not updated.")
                return
            print("Task approved.")

        elif choice == "2":
            conn.execute("""
                UPDATE crm_tasks
                SET review_status = 'rejected'
                WHERE task_id = ?
                  AND sync_status = 'not_synced'
            """, (task_id,))
            if conn.total_changes == 0:
                print("Task was not updated.")
                return
            print("Task rejected.")

        elif choice == "3":
            print("\nPress Enter to keep an existing value.")

            new_title = input("Task title: ").strip() or title
            new_owner = input("Owner: ").strip() or owner
            new_due = input("Deadline: ").strip() or due_date

            cursor = conn.execute("""
                UPDATE crm_tasks
                SET task_title = ?,
                    owner = ?,
                    due_date = ?,
                    review_status = 'pending'
                WHERE task_id = ?
                  AND sync_status = 'not_synced'
            """, (new_title, new_owner, new_due, task_id))

            if cursor.rowcount == 0:
                print("Task cannot be edited in its current sync state.")
                return

            print("Task updated and returned to pending review.")

        else:
            print("Invalid choice.")
            return

        conn.commit()

        updated_status = conn.execute("""
            SELECT review_status
            FROM crm_tasks
            WHERE task_id = ?
        """, (task_id,)).fetchone()[0]

        print("Updated Review Status:", updated_status)

        if is_demo:
            print("Demo task: Not eligible for live HubSpot sync.")


if __name__ == "__main__":
    review_task()
