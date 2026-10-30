
import os
import sys
import hmac
import json
import hashlib
import sqlite3
import subprocess

from pathlib import Path
from contextlib import closing
from datetime import date, datetime

import pandas as pd
import streamlit as st

from dotenv import load_dotenv


# ============================================================
# 1. APPLICATION CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
PHASE3_DIR = BASE_DIR / "phase3"

DB_PATH = PHASE3_DIR / "meeting_intelligence.db"
REFRESH_SCRIPT = PHASE3_DIR / "refresh_semantic_index.py"
METADATA_PATH = PHASE3_DIR / "embedding_metadata.jsonl"

load_dotenv(BASE_DIR / ".env")

if str(PHASE3_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE3_DIR))

st.set_page_config(
    page_title="Meeting Intelligence & Execution Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# 2. BLUE-AND-WHITE THEME
# ============================================================

st.markdown(
    """
<style>
.stApp {
    background: linear-gradient(
        135deg, #F2F7FF 0%, #FFFFFF 60%, #EAF3FF 100%
    );
}

.block-container {
    max-width: 1450px;
    padding-top: 2rem;
    padding-bottom: 3rem;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #153D70, #1E66AB);
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label {
    color: #FFFFFF !important;
}

section[data-testid="stSidebar"]
div[data-testid="stButton"] button {
    background: transparent;
    border: 1px solid transparent;
    color: #FFFFFF !important;
    border-radius: 10px;
    padding: 10px 14px;
    margin-bottom: 5px;
    width: 100%;
    min-height: 43px;
}

section[data-testid="stSidebar"]
div[data-testid="stButton"] button p {
    color: #FFFFFF !important;
    text-align: left;
    width: 100%;
}

section[data-testid="stSidebar"]
div[data-testid="stButton"] button:hover {
    background: #2C75BE;
    border-color: #5A9FE2;
}

section[data-testid="stSidebar"]
div[data-testid="stButton"] button[kind="primary"] {
    background: #2C75BE;
    border: 1px solid #72B2EF;
}

[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3 {
    color: #164E91 !important;
}

div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #D7E7FF;
    border-top: 4px solid #2878C9;
    border-radius: 14px;
    padding: 18px;
    box-shadow: 0 4px 14px rgba(18,60,112,0.06);
}

div[data-testid="stMetricLabel"] p {
    color: #4F6883 !important;
}

div[data-testid="stMetricValue"] {
    color: #164E91 !important;
}

.dashboard-hero {
    background: linear-gradient(120deg, #FFFFFF, #E7F1FF);
    padding: 28px;
    border-radius: 16px;
    border-left: 7px solid #2878C9;
    box-shadow: 0 4px 16px rgba(18,60,112,0.06);
    margin-bottom: 24px;
}

.dashboard-hero h1 {
    color: #164E91 !important;
    margin: 0 0 10px 0;
    font-size: 2rem;
}

.dashboard-hero p {
    color: #52708F !important;
    margin: 0;
}

.search-intro {
    background: #FFFFFF;
    border: 1px solid #D7E7FF;
    border-left: 5px solid #2878C9;
    padding: 18px;
    border-radius: 12px;
    margin-bottom: 18px;
}

.search-intro p {
    color: #385775 !important;
    margin: 0;
}

div[data-testid="stDataFrame"] {
    border: 1px solid #D7E7FF;
    border-radius: 12px;
    overflow: hidden;
}
</style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# 3. DATABASE FUNCTIONS
# ============================================================

@st.cache_data(ttl=60)
def load_meeting_data():

    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"Meeting database not found: {DB_PATH}"
        )

    with closing(sqlite3.connect(DB_PATH)) as conn:

        meetings = pd.read_sql_query(
            """
            SELECT
                meeting_id,
                summary,
                summary_confidence,
                overall_confidence,
                requires_human_review
            FROM meetings
            ORDER BY meeting_id
            """,
            conn
        )

        items = pd.read_sql_query(
            """
            SELECT
                meeting_id,
                item_type,
                text,
                owner,
                deadline,
                confidence,
                evidence_turn_ids
            FROM meeting_items
            """,
            conn
        )

    return meetings, items


@st.cache_data(ttl=60)
def load_crm_status():

    with closing(sqlite3.connect(DB_PATH)) as conn:

        notes = pd.read_sql_query(
            """
            SELECT
                note_id,
                meeting_id,
                review_status,
                sync_status,
                is_demo,
                hubspot_note_id
            FROM crm_notes
            """,
            conn
        )

        tasks = pd.read_sql_query(
            """
            SELECT
                task_id,
                meeting_id,
                task_title,
                owner,
                due_date,
                review_status,
                sync_status,
                is_demo,
                hubspot_task_id
            FROM crm_tasks
            """,
            conn
        )

    return notes, tasks


def meeting_exists(meeting_id):

    with closing(sqlite3.connect(DB_PATH)) as conn:

        row = conn.execute(
            """
            SELECT 1
            FROM meetings
            WHERE meeting_id = ?
            """,
            (meeting_id,)
        ).fetchone()

    return row is not None


def load_review_statuses():

    from review_workflow import (
        initialize_review_store,
        get_latest_review_map
    )

    initialize_review_store()

    return get_latest_review_map()


# ============================================================
# 4. DEADLINE AND ANALYTICS FUNCTIONS
# ============================================================

def parse_calendar_deadline(value):

    if value is None:
        return None

    if isinstance(value, float) and pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    formats = (
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y"
    )

    for date_format in formats:

        try:
            return datetime.strptime(
                text,
                date_format
            ).date()

        except ValueError:
            continue

    return None


def build_deadline_analysis(items):

    analysis = items.copy()

    analysis["deadline_clean"] = (
        analysis["deadline"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    analysis["parsed_deadline"] = (
        analysis["deadline_clean"].apply(
            parse_calendar_deadline
        )
    )

    analysis["has_deadline_value"] = (
        analysis["deadline_clean"].ne("")
    )

    analysis["has_valid_date"] = (
        analysis["parsed_deadline"].notna()
    )

    return analysis


def make_confidence_distribution(meetings):

    confidence = pd.to_numeric(
        meetings["overall_confidence"],
        errors="coerce"
    )

    valid = confidence[
        confidence.between(0, 1)
    ]

    bands = pd.cut(
        valid,
        bins=[
            -0.001,
            0.50,
            0.70,
            0.85,
            1.00001
        ],
        labels=[
            "Below 50%",
            "50%–69%",
            "70%–84%",
            "85%–100%"
        ],
        right=False
    )

    return (
        bands.value_counts(sort=False)
        .rename_axis("Confidence band")
        .reset_index(name="Meetings")
    )


def get_review_counts(meetings, latest_reviews):

    statuses = [
        latest_reviews.get(
            meeting_id,
            {}
        ).get("status", "pending")
        for meeting_id in meetings["meeting_id"]
    ]

    return {
        "pending": statuses.count("pending"),
        "approved": statuses.count("approved"),
        "rejected": statuses.count("rejected")
    }


# ============================================================
# 5. SEMANTIC SEARCH BACKEND
# ============================================================

@st.cache_resource(show_spinner=False)
def load_semantic_search():

    from search_service import (
        search_meeting_intelligence
    )

    return search_meeting_intelligence


# ============================================================
# 6. UPLOAD PROCESSING BACKEND
# ============================================================

def process_uploaded_meeting(meeting_id, transcript):

    from run_fireflies_meeting import (
        extract_meeting_intelligence
    )

    from save_fireflies_to_db import (
        save_meeting_to_db
    )

    if meeting_exists(meeting_id):
        raise ValueError(
            "This meeting has already been saved."
        )

    prediction = extract_meeting_intelligence(
        meeting_id,
        transcript
    )

    if not isinstance(prediction, dict):
        raise ValueError(
            "Unexpected Gemini extraction format."
        )

    result = save_meeting_to_db(
        meeting_id,
        prediction
    )

    if not meeting_exists(meeting_id):
        raise RuntimeError(
            "SQLite save could not be verified."
        )

    st.cache_data.clear()

    return prediction, result


# ============================================================
# 7. AUTOMATIC FAISS INDEX REFRESH
# ============================================================

def refresh_semantic_search(meeting_id):

    if not REFRESH_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Refresh script missing: {REFRESH_SCRIPT}"
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

        print(
            "INDEX REFRESH FAILED\n"
            + completed.stdout
            + "\n"
            + completed.stderr,
            flush=True
        )

        raise RuntimeError(
            "FAISS refresh failed. "
            "The meeting remains saved in SQLite."
        )

    if not METADATA_PATH.is_file():
        raise RuntimeError(
            "Embedding metadata was not created."
        )

    total_passages = 0
    meeting_passages = 0

    with METADATA_PATH.open(
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            if not line.strip():
                continue

            record = json.loads(line)

            total_passages += 1

            if record.get("meeting_id") == meeting_id:
                meeting_passages += 1

    if meeting_passages == 0:
        raise RuntimeError(
            "New meeting was not found "
            "in search metadata."
        )

    st.cache_resource.clear()

    st.session_state.pop(
        "meeting_search_results",
        None
    )

    st.session_state.pop(
        "meeting_search_question",
        None
    )

    return {
        "indexed_passages": meeting_passages,
        "total_passages": total_passages
    }


# ============================================================
# 8. LOCAL ADMINISTRATOR ACCESS
# ============================================================

def admin_unlock(
    session_key,
    form_key,
    button_label
):

    password = os.getenv(
        "MEETING_UPLOAD_PASSWORD",
        ""
    )

    if not password:

        st.warning(
            "Administrator password is not configured."
        )

        return False

    if st.session_state.get(session_key, False):
        return True

    with st.form(form_key):

        entered_password = st.text_input(
            "Administrator Password",
            type="password"
        )

        submitted = st.form_submit_button(
            button_label,
            type="primary"
        )

    if submitted:

        if hmac.compare_digest(
            entered_password,
            password
        ):

            st.session_state[session_key] = True
            st.rerun()

        else:
            st.error(
                "Incorrect administrator password."
            )

    return False


# ============================================================
# 9. SIDEBAR NAVIGATION
# ============================================================

NAV_ITEMS = [
    ("📊", "Executive Dashboard"),
    ("📁", "Meeting Explorer"),
    ("✅", "Decisions & Action Items"),
    ("🔎", "Semantic Search"),
    ("📤", "Add Meeting"),
    ("📝", "Human Review"),
    ("🔗", "HubSpot CRM")
]

VALID_PAGES = [
    name for _, name in NAV_ITEMS
]

if (
    "active_page" not in st.session_state
    or st.session_state.active_page not in VALID_PAGES
):
    st.session_state.active_page = (
        "Executive Dashboard"
    )

with st.sidebar:

    st.title("🧠 Meeting Intelligence")
    st.caption("Execution & Analytics Hub")

    st.divider()
    st.markdown("### Navigation")

    for icon, page_name in NAV_ITEMS:

        is_active = (
            st.session_state.active_page == page_name
        )

        if st.button(
            f"{icon}  {page_name}",
            key=f"nav_{page_name}",
            type=(
                "primary"
                if is_active
                else "secondary"
            ),
            use_container_width=True
        ):
            st.session_state.active_page = page_name
            st.rerun()

    st.divider()

    st.caption(
        "Python | Gemini | SQLite | FAISS | HubSpot"
    )

page = st.session_state.active_page


# ============================================================
# 10. LOAD APPLICATION DATA
# ============================================================

try:

    meetings, items = load_meeting_data()

except Exception as error:

    st.error(
        "Unable to load meeting database."
    )

    st.exception(error)
    st.stop()


# ============================================================
# 11. EXECUTIVE DASHBOARD
# ============================================================

if page == "Executive Dashboard":

    st.markdown(
        '<div class="dashboard-hero">'
        '<h1>Meeting Intelligence & Execution Hub</h1>'
        '<p>Executive analytics, extracted decisions, '
        'commitment tracking, human review, and '
        'organizational memory.</p>'
        '</div>',
        unsafe_allow_html=True
    )

    total_meetings = len(meetings)
    total_items = len(items)
    category_count = items["item_type"].nunique()

    action_items = items[
        items["item_type"].isin(
            ["action_items", "commitments"]
        )
    ].copy()

    flagged = pd.to_numeric(
        meetings["requires_human_review"],
        errors="coerce"
    ).fillna(0).astype(bool)

    flagged_count = int(flagged.sum())

    owner_values = (
        items["owner"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    owner_coverage = int(
        owner_values.ne("").sum()
    )

    deadline_data = build_deadline_analysis(items)

    deadlines_present = int(
        deadline_data["has_deadline_value"].sum()
    )

    valid_deadlines = int(
        deadline_data["has_valid_date"].sum()
    )

    unparsed_deadlines = (
        deadlines_present - valid_deadlines
    )

    try:
        latest_reviews = load_review_statuses()
        review_counts = get_review_counts(
            meetings,
            latest_reviews
        )

    except Exception as error:
        st.warning(
            "Human Review statistics unavailable."
        )
        st.caption(str(error))
        review_counts = None

    # --------------------------------------------------------
    # EXECUTIVE KPIs
    # --------------------------------------------------------

    st.subheader("Executive Overview")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Meetings",
            f"{total_meetings:,}"
        )

    with col2:
        st.metric(
            "Extracted Intelligence",
            f"{total_items:,}"
        )

    with col3:
        st.metric(
            "Actions & Commitments Identified",
            len(action_items)
        )

    with col4:
        st.metric(
            "Human-Approved Meetings",
            (
                review_counts["approved"]
                if review_counts is not None
                else "N/A"
            )
        )

    st.caption(
        "Actions and commitments are extracted from "
        "transcripts. Their completion status is "
        "not tracked in the extraction table."
    )

    st.divider()

    # --------------------------------------------------------
    # DATA COVERAGE
    # --------------------------------------------------------

    st.subheader(
        "Extraction Quality & Data Coverage"
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Items with Owners",
            owner_coverage
        )

    with c2:
        st.metric(
            "Items with Deadline Values",
            deadlines_present
        )

    with c3:
        st.metric(
            "Recognized Calendar Dates",
            valid_deadlines
        )

    with c4:
        st.metric(
            "Meetings Flagged by Gemini",
            flagged_count
        )

    if unparsed_deadlines:
        st.info(
            f"{unparsed_deadlines} deadline values "
            "could not be converted into exact "
            "calendar dates. Relative expressions "
            "were retained unchanged."
        )

    st.caption(
        "Extraction confidence is model-reported "
        "and is not independently verified accuracy."
    )

    st.divider()

    # --------------------------------------------------------
    # INTELLIGENCE CATEGORIES AND CONFIDENCE
    # --------------------------------------------------------

    category_col, confidence_col = (
        st.columns([3, 2])
    )

    with category_col:

        st.subheader(
            "Intelligence by Category"
        )

        type_counts = (
            items["item_type"]
            .fillna("Unclassified")
            .value_counts()
            .rename_axis("Category")
            .reset_index(name="Items")
        )

        if not type_counts.empty:
            st.bar_chart(
                type_counts,
                x="Category",
                y="Items",
                color="#2878C9"
            )

        st.caption(
            f"{category_count} distinct categories."
        )

    with confidence_col:

        st.subheader(
            "Extraction Confidence Distribution"
        )

        distribution = (
            make_confidence_distribution(meetings)
        )

        st.bar_chart(
            distribution,
            x="Confidence band",
            y="Meetings",
            color="#2878C9"
        )

        valid_confidence = pd.to_numeric(
            meetings["overall_confidence"],
            errors="coerce"
        )

        valid_confidence = valid_confidence[
            valid_confidence.between(0, 1)
        ]

        if not valid_confidence.empty:
            st.metric(
                "Average Model Confidence",
                f"{valid_confidence.mean():.2f}"
            )

        st.caption(
            "Model-reported confidence, not "
            "externally validated accuracy."
        )

    st.divider()

    # --------------------------------------------------------
    # ACTION AND COMMITMENT DEADLINES
    # --------------------------------------------------------

    st.subheader(
        "Action Items & Commitment Deadlines"
    )

    actionable_dates = (
        build_deadline_analysis(action_items)
    )

    dated_actions = actionable_dates[
        actionable_dates["has_valid_date"]
    ].copy()

    today = date.today()

    past_count = sum(
        value < today
        for value in dated_actions["parsed_deadline"]
    )

    upcoming_count = sum(
        value >= today
        for value in dated_actions["parsed_deadline"]
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(
            "Past-Dated Actions",
            past_count
        )

    with c2:
        st.metric(
            "Today or Future Dated",
            upcoming_count
        )

    with c3:
        st.metric(
            "Dated Actions & Commitments",
            len(dated_actions)
        )

    st.warning(
        "Past-dated does not necessarily mean overdue. "
        "The extraction table does not currently track "
        "completion of individual action items."
    )

    if not dated_actions.empty:

        st.markdown(
            "#### Actions with Exact Deadlines"
        )

        display_deadlines = dated_actions[
            [
                "meeting_id",
                "item_type",
                "text",
                "owner",
                "deadline",
                "parsed_deadline"
            ]
        ].copy()

        display_deadlines["parsed_deadline"] = (
            display_deadlines["parsed_deadline"]
            .astype(str)
        )

        st.dataframe(
            display_deadlines.sort_values(
                "parsed_deadline"
            ),
            hide_index=True,
            use_container_width=True
        )

    st.divider()

    # --------------------------------------------------------
    # OWNER ANALYTICS AND UNCLEAR DEADLINES
    # --------------------------------------------------------

    owner_col, missing_col = st.columns(2)

    with owner_col:

        st.subheader(
            "Actions & Commitments by Owner"
        )

        owner_names = (
            action_items["owner"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        assigned = owner_names[
            owner_names.ne("")
        ]

        owner_counts = (
            assigned.value_counts()
            .head(10)
            .rename_axis("Owner")
            .reset_index(name="Items")
        )

        if owner_counts.empty:
            st.info("No named owners available.")
        else:
            st.bar_chart(
                owner_counts,
                x="Owner",
                y="Items",
                color="#2878C9"
            )

        st.caption(
            "Counts reflect extracted assignments, "
            "not confirmed outstanding work."
        )

    with missing_col:

        st.subheader(
            "Deadline Data Requiring Clarification"
        )

        unclear = deadline_data[
            deadline_data["has_deadline_value"]
            &
            ~deadline_data["has_valid_date"]
        ]

        if unclear.empty:
            st.success(
                "All populated deadlines have "
                "recognized calendar dates."
            )

        else:
            deadline_counts = (
                unclear["deadline_clean"]
                .value_counts()
                .head(10)
                .rename_axis("Original deadline")
                .reset_index(name="Occurrences")
            )

            st.dataframe(
                deadline_counts,
                hide_index=True,
                use_container_width=True
            )

        st.caption(
            "Relative deadlines need meeting-date "
            "context before reliable alerting."
        )

    st.divider()

    # --------------------------------------------------------
    # HUMAN REVIEW
    # --------------------------------------------------------

    st.subheader(
        "Human Review & Governance"
    )

    if review_counts is not None:

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric(
                "Pending Human Review",
                review_counts["pending"]
            )

        with c2:
            st.metric(
                "Approved",
                review_counts["approved"]
            )

        with c3:
            st.metric(
                "Rejected",
                review_counts["rejected"]
            )

        with c4:
            st.metric(
                "Flagged by Gemini",
                flagged_count
            )

        review_chart = pd.DataFrame({
            "Status": [
                "Pending",
                "Approved",
                "Rejected"
            ],
            "Meetings": [
                review_counts["pending"],
                review_counts["approved"],
                review_counts["rejected"]
            ]
        })

        st.bar_chart(
            review_chart,
            x="Status",
            y="Meetings",
            color="#2878C9"
        )

    st.caption(
        "Human approval is independent of "
        "Gemini's extraction review flags."
    )

    st.divider()

    # --------------------------------------------------------
    # RISKS AND OBJECTIONS
    # --------------------------------------------------------

    st.subheader(
        "Risks & Customer Objections"
    )

    risk_col, objection_col = st.columns(2)

    with risk_col:

        risk_rows = items[
            items["item_type"] == "risks"
        ]

        st.metric(
            "Extracted Risks",
            len(risk_rows)
        )

        valid_risks = risk_rows[
            risk_rows["text"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        ]

        if not valid_risks.empty:
            st.dataframe(
                valid_risks[
                    ["meeting_id", "text", "confidence"]
                ].head(15),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info(
                "No descriptive risk text available."
            )

    with objection_col:

        objections = items[
            items["item_type"] == "objections"
        ]

        st.metric(
            "Extracted Objections",
            len(objections)
        )

        valid_objections = objections[
            objections["text"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        ]

        if not valid_objections.empty:
            st.dataframe(
                valid_objections[
                    ["meeting_id", "text", "confidence"]
                ].head(15),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info(
                "No descriptive objection text available."
            )

    st.caption(
        "These counts include historical extraction "
        "records, including some with empty text."
    )

    st.divider()

    # --------------------------------------------------------
    # SEARCH MEETING RECORDS
    # --------------------------------------------------------

    st.subheader(
        "Explore Meeting Records"
    )

    meeting_filter = st.text_input(
        "Find meetings by ID or summary",
        placeholder="Search meeting records..."
    )

    filtered = meetings.copy()

    if meeting_filter.strip():

        query = meeting_filter.strip()

        ids_match = (
            filtered["meeting_id"]
            .astype(str)
            .str.contains(
                query,
                case=False,
                regex=False,
                na=False
            )
        )

        summary_match = (
            filtered["summary"]
            .fillna("")
            .astype(str)
            .str.contains(
                query,
                case=False,
                regex=False,
                na=False
            )
        )

        filtered = filtered[
            ids_match | summary_match
        ]

    st.dataframe(
        filtered[
            [
                "meeting_id",
                "summary",
                "overall_confidence",
                "requires_human_review"
            ]
        ],
        hide_index=True,
        use_container_width=True
    )


# ============================================================
# 12. MEETING EXPLORER + EVIDENCE VIEWER
# ============================================================

elif page == "Meeting Explorer":

    from evidence_viewer import (
        render_evidence_viewer
    )

    st.title("📁 Meeting Explorer")

    st.write(
        "Explore meeting summaries, extracted decisions, "
        "owners, deadlines, and supporting evidence references."
    )

    meeting_ids = meetings["meeting_id"].tolist()

    if not meeting_ids:

        st.info("No meetings found.")

    else:

        selected_meeting = st.selectbox(
            "Select Meeting",
            meeting_ids
        )

        selected_data = meetings[
            meetings["meeting_id"] == selected_meeting
        ].iloc[0]

        st.divider()

        st.subheader("Meeting Overview")

        overview1, overview2, overview3 = (
            st.columns(3)
        )

        meeting_items = items[
            items["meeting_id"] == selected_meeting
        ]

        with overview1:
            st.metric(
                "Extracted Items",
                len(meeting_items)
            )

        with overview2:
            confidence = selected_data[
                "overall_confidence"
            ]

            st.metric(
                "Overall Model Confidence",
                (
                    f"{confidence:.2f}"
                    if pd.notna(confidence)
                    else "N/A"
                )
            )

        with overview3:
            flagged = bool(
                selected_data[
                    "requires_human_review"
                ]
            )

            st.metric(
                "Gemini Review Flag",
                "Yes" if flagged else "No"
            )

        st.subheader("Meeting Summary")

        summary = selected_data["summary"]

        if pd.isna(summary) or not str(summary).strip():
            summary = "No summary available."

        st.info(str(summary))

        st.subheader("Extracted Intelligence")

        if meeting_items.empty:

            st.info(
                "No extracted items for this meeting."
            )

        else:

            st.dataframe(
                meeting_items,
                hide_index=True,
                use_container_width=True
            )

        st.divider()

        # ----------------------------------------------------
        # NEW STEP 72: INTERACTIVE EVIDENCE VIEWER
        # ----------------------------------------------------

        show_evidence = st.checkbox(
            "Show Detailed Evidence Viewer",
            value=True,
            key="show_meeting_evidence"
        )

        if show_evidence:

            render_evidence_viewer(
                selected_meeting
            )

        st.caption(
            "Evidence IDs identify transcript turns. "
            "Original quotations are not displayed "
            "unless the source transcript is available "
            "and its turn mapping has been verified."
        )


# ============================================================
# 13. DECISIONS AND ACTION ITEMS
# ============================================================

elif page == "Decisions & Action Items":

    st.title("Decisions & Action Items")

    st.write(
        "Explore decisions, actions, commitments, "
        "risks, objections and unanswered questions."
    )

    categories = sorted(
        items["item_type"]
        .dropna()
        .unique()
        .tolist()
    )

    selected_categories = st.multiselect(
        "Filter by Category",
        categories,
        default=categories
    )

    filtered_items = items[
        items["item_type"].isin(
            selected_categories
        )
    ]

    st.metric(
        "Matching Extracted Items",
        len(filtered_items)
    )

    st.dataframe(
        filtered_items,
        hide_index=True,
        use_container_width=True
    )


# ============================================================
# 14. SEMANTIC SEARCH
# ============================================================

elif page == "Semantic Search":

    st.title("Semantic Search")

    st.markdown(
        '<div class="search-intro">'
        '<p>Search meeting summaries, decisions, '
        'commitments, risks, action items, and '
        'questions using Sentence Transformers '
        'and FAISS.</p>'
        '</div>',
        unsafe_allow_html=True
    )

    with st.form("meeting_search_form"):

        question = st.text_input(
            "Ask a question about meetings",
            placeholder=(
                "What decisions were made "
                "about customer analytics?"
            )
        )

        col1, col2 = st.columns(2)

        with col1:

            category = st.selectbox(
                "Content Type",
                [
                    "All",
                    "summary",
                    "decisions",
                    "action_items",
                    "commitments",
                    "risks",
                    "objections",
                    "unanswered_questions"
                ]
            )

        with col2:

            top_k = st.slider(
                "Number of Results",
                min_value=1,
                max_value=20,
                value=5
            )

        unique_meetings = st.checkbox(
            "One result per meeting",
            value=True
        )

        show_all = st.checkbox(
            "Include low-similarity results",
            value=False
        )

        submitted = st.form_submit_button(
            "🔎 Search Meetings",
            type="primary",
            use_container_width=True
        )

    if submitted:

        if not question.strip():

            st.warning(
                "Please enter a question."
            )

        else:

            try:

                with st.spinner(
                    "Searching meeting intelligence..."
                ):

                    search_function = (
                        load_semantic_search()
                    )

                    results = search_function(
                        question=question,
                        top_k=top_k,
                        content_type=(
                            None
                            if category == "All"
                            else category
                        ),
                        unique_meetings=unique_meetings,
                        min_similarity=(
                            None if show_all else 0.30
                        )
                    )

                st.session_state[
                    "meeting_search_results"
                ] = results

                st.session_state[
                    "meeting_search_question"
                ] = question

            except Exception as error:

                st.error(
                    "Semantic search failed."
                )

                st.exception(error)

                st.session_state.pop(
                    "meeting_search_results",
                    None
                )

    if "meeting_search_results" in st.session_state:

        results = st.session_state[
            "meeting_search_results"
        ]

        st.divider()
        st.subheader("Search Results")

        st.caption(
            "Question: "
            + st.session_state.get(
                "meeting_search_question",
                ""
            )
        )

        st.metric(
            "Matching Passages",
            len(results)
        )

        if not results:

            st.info(
                "No passages matched your settings."
            )

        for rank, result in enumerate(
            results,
            start=1
        ):

            with st.container(border=True):

                st.markdown(
                    f"### Result {rank}"
                )

                left, right = st.columns(2)

                with left:
                    st.write(
                        "**Meeting ID:**",
                        result["meeting_id"]
                    )

                    st.write(
                        "**Category:**",
                        result["content_type"]
                    )

                with right:
                    st.write(
                        "**Similarity:**",
                        f"{result['similarity']:.4f}"
                    )

                    st.caption(
                        "Similarity is not an "
                        "accuracy percentage."
                    )

                st.markdown("**Relevant Passage**")
                st.write(result["text"])

                if result.get("owner"):
                    st.write(
                        "**Owner:**",
                        result["owner"]
                    )

                if result.get("deadline"):
                    st.write(
                        "**Deadline:**",
                        result["deadline"]
                    )

                if result.get("evidence_turn_ids"):
                    st.write(
                        "**Evidence Turn IDs:**",
                        result["evidence_turn_ids"]
                    )

                if result.get("source_document_id"):
                    st.caption(
                        "Source: "
                        + str(
                            result["source_document_id"]
                        )
                    )


# ============================================================
# 15. ADD MEETING + AUTOMATIC FAISS INDEXING
# ============================================================

elif page == "Add Meeting":

    st.title("📤 Add New Meeting")

    st.write(
        "Upload a transcript, extract intelligence "
        "with Gemini, save to SQLite, and "
        "automatically refresh Semantic Search."
    )

    st.divider()

    uploads_enabled = (
        os.getenv(
            "ENABLE_MEETING_UPLOAD",
            "false"
        ).strip().lower() == "true"
    )

    if not uploads_enabled:

        st.warning(
            "Meeting uploads are disabled "
            "in the environment configuration."
        )

        st.stop()

    authorized = admin_unlock(
        "meeting_upload_authorized",
        "meeting_upload_login",
        "Unlock Add Meeting"
    )

    if not authorized:
        st.stop()

    st.success("Meeting upload access enabled.")

    if st.button("Lock Meeting Upload"):

        st.session_state[
            "meeting_upload_authorized"
        ] = False

        st.rerun()

    st.subheader("Upload Transcript")

    uploaded_file = st.file_uploader(
        "Choose a transcript file",
        type=["txt", "md", "vtt"],
        help="Maximum file size: 100 KB"
    )

    if uploaded_file is not None:

        raw_bytes = uploaded_file.getvalue()

        if len(raw_bytes) > 100_000:

            st.error(
                "File exceeds the 100 KB limit."
            )

            st.stop()

        try:

            transcript_text = raw_bytes.decode(
                "utf-8-sig"
            ).strip()

        except UnicodeDecodeError:

            st.error(
                "Upload a UTF-8 text file."
            )

            st.stop()

        if len(transcript_text) < 100:

            st.warning(
                "Transcript must contain "
                "at least 100 characters."
            )

            st.stop()

        content_hash = hashlib.sha256(
            raw_bytes
        ).hexdigest()

        meeting_id = (
            "manual_" + content_hash[:24]
        )

        st.subheader("Transcript Details")

        col1, col2 = st.columns(2)

        with col1:
            st.write(
                "**Filename:**",
                uploaded_file.name
            )

            st.write(
                "**Characters:**",
                len(transcript_text)
            )

        with col2:
            st.write(
                "**Generated Meeting ID:**",
                meeting_id
            )

            st.write(
                "**Words:**",
                len(transcript_text.split())
            )

        with st.expander(
            "Preview Uploaded Transcript"
        ):

            st.text_area(
                "Transcript Preview",
                value=transcript_text,
                height=300,
                disabled=True
            )

        if meeting_exists(meeting_id):

            st.info(
                "This transcript has already "
                "been processed and saved."
            )

            st.stop()

        st.info(
            "Stages: Gemini extraction, SQLite saving, "
            "and automatic FAISS refresh."
        )

        if st.button(
            "Process, Save & Index Meeting",
            type="primary",
            use_container_width=True
        ):

            try:

                with st.spinner(
                    "Extracting and saving meeting..."
                ):

                    prediction, save_result = (
                        process_uploaded_meeting(
                            meeting_id,
                            transcript_text
                        )
                    )

            except Exception as error:

                st.error(
                    "Meeting extraction or saving failed."
                )

                st.exception(error)
                st.stop()

            st.success(
                "Meeting successfully saved to SQLite."
            )

            st.write(
                "**Saved Meeting ID:**",
                meeting_id
            )

            try:

                with st.spinner(
                    "Updating embeddings and FAISS..."
                ):

                    index_result = (
                        refresh_semantic_search(
                            meeting_id
                        )
                    )

                st.success(
                    "Automatic semantic indexing "
                    "completed successfully!"
                )

                metric1, metric2 = st.columns(2)

                with metric1:
                    st.metric(
                        "New Meeting Passages Indexed",
                        index_result[
                            "indexed_passages"
                        ]
                    )

                with metric2:
                    st.metric(
                        "Total Searchable Passages",
                        index_result[
                            "total_passages"
                        ]
                    )

                st.info(
                    "The meeting is now searchable."
                )

            except Exception as error:

                st.warning(
                    "Meeting saved, but indexing "
                    "did not complete."
                )

                st.error(str(error))

                st.info(
                    "You can retry using "
                    "phase3/refresh_semantic_index.py."
                )

            with st.expander(
                "View Gemini Extraction Output"
            ):
                st.json(prediction)


# ============================================================
# 16. HUMAN REVIEW
# ============================================================

elif page == "Human Review":

    from review_workflow import (
        initialize_review_store,
        get_latest_review_map,
        get_review_history,
        save_review_decision
    )

    st.title("📝 Human Review")

    st.write(
        "Review meeting intelligence, record "
        "approval decisions, and maintain history."
    )

    try:

        initialize_review_store()

        latest_reviews = (
            get_latest_review_map()
        )

    except Exception as error:

        st.error(
            "Could not initialize Human Review."
        )

        st.exception(error)
        st.stop()

    review_data = meetings.copy()

    review_data["flagged"] = (
        pd.to_numeric(
            review_data[
                "requires_human_review"
            ],
            errors="coerce"
        ).fillna(0).astype(bool)
    )

    review_data["review_status"] = (
        review_data["meeting_id"].apply(
            lambda meeting_id: latest_reviews.get(
                meeting_id,
                {}
            ).get("status", "pending")
        )
    )

    review_data["reviewer"] = (
        review_data["meeting_id"].apply(
            lambda meeting_id: latest_reviews.get(
                meeting_id,
                {}
            ).get("reviewer", "")
        )
    )

    pending_count = int(
        (
            review_data["review_status"]
            == "pending"
        ).sum()
    )

    approved_count = int(
        (
            review_data["review_status"]
            == "approved"
        ).sum()
    )

    rejected_count = int(
        (
            review_data["review_status"]
            == "rejected"
        ).sum()
    )

    flagged_count = int(
        review_data["flagged"].sum()
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Pending Review", pending_count)

    with col2:
        st.metric("Approved", approved_count)

    with col3:
        st.metric("Rejected", rejected_count)

    with col4:
        st.metric("Flagged by Gemini", flagged_count)

    st.divider()

    st.subheader("Review Queue")

    filter_col1, filter_col2 = st.columns(2)

    with filter_col1:

        meeting_scope = st.selectbox(
            "Meeting Scope",
            [
                "All Meetings",
                "Flagged Meetings"
            ]
        )

    with filter_col2:

        status_filter = st.selectbox(
            "Review Status",
            [
                "All",
                "Pending",
                "Approved",
                "Rejected"
            ]
        )

    filtered = review_data.copy()

    if meeting_scope == "Flagged Meetings":
        filtered = filtered[
            filtered["flagged"]
        ]

    if status_filter != "All":
        filtered = filtered[
            filtered["review_status"]
            == status_filter.lower()
        ]

    st.write(
        "**Meetings in current queue:**",
        len(filtered)
    )

    st.dataframe(
        filtered[
            [
                "meeting_id",
                "overall_confidence",
                "flagged",
                "review_status",
                "reviewer"
            ]
        ],
        hide_index=True,
        use_container_width=True
    )

    if st.session_state.get("review_flash"):

        st.success(
            st.session_state.pop(
                "review_flash"
            )
        )

    if filtered.empty:

        st.info(
            "No meetings match these filters."
        )

        st.stop()

    st.divider()
    st.subheader("Review Meeting")

    selected_meeting = st.selectbox(
        "Select a meeting to review",
        filtered["meeting_id"].tolist(),
        key="selected_review_meeting"
    )

    selected_row = meetings[
        meetings["meeting_id"] == selected_meeting
    ].iloc[0]

    current_status = latest_reviews.get(
        selected_meeting,
        {}
    ).get("status", "pending")

    st.write(
        "**Current Review Status:**",
        current_status.title()
    )

    st.write(
        "**Gemini Confidence:**",
        selected_row["overall_confidence"]
    )

    st.write(
        "**Flagged by Gemini:**",
        bool(
            selected_row[
                "requires_human_review"
            ]
        )
    )

    st.markdown("### Meeting Summary")

    summary = selected_row["summary"]

    if pd.isna(summary) or not str(summary).strip():
        summary = "No summary available."

    st.info(str(summary))

    st.markdown("### Extracted Intelligence")

    selected_items = items[
        items["meeting_id"] == selected_meeting
    ]

    if selected_items.empty:

        st.warning(
            "No extracted items for this meeting."
        )

    else:

        st.dataframe(
            selected_items,
            hide_index=True,
            use_container_width=True
        )

    st.markdown("### Review History")

    history = get_review_history(selected_meeting)

    if history:

        st.dataframe(
            pd.DataFrame(history)[
                [
                    "reviewed_at",
                    "status",
                    "reviewer",
                    "review_note",
                    "review_id"
                ]
            ],
            hide_index=True,
            use_container_width=True
        )

    else:

        st.info(
            "No human-review decisions "
            "have been recorded yet."
        )

    st.divider()

    st.subheader("Record Review Decision")

    authorized = admin_unlock(
        "meeting_review_authorized",
        "meeting_review_login",
        "Unlock Human Review"
    )

    if not authorized:

        st.caption(
            "Administrator access is required "
            "to approve or reject meetings."
        )

        st.stop()

    st.success(
        "Human Review editing enabled."
    )

    if st.button("Lock Human Review"):

        st.session_state[
            "meeting_review_authorized"
        ] = False

        st.rerun()

    with st.form("review_decision_form"):

        reviewer_name = st.text_input(
            "Reviewer Name",
            placeholder="Enter reviewer name",
            max_chars=80
        )

        decision = st.radio(
            "Review Decision",
            [
                "Approve",
                "Reject",
                "Return to Pending"
            ],
            horizontal=True
        )

        review_note = st.text_area(
            "Review Notes",
            placeholder=(
                "Describe your review decision."
            ),
            max_chars=2000
        )

        confirmed = st.checkbox(
            "I have inspected the meeting summary "
            "and extracted information."
        )

        submitted = st.form_submit_button(
            "Save Review Decision",
            type="primary",
            use_container_width=True
        )

    if submitted:

        if not confirmed:

            st.error(
                "Confirm that you reviewed the meeting."
            )

        elif not reviewer_name.strip():

            st.error(
                "Enter the reviewer name."
            )

        elif (
            decision == "Reject"
            and not review_note.strip()
        ):

            st.error(
                "A rejection reason is required."
            )

        else:

            status_mapping = {
                "Approve": "approved",
                "Reject": "rejected",
                "Return to Pending": "pending"
            }

            try:

                saved_review = save_review_decision(
                    meeting_id=selected_meeting,
                    status=status_mapping[decision],
                    reviewer=reviewer_name,
                    note=review_note
                )

                st.session_state["review_flash"] = (
                    "Review saved: "
                    + saved_review["status"].title()
                    + " | Meeting: "
                    + selected_meeting
                )

                st.rerun()

            except Exception as error:

                st.error(
                    "Review decision could not be saved."
                )

                st.exception(error)

    st.caption(
        "Review decisions are stored in SQLite "
        "and do not automatically sync to HubSpot."
    )


# ============================================================
# 17. HUBSPOT CRM - READ ONLY
# ============================================================

elif page == "HubSpot CRM":

    st.title("HubSpot CRM Integration")

    st.info(
        "CRM notes and tasks are displayed for "
        "monitoring. This page does not trigger "
        "live HubSpot synchronization."
    )

    try:

        notes, tasks = load_crm_status()

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "CRM Notes",
                len(notes)
            )

        with col2:
            st.metric(
                "CRM Tasks",
                len(tasks)
            )

        with col3:

            synced_count = int(
                (
                    notes["sync_status"] == "synced"
                ).sum()
                +
                (
                    tasks["sync_status"] == "synced"
                ).sum()
            )

            st.metric(
                "Synced Records",
                synced_count
            )

        st.divider()

        st.subheader("CRM Notes")

        st.dataframe(
            notes,
            hide_index=True,
            use_container_width=True
        )

        st.subheader("CRM Tasks")

        st.dataframe(
            tasks,
            hide_index=True,
            use_container_width=True
        )

    except Exception as error:

        st.warning(
            "Unable to load CRM records."
        )

        st.exception(error)

    st.caption(
        "Meeting-level and CRM-record-level "
        "approval safeguards remain enforced "
        "by the separate synchronization modules."
    )
