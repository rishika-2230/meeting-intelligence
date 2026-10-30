
from functools import lru_cache

from search_meetings import load_search_engine
from search_meetings_filtered import search_filtered


@lru_cache(maxsize=1)
def get_search_engine():
    """Load model and index once per Python process."""
    return load_search_engine()


def search_meeting_intelligence(
    question,
    top_k=5,
    content_type=None,
    meeting_id=None,
    unique_meetings=True,
    min_similarity=0.30,
):
    """
    Reusable semantic search function.

    min_similarity=None disables score filtering.
    Similarity scores are not accuracy probabilities.
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Please enter a search question.")

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    model, index, metadata = get_search_engine()

    # Retrieve candidates before applying similarity filtering.
    candidates = search_filtered(
        question=question,
        model=model,
        index=index,
        metadata=metadata,
        top_k=index.ntotal,
        content_type=content_type,
        meeting_id=meeting_id,
        unique_meetings=unique_meetings,
    )

    if min_similarity is not None:
        candidates = [
            result
            for result in candidates
            if result["similarity"] >= min_similarity
        ]

    return candidates[:top_k]


if __name__ == "__main__":

    questions = [
        (
            "What decisions were made about product design?",
            "decisions",
        ),
        (
            "What follow-up work was assigned for the next meeting?",
            "action_items",
        ),
        (
            "What questions remained unanswered about project approvals?",
            "unanswered_questions",
        ),
    ]

    for question, content_type in questions:

        print("\n" + "=" * 60)
        print("QUESTION:", question)
        print("CONTENT TYPE:", content_type)

        results = search_meeting_intelligence(
            question=question,
            content_type=content_type,
            top_k=5,
            min_similarity=0.30,
        )

        print("Results above threshold:", len(results))

        if not results:
            print(
                "No sufficiently similar results found. "
                "Try a different query or remove the threshold."
            )

        for rank, result in enumerate(results, start=1):
            print(f"\nRESULT {rank}")
            print("Meeting:", result["meeting_id"])
            print("Similarity:", round(result["similarity"], 4))
            print("Passage:", result["text"])
            print("Evidence:", result["evidence_turn_ids"])

    print("\nSEARCH SERVICE TEST COMPLETE")
    print("No SQLite modifications.")
    print("No HubSpot API requests.")
