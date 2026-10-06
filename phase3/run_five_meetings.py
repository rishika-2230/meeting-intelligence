import json
import time
from pathlib import Path

from google import genai

from config import (
    GEMINI_API_KEY,
    MODEL_NAME,
    DEVELOPMENT_DATASET_PATH,
    SCHEMA_PATH,
    PROMPT_TEMPLATE_PATH,
    OUTPUT_DIR,
)


client = genai.Client(api_key=GEMINI_API_KEY)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path):
    records = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line:
                records.append(json.loads(line))

    return records


def run_gemini_with_retry(prompt, schema, max_retries=5):
    for attempt in range(1, max_retries + 1):

        try:
            interaction = client.interactions.create(
                model=MODEL_NAME,
                input=prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema,
                },
            )

            return json.loads(interaction.output_text)

        except Exception as e:
            error_text = str(e)

            print(f"Attempt {attempt}/{max_retries} failed:")
            print(error_text)

            if attempt == max_retries:
                raise

            if "429" in error_text:
                wait_seconds = 65
            elif "500" in error_text:
                wait_seconds = 30
            else:
                wait_seconds = 20

            print(f"Waiting {wait_seconds} seconds before retry...")
            time.sleep(wait_seconds)


def main():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    meetings = load_jsonl(DEVELOPMENT_DATASET_PATH)
    schema = load_json(SCHEMA_PATH)

    with open(
        PROMPT_TEMPLATE_PATH,
        "r",
        encoding="utf-8"
    ) as f:
        prompt_template = f.read()

    print(f"Loaded {len(meetings)} meetings.")
    print(f"Model: {MODEL_NAME}")
    print()

    successful = 0
    failed = 0
    skipped = 0

    for index, meeting in enumerate(meetings, start=1):

        meeting_id = meeting["meeting_id"]

        output_path = (
            OUTPUT_DIR /
            f"{meeting_id}_prediction.json"
        )

        print("=" * 60)
        print(
            f"Processing {index}/{len(meetings)}: "
            f"{meeting_id}"
        )

        if output_path.exists():
            print("SKIPPED: prediction already exists.")
            skipped += 1
            continue

        prompt = prompt_template.format(
            meeting_id=meeting_id,
            transcript_text=meeting["transcript_text"],
        )

        try:
            prediction = run_gemini_with_retry(
                prompt,
                schema
            )

            with open(
                output_path,
                "w",
                encoding="utf-8"
            ) as f:
                json.dump(
                    prediction,
                    f,
                    indent=2,
                    ensure_ascii=False
                )

            successful += 1

            print(
                f"SUCCESS: Saved "
                f"{output_path.name}"
            )

            # Small pause between successful requests
            time.sleep(65)

        except Exception as e:
            failed += 1

            print(
                f"FAILED: {meeting_id}"
            )
            print(e)

        print()

    print("=" * 60)
    print("20-meeting run finished.")
    print(f"Successful: {successful}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()