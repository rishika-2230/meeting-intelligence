
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

FIREFLIES_URL = "https://api.fireflies.ai/graphql"


def fetch_fireflies_transcript(meeting_id):
    api_key = os.getenv("FIREFLIES_API_KEY")

    if not api_key:
        raise ValueError("FIREFLIES_API_KEY is missing")

    query = """
    query GetTranscript($id: String!) {
      transcript(id: $id) {
        id
        title
        participants
        sentences {
          speaker_name
          text
          start_time
        }
      }
    }
    """

    response = requests.post(
        FIREFLIES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "query": query,
            "variables": {"id": meeting_id}
        },
        timeout=30
    )

    response.raise_for_status()
    result = response.json()

    if result.get("errors"):
        raise RuntimeError(
            f"Fireflies API error: {result['errors']}"
        )

    transcript = result.get("data", {}).get("transcript")

    if not transcript:
        raise ValueError(
            f"No transcript found for meeting {meeting_id}"
        )

    return transcript
