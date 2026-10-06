# Meeting Intelligence & Execution Hub

> 🚧 **Project Status: Active Development**

An AI-powered meeting intelligence pipeline designed to transform unstructured meeting transcripts into structured, evidence-backed business information such as decisions, commitments, owners, deadlines, objections, risks, and unanswered questions.

The project combines LLM-based structured extraction, evidence validation, evaluation, and meeting-level data modeling, with ongoing work toward real-time Fireflies integration and a searchable execution layer.

---

## Business Problem

Important decisions and commitments are often buried inside meeting transcripts, making follow-up difficult and creating fragmented organizational knowledge.

This project is designed to convert meeting conversations into structured, actionable records that can eventually support:

- Decision tracking
- Commitment and action-item monitoring
- Owner and deadline tracking
- Customer objection analysis
- Risk identification
- Unanswered-question tracking
- Semantic meeting search
- Human review of uncertain extractions
- CRM synchronization

---

## Current Project Status

The core transcript-processing and structured-extraction pipeline has been implemented and tested.

### Current milestone

**120 meetings processed successfully with 0 processing failures.**

Completed work includes:

- Dataset preparation
- Development/evaluation dataset creation
- Structured extraction schema
- LLM extraction pipeline
- Evidence citation and validation
- Multi-meeting batch processing
- 20-meeting development evaluation
- 120-meeting processing run
- Structured meeting and meeting-item tables
- Aggregate prediction output
- Initial Fireflies webhook implementation

### In Progress

- Fireflies API/webhook integration
- Automated transcript ingestion
- CRM integration
- Semantic search
- Human-review workflow
- Management dashboard
- Production deployment

---

## Dataset

The project currently uses meeting transcript data derived from **QMSum**, including meetings originating from conversational meeting corpora such as AMI.

A 20-meeting development/evaluation subset was first used to test and refine the extraction and evidence-validation pipeline before scaling processing to 120 meetings.

Main dataset files:

```text
data/phase1/qmsum_120_meetings.jsonl
data/phase2/development_evaluation_20.jsonl
data/phase2/development_evaluation_20.csv
```

---

## Processing Pipeline

```text
Meeting Transcript
        |
        v
Dataset Preparation
        |
        v
Structured LLM Extraction
        |
        v
Schema Validation
        |
        v
Evidence Citation Validation
        |
        v
Decision / Commitment / Risk / Objection Extraction
        |
        v
Confidence & Evaluation Layer
        |
        v
Structured Meeting Tables
        |
        v
Search / Dashboard / CRM Integration
```

---

## Extracted Information

The extraction schema is designed to identify structured meeting intelligence including:

- Decisions
- Commitments
- Action items
- Owners
- Deadlines
- Objections
- Risks
- Unanswered questions
- Supporting transcript evidence
- Confidence information

The schema is defined in:

```text
data/phase2/meeting_intelligence_schema.json
```

---

## Evidence-Backed Extraction

A key design principle of this project is that extracted information should not be accepted without supporting transcript evidence.

The pipeline therefore validates evidence associated with extracted meeting items.

Relevant scripts include:

```text
phase3/show_evidence.py
phase3/validate_evidence.py
phase3/validate_evidence_120.py
phase3/validate_prediction.py
```

This architecture is intended to reduce unsupported LLM outputs and make extracted information easier to audit.

---

## Evaluation

The pipeline was first evaluated on a 20-meeting development set before scaling to the larger processing run.

Evaluation artifacts include:

```text
phase3/evaluation_20_report.csv
data/phase2/EVALUATION_PROTOCOL.md
data/phase2/evaluation_scorecard_template.csv
```

The evaluation workflow considers structured extraction quality and evidence support rather than relying solely on free-form summary similarity.

---

## 120-Meeting Processing Run

The batch-processing pipeline was subsequently scaled to **120 meetings**.

**Result: 120 meetings processed with 0 failures.**

Important output artifacts include:

```text
phase3/meetings_120.csv
phase3/meeting_items_120.csv
phase3/predictions_120_combined.json
```

Individual generated prediction files are intentionally excluded from version control to keep the repository concise.

---

## Fireflies Integration

The project is being extended from offline transcript processing to real-time meeting ingestion using Fireflies.

Current webhook implementation:

```text
fireflies_webhook.py
```

Target workflow:

```text
Fireflies Meeting
        |
        v
Webhook Event
        |
        v
Transcript Retrieval
        |
        v
Meeting Intelligence Extraction
        |
        v
Evidence Validation
        |
        v
Structured Storage
        |
        v
CRM / Search / Dashboard
```

This integration is currently **under development**.

---

## Project Structure

```text
meeting-intelligence/
|
|-- data/
|   |-- phase1/
|   |   `-- qmsum_120_meetings.jsonl
|   |
|   `-- phase2/
|       |-- development_evaluation_20.jsonl
|       |-- development_evaluation_20.csv
|       |-- EVALUATION_PROTOCOL.md
|       |-- evaluation_scorecard_template.csv
|       |-- extraction_prompt_template.txt
|       `-- meeting_intelligence_schema.json
|
|-- phase3/
|   |-- clean_predictions.py
|   |-- config.py
|   |-- evaluate_twenty_meetings.py
|   |-- run_one_meeting.py
|   |-- run_five_meetings.py
|   |-- run_twenty_meetings.py
|   |-- run_120_meetings.py
|   |-- show_evidence.py
|   |-- validate_evidence.py
|   |-- validate_evidence_120.py
|   |-- validate_prediction.py
|   |-- evaluation_20_report.csv
|   |-- meetings_120.csv
|   |-- meeting_items_120.csv
|   `-- predictions_120_combined.json
|
|-- fireflies_webhook.py
|-- test_env.py
|-- test_gemini.py
|-- .gitignore
`-- README.md
```

---

## Technology Stack

**Language**

- Python

**AI / NLP**

- Large Language Model based structured extraction
- Gemini API
- Prompt-based information extraction
- JSON schema validation

**Data Processing**

- JSON / JSONL
- CSV
- Python data-processing pipeline

**Meeting Integration**

- Fireflies API
- Webhooks

**Planned Components**

- Semantic search
- Vector embeddings
- CRM integration
- Management dashboard
- Human-review interface

---

## Repository Security

API credentials and environment variables are intentionally excluded from version control.

The repository ignores:

```text
.env
.env.*
__pycache__/
venv/
.venv/
```

API keys should be supplied through environment variables rather than hard-coded into source files.

---

## Development Roadmap

### Completed

- [x] Dataset preparation
- [x] 20-meeting development/evaluation set
- [x] Structured extraction schema
- [x] LLM extraction pipeline
- [x] Evidence validation
- [x] Batch processing
- [x] 20-meeting evaluation workflow
- [x] 120-meeting processing run
- [x] Structured meeting tables
- [x] Aggregate prediction output

### In Progress

- [ ] Complete Fireflies integration
- [ ] Automated meeting ingestion
- [ ] CRM synchronization
- [ ] Semantic search
- [ ] Human-review interface
- [ ] Analytics dashboard
- [ ] Production deployment

---

## Why This Project

This project demonstrates an end-to-end approach to applying LLMs to a business operations problem rather than using an LLM only for generic summarization.

The emphasis is on:

- Structured outputs
- Evidence traceability
- Evaluation
- Batch reliability
- Business-action extraction
- Integration with operational systems

---

## Note

This repository represents an **ongoing portfolio project**. Features and evaluation results will continue to evolve as the Fireflies integration, search layer, CRM workflow, and user interface are completed.