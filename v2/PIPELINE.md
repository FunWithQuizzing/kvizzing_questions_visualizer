# KVizzing v2 Pipeline

End-to-end architecture from raw WhatsApp chat export to the live visualizer.

---

## Run Modes

The pipeline always receives the **full `_chat.txt`** as input — WhatsApp exports the entire history each time. Two run modes are supported:

| Mode | When | What gets processed |
|---|---|---|
| **Backfill** | First run, or re-processing history | All dates in `_chat.txt` not already in the store |
| **Incremental** | Daily after backfill is done | Only the last day's messages |

Both modes use the same code path. The difference is purely in the **date window** passed to the parse stage:
- Backfill: `since = None` (process everything not yet in the store)
- Incremental: `since = yesterday` (process only the most recent day)

State is tracked in a single `pipeline_state.json` file that records the last successfully processed date. On each run, the pipeline reads this file to decide what to process, and updates it on success.

```json
// pipeline_state.json
{
  "last_processed_date": "2026-03-25",
  "total_questions": 847
}
```

---

## Overview

```
data/raw/_chat.txt  (always the full export)
        │
        ▼
┌───────────────────────────────────┐
│  0. Date Filter                   │
│  Backfill: all dates not in store │
│  Incremental: last day only       │
└───────────────┬───────────────────┘
                │  slice of messages
                ▼
┌───────────────┐
│  1. Parse     │  Messages → structured objects
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  2. Extract   │  Q&A threads via LLM
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  3. Structure │  Map to schema, validate, deduplicate
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  4. Enrich    │  Topic/tags/embeddings via LLM, reactions from SQLite
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  5. Store     │  Upsert into questions.db (SQLite)
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  6. Export    │  SQLite → JSON + search indices for the UI
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  7. Deploy    │  Build static site + push to GitHub Pages / Netlify
└───────────────┘
```

---

## Stage 0 — Date Filter

**Input:** `data/raw/_chat.txt` + `pipeline_state.json`

**What it does:**
- Reads `last_processed_date` from `pipeline_state.json`
- Scans `_chat.txt` for all dates present
- **Backfill mode** (`last_processed_date` is null): returns all dates
- **Incremental mode**: returns only dates after `last_processed_date` — in practice, just yesterday/today
- Passes the relevant message slice to Stage 1

**Notes:**
- Because the full chat is always the input, this stage never misses data — even if a day was skipped, the next run will catch up.
- If `pipeline_state.json` doesn't exist, the pipeline assumes a fresh backfill.

---

## Stage 1 — Parse

**Input:** Filtered message slice from Stage 0

**What it does:**
- Parses the WhatsApp message format: `[M/D/YY, HH:MM:SS] Username: Message`
- Handles multi-line messages (continuation lines have no timestamp prefix)
- Detects media placeholders (`<image omitted>`, `<video omitted>`)
- Normalises usernames (strips leading `~`, trims whitespace)

**Output:** Per-day arrays of structured message objects

```json
{
  "timestamp": "2026-03-16T07:18:47",
  "username": "pratik.s.chandarana",
  "text": "Q7.",
  "has_media": true
}
```

**Notes:**
- Pure parsing — no LLM, no intelligence. Fast and deterministic.
- Already largely implemented in `v1/analysis_methods.py`.

---

## Stage 2 — Extract

**Input:** Parsed messages per day

**What it does:**
- Identifies Q&A threads — a question, its replies, and a confirmation or reveal
- Detects session markers (e.g. "###Quiz Start", score tracking, quizmaster patterns)
- Groups messages into candidate Q&A pairs
- Assigns preliminary `extraction_confidence`:
  - `high` — explicit confirmation message found
  - `medium` — strong contextual signal ("correct", "bingo" nearby)
  - `low` — no confirmation found

**LLM role:**
The hardest stage. Heuristics alone miss too many edge cases. An LLM (Claude API recommended) is used to:
- Determine if a message is a question posed to the group
- Identify the confirmation or reveal message
- Classify each thread message's role (`attempt`, `hint`, `confirmation`, `chat`, `answer_reveal`)
- Extract session metadata (quizmaster, theme, question number)

Prompt strategy: feed a sliding window of ~40 messages around a suspected question and ask for a structured candidate pair as JSON output.

**Output:** Raw candidate pairs (not yet schema-validated)

**Notes:**
- Produces *candidates* — not all will pass schema validation in Stage 3.
- `extraction_confidence: "low"` candidates are kept, stored, but hidden from the UI by default.

---

## Stage 3 — Structure

**Input:** Raw candidates from Stage 2

**What it does:**
- Maps each candidate to the `KVizzingQuestion` Pydantic model
- Computes derived fields:
  - `stats.wrong_attempts` — count of `attempt` entries with `is_correct: false`
  - `stats.hints_given` — count of `hint` entries
  - `stats.time_to_answer_seconds` — delta between question and answer timestamps
  - `stats.unique_participants` — distinct usernames among attempts
  - `stats.difficulty` — derived from `wrong_attempts` (0→easy, 1–3→medium, 4+→hard)
- Assigns `id` in `YYYY-MM-DD-NNN` format (NNN = 1-based index within the day)
- Validates against the Pydantic schema — invalid candidates are logged and skipped

**Output:** Validated `KVizzingQuestion` objects ready for storage

**Notes:**
- Pydantic is the quality gate. Anything that doesn't conform is logged to `data/errors/` for manual review.
- `session` is populated here if Stage 2 detected session markers.

---

## Stage 4 — Enrich *(optional)*

**Input:** Validated questions from Stage 3 + optionally WhatsApp SQLite DB

**What it does:**

| Enrichment | Source | Output | Required for |
|---|---|---|---|
| Topic classification | LLM | `question.topic` | Topic filter |
| Tag generation | LLM | `question.tags` | Tag filter |
| Embeddings | Embedding model | stored in `questions.db` | Semantic search |
| Reactions | WhatsApp SQLite DB | `reactions[]` | Highlights reel |
| Highlights | Derived from reactions + config | `highlights` | Highlights reel |

**Embeddings for semantic search:**
Each question's text is embedded into a vector using an embedding model (e.g. `text-embedding-3-small` from OpenAI, or a local model via `sentence-transformers`). Vectors are stored in a dedicated `embeddings` table in `questions.db`, keyed on `question.id`.

At export time (Stage 6), these vectors are used to build a static HNSW index file. In the browser, a user's search query is embedded client-side using `transformers.js` (runs the model in-browser via WASM), and the HNSW index is queried for nearest neighbours — returning semantically similar questions with no backend required.

This means a search like *"questions about Indian history"* surfaces relevant questions even if those exact words don't appear in the question text.

**Notes:**
- All enrichments are fully optional. Only new questions (not already enriched in the store) are sent to the LLM — incremental runs are cheap.
- Reactions require the WhatsApp SQLite DB from device backup (iOS: `ChatStorage.sqlite`; Android: `msgstore.db`). Pipeline skips gracefully if not provided.
- Embedding the full backfill (~1,500 questions) is a one-time batch job. Each incremental run embeds only the new day's questions.

---

## Stage 5 — Store

**Input:** Enriched (or structured) `KVizzingQuestion` objects

**What it does:**
- Upserts each question into `data/questions.db` (SQLite) keyed on `id`
- A unique constraint on `id` means re-running the pipeline is always safe — existing questions are updated, new ones are inserted, nothing is duplicated
- Updates `pipeline_state.json` with the new `last_processed_date` and total question count

**Why SQLite over flat JSON:**

| | Flat JSON | SQLite |
|---|---|---|
| Deduplication | Manual, error-prone | Unique constraint on `id` |
| Incremental append | Requires reading + rewriting full file | Single `INSERT OR REPLACE` |
| Querying (e.g. by date, topic) | Load entire file client-side | Native SQL |
| Human-readable | Yes | No (but DB Browser for SQLite is free) |
| Git-committable | Yes | Yes (binary diff, but committable) |
| Export to JSON | Is JSON | One query |

At the expected scale (~1,000–2,000 questions over several years), both would work. SQLite is chosen because **safe incremental updates are guaranteed by the schema**, not by careful file management.

**Output:** `data/questions.db` — the single source of truth for all processed questions

---

## Stage 6 — Export

**Input:** `data/questions.db`

**What it does:**
- Exports the full archive to `data/questions.json` (sorted by `question.timestamp`)
- Generates `data/questions_by_date/YYYY-MM-DD.json` — per-day slices for calendar queries
- Generates `data/sessions.json` — index of all sessions (loaded first by the calendar sidebar)
- Generates `data/stats.json` — pre-aggregated leaderboards, topic counts, difficulty over time
- Generates `data/tags.json` — tag → question ID index for instant tag filtering
- Builds `data/search.hnsw` — static HNSW vector index from stored embeddings, consumed by the browser for semantic search (only generated if embeddings are present)

**Why pre-aggregate:** The UI is a static site. Computing leaderboards or tag indices client-side over thousands of questions on every load is wasteful. Everything is computed once at export time.

**Search capabilities enabled by this export:**

| Search type | How | File used |
|---|---|---|
| Keyword / full-text | Pagefind indexes rendered HTML at build time | Pagefind index (auto-generated) |
| Filter by asker | Client-side filter on `questions.json` | `questions.json` |
| Filter by tag | Tag → ID lookup | `data/tags.json` |
| Filter by topic / difficulty / type | Client-side filter | `questions.json` |
| Semantic search | Query embedded in-browser → HNSW nearest-neighbour | `data/search.hnsw` |

**Output:**
```
data/
  questions.json              ← full archive for the UI
  questions_by_date/
    2025-09-23.json
    2026-03-16.json
    ...
  sessions.json               ← calendar sidebar loads this first
  stats.json                  ← pre-computed leaderboards + charts
  tags.json                   ← tag → [question_id, ...] index
  search.hnsw                 ← vector index for semantic search (optional)
  questions.db                ← pipeline's internal store (not served to UI)
  pipeline_state.json         ← tracks last processed date
```

---

## Stage 7 — Deploy

**Input:** `data/` files + visualizer source (`v2/visualizer/`)

**What it does:**
- Runs the frontend build (SvelteKit / Next.js static export)
- Outputs a fully static site to `dist/`
- Deploys to GitHub Pages or Netlify

**Trigger options:**

```bash
# Full backfill + deploy (first time)
make backfill && make build && make deploy

# Daily incremental run
make incremental && make build && make deploy
```

---

## Data Flow Summary

```
data/raw/_chat.txt              ← drop the full WhatsApp export here (every run)

pipeline_state.json             ← tracks last processed date

data/questions.db               ← SQLite store: questions + embeddings (Stages 1–5)
data/errors/                    ← failed validations for manual review

data/questions.json             ← Stage 6 export (UI-ready)
data/questions_by_date/         ← Stage 6 export (calendar queries)
data/sessions.json              ← Stage 6 export (calendar sidebar)
data/stats.json                 ← Stage 6 export (leaderboards, charts)
data/tags.json                  ← Stage 6 export (tag filter index)
data/search.hnsw                ← Stage 6 export (semantic search index, optional)

dist/                           ← Stage 7 output (deployable static site)
```

---

## What's Already Built

| Stage | Status |
|---|---|
| 0. Date Filter | Not started |
| 1. Parse | Largely done in `v1/analysis_methods.py` — needs porting |
| 2. Extract | Partially done in v1 — needs LLM integration and session detection |
| 3. Structure | Schema complete (`v2/schema/`). Mapping logic to be written. |
| 4. Enrich | Not started |
| 5. Store | Not started |
| 6. Export | Not started |
| 7. Deploy | Not started |

---

## Open Questions

1. **LLM for extraction**: Claude API vs local Llama (v1 used Llama)? Claude will be more accurate; cost is low given infrequent runs.
2. **Embedding model**: OpenAI `text-embedding-3-small` (fast, hosted, small cost) vs a local `sentence-transformers` model (free, runs offline, slower backfill)? For a one-time backfill of ~1,500 questions, either is fine.
3. **Semantic search client-side model**: `transformers.js` embeds the user's query in-browser (no backend needed) but adds ~20MB WASM download on first search. Acceptable given the audience (members who use it regularly)?
4. **Error review**: A lightweight CLI or UI to review `extraction_confidence: "low"` candidates and promote/discard them manually? Or is editing `questions.db` directly acceptable for now?
5. **Reactions timing**: The WhatsApp SQLite DB is not always available. Should reactions be a separate optional enrichment run, decoupled from the daily pipeline?
6. **questions.db in git**: Commit it so the data travels with the code, or keep local-only? Committing means anyone can clone and run the visualizer immediately; not committing keeps the repo lean but requires a full re-run on a new machine.
