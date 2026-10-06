import json

from config import (
    DATASET_PATH,
    OUTPUT_DIR
)

# Load meetings
meetings = {}

with open(
    DATASET_PATH,
    "r",
    encoding="utf-8"
) as f:

    for line in f:

        if line.strip():

            meeting = json.loads(line)

            meetings[
                meeting["meeting_id"]
            ] = meeting


# Show evidence for every prediction
for file_path in OUTPUT_DIR.glob(
    "*_prediction.json"
):

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as f:

        prediction = json.load(f)


    meeting_id = prediction.get(
        "meeting_id"
    )

    if meeting_id not in meetings:

        print(
            f"\nSkipping {meeting_id}"
        )

        continue


    meeting = meetings[
        meeting_id
    ]

    lines = meeting[
        "transcript_text"
    ].splitlines()


    print("\n")
    print("=" * 60)
    print("MEETING:", meeting_id)
    print("=" * 60)


    # Decisions
    for decision in prediction.get(
        "decisions",
        []
    ):

        print("\nDECISION:")
        print(
            decision.get(
                "decision",
                ""
            )
        )

        print("\nEVIDENCE:")

        for turn_id in decision.get(
            "evidence_turn_ids",
            []
        ):

            if (
                0 <= turn_id <
                len(lines)
            ):

                print(
                    f"[{turn_id}] "
                    f"{lines[turn_id]}"
                )

        print("-" * 50)


    # Action Items
    for action in prediction.get(
        "action_items",
        []
    ):

        print("\nACTION ITEM:")
        print(
            action.get(
                "action",
                ""
            )
        )

        print("\nEVIDENCE:")

        for turn_id in action.get(
            "evidence_turn_ids",
            []
        ):

            if (
                0 <= turn_id <
                len(lines)
            ):

                print(
                    f"[{turn_id}] "
                    f"{lines[turn_id]}"
                )

        print("-" * 50)