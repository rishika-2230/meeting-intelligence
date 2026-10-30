
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


# ---------------------------------------------
# 1. Configuration
# ---------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

INPUT_PATH = BASE_DIR / "search_chunks.jsonl"
EMBEDDINGS_PATH = BASE_DIR / "search_embeddings.npy"
METADATA_PATH = BASE_DIR / "embedding_metadata.jsonl"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
BATCH_SIZE = 32
TOKEN_OVERLAP = 30


# ---------------------------------------------
# 2. Load existing search chunks
# ---------------------------------------------

def load_chunks():
    chunks = []

    with INPUT_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                chunks.append(json.loads(line))

    return chunks


# ---------------------------------------------
# 3. Avoid embedding-model truncation
# ---------------------------------------------

def split_for_model(chunk, model):
    tokenizer = model.tokenizer

    max_tokens = (
        model.max_seq_length
        - tokenizer.num_special_tokens_to_add(pair=False)
        - 4
    )

    if max_tokens <= TOKEN_OVERLAP:
        raise ValueError("Invalid token limit")

    token_ids = tokenizer.encode(
        chunk["text"],
        add_special_tokens=False
    )

    if not token_ids:
        return []

    sections = []
    start = 0

    while start < len(token_ids):
        end = min(start + max_tokens, len(token_ids))

        text = tokenizer.decode(
            token_ids[start:end],
            skip_special_tokens=True
        )

        section = dict(chunk)
        section["embedding_id"] = (
            f"{chunk['chunk_id']}:part:{len(sections):04d}"
        )
        section["source_chunk_id"] = chunk["chunk_id"]
        section["text"] = text
        section["token_start"] = start
        section["token_end"] = end

        sections.append(section)

        if end == len(token_ids):
            break

        start = end - TOKEN_OVERLAP

    return sections


# ---------------------------------------------
# 4. Generate embeddings
# ---------------------------------------------

def main():
    print("=" * 55)
    print("SEMANTIC SEARCH - EMBEDDING GENERATION")
    print("=" * 55)

    chunks = load_chunks()
    print("Original search chunks:", len(chunks))

    if not chunks:
        raise ValueError("No search chunks found")

    print("\nLoading Sentence Transformers model...")

    model = SentenceTransformer(MODEL_NAME)

    print("Model loaded successfully.")
    print("Maximum sequence length:", model.max_seq_length)

    records = []

    for chunk in chunks:
        records.extend(split_for_model(chunk, model))

    texts = [record["text"] for record in records]

    if not texts:
        raise ValueError("No valid text found")

    print("Embedding passages:", len(texts))
    print("\nGenerating embeddings...")

    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    embeddings = np.asarray(
        embeddings,
        dtype=np.float32
    )

    # -----------------------------------------
    # 5. Validate embeddings
    # -----------------------------------------

    assert embeddings.shape[0] == len(records)
    assert embeddings.shape[1] == 384

    assert np.isfinite(embeddings).all(), (
        "Invalid embedding values found"
    )

    embedding_ids = [
        record["embedding_id"] for record in records
    ]

    assert len(set(embedding_ids)) == len(records), (
        "Duplicate embedding IDs detected"
    )

    # -----------------------------------------
    # 6. Save vectors and matching metadata
    # -----------------------------------------

    np.save(EMBEDDINGS_PATH, embeddings)

    with METADATA_PATH.open(
        "w",
        encoding="utf-8"
    ) as file:
        for record in records:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                ) + "\n"
            )

    # -----------------------------------------
    # 7. Report
    # -----------------------------------------

    print("\n--- EMBEDDING RESULTS ---")

    print("Original chunks:", len(chunks))
    print("Embedded passages:", len(records))
    print("Embedding dimensions:", embeddings.shape[1])
    print("Embedding matrix shape:", embeddings.shape)

    print("\n--- FILES CREATED ---")

    print(EMBEDDINGS_PATH.name)
    print(METADATA_PATH.name)

    print("\n--- VALIDATION ---")

    print("Embedding count: PASS")
    print("Embedding dimensions: PASS")
    print("Unique embedding IDs: PASS")
    print("Source meeting references: PRESERVED")

    print("\nEMBEDDING GENERATION COMPLETE")
    print("SQLite database unchanged.")


if __name__ == "__main__":
    main()
