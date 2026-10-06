# Phase 2 — LLM Schema & Evaluation Set

Phase 2 prepares the extraction contract and a controlled 20-meeting development/evaluation subset.
No LLM predictions have been generated yet.

## Outputs
- `meeting_intelligence_schema.json` — strict JSON Schema.
- `extraction_prompt_template.txt` — evidence-grounded extraction prompt.
- `development_evaluation_20.csv` — metadata for selected 20 meetings.
- `development_evaluation_20.jsonl` — transcripts plus held-out evaluation ground truth.
- `evaluation_scorecard_template.csv` — experiment tracking/evaluation table.
- `EVALUATION_PROTOCOL.md` — validation procedure.

## 20-meeting subset
Domain distribution: {'Product': 10, 'Academic': 5, 'Committee': 5}
Split distribution: {'train': 11, 'test': 5, 'val': 4}
Meetings with AMI manual decision annotations: 10

## Important
The `evaluation_ground_truth` section in the JSONL must NOT be sent to the LLM.
It exists only for post-prediction evaluation.
