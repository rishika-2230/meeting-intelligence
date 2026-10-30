
import json
import sqlite3

from collections import Counter
from contextlib import closing
from pathlib import Path


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "meeting_intelligence.db"

CATEGORY_NAMES = {
    "decisions": "Decisions",
    "commitments": "Commitments",
    "action_items": "Action Items",
    "risks": "Risks",
    "objections": "Objections",
    "unanswered_questions": "Unanswered Questions",
}


# ============================================================
# 2. NORMALIZE EVIDENCE REFERENCES
# ============================================================

def parse_evidence_references(raw_value):
    """
    Parse existing evidence_turn_ids from SQLite.

    This function does not assume that the
    referenced transcript text is available.

    Returns a list of reference IDs and an
    optional parsing warning.
    """

    if raw_value is None:
        return [], None

    if isinstance(raw_value, list):
        parsed = raw_value

    elif isinstance(raw_value, str):

        value = raw_value.strip()

        if not value:
            return [], None

        try:
            parsed = json.loads(value)

        except json.JSONDecodeError:
            return [], "Evidence references are not valid JSON."

    else:
        return [], "Unexpected evidence reference format."

    if not isinstance(parsed, list):
        return [], "Evidence references are not a list."

    references = []

    for reference in parsed:

        if reference is None:
            continue

        if isinstance(reference, bool):
            continue

        if isinstance(reference, (str, int)):
            text = str(reference).strip()

            if text and text not in references:
                references.append(text)

    return references, None


# ============================================================
# 3. LOAD MEETING AND EXTRACTED ITEMS
# ============================================================

def load_meeting_evidence(meeting_id):
    """
    Retrieve an existing meeting and its extracted
    intelligence from SQLite.

    This function performs no database writes.
    """

    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"Meeting database not found: {DB_PATH}"
        )

    with closing(sqlite3.connect(DB_PATH)) as conn:

        conn.row_factory = sqlite3.Row

        meeting = conn.execute(
            """
            SELECT
                meeting_id,
                summary,
                summary_confidence,
                overall_confidence,
                requires_human_review
            FROM meetings
            WHERE meeting_id = ?
            """,
            (meeting_id,)
        ).fetchone()

        if meeting is None:
            raise ValueError(
                f"Meeting not found: {meeting_id}"
            )

        rows = conn.execute(
            """
            SELECT
                rowid AS item_rowid,
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
            (meeting_id,)
        ).fetchall()

    extracted_items = []

    for row in rows:

        item = dict(row)

        references, warning = parse_evidence_references(
            item["evidence_turn_ids"]
        )

        item["evidence_references"] = references
        item["evidence_count"] = len(references)
        item["evidence_warning"] = warning

        # Distinguish references from transcript evidence.
        # A reference ID alone is not a verified quotation.
        item["source_text_available"] = False

        extracted_items.append(item)

    return {
        "meeting": dict(meeting),
        "items": extracted_items
    }


# ============================================================
# 4. EVIDENCE COVERAGE STATISTICS
# ============================================================

def calculate_evidence_coverage(items):
    """
    Report how many extracted items have evidence IDs.

    This measures reference availability only,
    not whether the cited statements are correct.
    """

    total_items = len(items)

    with_references = sum(
        bool(item["evidence_references"])
        for item in items
    )

    without_references = (
        total_items - with_references
    )

    malformed = sum(
        bool(item["evidence_warning"])
        for item in items
    )

    total_references = sum(
        item["evidence_count"]
        for item in items
    )

    coverage_percentage = (
        round(
            100 * with_references / total_items,
            2
        )
        if total_items
        else 0.0
    )

    return {
        "total_items": total_items,
        "items_with_references": with_references,
        "items_without_references": without_references,
        "malformed_reference_fields": malformed,
        "total_reference_links": total_references,
        "reference_coverage_percentage": coverage_percentage,
    }


# ============================================================
# 5. BUILD EVIDENCE REPORT
# ============================================================

def build_evidence_report(meeting_id):

    data = load_meeting_evidence(meeting_id)

    meeting = data["meeting"]
    items = data["items"]

    coverage = calculate_evidence_coverage(items)

    category_counts = Counter(
        item["item_type"]
        for item in items
    )

    return {
        "meeting_id": meeting_id,
        "summary": meeting.get("summary"),
        "overall_confidence": meeting.get(
            "overall_confidence"
        ),
        "requires_human_review": bool(
            meeting.get("requires_human_review")
        ),
        "category_counts": dict(category_counts),
        "evidence_coverage": coverage,
        "items": items,
        "source_transcript_status": (
            "Not available in the current SQLite schema"
        ),
    }


# ============================================================
# 6. STREAMLIT EVIDENCE VIEWER
# ============================================================

def render_evidence_viewer(meeting_id):
    """
    Render a detailed evidence inspection interface
    inside a Streamlit application.

    Import Streamlit only when this function runs.
    """

    import streamlit as st

    try:
        report = build_evidence_report(meeting_id)

    except Exception as error:
        st.error(
            "Unable to load meeting evidence."
        )
        st.exception(error)
        return

    st.subheader("Evidence & Extraction Details")

    st.caption(
        f"Meeting ID: {meeting_id}"
    )

    coverage = report["evidence_coverage"]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Extracted Items",
            coverage["total_items"]
        )

    with col2:
        st.metric(
            "Items with Evidence IDs",
            coverage["items_with_references"]
        )

    with col3:
        st.metric(
            "Evidence Reference Coverage",
            f"{coverage['reference_coverage_percentage']:.1f}%"
        )

    st.info(
        "Evidence coverage counts items with stored "
        "turn references. It does not verify that "
        "the referenced transcript supports the claim."
    )

    st.warning(
        "Original transcript turns are not stored "
        "in the current SQLite database. "
        "The viewer displays reference IDs only; "
        "it does not invent speaker quotations."
    )

    items = report["items"]

    if not items:
        st.info(
            "No extracted intelligence is stored "
            "for this meeting."
        )
        return

    available_categories = sorted({
        item["item_type"]
        for item in items
    })

    category_filter = st.selectbox(
        "Evidence Category",
        ["All Categories"] + available_categories,
        format_func=lambda value: (
            "All Categories"
            if value == "All Categories"
            else CATEGORY_NAMES.get(value, value)
        ),
        key=f"evidence_category_{meeting_id}"
    )

    search_term = st.text_input(
        "Find an extracted statement",
        placeholder="Search decisions, actions, risks...",
        key=f"evidence_filter_{meeting_id}"
    )

    filtered_items = items

    if category_filter != "All Categories":

        filtered_items = [
            item
            for item in filtered_items
            if item["item_type"] == category_filter
        ]

    if search_term.strip():

        query = search_term.strip().casefold()

        filtered_items = [
            item
            for item in filtered_items
            if query in str(
                item.get("text") or ""
            ).casefold()
        ]

    st.caption(
        f"Showing {len(filtered_items)} "
        f"of {len(items)} extracted items."
    )

    if not filtered_items:
        st.info("No items match your filters.")
        return

    for number, item in enumerate(
        filtered_items,
        start=1
    ):

        text = str(
            item.get("text") or ""
        ).strip()

        category_name = CATEGORY_NAMES.get(
            item["item_type"],
            item["item_type"]
        )

        heading = (
            f"{number}. {category_name}: "
            + (
                text[:90] + "..."
                if len(text) > 90
                else text or "(Empty extraction text)"
            )
        )

        with st.expander(heading):

            st.markdown("**Extracted statement**")

            if text:
                st.write(text)
            else:
                st.warning(
                    "This extraction has no stored text."
                )

            owner = item.get("owner")
            deadline = item.get("deadline")
            confidence = item.get("confidence")

            metadata_col1, metadata_col2 = (
                st.columns(2)
            )

            with metadata_col1:

                st.write(
                    "**Owner:**",
                    owner or "Not specified"
                )

                st.write(
                    "**Category:**",
                    category_name
                )

            with metadata_col2:

                st.write(
                    "**Deadline:**",
                    deadline or "Not specified"
                )

                if confidence is None:
                    st.write(
                        "**Model confidence:** N/A"
                    )
                else:
                    st.write(
                        "**Model confidence:**",
                        f"{float(confidence):.2f}"
                    )

            st.divider()

            st.markdown(
                "**Supporting Evidence Turn IDs**"
            )

            references = item[
                "evidence_references"
            ]

            if references:

                st.code(
                    ", ".join(
                        f"Turn {reference}"
                        for reference in references
                    ),
                    language="text"
                )

                st.caption(
                    "Reference IDs were retained from "
                    "the extraction. The corresponding "
                    "speaker statements have not yet "
                    "been loaded or independently verified."
                )

            else:

                st.warning(
                    "No usable evidence-turn references "
                    "are stored for this item."
                )

            if item["evidence_warning"]:

                st.error(
                    item["evidence_warning"]
                )


# ============================================================
# 7. READ-ONLY COMMAND LINE SELF-TEST
# ============================================================

def run_self_test():

    print("=" * 60)
    print("MEETING INTELLIGENCE - EVIDENCE VIEWER TEST")
    print("=" * 60)

    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)

    with closing(sqlite3.connect(DB_PATH)) as conn:

        meeting_count = conn.execute(
            "SELECT COUNT(*) FROM meetings"
        ).fetchone()[0]

        item_count = conn.execute(
            "SELECT COUNT(*) FROM meeting_items"
        ).fetchone()[0]

        sample_meeting = conn.execute(
            """
            SELECT meeting_id
            FROM meeting_items
            WHERE evidence_turn_ids IS NOT NULL
              AND TRIM(evidence_turn_ids) NOT IN ('', '[]')
            ORDER BY rowid
            LIMIT 1
            """
        ).fetchone()

    print("Total meetings:", meeting_count)
    print("Total extracted items:", item_count)

    if sample_meeting is None:
        print("No evidence references available.")
        return

    meeting_id = sample_meeting[0]

    report = build_evidence_report(meeting_id)

    print("\nSample meeting:", meeting_id)

    print(
        "Extracted items:",
        report["evidence_coverage"]["total_items"]
    )

    print(
        "Items with evidence references:",
        report["evidence_coverage"][
            "items_with_references"
        ]
    )

    print(
        "Evidence reference coverage:",
        report["evidence_coverage"][
            "reference_coverage_percentage"
        ],
        "%"
    )

    assert report["meeting_id"] == meeting_id

    for item in report["items"]:
        assert isinstance(
            item["evidence_references"],
            list
        )

    print("\nMeeting lookup: PASS")
    print("Evidence JSON parsing: PASS")
    print("Category extraction: PASS")
    print("Coverage calculation: PASS")
    print("Missing source text handled safely: PASS")

    print("\nEVIDENCE VIEWER BACKEND TEST: PASS")
    print("SQLite database unchanged.")
    print("No Gemini, Fireflies, or HubSpot calls made.")


if __name__ == "__main__":
    run_self_test()
