import json
import csv
from pathlib import Path
from statistics import mean


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATASET_PATH = (
    PROJECT_ROOT
    / "data"
    / "phase2"
    / "development_evaluation_20.jsonl"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "phase3"
    / "outputs"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "phase3"
    / "evaluation_20_report.csv"
)


SECTIONS = [
    "decisions",
    "commitments",
    "action_items",
    "objections",
    "risks",
    "unanswered_questions",
]


def load_jsonl(path):
    records = []

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            line = line.strip()

            if line:
                records.append(
                    json.loads(line)
                )

    return records


def normalize_text(text):
    if not text:
        return ""

    text = text.lower().strip()

    chars = [
        ".", ",", ";", ":",
        "!", "?", "-", "_",
        "(", ")", "[", "]",
        "{", "}", "'", '"',
    ]

    for char in chars:
        text = text.replace(
            char,
            " "
        )

    return " ".join(
        text.split()
    )


def get_item_text(item):
    possible_keys = [
        "text",
        "decision",
        "description",
        "action",
        "commitment",
        "objection",
        "risk",
        "question",
    ]

    for key in possible_keys:

        value = item.get(key)

        if (
            isinstance(value, str)
            and value.strip()
        ):
            return value.strip()

    return ""


def word_overlap_score(
    prediction_text,
    reference_text
):
    pred_words = set(
        normalize_text(
            prediction_text
        ).split()
    )

    ref_words = set(
        normalize_text(
            reference_text
        ).split()
    )

    if not pred_words or not ref_words:
        return 0.0

    overlap = (
        pred_words
        & ref_words
    )

    union = (
        pred_words
        | ref_words
    )

    return (
        len(overlap)
        / len(union)
    )


def get_reference_summary(
    ground_truth
):
    # Correct QMSum ground-truth field
    value = ground_truth.get(
        "qmsum_reference_summary"
    )

    if isinstance(value, str):
        return value

    if isinstance(value, list):

        summary_parts = []

        for item in value:

            if isinstance(item, str):
                summary_parts.append(item)

            elif isinstance(item, dict):

                if "answer" in item:
                    summary_parts.append(
                        str(item["answer"])
                    )

                elif "summary" in item:
                    summary_parts.append(
                        str(item["summary"])
                    )

                else:
                    summary_parts.append(
                        str(item)
                    )

            else:
                summary_parts.append(
                    str(item)
                )

        return " ".join(
            summary_parts
        )

    if isinstance(value, dict):

        if "answer" in value:
            return str(
                value["answer"]
            )

        if "summary" in value:
            return str(
                value["summary"]
            )

        return str(value)

    return ""


def evaluate_meeting(
    meeting,
    prediction
):
    meeting_id = (
        meeting["meeting_id"]
    )

    ground_truth = (
        meeting.get(
            "evaluation_ground_truth",
            {}
        )
    )

    summary_data = (
        prediction.get(
            "summary",
            {}
        )
    )

    predicted_summary = (
        summary_data.get(
            "text",
            ""
        )
    )

    reference_summary = (
        get_reference_summary(
            ground_truth
        )
    )

    summary_overlap = (
        word_overlap_score(
            predicted_summary,
            reference_summary
        )
    )

    total_items = 0
    items_with_evidence = 0
    total_evidence_ids = 0

    confidence_values = []

    duplicate_count = 0

    for section in SECTIONS:

        items = prediction.get(
            section,
            []
        )

        seen = set()

        for item in items:

            total_items += 1

            evidence_ids = (
                item.get(
                    "evidence_turn_ids",
                    []
                )
            )

            if evidence_ids:

                items_with_evidence += 1

                total_evidence_ids += len(
                    evidence_ids
                )

            confidence = (
                item.get(
                    "confidence"
                )
            )

            if isinstance(
                confidence,
                (int, float)
            ):
                confidence_values.append(
                    confidence
                )

            item_text = (
                get_item_text(
                    item
                )
            )

            normalized = (
                normalize_text(
                    item_text
                )
            )

            if normalized:

                if normalized in seen:
                    duplicate_count += 1

                else:
                    seen.add(
                        normalized
                    )

    evidence_coverage = 0.0

    if total_items > 0:

        evidence_coverage = (
            items_with_evidence
            / total_items
        )

    average_confidence = 0.0

    if confidence_values:

        average_confidence = mean(
            confidence_values
        )

    ami_decisions = (
        ground_truth.get(
            "ami_manual_decisions",
            []
        )
    )

    ami_decision_count = (
        len(ami_decisions)
        if isinstance(
            ami_decisions,
            list
        )
        else 0
    )

    predicted_decision_count = len(
        prediction.get(
            "decisions",
            []
        )
    )

    return {
        "meeting_id": meeting_id,

        "domain": meeting.get(
            "domain",
            ""
        ),

        "split": meeting.get(
            "split",
            ""
        ),

        "summary_overlap_score": round(
            summary_overlap,
            4
        ),

        "predicted_decisions": (
            predicted_decision_count
        ),

        "ami_reference_decisions": (
            ami_decision_count
        ),

        "total_extracted_items": (
            total_items
        ),

        "items_with_evidence": (
            items_with_evidence
        ),

        "evidence_coverage": round(
            evidence_coverage,
            4
        ),

        "total_evidence_citations": (
            total_evidence_ids
        ),

        "average_item_confidence": round(
            average_confidence,
            4
        ),

        "exact_duplicate_count": (
            duplicate_count
        ),

        "overall_confidence": (
            prediction.get(
                "overall_confidence",
                ""
            )
        ),

        "requires_human_review": (
            prediction.get(
                "requires_human_review",
                ""
            )
        ),
    }


def main():

    meetings = load_jsonl(
        DATASET_PATH
    )

    results = []

    missing_predictions = []

    for meeting in meetings:

        meeting_id = (
            meeting["meeting_id"]
        )

        prediction_path = (
            OUTPUT_DIR
            / f"{meeting_id}_prediction.json"
        )

        if not prediction_path.exists():

            missing_predictions.append(
                meeting_id
            )

            continue

        with open(
            prediction_path,
            "r",
            encoding="utf-8"
        ) as file:

            prediction = json.load(
                file
            )

        result = evaluate_meeting(
            meeting,
            prediction
        )

        results.append(
            result
        )

    if not results:

        print(
            "No predictions were found."
        )

        return

    fieldnames = list(
        results[0].keys()
    )

    with open(
        REPORT_PATH,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(
            results
        )

    print("=" * 60)
    print("20-MEETING EVALUATION")
    print("=" * 60)

    print(
        f"Meetings evaluated: "
        f"{len(results)}"
    )

    print(
        f"Missing predictions: "
        f"{len(missing_predictions)}"
    )

    avg_summary_overlap = mean(
        result[
            "summary_overlap_score"
        ]
        for result in results
    )

    avg_evidence_coverage = mean(
        result[
            "evidence_coverage"
        ]
        for result in results
    )

    total_duplicates = sum(
        result[
            "exact_duplicate_count"
        ]
        for result in results
    )

    review_count = sum(
        1
        for result in results
        if result[
            "requires_human_review"
        ] is True
    )

    print(
        f"Average summary overlap: "
        f"{avg_summary_overlap:.4f}"
    )

    print(
        f"Average evidence coverage: "
        f"{avg_evidence_coverage:.2%}"
    )

    print(
        f"Exact duplicates remaining: "
        f"{total_duplicates}"
    )

    print(
        f"Human review flagged: "
        f"{review_count}/"
        f"{len(results)}"
    )

    print()

    print(
        "Report saved to:"
    )

    print(
        REPORT_PATH
    )


if __name__ == "__main__":
    main()