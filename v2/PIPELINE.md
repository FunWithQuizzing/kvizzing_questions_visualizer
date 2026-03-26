# KVizzing v2 Pipeline

End-to-end architecture from raw WhatsApp chat export to the live visualizer.

---

## Run Modes

The pipeline always receives the **full `_chat.txt`** as input — WhatsApp exports the entire history each time. Two run modes are supported:

| Mode | When | What gets processed |
|---|---|---|
| **Backfill** | First run, or re-processing history | All dates in `_chat.txt` not already in the store |
| **Incremental** | Daily after backfill is done | Only dates after `last_stored_date` |

Both modes use the same code path. The difference is purely in the **date window** passed to Stage 0:
- Backfill: `since = None` (process everything not yet in the store)
- Incremental: `since = last_stored_date` (process only new days)

State is tracked in `pipeline_state.json`, updated independently for storing and exporting so a failure in either doesn't corrupt the other:

```json
{
  "last_stored_date": "2026-03-25",
  "last_exported_date": "2026-03-25",
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
│  Incremental: dates after last    │
└───────────────┬───────────────────┘
                │  slice of messages
                │  + lookahead buffer (next 4h)
                ▼
┌───────────────┐
│  1. Parse     │  Messages → structured objects
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  2. Extract   │  Heuristic pre-filter → LLM Q&A extraction
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  3. Structure │  Map to schema, validate, assign stable IDs
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  4. Enrich    │  Topic/tags/embeddings via LLM (reactions separate)
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  5. Store     │  Upsert into questions.db (SQLite, transactional)
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

**Reactions enrichment** is a fully separate, on-demand command run when a WhatsApp SQLite DB backup is available:

```bash
python3 pipeline.py enrich-reactions --db path/to/ChatStorage.sqlite
```

---

## Stage 0 — Date Filter

**Input:** `data/raw/_chat.txt` + `pipeline_state.json`

**What it does:**
- Reads `last_stored_date` from `pipeline_state.json`
- Backfill: collects all dates not yet in the store
- Incremental: collects all dates after `last_stored_date`
- For each date collected, includes a **4-hour lookahead buffer** into the next day's messages

**Why the lookahead buffer (critical):**
Q&A threads frequently span midnight — a question posted at 11:45 PM may not be answered until 12:10 AM the next day. Without a lookahead, the thread is split: Stage 2 sees a question with no answer on day D, and orphaned replies on day D+1. The 4-hour buffer ensures threads started in the late evening are captured in full. Duplicate messages from the buffer (already processed on the next day's run) are deduplicated in Stage 5 via the stable question ID.

**Notes:**
- If `pipeline_state.json` doesn't exist → fresh backfill.
- Because the full chat is always the input, missed days are always caught on the next run.

---

## Stage 1 — Parse

**Input:** Filtered message slice (with lookahead) from Stage 0

**What it does:**
- Filters out WhatsApp system messages before any parsing ("X was added", "Messages and calls are end-to-end encrypted", "X changed the group name", "This message was deleted", etc.)
- Parses the WhatsApp message format. Handles multiple locale variants:
  - `[M/D/YY, HH:MM:SS AM/PM] Username: Message` (US locale)
  - `[DD/MM/YYYY, HH:MM:SS] Username: Message` (international locale)
- Handles multi-line messages (continuation lines have no timestamp prefix)
- Detects media placeholders (`<image omitted>`, `<video omitted>`)
- Normalises usernames: strips leading `~`, trims whitespace

**Output:** Per-day arrays of structured message objects

```json
{
  "timestamp": "2026-03-16T07:18:47",
  "username": "pratik.s.chandarana",
  "text": "Q7.",
  "has_media": true
}
```

**Known limitation — username drift:**
Group members change their display names over time. The same person may appear as "Pratik" in 2025 and "pratik.s.chandarana" in 2026. The pipeline treats these as different users. A username alias map (`config/username_aliases.json`) can be maintained manually to merge known aliases, but automated resolution is out of scope.

---

## Stage 2 — Extract

**Input:** Parsed messages per day (with lookahead buffer)

**Two-phase approach:**

### Phase 2a — Heuristic Pre-filter

Before invoking the LLM, cheap heuristics shortlist *candidate question messages* to avoid sending every message to the LLM (which would make a full backfill extremely expensive):

- Message ends with `?`, or starts with `Q.`, `Q1.`, `Q:`, `Flash Q`, etc.
- Message is followed by ≥ 2 replies within 15 minutes from different users
- Message contains known session markers (`###Quiz Start`, `Round`, `Score`)

Only messages passing the pre-filter are sent to Phase 2b.

### Phase 2b — LLM Extraction

For each candidate, the LLM (Claude API) receives a window of ~40 messages centred on the candidate and is asked to output a structured candidate pair:

- Is this a genuine question posed to the group?
- What are the discussion thread boundaries (start/end message)?
- What is the role of each message (`attempt`, `hint`, `confirmation`, `chat`, `answer_reveal`)?
- Was the answer confirmed? What was the confirmation message?
- Is this part of a session? If so, extract quizmaster, theme, question number.

**Output:** Raw candidate pairs (not yet schema-validated), with preliminary `extraction_confidence`:
- `high` — explicit confirmation message found
- `medium` — strong contextual signal ("correct", "bingo" nearby)
- `low` — no confirmation found

**Notes:**
- The window can span day boundaries thanks to the Stage 0 lookahead buffer.
- A single window may contain parts of multiple Q&A threads; the LLM should return all of them.
- `extraction_confidence: "low"` candidates are kept and stored, but hidden from the UI by default.

---

## Stage 3 — Structure

**Input:** Raw candidates from Stage 2

**What it does:**
- Maps each candidate to the `KVizzingQuestion` Pydantic model
- Computes derived fields:
  - `stats.wrong_attempts` — count of `attempt` entries with `is_correct: false`
  - `stats.hints_given` — count of `hint` entries
  - `stats.time_to_answer_seconds` — delta between question and answer timestamps (floored at 0)
  - `stats.unique_participants` — distinct usernames among attempts
  - `stats.difficulty` — derived from `wrong_attempts` (0→easy, 1–3→medium, 4+→hard)
- Assigns a **stable ID**: `YYYY-MM-DD-HHMMSS` based on the question message's timestamp, not a positional index. This ensures the same question always gets the same ID across re-runs.
- Validates against the Pydantic schema — invalid candidates are logged to `data/errors/` and skipped

**Why timestamp-based IDs (critical):**
A positional index (`YYYY-MM-DD-001`) changes if the extraction for that day produces different results on a re-run (e.g. one question is dropped). A timestamp-based ID is derived from the data itself and is stable. The `id` regex in the schema (`^\d{4}-\d{2}-\d{2}-\d+$`) accommodates this — `HHMMSS` is still all digits.

**Notes:**
- `session` is populated here if Stage 2 detected session markers.
- Pydantic is the quality gate. Validation failures are written to `data/errors/YYYY-MM-DD_errors.json`.

---

## Stage 4 — Enrich *(LLM enrichment only; reactions are separate)*

**Input:** Validated questions from Stage 3

**What it does:**

| Enrichment | Source | Output | Required for |
|---|---|---|---|
| Topic classification | LLM (Claude) | `question.topic` | Topic filter |
| Tag generation | LLM (Claude) | `question.tags` | Tag filter |
| Embeddings | OpenAI `text-embedding-3-small` | `embeddings` table in DB | Semantic search (deferred) |

**Embedding model consistency:**
The model name is stored alongside each embedding vector in the `embeddings` table. The pipeline checks on startup that the configured model matches what is already in the DB and refuses to run if they differ — mixing vectors from different models produces meaningless similarity scores.

```sql
CREATE TABLE embeddings (
    question_id TEXT PRIMARY KEY,
    model       TEXT NOT NULL,
    vector      BLOB NOT NULL   -- serialised float32 array
);
```

**Emoji→category config:**
The `highlights` computation (part of reactions enrichment) uses a mapping file at `v2/pipeline/config/emoji_categories.json`. Example:
```json
{ "😂": "funny", "😄": "funny", "❤️": "crowd_favourite", "✅": "confirmed_correct", "🔥": "spicy", "😮": "surprising" }
```
New categories are added here without touching the schema.

**Notes:**
- Only questions not already enriched in the store are sent to the LLM — incremental runs are cheap.
- Embedding the full backfill (~1,500 questions) at `text-embedding-3-small` rates costs < $0.01.
- Semantic search is not surfaced in the UI yet (see Open Questions). Embeddings are generated now so the HNSW index can be built later without re-processing.

---

## Reactions Enrichment *(separate, on-demand)*

Reactions are fully decoupled from the daily pipeline because the WhatsApp SQLite DB is not always available.

```bash
python3 pipeline.py enrich-reactions --db path/to/ChatStorage.sqlite
```

**What it does:**
- Reads reaction records from the SQLite DB (`ZWAMESSAGEREACTION` on iOS, `message_reactions` on Android)
- Matches reactions to questions by `message_timestamp`
- Updates `reactions[]` and computes `highlights` using `config/emoji_categories.json`
- Upserts back into `questions.db`

Run this whenever a device backup is available. Safe to re-run — reactions are replaced, not appended.

---

## Stage 5 — Store

**Input:** Enriched `KVizzingQuestion` objects from Stage 4

**SQLite schema:**

The full question JSON is stored as a blob for simplicity, alongside indexed scalar columns for fast filtering. This avoids a complex normalised schema while keeping common queries efficient.

```sql
CREATE TABLE questions (
    id                    TEXT PRIMARY KEY,
    date                  TEXT NOT NULL,        -- YYYY-MM-DD, indexed
    asker                 TEXT NOT NULL,        -- indexed
    session_id            TEXT,                 -- indexed, null for ad-hoc
    topic                 TEXT,                 -- indexed
    difficulty            TEXT,                 -- indexed
    extraction_confidence TEXT NOT NULL,        -- indexed
    has_reactions         INTEGER DEFAULT 0,
    payload               TEXT NOT NULL         -- full KVizzingQuestion JSON
);

CREATE INDEX idx_questions_date       ON questions(date);
CREATE INDEX idx_questions_asker      ON questions(asker);
CREATE INDEX idx_questions_session    ON questions(session_id);
CREATE INDEX idx_questions_topic      ON questions(topic);
CREATE INDEX idx_questions_difficulty ON questions(difficulty);
```

**What it does:**
- Wraps each day's batch in a **single SQLite transaction** — either all questions for the day are stored or none are (no partial state)
- `INSERT OR REPLACE` on `id` ensures re-runs are always safe
- Updates `pipeline_state.json` → sets `last_stored_date` (not `last_exported_date`)

**Output:** `data/questions.db`

---

## Stage 6 — Export

**Input:** `data/questions.db`

**What it does:**
- Queries all questions and exports to `data/questions.json` (sorted by `question.timestamp`)
- Generates `data/questions_by_date/YYYY-MM-DD.json` — per-day slices for calendar queries
- Generates `data/sessions.json` — index of all sessions with metadata (loaded first by calendar sidebar)
- Generates `data/stats.json` — pre-aggregated leaderboards, topic counts, difficulty over time
- Generates `data/tags.json` — tag → [question_id, ...] index for instant tag filtering
- Builds `data/search.hnsw` — HNSW vector index from stored embeddings *(only if embeddings present)*
- Updates `pipeline_state.json` → sets `last_exported_date`

**Why pre-aggregate:**
The UI is a static site with no backend. Computing leaderboards or tag indices client-side over thousands of questions on every load is wasteful. Everything is computed once at export time.

**Search capabilities:**

| Search type | How | Asset |
|---|---|---|
| Keyword / full-text | Pagefind indexes rendered HTML at build time | Pagefind index (auto) |
| Filter by asker | Client-side filter on `questions.json` | `questions.json` |
| Filter by tag | Tag → ID lookup | `data/tags.json` |
| Filter by topic / difficulty / type | Indexed columns in export | `questions.json` |
| Semantic search *(deferred)* | In-browser HNSW nearest-neighbour | `data/search.hnsw` |

**Output:**
```
data/
  questions.json              ← full archive for the UI (committed to git)
  questions_by_date/
    2025-09-23.json
    2026-03-16.json
    ...
  sessions.json               ← calendar sidebar loads this first
  stats.json                  ← pre-computed leaderboards + charts
  tags.json                   ← tag → [question_id, ...] index
  search.hnsw                 ← vector index for semantic search (optional)
  questions.db                ← pipeline internal store (gitignored)
  pipeline_state.json         ← tracks last stored + exported dates
```

---

## Stage 7 — Deploy

**Input:** `data/` files + visualizer source (`v2/visualizer/`)

**What it does:**
- Copies `data/` into the frontend's `static/` (or `public/`) directory so JSON files are served as static assets
- Runs Pagefind to build the full-text search index over rendered HTML
- Runs the frontend build (SvelteKit / Next.js static export) → `dist/`
- Deploys to GitHub Pages or Netlify

**Trigger:**

```bash
# Full backfill + deploy (first time)
make backfill && make export && make build && make deploy

# Daily incremental run
make incremental && make export && make build && make deploy

# Reactions enrichment (run when device backup is available)
make enrich-reactions DB=path/to/ChatStorage.sqlite && make export && make build && make deploy
```

**Note:** The pipeline is triggered manually — WhatsApp chat exports require a manual export from the phone and placement in `data/raw/`. Fully automated daily runs are not feasible given this constraint.

---

## Gitignore

The following must be in `.gitignore` to prevent data files from being accidentally committed:

```
data/raw/           # raw chat exports — private
data/questions.db   # binary, regenerable from raw chat
data/errors/        # ephemeral error logs
```

The following **should be committed** so the visualizer works immediately on clone:

```
data/questions.json              # the UI's primary data source
data/questions_by_date/          # calendar queries
data/sessions.json
data/stats.json
data/tags.json
pipeline_state.json
```

---

## Error Review

Low-confidence candidates logged to `data/errors/` can be reviewed with:

```bash
python3 pipeline.py review
```

This prints each candidate one by one and accepts:
- `a` — approve (promotes to `high` confidence, stores in DB)
- `r` — reject (discards permanently)
- `s` — skip (leaves in errors for later)

---

## Data Flow Summary

```
data/raw/_chat.txt              ← drop full WhatsApp export here (every run)
v2/pipeline/config/
  emoji_categories.json         ← emoji → highlight category mapping
  username_aliases.json         ← manual username deduplication (optional)

pipeline_state.json             ← last_stored_date + last_exported_date

data/questions.db               ← SQLite: questions + embeddings (gitignored)
data/errors/                    ← failed validations for manual review (gitignored)

data/questions.json             ← Stage 6 export (committed to git)
data/questions_by_date/         ← Stage 6 export (committed to git)
data/sessions.json              ← Stage 6 export (committed to git)
data/stats.json                 ← Stage 6 export (committed to git)
data/tags.json                  ← Stage 6 export (committed to git)
data/search.hnsw                ← Stage 6 export, semantic search (optional)

dist/                           ← Stage 7 output (deployable static site)
```

---

## What's Already Built

| Stage | Status |
|---|---|
| 0. Date Filter | Not started |
| 1. Parse | Largely done in `v1/analysis_methods.py` — needs porting + system message filtering |
| 2. Extract | Partially done in v1 — needs heuristic pre-filter, LLM integration, session detection |
| 3. Structure | Schema complete (`v2/schema/`). Mapping logic + stable ID assignment to be written. |
| 4. Enrich | Not started |
| Reactions Enrichment | Not started |
| 5. Store | Not started |
| 6. Export | Not started |
| 7. Deploy | Not started |
| Error review CLI | Not started |

---

## Resolved Design Decisions

| # | Question | Decision |
|---|---|---|
| 1 | LLM for extraction | **Claude API** — better handling of informal Indian English, emojis, non-obvious confirmations |
| 2 | Embedding model | **OpenAI `text-embedding-3-small`** — cheap, hosted, no local ML setup. Backfill of ~1,500 questions costs < $0.01 |
| 3 | Semantic search in UI | **Deferred** — 20MB WASM download is too heavy for mobile users. Embeddings generated now; HNSW index and UI added later |
| 4 | Error review | **Simple CLI** (`pipeline.py review`) — approve/reject/skip per candidate |
| 5 | Reactions enrichment | **Fully decoupled** — separate `enrich-reactions` command, not part of the daily pipeline |
| 6 | questions.db in git | **Not committed** — binary diffs bloat repo history. `questions.json` (the export) is committed instead and is sufficient to run the UI |
