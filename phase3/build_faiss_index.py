
import json
from pathlib import Path

import faiss
import numpy as np


# --------------------------------------------
# 1. Configuration
# --------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

EMBEDDINGS_PATH = BASE_DIR / "search_embeddings.npy"
METADATA_PATH = BASE_DIR / "embedding_metadata.jsonl"
INDEX_PATH = BASE_DIR / "meeting_search.index"


# --------------------------------------------
# 2. Load embeddings and metadata
# --------------------------------------------

def load_data():

    embeddings = np.load(
        EMBEDDINGS_PATH,
        allow_pickle=False
    )

    metadata = []

    with METADATA_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                metadata.append(json.loads(line))

    return embeddings, metadata


# --------------------------------------------
# 3. Build FAISS index
# --------------------------------------------

def main():

    print("=" * 55)
    print("SEMANTIC SEARCH - FAISS INDEX BUILDING")
    print("=" * 55)

    embeddings, metadata = load_data()

    print("Embeddings loaded:", len(embeddings))
    print("Metadata records:", len(metadata))

    if embeddings.ndim != 2:
        raise ValueError("Embeddings must be a 2D array")

    if len(embeddings) != len(metadata):
        raise ValueError(
            "Embedding and metadata counts do not match"
        )

    if not len(embeddings):
        raise ValueError("No embeddings available")

    if not np.isfinite(embeddings).all():
        raise ValueError("Invalid values in embeddings")

    ids = [record["embedding_id"] for record in metadata]

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate embedding IDs found")

    embeddings = np.ascontiguousarray(
        embeddings,
        dtype=np.float32
    )

    dimension = embeddings.shape[1]

    # Normalize vectors for cosine similarity.
    faiss.normalize_L2(embeddings)

    # Exact vector search using inner product.
    index = faiss.IndexFlatIP(dimension)

    index.add(embeddings)

    assert index.ntotal == len(metadata)

    print("\n--- INDEX DETAILS ---")
    print("FAISS index type: IndexFlatIP")
    print("Vector dimensions:", dimension)
    print("Total indexed vectors:", index.ntotal)

    # ----------------------------------------
    # 4. Save FAISS index
    # ----------------------------------------

    faiss.write_index(index, str(INDEX_PATH))

    # Reload the saved index to verify it.
    loaded_index = faiss.read_index(str(INDEX_PATH))

    assert loaded_index.ntotal == index.ntotal
    assert loaded_index.d == dimension

    # Search using the first existing embedding.
    scores, positions = loaded_index.search(
        embeddings[:1],
        5
    )

    print("\n--- TEST VECTOR SEARCH ---")

    for rank, (position, score) in enumerate(
        zip(positions[0], scores[0]),
        start=1
    ):
        if position < 0:
            continue

        record = metadata[int(position)]

        print(
            f"{rank}. Meeting: {record['meeting_id']}"
        )
        print(f"   Similarity: {float(score):.4f}")
        print(
            f"   Content type: {record['content_type']}"
        )

    assert scores[0][0] > 0.99, (
        "Self-similarity verification failed"
    )

    # ----------------------------------------
    # 5. Final validation
    # ----------------------------------------

    print("\n--- VALIDATION ---")
    print("Embedding/metadata alignment: PASS")
    print("Unique embedding IDs: PASS")
    print("Saved index reload: PASS")
    print("Similarity search: PASS")

    print("\nFAISS index saved:", INDEX_PATH.name)
    print("FAISS INDEX BUILDING COMPLETE")
    print("SQLite database unchanged.")


if __name__ == "__main__":
    main()
