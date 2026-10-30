
import numpy as np

from search_meetings import load_search_engine


# -----------------------------------------
# 1. Semantic search with filters
# -----------------------------------------

def search_filtered(
    question,
    model,
    index,
    metadata,
    top_k=5,
    content_type=None,
    meeting_id=None,
    unique_meetings=True
):
    if not question.strip():
        raise ValueError("Search question cannot be empty")

    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    query_vector = model.encode(
        [question],
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    query_vector = np.ascontiguousarray(
        query_vector,
        dtype=np.float32
    )

    # Search all indexed passages so that filters
    # do not accidentally exclude valid matches.
    scores, positions = index.search(
        query_vector,
        index.ntotal
    )

    results = []
    seen_meetings = set()

    for score, position in zip(scores[0], positions[0]):

        if position < 0:
            continue

        record = metadata[int(position)]

        if content_type:
            if (
                str(record["content_type"]).casefold()
                != content_type.casefold()
            ):
                continue

        if meeting_id:
            if record["meeting_id"] != meeting_id:
                continue

        if unique_meetings:
            if record["meeting_id"] in seen_meetings:
                continue

            seen_meetings.add(record["meeting_id"])

        results.append({
            "meeting_id": record["meeting_id"],
            "content_type": record["content_type"],
            "similarity": float(score),
            "text": record["text"],
            "source_document_id": record.get(
                "source_document_id"
            ),
            "owner": record.get("owner"),
            "deadline": record.get("deadline"),
            "evidence_turn_ids": record.get(
                "evidence_turn_ids"
            )
        })

        if len(results) >= top_k:
            break

    return results


# -----------------------------------------
# 2. Display search results
# -----------------------------------------

def show_results(results):

    print("\n" + "=" * 60)
    print("FILTERED SEMANTIC SEARCH RESULTS")
    print("=" * 60)

    if not results:
        print("No results match the selected filters.")
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
            "Source:",
            result["source_document_id"]
        )

        if result["owner"]:
            print("Owner:", result["owner"])

        if result["deadline"]:
            print("Deadline:", result["deadline"])

        if result["evidence_turn_ids"]:
            print(
                "Evidence turn IDs:",
                result["evidence_turn_ids"]
            )

        print("\nRelevant passage:")
        print(result["text"])


# -----------------------------------------
# 3. Interactive search interface
# -----------------------------------------

def main():

    model, index, metadata = load_search_engine()

    available_types = sorted({
        record["content_type"]
        for record in metadata
    })

    print("\n" + "=" * 60)
    print("MEETING INTELLIGENCE - FILTERED SEARCH")
    print("=" * 60)

    print("\nAvailable content types:")

    for content_type in available_types:
        print(" -", content_type)

    print("\nType 'exit' to stop.")

    while True:

        question = input(
            "\nEnter search question: "
        ).strip()

        if question.lower() in {"exit", "quit"}:
            print("Search closed.")
            break

        if not question:
            print("Please enter a question.")
            continue

        content_type = input(
            "Content type (Enter for all): "
        ).strip()

        if content_type and content_type not in available_types:
            print("Invalid content type.")
            continue

        meeting_id = input(
            "Meeting ID (Enter for all): "
        ).strip()

        unique_choice = input(
            "One result per meeting? (Y/n): "
        ).strip().lower()

        unique_meetings = unique_choice != "n"

        results = search_filtered(
            question=question,
            model=model,
            index=index,
            metadata=metadata,
            top_k=5,
            content_type=content_type or None,
            meeting_id=meeting_id or None,
            unique_meetings=unique_meetings
        )

        show_results(results)


if __name__ == "__main__":
    main()
