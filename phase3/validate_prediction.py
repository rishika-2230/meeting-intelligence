import json
from pathlib import Path

from jsonschema import validate
from jsonschema.exceptions import ValidationError

from config import (
    SCHEMA_PATH,
    OUTPUT_DIR
)


# Load schema

with open(
    SCHEMA_PATH,
    "r",
    encoding="utf-8"
) as f:

    schema = json.load(f)


prediction_files = list(
    OUTPUT_DIR.glob(
        "*_prediction.json"
    )
)


if not prediction_files:

    raise FileNotFoundError(
        "No prediction files found."
    )


for file_path in prediction_files:

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as f:

        prediction = json.load(f)


    try:

        validate(
            instance=prediction,
            schema=schema
        )

        print(
            file_path.name,
            "→ SCHEMA VALID"
        )


    except ValidationError as e:

        print(
            file_path.name,
            "→ SCHEMA INVALID"
        )

        print(
            e.message
        )