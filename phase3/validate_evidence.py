import json

from config import (
    DATASET_PATH,
    OUTPUT_DIR
)


# ==========================================
# 1. LOAD DEVELOPMENT MEETINGS
# ==========================================

meetings = {}

with open(
    DATASET_PATH,
    "r",
    encoding="utf-8"
) as f:

    for line in f:

        if line.strip():

            meeting = json.loads(line)

            meeting_id = meeting["meeting_id"]

            meetings[meeting_id] = meeting


print(
    f"Loaded {len(meetings)} meetings "
    "from development dataset."
)


# ==========================================
# 2. SECTIONS THAT CONTAIN EVIDENCE
# ==========================================

sections = [
    "decisions",
    "commitments",
    "action_items",
    "objections",
    "risks",
    "unanswered_questions"
]


# ==========================================
# 3. FIND PREDICTION FILES
# ==========================================

prediction_files = list(
    OUTPUT_DIR.glob("*_prediction.json")
)


if not prediction_files:

    print(
        "No prediction files found "
        "in the outputs folder."
    )

    raise SystemExit


print(
    f"Found {len(prediction_files)} "
    "prediction file(s).\n"
)


# ==========================================
# 4. VALIDATE EACH PREDICTION
# ==========================================

for file_path in prediction_files:

    print(
        "----------------------------------------"
    )

    print(
        f"Checking: {file_path.name}"
    )


    # --------------------------------------
    # Load prediction
    # --------------------------------------

    try:

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as f:

            prediction = json.load(f)

    except Exception as e:

        print(
            f"ERROR: Could not read file: {e}"
        )

        continue


    # --------------------------------------
    # Get meeting ID
    # --------------------------------------

    meeting_id = prediction.get(
        "meeting_id"
    )


    if not meeting_id:

        print(
            "SKIPPED: Prediction does not "
            "contain meeting_id."
        )

        continue


    # ======================================
    # IMPORTANT FIX
    # ======================================

    if meeting_id not in meetings:

        print(
            f"{meeting_id} → SKIPPED"
        )

        print(
            "Reason: Meeting not found in "
            "current development dataset."
        )

        continue


    # --------------------------------------
    # Get original meeting
    # --------------------------------------

    meeting = meetings[meeting_id]


    transcript_text = meeting.get(
        "transcript_text",
        ""
    )


    transcript_lines = (
        transcript_text.splitlines()
    )


    turn_count = len(
        transcript_lines
    )


    print(
        f"Meeting ID: {meeting_id}"
    )

    print(
        f"Transcript turns: {turn_count}"
    )


    # --------------------------------------
    # Store evidence errors
    # --------------------------------------

    errors = []


    # ======================================
    # 5. VALIDATE SUMMARY EVIDENCE
    # ======================================

    summary = prediction.get(
        "summary",
        {}
    )


    summary_ids = summary.get(
        "evidence_turn_ids",
        []
    )


    for turn_id in summary_ids:

        if not isinstance(
            turn_id,
            int
        ):

            errors.append(
                f"Summary evidence ID "
                f"is not an integer: {turn_id}"
            )

            continue


        if not (
            0 <= turn_id < turn_count
        ):

            errors.append(
                f"Summary invalid "
                f"turn ID: {turn_id}"
            )


    # ======================================
    # 6. VALIDATE OTHER EVIDENCE
    # ======================================

    for section in sections:

        items = prediction.get(
            section,
            []
        )


        if not isinstance(
            items,
            list
        ):

            errors.append(
                f"{section} is not a list."
            )

            continue


        for item_number, item in enumerate(
            items,
            start=1
        ):

            evidence_ids = item.get(
                "evidence_turn_ids",
                []
            )


            for turn_id in evidence_ids:

                if not isinstance(
                    turn_id,
                    int
                ):

                    errors.append(
                        f"{section} item "
                        f"{item_number}: "
                        f"evidence ID is not "
                        f"an integer: {turn_id}"
                    )

                    continue


                if not (
                    0 <=
                    turn_id <
                    turn_count
                ):

                    errors.append(
                        f"{section} item "
                        f"{item_number}: "
                        f"invalid turn ID "
                        f"{turn_id}"
                    )


    # ======================================
    # 7. PRINT RESULT
    # ======================================

    if errors:

        print(
            f"\n{meeting_id} → "
            "INVALID EVIDENCE"
        )

        print(
            f"Found {len(errors)} "
            "error(s):"
        )


        for error in errors:

            print(
                f"  - {error}"
            )


    else:

        print(
            f"\n{meeting_id} → "
            "EVIDENCE IDs VALID"
        )


print(
    "\n========================================"
)

print(
    "Evidence validation finished."
)

print(
    "========================================"
)