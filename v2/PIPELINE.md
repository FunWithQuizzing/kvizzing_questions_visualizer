# KVizzing v2 Pipeline

End-to-end architecture from raw WhatsApp chat export to the live visualizer.

---

## Overview

```
Raw chat export (.txt)
        │
        ▼
┌───────────────┐
│  1. Parse     │  Split messages into structured objects
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  2. Extract   │  Identify Q&A threads using LLM
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  3. Structure │  Map to KVizzingQuestion schema + validate
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  4. Enrich    │  Add topic, difficulty, reactions (optional)
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  5. Build     │  Assemble data/ files for the UI
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  6. Deploy    │  Static site → GitHub Pages / Netlify
└───────────────┘
```

---

## Stage 1 — Parse

**Input:** `data/raw/_chat.txt` (WhatsApp `.txt` export)

**What it does:**
- Parses the WhatsApp message format: `[M/D/YY, HH:MM:SS] Username: Message`
- Handles multi-line messages (continuation lines have no timestamp prefix)
- Detects media placeholders (`<image omitted>`, `<video omitted>`)
- Splits output into one file per day

**Output:** `data/parsed/YYYY-MM-DD.json` — array of message objects per day

```json
{
  "timestamp": "2026-03-16T07:18:47",
  "username": "pratik.s.chandarana",
  "text": "Q7.",
  "has_media": true
}
```

**Notes:**
- Pure parsing — no intelligence, no LLM. Fast and deterministic.
- Username normalisation happens here (strip leading `~`, trim whitespace).
- This stage is already largely implemented in `v1/analysis_methods.py`.

---

## Stage 2 — Extract

**Input:** `data/parsed/YYYY-MM-DD.json`

**What it does:**
- Identifies Q&A threads — a question message, its replies, and a confirmation or reveal
- Detects session markers (e.g. "###Quiz Start", score tracking messages, quizmaster patterns)
- Groups messages into candidate Q&A pairs
- Assigns a preliminary `extraction_confidence` based on signal strength:
  - `high`: explicit confirmation message found
  - `medium`: strong contextual signal (e.g. "correct", "bingo" nearby)
  - `low`: no confirmation found

**Output:** `data/extracted/YYYY-MM-DD_candidates.json` — raw candidate pairs, not yet schema-validated

**LLM role:**
The extraction step is the hardest part of the pipeline. Heuristics alone will miss edge cases. An LLM call (e.g. Claude) is used to:
- Determine if a message is a question being posed to the group
- Identify the confirmation message for an answer
- Classify the role of each message in the thread (`attempt`, `hint`, `confirmation`, etc.)
- Extract session metadata (quizmaster, theme, question number)

Suggested prompt strategy: feed the LLM a window of messages (e.g. 30–50 around a suspected question) and ask it to output a structured candidate pair.

**Notes:**
- This stage produces *candidates* — not all will be valid Q&A pairs.
- `extraction_confidence: "low"` candidates are kept but filtered out of the UI by default.

---

## Stage 3 — Structure

**Input:** `data/extracted/YYYY-MM-DD_candidates.json`

**What it does:**
- Maps each candidate to the `KVizzingQuestion` Pydantic model
- Computes derived fields:
  - `stats.wrong_attempts` — count of `attempt` entries with `is_correct: false`
  - `stats.hints_given` — count of `hint` entries
  - `stats.time_to_answer_seconds` — delta between `question.timestamp` and `answer.timestamp`
  - `stats.unique_participants` — distinct usernames in `attempt` entries
  - `stats.difficulty` — derived from `wrong_attempts` (0 → easy, 1–3 → medium, 4+ → hard)
- Validates each object against the schema; logs and skips invalid ones
- Assigns a unique `id` in `YYYY-MM-DD-NNN` format

**Output:** `data/structured/YYYY-MM-DD.json` — validated `KVizzingQuestion` arrays

**Notes:**
- Pydantic validation acts as a quality gate. Anything that doesn't conform to the schema is logged to `data/errors/YYYY-MM-DD_errors.json` for manual review.
- `session` is populated here if the extraction stage detected session markers.

---

## Stage 4 — Enrich *(optional)*

**Input:** `data/structured/YYYY-MM-DD.json` + optionally WhatsApp SQLite DB

**What it does:**

| Enrichment | Source | Output field |
|---|---|---|
| Topic classification | LLM (classify question text) | `question.topic` |
| Tag generation | LLM | `question.tags` |
| Reactions | WhatsApp SQLite DB (`ChatStorage.sqlite` / `msgstore.db`) | `reactions[]` |
| Highlights | Derived from reactions + emoji→category config | `highlights` |

**Output:** `data/enriched/YYYY-MM-DD.json` — same structure as structured, with optional fields populated

**Notes:**
- This stage is fully optional. The visualizer works without it — topic/tag filters are simply empty, and the highlights reel is hidden.
- Reactions require access to the device SQLite DB, which not everyone will have. The pipeline gracefully skips this if the DB is not provided.
- Topic/tag LLM calls can be batched cheaply since question texts are short.

---

## Stage 5 — Build Data

**Input:** All files from `data/structured/` (or `data/enriched/` if enrichment ran)

**What it does:**
- Merges all daily files into `data/questions.json` (sorted by `question.timestamp`)
- Splits into `data/questions_by_date/YYYY-MM-DD.json` for efficient date-range queries
- Generates `data/sessions.json` — index of all sessions with metadata and question counts
- Generates `data/stats.json` — pre-computed aggregate stats (leaderboards, topic counts, etc.) so the UI doesn't need to compute them client-side

**Output:**
```
data/
  questions.json                  ← full archive
  questions_by_date/
    2025-09-23.json
    2026-03-16.json
    ...
  sessions.json                   ← session index
  stats.json                      ← pre-aggregated stats
```

**Notes:**
- Pre-aggregating stats at build time keeps the UI fast — no client-side reduce over thousands of questions on load.
- `sessions.json` is what the calendar sidebar loads first to render session events without fetching the full archive.

---

## Stage 6 — Deploy

**Input:** `data/` files + visualizer source (`v2/visualizer/`)

**What it does:**
- Runs the frontend build (SvelteKit / Next.js static export)
- Outputs a fully static site (`dist/` or `out/`)
- Deploys to GitHub Pages or Netlify

**Recommended trigger:** a simple shell script or `Makefile` target that runs all pipeline stages in order, then builds and deploys.

```
make pipeline   # stages 1–5
make build      # stage 6 (build UI)
make deploy     # push to GitHub Pages / Netlify
```

---

## Data Flow Summary

```
data/raw/                    ← you drop the chat export here
  _chat.txt

data/parsed/                 ← Stage 1 output
  YYYY-MM-DD.json

data/extracted/              ← Stage 2 output
  YYYY-MM-DD_candidates.json

data/structured/             ← Stage 3 output (schema-validated)
  YYYY-MM-DD.json

data/enriched/               ← Stage 4 output (optional)
  YYYY-MM-DD.json

data/                        ← Stage 5 output (UI-ready)
  questions.json
  questions_by_date/
  sessions.json
  stats.json

dist/ (or out/)              ← Stage 6 output (deployable static site)
```

---

## What's Already Built

| Stage | Status |
|---|---|
| 1. Parse | Largely done in `v1/analysis_methods.py` — needs porting to v2 |
| 2. Extract | Partially done in v1 — needs LLM integration and session detection |
| 3. Structure | Schema is complete (`v2/schema/`). Mapping logic to be written. |
| 4. Enrich | Not started |
| 5. Build Data | Not started |
| 6. Deploy | Not started |

---

## Open Questions

1. **LLM for extraction**: Claude API vs local Llama (v1 used Llama)? Claude will be more accurate but has a cost per run. For a group chat archive that's processed once (or infrequently), Claude API is likely the right call.
2. **Incremental runs**: Should the pipeline support incremental updates (only process new days) or always run from scratch? Incremental is more efficient but adds complexity.
3. **Error review UI**: Should there be a lightweight way to review and correct `extraction_confidence: "low"` candidates, or is manual JSON editing acceptable for now?
