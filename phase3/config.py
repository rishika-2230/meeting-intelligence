from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

PHASE2_DIR = BASE_DIR / "data" / "phase2"

OUTPUT_DIR = BASE_DIR / "phase3" / "outputs"

DATASET_PATH = (
    PHASE2_DIR
    / "development_evaluation_20.jsonl"
)

SCHEMA_PATH = (
    PHASE2_DIR
    / "meeting_intelligence_schema.json"
)

PROMPT_PATH = (
    PHASE2_DIR
    / "extraction_prompt_template.txt"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

MODEL_NAME = "gemini-3.5-flash-lite"

# Start with ONE meeting.
NUM_MEETINGS = 1