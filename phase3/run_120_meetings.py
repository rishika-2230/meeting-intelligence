import json
import time
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATASET_PATH = (
    PROJECT_ROOT
    / "data"
    / "phase1"
    / "qmsum_120_meetings.jsonl"
)

SCHEMA_PATH = (
    PROJECT_ROOT
    / "data"
    / "phase2"
    / "meeting_intelligence_schema.json"
)

PROMPT_PATH = (
    PROJECT_ROOT
    / "data"
    / "phase2"
    / "extraction_prompt_template.txt"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "phase3"
    / "outputs_120"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

MODEL_NAME = "gemini-3.5-flash-lite"

load_dotenv(
    PROJECT_ROOT / ".env"
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY was not found in the .env file."
    )


client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ============================================================
# FILE LOADING
# ============================================================

def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def load_jsonl(path):

    records = []

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            line = line.strip()

            if line:

                records.append(
                    json.loads(line)
                )

    return records


# ============================================================
# GEMINI EXTRACTION WITH RETRIES
# ============================================================

def run_gemini_with_retry(
    prompt,
    schema,
    max_retries=5
):

    for attempt in range(
        1,
        max_retries + 1
    ):

        try:

            interaction = (
                client.interactions.create(
                    model=MODEL_NAME,
                    input=prompt,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": schema,
                    },
                )
            )

            prediction = json.loads(
                interaction.output_text
            )

            return prediction

        except Exception as error:

            error_text = str(error)

            print()
            print(
                f"Attempt "
                f"{attempt}/{max_retries} failed."
            )

            print(error_text)

            if attempt == max_retries:
                raise

            if "429" in error_text:

                wait_seconds = 65

            elif "500" in error_text:

                wait_seconds = 30

            else:

                wait_seconds = 20

            print(
                f"Waiting {wait_seconds} "
                f"seconds before retry..."
            )

            time.sleep(
                wait_seconds
            )


# ============================================================
# MAIN 120-MEETING PIPELINE
# ============================================================

def main():

    # --------------------------------------------------------
    # Load data
    # --------------------------------------------------------

    meetings = load_jsonl(
        DATASET_PATH
    )

    schema = load_json(
        SCHEMA_PATH
    )

    with open(
        PROMPT_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        prompt_template = (
            file.read()
        )


    # --------------------------------------------------------
    # Dataset safety check
    # --------------------------------------------------------

    print("=" * 70)
    print("MEETING INTELLIGENCE — 120 MEETING EXTRACTION")
    print("=" * 70)

    print(
        f"Dataset: {DATASET_PATH}"
    )

    print(
        f"Meetings loaded: {len(meetings)}"
    )

    print(
        f"Model: {MODEL_NAME}"
    )

    print(
        f"Output directory: {OUTPUT_DIR}"
    )

    print()

    if len(meetings) != 120:

        raise ValueError(
            f"Expected exactly 120 meetings, "
            f"but found {len(meetings)}."
        )


    # --------------------------------------------------------
    # Counters
    # --------------------------------------------------------

    successful = 0
    skipped = 0
    failed = 0

    failed_meetings = []


    # --------------------------------------------------------
    # Process meetings
    # --------------------------------------------------------

    for index, meeting in enumerate(
        meetings,
        start=1
    ):

        meeting_id = (
            meeting["meeting_id"]
        )

        output_path = (
            OUTPUT_DIR
            / f"{meeting_id}_prediction.json"
        )

        print("=" * 70)

        print(
            f"Processing "
            f"{index}/120: "
            f"{meeting_id}"
        )


        # ----------------------------------------------------
        # Resume protection
        # ----------------------------------------------------

        if output_path.exists():

            print(
                "SKIPPED: "
                "prediction already exists."
            )

            skipped += 1

            continue


        # ----------------------------------------------------
        # Build prompt
        # ----------------------------------------------------

        prompt = (
            prompt_template.format(
                meeting_id=meeting_id,
                transcript_text=(
                    meeting[
                        "transcript_text"
                    ]
                ),
            )
        )


        # ----------------------------------------------------
        # Gemini extraction
        # ----------------------------------------------------

        try:

            prediction = (
                run_gemini_with_retry(
                    prompt,
                    schema
                )
            )


            # ------------------------------------------------
            # Meeting-ID safety check
            # ------------------------------------------------

            predicted_meeting_id = (
                prediction.get(
                    "meeting_id"
                )
            )

            if (
                predicted_meeting_id
                != meeting_id
            ):

                raise ValueError(
                    f"Meeting ID mismatch. "
                    f"Expected {meeting_id}, "
                    f"received "
                    f"{predicted_meeting_id}"
                )


            # ------------------------------------------------
            # Save prediction
            # ------------------------------------------------

            with open(
                output_path,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    prediction,
                    file,
                    indent=2,
                    ensure_ascii=False
                )


            successful += 1

            print(
                f"SUCCESS: "
                f"{output_path.name}"
            )


            # ------------------------------------------------
            # Free-tier rate-limit protection
            # ------------------------------------------------

            print(
                "Waiting 65 seconds "
                "before next request..."
            )

            time.sleep(65)


        except Exception as error:

            failed += 1

            failed_meetings.append(
                meeting_id
            )

            print(
                f"FAILED: "
                f"{meeting_id}"
            )

            print(error)


        print()


    # ========================================================
    # FINAL REPORT
    # ========================================================

    print()
    print("=" * 70)
    print("120-MEETING EXTRACTION FINISHED")
    print("=" * 70)

    print(
        f"Successful this run: "
        f"{successful}"
    )

    print(
        f"Already existing/skipped: "
        f"{skipped}"
    )

    print(
        f"Failed: "
        f"{failed}"
    )

    print(
        f"Total accounted for: "
        f"{successful + skipped + failed}/120"
    )


    if failed_meetings:

        print()
        print(
            "Failed meeting IDs:"
        )

        for meeting_id in failed_meetings:

            print(
                f"- {meeting_id}"
            )


    print()
    print(
        "Predictions saved in:"
    )

    print(
        OUTPUT_DIR
    )


if __name__ == "__main__":
    main()