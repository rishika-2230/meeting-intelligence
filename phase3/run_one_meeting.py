import os
import json

from dotenv import load_dotenv
from google import genai

from config import (
    DATASET_PATH,
    SCHEMA_PATH,
    PROMPT_PATH,
    OUTPUT_DIR,
    MODEL_NAME,
)


# -----------------------------
# Load API key
# -----------------------------

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY not found."
    )


client = genai.Client(
    api_key=api_key
)


# -----------------------------
# Load first meeting
# -----------------------------

with open(
    DATASET_PATH,
    "r",
    encoding="utf-8"
) as f:

    first_line = f.readline()

meeting = json.loads(first_line)


# -----------------------------
# Load schema
# -----------------------------

with open(
    SCHEMA_PATH,
    "r",
    encoding="utf-8"
) as f:

    schema = json.load(f)


# -----------------------------
# Load prompt template
# -----------------------------

with open(
    PROMPT_PATH,
    "r",
    encoding="utf-8"
) as f:

    prompt_template = f.read()


# -----------------------------
# Build prompt
# -----------------------------

prompt = prompt_template.format(

    meeting_id=
        meeting["meeting_id"],

    transcript_text=
        meeting["transcript_text"]

)


print(
    "Processing meeting:",
    meeting["meeting_id"]
)


# -----------------------------
# Call Gemini
# -----------------------------

interaction = client.interactions.create(

    model=MODEL_NAME,

    input=prompt,

    response_format={

        "type": "text",

        "mime_type":
            "application/json",

        "schema":
            schema

    }

)


# -----------------------------
# Parse response
# -----------------------------

prediction = json.loads(
    interaction.output_text
)


# -----------------------------
# Save output
# -----------------------------

output_path = (

    OUTPUT_DIR
    / f"{meeting['meeting_id']}_prediction.json"

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


print(
    "Prediction saved to:",
    output_path
)

print(
    "\nMeeting:",
    meeting["meeting_id"]
)

print(
    "Decisions:",
    len(
        prediction.get(
            "decisions",
            []
        )
    )
)

print(
    "Actions:",
    len(
        prediction.get(
            "action_items",
            []
        )
    )
)

print(
    "Confidence:",
    prediction.get(
        "overall_confidence"
    )
)