
import csv
from pathlib import Path

from search_meetings import load_search_engine
from search_meetings_filtered import search_filtered


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "search_relevance_evaluation.csv"

# Three questions targeting different information types.
TEST_QUERIES = [
    {
        "question": "What decisions were made about product design?",
        "content_type": "decisions"
    },
    {
        "question": "What follow-up work was assigned for the next meeting?",
        "content_type": "action_items"
    },
    {
        "question": "What questions remained unanswered about project approvals?",
        "content_type": "unanswered_questions"
    }
]

TOP_K = 5


def ask_relevance():
    """
    Human relevance labels:
      0 = Not relevant
      1 = Partially relevant
      2 = Directly relevant
    """

    while True:
        answer = input(
            "Relevance (0=No, 1=Partial, 2=Yes): "
        ).strip()

        if answer in {"0", "1", "2"}:
            return int(answer)

        print("Please enter 0, 1, or 2.")


def main():

    print("=" * 60)
    print("SEMANTIC SEARCH - RELEVANCE EVALUATION")
    print("=" * 60)

    model, index, metadata = load_search_engine()

    evaluations = []
    overall_relevant = 0
    overall_results = 0

    for query_number, test in enumerate(
        TEST_QUERIES, start=1
    ):

        question = test["question"]
        content_type = test["content_type"]

        results = search_filtered(
            question=question,
            model=model,
            index=index,
            metadata=metadata,
            top_k=TOP_K,
            content_type=content_type,
            unique_meetings=True
        )

        print("\n" + "=" * 60)
        print(f"QUESTION {query_number} OF {len(TEST_QUERIES)}")
        print("=" * 60)

        print("Question:", question)
        print("Filter:", content_type)
        print("Results returned:", len(results))

        relevant_count = 0

        for rank, result in enumerate(results, start=1):

            print("\n" + "-" * 55)
            print(f"RESULT {rank}")
            print("Meeting:", result["meeting_id"])
            print(
                "Similarity:",
                round(result["similarity"], 4)
            )
            print("Evidence:", result["evidence_turn_ids"])
            print("\nPassage:")
            print(result["text"])

            rating = ask_relevance()

            # Strict metric: directly relevant only.
            if rating == 2:
                relevant_count += 1

            evaluations.append({
                "question": question,
                "content_type": content_type,
                "rank": rank,
                "meeting_id": result["meeting_id"],
                "similarity": round(
                    result["similarity"], 4
                ),
                "relevance": rating,
                "source_document_id": (
                    result["source_document_id"]
                ),
                "passage": result["text"]
            })

        precision = relevant_count / TOP_K

        overall_relevant += relevant_count
        overall_results += TOP_K

        print("\n--- QUESTION SUMMARY ---")
        print("Directly relevant:", relevant_count)
        print("Precision@5:", f"{precision:.2%}")

    # ---------------------------------------
    # Save evaluation results
    # ---------------------------------------

    fields = [
        "question",
        "content_type",
        "rank",
        "meeting_id",
        "similarity",
        "relevance",
        "source_document_id",
        "passage"
    ]

    with OUTPUT_PATH.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields
        )

        writer.writeheader()
        writer.writerows(evaluations)

    # ---------------------------------------
    # Final summary
    # ---------------------------------------

    overall_precision = (
        overall_relevant / overall_results
        if overall_results else 0
    )

    print("\n" + "=" * 60)
    print("SEMANTIC SEARCH - FINAL EVALUATION")
    print("=" * 60)

    print("Questions evaluated:", len(TEST_QUERIES))
    print("Results judged:", len(evaluations))
    print("Directly relevant results:", overall_relevant)

    print(
        "Overall Precision@5:",
        f"{overall_precision:.2%}"
    )

    print("\nEvaluation saved:", OUTPUT_PATH.name)
    print("SQLite database unchanged.")
    print("No HubSpot API requests made.")
    print("\nEVALUATION COMPLETE")


if __name__ == "__main__":
    main()
