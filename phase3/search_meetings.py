
import json
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


# --------------------------------------------
# 1. Configuration
# --------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

INDEX_PATH = BASE_DIR / "meeting_search.index"
METADATA_PATH = BASE_DIR / "embedding_metadata.jsonl"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


# --------------------------------------------
# 2. Load model, FAISS index and metadata
# --------------------------------------------

def load_search_engine():

    print("Loading semantic search engine...")

    if not INDEX_PATH.exists():
        raise FileNotFoundError(
            f"FAISS index missing: {INDEX_PATH}"
        )

    if not METADATA_PATH.exists():
        raise FileNotFoundError(
            f"Metadata missing: {METADATA_PATH}"
        )

    model = SentenceTransformer(MODEL_NAME)

    index = faiss.read_index(str(INDEX_PATH))

    with METADATA_PATH.open(
        "r", encoding="utf-8"
    ) as file:
        metadata = [
            json.loads(line)
            for line in file
            if line.strip()
        ]

    if index.ntotal != len(metadata):
        raise ValueError(
            "FAISS index and metadata counts do not match"
        )

    model_dimension = model.get_sentence_embedding_dimension()

    if model_dimension != index.d:
        raise ValueError(
            "Embedding model and FAISS dimensions do not match"
        )

    print("Model: LOADED")
    print("Indexed passages:", index.ntotal)
    print("Search engine: READY")

    return model, index, metadata


# --------------------------------------------
# 3. Search using natural-language questions
# --------------------------------------------

def semantic_search(question, model, index, metadata, top_k=5):

    question = question.strip()

    if not question:
        raise ValueError("Search question cannot be empty")

    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    # Convert the question into a numerical embedding.
    query_embedding = model.encode(
        [question],
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    query_embedding = np.ascontiguousarray(
        query_embedding,
        dtype=np.float32
    )

    # Find the nearest passages in FAISS.
    scores, positions = index.search(
        query_embedding,
        min(top_k, index.ntotal)
    )

    results = []

    for score, position in zip(
        scores[0], positions[0]
    ):
        if position < 0:
            continue

        record = metadata[int(position)]

        results.append({
            "meeting_id": record["meeting_id"],
            "content_type": record["content_type"],
            "similarity": float(score),
            "text": record["text"],
            "owner": record.get("owner"),
            "deadline": record.get("deadline"),
            "evidence_turn_ids": record.get(
                "evidence_turn_ids"
            ),
            "source_document_id": record.get(
                "source_document_id"
            )
        })

    return results


# --------------------------------------------
# 4. Display results
# --------------------------------------------

def display_results(results):

    print("\n" + "=" * 60)
    print("SEMANTIC SEARCH RESULTS")
    print("=" * 60)

    if not results:
        print("No matching passages found.")
        return

    for rank, result in enumerate(results, start=1):

        print(f"\nRESULT {rank}")
        print("-" * 50)

        print("Meeting ID:", result["meeting_id"])
        print("Content type:", result["content_type"])

        print(
            "Similarity:",
            f"{result['similarity']:.4f}"
        )

        print(
            "Source document:",
            result["source_document_id"]
        )

        if result["owner"]:
            print("Owner:", result["owner"])

        if result["deadline"]:
            print("Deadline:", result["deadline"])

        if result["evidence_turn_ids"]:
            print(
                "Evidence turns:",
                result["evidence_turn_ids"]
            )

        print("\nRelevant passage:")
        print(result["text"][:600])


# --------------------------------------------
# 5. Interactive search
# --------------------------------------------

def main():

    model, index, metadata = load_search_engine()

    print("\n" + "=" * 60)
    print("MEETING INTELLIGENCE - SEMANTIC SEARCH")
    print("=" * 60)

    print("Type a natural-language question.")
    print("Type 'exit' to stop searching.")

    while True:

        question = input(
            "\nEnter your search question: "
        ).strip()

        if question.lower() in {"exit", "quit"}:
            print("Semantic search closed.")
            break

        if not question:
            print("Please enter a question.")
            continue

        results = semantic_search(
            question,
            model,
            index,
            metadata,
            top_k=5
        )

        display_results(results)


if __name__ == "__main__":
    main()
