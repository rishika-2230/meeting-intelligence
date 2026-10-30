
import json
from pathlib import Path


def normalize_fireflies_transcript(meeting):
    """Convert Fireflies transcript segments into numbered lines."""

    sentences = meeting.get("sentences") or []
    lines = []

    for index, sentence in enumerate(sentences):
        speaker = sentence.get("speaker_name") or "Unknown Speaker"
        text = (sentence.get("text") or "").strip()

        if text:
            lines.append(f"[{index:04d}] {speaker}: {text}")

    return "\n".join(lines)


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent

    input_path = base_dir / "fireflies_test_transcript.json"
    output_path = base_dir / "fireflies_normalized_transcript.txt"

    meeting = json.loads(
        input_path.read_text(encoding="utf-8")
    )

    normalized_text = normalize_fireflies_transcript(meeting)

    output_path.write_text(
        normalized_text,
        encoding="utf-8"
    )

    print("Meeting:", meeting.get("title"))
    print("Original segments:", len(meeting.get("sentences") or []))
    print("Normalized transcript lines:", len(normalized_text.splitlines()))
    print("Saved to:", output_path)
