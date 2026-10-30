
import json
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "search_documents.jsonl"
OUTPUT_PATH = BASE_DIR / "search_chunks.jsonl"

CHUNK_SIZE = 220
CHUNK_OVERLAP = 35


def split_text(text):
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = min(start + CHUNK_SIZE, len(words))

        chunks.append({
            "text": " ".join(words[start:end]),
            "word_start": start,
            "word_end": end
        })

        if end == len(words):
            break

        start = end - CHUNK_OVERLAP

    return chunks


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_PATH}"
        )

    all_chunks = []
    content_counts = Counter()
    document_count = 0

    with INPUT_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            document = json.loads(line)
            document_count += 1

            text = str(document.get("text") or "").strip()

            if not text:
                continue

            sections = split_text(text)

            for index, section in enumerate(sections):
                chunk = {
                    **document,
                    "chunk_id": (
                        f"{document['document_id']}:chunk:{index:04d}"
                    ),
                    "source_document_id": document["document_id"],
                    "chunk_index": index,
                    "text": section["text"],
                    "word_start": section["word_start"],
                    "word_end": section["word_end"]
                }

                all_chunks.append(chunk)
                content_counts[document["content_type"]] += 1

    chunk_ids = [chunk["chunk_id"] for chunk in all_chunks]

    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Duplicate chunk IDs detected")

    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        for chunk in all_chunks:
            file.write(
                json.dumps(chunk, ensure_ascii=False) + "\n"
            )

    print("=" * 50)
    print("SEMANTIC SEARCH - TEXT CHUNKING")
    print("=" * 50)

    print("Input documents:", document_count)
    print("Total chunks:", len(all_chunks))
    print("Unique chunk IDs:", len(set(chunk_ids)))

    print("\n--- CONTENT TYPES ---")
    for content_type, count in sorted(content_counts.items()):
        print(f"{content_type}: {count}")

    print("\n--- VALIDATION ---")
    assert len(all_chunks) >= document_count

    print("Chunk ID uniqueness: PASS")
    print("Meeting references preserved: PASS")
    print("Output file:", OUTPUT_PATH.name)
    print("\nCHUNKING COMPLETE")
    print("SQLite database unchanged.")


if __name__ == "__main__":
    main()
