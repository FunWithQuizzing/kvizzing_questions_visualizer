# KVizzing Questions Visualizer

A pipeline for extracting, structuring, and visualising quiz questions from the KVizzing WhatsApp group.

---

## What is KVizzing?

KVizzing is a WhatsApp group where members regularly post trivia questions across topics like history, science, literature, technology, sports, and entertainment. Questions range from quick factual recalls to multi-part identify questions and connect-the-dots puzzles. This project extracts those Q&A threads from raw chat exports and turns them into structured, queryable data.

---

## Repository Structure

```
v1/                          # Initial extraction pipeline
  analysis_methods.py        # Chat parsing, filtering, and Q&A extraction
  llm_call_llama_v2.py       # LLM-assisted extraction using Llama
  Explainer.docx             # Overview of the v1 approach

v2/                          # Current version
  PIPELINE.md                # End-to-end pipeline architecture (parse → extract → structure → enrich → deploy)
  schema/                    # Single source of truth for the data model
    schema.py                # Pydantic models — run to regenerate everything
    schema.json              # Auto-generated JSON Schema (never edit by hand)
    examples.json            # 4 verified sample instances
    README.md                # Human-readable schema reference
    test_schema.py           # 48 tests covering schema correctness
  visualizer/                # Web app for browsing and exploring the archive
    PRD.md                   # Product requirements document
```

---

## Data Model

Each extracted Q&A pair is a `KVizzingQuestion` object. Key fields:

| Field | Description |
|---|---|
| `id` | Unique identifier — `YYYY-MM-DD-NNN` |
| `question` | Text, asker, type, topic, tags, media flag |
| `answer` | Text, solver, confirmation, collaborative flag, multi-part breakdown |
| `discussion` | Full ordered message thread |
| `stats` | Wrong attempts, hints, time to answer, difficulty |
| `session` | Populated for quizmaster-hosted sessions; null for ad-hoc questions |
| `reactions` | Optional enrichment from WhatsApp SQLite DB |
| `highlights` | Derived emoji category labels (funny, crowd_favourite, etc.) |
| `extraction_confidence` | `high` / `medium` / `low` — how certain the extraction is |

See [`v2/schema/README.md`](v2/schema/README.md) for the full schema, design decisions, and sample instances.

---

## v1 Pipeline

The v1 pipeline (`v1/analysis_methods.py`) parses raw WhatsApp chat exports (`.txt`), filters by date/user, splits into daily files, and extracts Q&A pairs using regex heuristics and an LLM call via Llama. Output is plain text per day.

---

## v2 Pipeline

v2 is under active development. The schema (`v2/schema/`) is complete and locked. The next step is a structured extraction pipeline that outputs validated `KVizzingQuestion` JSON objects conforming to the schema.

The visualizer spec is defined in [`v2/visualizer/PRD.md`](v2/visualizer/PRD.md) — a question feed, detail view, stats/leaderboards, session explorer, and highlights reel, deployable as a static site.

---

## Workflow

### Updating the schema

```bash
cd v2/schema
# Edit schema.py or examples.json, then:
python3 schema.py        # regenerates schema.json and injects into README.md
python3 -m pytest test_schema.py -v   # run 48 schema tests
```

The pre-commit hook runs `schema.py` automatically whenever `schema.py` or `examples.json` is staged.

---

## Privacy

Raw WhatsApp chat exports and derived data files are excluded from this repository via `.gitignore`. Only pipeline code and schema definitions are tracked.
