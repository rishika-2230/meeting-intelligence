
import os
import json
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from config import SCHEMA_PATH, PROMPT_PATH, MODEL_NAME


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def extract_meeting_intelligence(meeting_id, transcript_text):
    """Extract structured meeting intelligence using Gemini."""

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("GEMINI_API_KEY not found")

    if not transcript_text.strip():
        raise ValueError("Transcript is empty")

    schema = json.loads(
        Path(SCHEMA_PATH).read_text(encoding="utf-8")
    )

    prompt_template = Path(PROMPT_PATH).read_text(
        encoding="utf-8"
    )

    prompt = prompt_template.format(
        meeting_id=meeting_id,
        transcript_text=transcript_text
    )

    client = genai.Client(api_key=api_key)

    interaction = client.interactions.create(
        model=MODEL_NAME,
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": schema
        }
    )

    prediction = json.loads(interaction.output_text)

    if not isinstance(prediction, dict):
        raise ValueError("Gemini returned an invalid prediction")

    return prediction


if __name__ == "__main__":
    meeting_id = "01M54M21AKYXP0BZ5B1SMQEDXY"

    transcript_path = (
        BASE_DIR / "phase3" / "fireflies_normalized_transcript.txt"
    )

    output_path = (
        BASE_DIR / "phase3" / "fireflies_prediction.json"
    )

    transcript_text = transcript_path.read_text(
        encoding="utf-8"
    )

    print("Processing Fireflies meeting:", meeting_id)

    prediction = extract_meeting_intelligence(
        meeting_id,
        transcript_text
    )

    output_path.write_text(
        json.dumps(prediction, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("Prediction saved:", output_path)
    print("Decisions:", len(prediction.get("decisions", [])))
    print("Action items:", len(prediction.get("action_items", [])))
    print("Risks:", len(prediction.get("risks", [])))
    print(
        "Overall confidence:",
        prediction.get("overall_confidence")
    )
