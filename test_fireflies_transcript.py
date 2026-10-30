import os
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

import sys

meeting_id = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "01M54M21AKYXP0BZ5B1SMQEDXY"
)

query = """
query GetTranscript($id: String!) {
  transcript(id: $id) {
    id
    title
    sentences {
      speaker_name
      text
      start_time
    }
  }
}
"""

response = requests.post(
    "https://api.fireflies.ai/graphql",
    headers={
        "Authorization": f"Bearer {os.getenv('FIREFLIES_API_KEY')}",
        "Content-Type": "application/json"
    },
    json={
        "query": query,
        "variables": {"id": meeting_id}
    },
    timeout=30
)

print("HTTP Status:", response.status_code)

result = response.json()

if result.get("errors"):
    print("API Errors:", result["errors"])
else:
    transcript = result.get("data", {}).get("transcript")

    if transcript:
        sentences = transcript.get("sentences") or []
        print("Meeting ID:", transcript["id"])
        print("Title:", transcript["title"])
        print("Total transcript segments:", len(sentences))

        for sentence in sentences[:3]:
            print(sentence)
    else:
        print("No transcript returned:", result)
import json
from pathlib import Path

if transcript:
    output_path = Path("phase3/fireflies_test_transcript.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)

    print("Saved transcript to:", output_path)