import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "phase3" / "outputs"


SECTIONS = [
    "decisions",
    "commitments",
    "action_items",
    "objections",
    "risks",
    "unanswered_questions",
]


def normalize_text(text):
    if not text:
        return ""

    text = text.lower().strip()

    replacements = [
        ".", ",", ";", ":", "!", "?", "-", "_",
        "(", ")", "[", "]", "{", "}", "'", '"'
    ]

    for char in replacements:
        text = text.replace(char, " ")

    return " ".join(text.split())


def get_item_text(item):
    """
    Tries common text-field names used in the schema.
    """
    for key in [
        "text",
        "decision",
        "description",
        "action",
        "commitment",
        "objection",
        "risk",
        "question",
    ]:
        value = item.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def merge_evidence(existing_item, duplicate_item):
    existing_ids = existing_item.get("evidence_turn_ids", [])
    duplicate_ids = duplicate_item.get("evidence_turn_ids", [])

    merged = []

    for turn_id in existing_ids + duplicate_ids:
        if turn_id not in merged:
            merged.append(turn_id)

    existing_item["evidence_turn_ids"] = merged


def deduplicate_section(items):
    """
    Removes exact normalized duplicates.

    If duplicates have different evidence citations,
    their evidence IDs are merged into one item.
    """

    unique_items = []
    seen = {}

    for item in items:
        item_text = get_item_text(item)
        normalized = normalize_text(item_text)

        # Keep items that cannot be safely compared
        if not normalized:
            unique_items.append(item)
            continue

        if normalized in seen:
            existing_item = seen[normalized]

            merge_evidence(existing_item, item)

            # Keep the higher confidence score if available
            existing_confidence = existing_item.get("confidence")
            duplicate_confidence = item.get("confidence")

            if (
                isinstance(existing_confidence, (int, float))
                and isinstance(duplicate_confidence, (int, float))
            ):
                existing_item["confidence"] = max(
                    existing_confidence,
                    duplicate_confidence
                )

            print(f"  DUPLICATE REMOVED: {item_text}")

        else:
            seen[normalized] = item
            unique_items.append(item)

    return unique_items


def clean_prediction(prediction):
    total_removed = 0

    for section in SECTIONS:
        items = prediction.get(section, [])

        if not isinstance(items, list):
            continue

        before = len(items)

        cleaned_items = deduplicate_section(items)

        after = len(cleaned_items)

        prediction[section] = cleaned_items

        removed = before - after
        total_removed += removed

        if removed:
            print(f"  {section}: removed {removed} duplicate(s)")

    return prediction, total_removed


def main():
    prediction_files = sorted(
        OUTPUT_DIR.glob("*_prediction.json")
    )

    print(f"Found {len(prediction_files)} prediction file(s).")
    print()

    total_removed_all_files = 0

    for prediction_file in prediction_files:

        print("=" * 60)
        print(f"Cleaning: {prediction_file.name}")

        with open(
            prediction_file,
            "r",
            encoding="utf-8"
        ) as f:
            prediction = json.load(f)

        cleaned_prediction, removed = clean_prediction(
            prediction
        )

        total_removed_all_files += removed

        with open(
            prediction_file,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                cleaned_prediction,
                f,
                indent=2,
                ensure_ascii=False
            )

        if removed == 0:
            print("  No exact duplicates found.")

        print()

    print("=" * 60)
    print(
        f"Cleaning finished. "
        f"Total duplicates removed: {total_removed_all_files}"
    )


if __name__ == "__main__":
    main()