import json
import time
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from config import (
    MODEL_NAME,
    DATASET_PATH,
    SCHEMA_PATH,
    PROMPT_PATH,
    OUTPUT_DIR,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY was not found in the .env file."
    )


client = genai.Client(
    api_key=GEMINI_API_KEY
)


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
                f"{attempt}/{max_retries} failed"
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


def main():

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

    print(
        f"Loaded "
        f"{len(meetings)} meetings."
    )

    print(
        f"Model: {MODEL_NAME}"
    )

    print()

    successful = 0
    skipped = 0
    failed = 0

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

        print("=" * 60)

        print(
            f"Processing "
            f"{index}/{len(meetings)}: "
            f"{meeting_id}"
        )

        if output_path.exists():

            print(
                "SKIPPED: "
                "prediction already exists."
            )

            skipped += 1

            continue

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

        try:

            prediction = (
                run_gemini_with_retry(
                    prompt,
                    schema
                )
            )

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

            time.sleep(65)

        except Exception as error:

            failed += 1

            print(
                f"FAILED: "
                f"{meeting_id}"
            )

            print(error)

        print()

    print("=" * 60)

    print(
        "20-meeting run finished."
    )

    print(
        f"Successful: {successful}"
    )

    print(
        f"Skipped: {skipped}"
    )

    print(
        f"Failed: {failed}"
    )


if __name__ == "__main__":
    main()