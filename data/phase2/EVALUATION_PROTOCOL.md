# Phase 2 Evaluation Protocol

## Purpose
Develop and validate the extraction contract on 20 meetings before processing all 120.

## Development set
20 meetings are selected to cover:
- Product meetings with AMI manual decision annotations where possible.
- Academic meetings.
- Committee meetings.
- Train/validation/test partitions.
- Long, annotation-rich transcripts.

## Model input
Only `meeting_id` and `transcript_text` are supplied to the extraction model.
Reference summaries, QMSum queries/topics, and AMI annotations are held out as ground truth.

## Required checks
1. JSON/schema validity: output must validate against `meeting_intelligence_schema.json`.
2. Evidence validity: every cited turn must exist and support the extracted claim.
3. Summary quality: compare generated summary with QMSum human reference.
4. Decision extraction: for meetings with AMI decision ground truth, manually/semantically align
   predicted decisions to reference decisions and compute precision, recall, and F1.
5. Hallucination audit: count unsupported owners, deadlines, actions, decisions, risks, and objections.
6. Human-review calibration: compare confidence/review flags with reviewer judgments.

## Recommended acceptance gate before all 120 meetings
- 100% schema-valid outputs.
- >= 95% valid evidence citations.
- No fabricated owner/deadline accepted as correct.
- Decision extraction reviewed on all available AMI-grounded development meetings.
- Prompt/schema revised until failure modes are documented and acceptable.

Do not treat confidence thresholds as calibrated until validation supports them.
