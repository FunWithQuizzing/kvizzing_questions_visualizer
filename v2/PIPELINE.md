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

State is tracked in `data/pipeline_state.json`, updated independently for storing and exporting so a failure in either doesn't corrupt the other:

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
│  4. Enrich    │  Topic/tags via LLM (reactions + media separate)
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

**Reactions enrichment** and **media enrichment** are fully separate, on-demand commands run when the relevant sources become available:

```bash
python3 pipeline.py enrich-reactions --db path/to/ChatStorage.sqlite
python3 pipeline.py enrich-media --media-dir path/to/WhatsApp/Media
```

---

## Directory Structure

```
KVizzing/
  v1/                         ← DO NOT MODIFY — legacy code and data
    _chat.txt                 ← source chat export (read-only input to v2 pipeline)
    analysis_methods.py       ← reference for porting Stage 1/2 logic
    ...

  v2/
    PIPELINE.md               ← this document
    data/
      raw/                    ← drop _chat.txt here before running (gitignored)
      questions.db            ← SQLite store (gitignored)
      errors/                 ← validation failures (gitignored)
      questions.json          ← Stage 6 export (committed)
      sessions.json           ← Stage 6 export (committed)
      stats.json              ← Stage 6 export (committed)
      tags.json               ← Stage 6 export (committed)
      members.json            ← Stage 6 export (committed)
      pipeline_state.json     ← last stored/exported dates (committed)
      media/                  ← matched media files via Git LFS (committed)

    pipeline/
      pipeline.py             ← main CLI entry point (run modes + sub-commands)
      Makefile                ← shorthand targets: backfill, incremental, export, build, deploy
      config/
        pipeline_config.json  ← source_timezone, batch sizes, etc.
        emoji_categories.json ← emoji → highlight category mapping
        username_aliases.json ← manual username deduplication
        members.json          ← manually maintained: display names, colours, avatars
      stages/
        stage0_filter.py
        stage1_parse.py
        stage2_extract.py
        stage3_structure.py
        stage4_enrich.py
        stage5_store.py
        stage6_export.py
      enrichment/
        reactions.py
        media.py
      review.py               ← error review CLI (approve/reject/skip)
      tests/
        test_stage1_parse.py
        test_stage2_extract.py
        test_stage3_structure.py
        test_stage4_enrich.py
        test_stage5_store.py
        test_stage6_export.py
        test_reactions.py
        test_media.py
        fixtures/             ← sample chat snippets and expected outputs

    schema/
      schema.py               ← Pydantic models (single source of truth)
      schema.json             ← generated from schema.py
      examples.json           ← canonical example questions
      test_schema.py          ← existing schema tests

    visualizer/
      PRD.md                  ← product requirements
      package.json
      svelte.config.js
      tailwind.config.js
      vite.config.js
      config/
        app_config.json       ← all tunable UI values (attempts, thresholds, tagline, palette)
      src/
        lib/
          stores/
            QuestionStore.js  ← single data access layer (never fetch JSON directly from components)
          components/
            calendar/
            feed/
            session/
            question/
            highlights/
            shared/
        routes/
          +page.svelte                    ← Feed / landing page
          +layout.svelte                  ← shared layout (nav + calendar sidebar)
          session/[id]/+page.svelte
          question/[id]/+page.svelte
          sessions/+page.svelte
          highlights/+page.svelte
      tests/
        unit/                 ← Vitest: pure logic, no DOM
          QuestionStore.test.js
          filters.test.js
          answerMatching.test.js
          memberColor.test.js
        integration/          ← Playwright: page-level behaviour, not visual assertions
          feed.test.js
          session.test.js
          question.test.js
      static/
        data/                 ← symlink or copy of v2/data/ at build time
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
| Media Enrichment | Not started |
| 5. Store | Not started |
| 6. Export | Not started |
| 7. Deploy | Not started |
| Error review CLI | Not started |

---

## Testing Strategy

### Pipeline tests (pytest)

- One test file per stage, organised as **test classes** (e.g. `class TestStage1Parse`, `class TestStage2Extract`)
- Tests use fixture chat snippets in `tests/fixtures/` — small, self-contained message slices, not the full `_chat.txt`
- Stage 4 LLM calls are **mocked** in tests — tests validate the enrichment logic and API call structure, not the LLM output
- Run with: `python3 -m pytest v2/pipeline/tests/ -v`

### Visualizer tests (Vitest + Playwright)

- **Unit tests** (Vitest): pure logic only — `QuestionStore` filtering, answer matching (exact/fuzzy/wrong), member colour hashing, URL param serialisation. Fast, no DOM.
- **Integration tests** (Playwright): page-level behaviour — does the feed render cards, do filters update results, does Question Detail show the submission block. Test **behaviour, not appearance** — no assertions on colours, fonts, pixel positions, or specific CSS classes. Tests survive UI refactors.
- Run with: `npm run test:unit` (Vitest) and `npm run test:integration` (Playwright)

### CI / deployment gate

Tests run automatically before every deploy. Netlify build command:
```
npm run test:unit && npm run build && npm run test:integration
```
Order matters: unit tests run first (fast, no server needed), then the app is built, then Playwright integration tests run against the built output via `vite preview` (configured in `playwright.config.js` as `webServer`). If any test fails, the deploy does not proceed.

---

## Stage 0 — Date Filter

**Input:** `data/raw/_chat.txt` + `data/pipeline_state.json`

**What it does:**
- Reads `last_stored_date` from `data/pipeline_state.json`
- Backfill: collects all dates not yet in the store — determined by `SELECT DISTINCT date FROM questions` against `questions.db`. Any date present in `_chat.txt` but absent from the DB is queued for processing.
- Incremental: collects all dates after `last_stored_date`
- For each date collected, includes a **4-hour lookahead buffer** into the next day's messages

**Why the lookahead buffer (critical):**
Q&A threads frequently span midnight — a question posted at 11:45 PM may not be answered until 12:10 AM the next day. Without a lookahead, the thread is split: Stage 2 sees a question with no answer on day D, and orphaned replies on day D+1. The 4-hour buffer ensures threads started in the late evening are captured in full. Duplicate messages from the buffer (already processed on the next day's run) are deduplicated in Stage 5 via the stable question ID.

**Notes:**
- If `data/pipeline_state.json` doesn't exist → fresh backfill.
- Because the full chat is always the input, missed days are always caught on the next run.

---

## Stage 1 — Parse

**Input:** Filtered message slice (with lookahead) from Stage 0

**What it does:**
- Filters out WhatsApp system messages before any parsing ("X was added", "Messages and calls are end-to-end encrypted", "X changed the group name", etc.)
- Filters out deleted message tombstones ("This message was deleted") — these are user messages in the export, not system messages, but carry no content and should not be treated as attempts or hints
- Parses the WhatsApp message format. Handles multiple locale variants:
  - `[M/D/YY, HH:MM:SS AM/PM] Username: Message` (US locale)
  - `[DD/MM/YYYY, HH:MM:SS] Username: Message` (international locale)
- Handles multi-line messages (continuation lines have no timestamp prefix)
- Detects media placeholders (`<image omitted>`, `<video omitted>`)
- Normalises usernames: strips leading `~`, trims whitespace
- **Converts timestamps to UTC:** WhatsApp exports local time with no timezone offset. The source timezone is configured in `config/pipeline_config.json` as `"source_timezone": "America/Chicago"`. Stage 1 attaches this zone to each parsed timestamp and converts to UTC. The IANA zone handles CST/CDT transitions automatically — no special DST logic needed.

**Output:** Per-day arrays of structured message objects

```json
{
  "timestamp": "2026-03-16T07:18:47Z",
  "username": "pratik.s.chandarana",
  "text": "Q7.",
  "has_media": true
}
```

The `Z` suffix is mandatory — it marks the timestamp as UTC, not naive local time. All downstream stages and the UI depend on this to render timestamps correctly in the user's timezone.

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
- Did the quizmaster post a score update immediately after this question (within the window)? If yes, extract it as `scores_after: [{username, score}, ...]`. Null if no score announcement is present. **Attribution rule:** only capture scores that appear after this question's answer confirmation AND before the next question begins. In active sessions the next question often starts within the 40-message window — the LLM must use question boundaries, not just proximity, to attribute scores to the correct question.

**Output:** Raw candidate pairs (not yet schema-validated), with preliminary `extraction_confidence`:
- `high` — explicit confirmation message found
- `medium` — strong contextual signal ("correct", "bingo" nearby)
- `low` — no confirmation found

**Notes:**
- The window can span day boundaries thanks to the Stage 0 lookahead buffer.
- A single window may contain parts of multiple Q&A threads; the LLM should return all of them.
- `extraction_confidence: "low"` candidates are kept and stored, but hidden from the UI by default.
- **Overlapping windows produce duplicate extractions intentionally.**

### Phase 2c — Score Announcement Detection *(sessions only)*

Score announcements happen at the *end* of a session — after all questions are done — so they fall outside any individual Q&A extraction window. Score detection is a separate pass run once per detected session, over the **full session message span** (from the first session marker to ~30 messages after the last question).

The LLM is given this full session span and asked: did the quizmaster post a final score announcement? If yes, extract it as `[{username, score}, ...]`. If no score announcement is found, scores are null for that session.

Score announcements are not Q&A pairs — they are stored in the `session_scores` table (see Stage 5), not as `KVizzingQuestion` objects. When several candidates fall within 40 messages of each other, their windows overlap and each window may extract the same Q&A pair. This is fine — Stage 5's `INSERT OR REPLACE` on the timestamp-based ID means the last write wins and the result is always correct. No deduplication step is needed before storing.
- **LLM output token limits:** The 40-message window should be capped so the full prompt (system + messages + response) stays within the model's context limit. If a window exceeds this (e.g. very long messages), truncate from the outer edges, keeping the candidate message centred.

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
  - `stats.difficulty` — heuristic baseline derived from `wrong_attempts` (0→easy, 1–3→medium, 4+→hard). May be refined by LLM in Stage 4 for unanswered or low-engagement questions.
- Assigns a **stable ID**: `YYYY-MM-DD-HHMMSS` based on the question message's timestamp, not a positional index. If two questions share the same second (rare but possible in an active session), a 1-digit counter is appended: `YYYY-MM-DD-HHMMSS2`, `YYYY-MM-DD-HHMMSS3`. This ensures the same question always gets the same ID across re-runs.
- Validates against the Pydantic schema — invalid candidates are logged to `data/errors/` and skipped

**Why timestamp-based IDs (critical):**
A positional index (`YYYY-MM-DD-001`) changes if the extraction for that day produces different results on a re-run (e.g. one question is dropped). A timestamp-based ID is derived from the data itself and is stable. The `id` regex in the schema (`^\d{4}-\d{2}-\d{2}-\d+$`) accommodates both `HHMMSS` (6 digits) and collision suffixes like `HHMMSS2` (7 digits) — all still all-digit.

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
| Difficulty refinement | LLM (Claude), selective | `stats.difficulty` | Difficulty filter, stats |

**Difficulty — two-stage approach:**

Stage 3 always sets a heuristic baseline from `wrong_attempts` (0→easy, 1–3→medium, 4+→hard). Stage 4 selectively overrides this for questions where the heuristic is unreliable:

- **Unanswered questions** (`answer.text == null`): 0 wrong attempts doesn't mean easy — the group simply didn't engage. LLM assesses difficulty from the question text itself.
- **Questions with 0 attempts but low confidence**: may have been ignored, not easy. LLM reviews.
- **All other questions**: heuristic stands. No LLM call made.

This keeps Stage 4 API costs low — only a small subset of questions get the LLM difficulty pass.

**Notes:**
- Only questions not already enriched in the store are sent to the LLM — incremental runs are cheap.
- Questions are sent in **batches** (e.g. 10–20 per API call) with a structured prompt asking the LLM to return enrichment for all questions in the batch. This reduces API calls significantly for backfill runs. Batch size is tunable in `config/pipeline_config.json`.
- Topic and tag quality depends on prompt design. Both are stored as nullable fields; missing values simply mean those filters won't surface the question.
- **API failure handling:** On rate limit (HTTP 429), the pipeline retries with exponential backoff (3 attempts). On any other API error or malformed LLM response, the question is logged to `data/errors/` with the error reason, left unenriched (`topic: null`, `tags: []`), and processing continues. The pipeline never fails hard on enrichment — a question with no topic/tags is still valid and stored.

**Emoji→category config:**
The `highlights` computation (part of reactions enrichment) uses a mapping file at `v2/pipeline/config/emoji_categories.json`. Example:
```json
{ "😂": "funny", "😄": "funny", "❤️": "crowd_favourite", "✅": "confirmed_correct", "🔥": "spicy", "😮": "surprising" }
```
New categories are added here without touching the schema.

---

## Pipeline Config Reference

All tunable values live in `v2/pipeline/config/pipeline_config.json`. Nothing is hardcoded in the pipeline stages. Full schema:

```json
{
  "source_timezone": "America/Chicago",
  "chat_file": "data/raw/_chat.txt",

  "stage0": {
    "lookahead_hours": 4
  },

  "stage1": {
    "locale_formats": ["%m/%d/%y, %I:%M:%S %p", "%d/%m/%Y, %H:%M:%S"]
  },

  "stage2": {
    "extraction_window_messages": 40,
    "heuristic_reply_window_minutes": 15,
    "heuristic_min_replies": 2
  },

  "stage3": {
    "difficulty": {
      "easy_max_wrong_attempts": 0,
      "medium_max_wrong_attempts": 3
    }
  },

  "stage4": {
    "llm_model": "claude-sonnet-4-6",
    "llm_batch_size": 15,
    "llm_max_retries": 3,
    "llm_retry_base_delay_seconds": 2
  },

  "reactions_enrichment": {
    "timestamp_tolerance_seconds": 1
  },

  "media_enrichment": {
    "match_window_seconds": 30
  }
}
```

Any value here can be changed without touching pipeline code.

---

### Future: Semantic Search

Semantic search is **out of scope for v2** but the pipeline is designed so it can be added as a Stage 4 enrichment pass without changing any other stage:

1. Add an `embeddings` table to `questions.db`:
```sql
CREATE TABLE embeddings (
    question_id TEXT PRIMARY KEY,
    model       TEXT NOT NULL,   -- store model name to prevent mixing vectors
    vector      BLOB NOT NULL    -- serialised float32 array
);
```
2. In Stage 4, call an embedding model (e.g. OpenAI `text-embedding-3-small`) for each unenriched question and store the vector
3. In Stage 6, build a static HNSW index file from the stored vectors
4. In the UI, embed the user's search query in-browser via `transformers.js` and query the HNSW index

The SQLite schema for `questions` is unchanged. No other stage is affected.

---

## Reactions Enrichment *(separate, on-demand)*

Reactions are fully decoupled from the daily pipeline because the WhatsApp SQLite DB is not always available.

```bash
python3 pipeline.py enrich-reactions --db path/to/ChatStorage.sqlite
```

**What it does:**
- Reads reaction records from the SQLite DB (`ZWAMESSAGEREACTION` on iOS, `message_reactions` on Android)
- Normalises WhatsApp DB timestamps (stored as Unix epoch integers in seconds) to UTC ISO strings before matching — ensures consistent comparison with `question.timestamp` values stored in the pipeline
- Matches reactions to questions by `message_timestamp` within a **±1 second tolerance** — WhatsApp reaction records may have slight timestamp drift relative to the message timestamp stored in the pipeline
- Updates `reactions[]` and computes `highlights` using `config/emoji_categories.json`
- Upserts back into `questions.db`

Run this whenever a device backup is available. Safe to re-run — reactions are replaced, not appended.

---

## Media Enrichment *(separate, on-demand)*

Media files (images, videos, audio notes) are fully decoupled from the daily pipeline because they require a WhatsApp media backup, which is not always available. A plain `.txt` export contains no media — only the `<image omitted>` / `<video omitted>` placeholder text that Stage 1 already detects.

```bash
python3 pipeline.py enrich-media --media-dir path/to/WhatsApp/Media
```

**How timestamp matching works:**

WhatsApp media filenames encode a creation date — e.g. `IMG-20260316-WA0007.jpg`. The pipeline matches files to questions using the following priority:

1. **EXIF `DateTimeOriginal`** (most reliable — embedded in the image at capture time, unaffected by device or export)
2. **Filename date** (`YYYYMMDD` component) — narrows to the right day; the `WA` sequence number is used as a relative ordering hint within that day but is **not** treated as globally reliable (it is device-specific and resets across exports)
3. **File modification time** — last fallback; least reliable

A file is matched to a question if its resolved timestamp falls within a ±30-second window of `question.timestamp`. Within that window, the closest match wins.

**Discussion entry media:** Messages in the discussion thread also carry timestamps. The same matching logic applies — if a media file's timestamp matches a `DiscussionEntry.timestamp` more closely than any question timestamp, it is attached to that entry instead. This handles hint images and answer reveal images correctly.

**Unmatched files:** Media files that cannot be correlated to any question or discussion entry within the ±30-second window are ignored. They are not copied into `data/media/` and not recorded anywhere. A summary of unmatched files is printed at the end of the command for manual review.

Questions where `has_media: true` and `question.media == null` are the targets — `has_media: true` means the chat export recorded a media placeholder, but no file has been extracted yet.

**What it does:**
- Scans `--media-dir` for WhatsApp media files (`.jpg`, `.mp4`, `.opus`, `.pdf`, etc.)
- Matches files to questions by timestamp, populating `question.media[]`
- Also matches media to discussion entries (hints or answer reveals that included images)
- Copies matched files to `data/media/YYYY-MM-DD/` under the question date
- Updates `question.media[].url` to a relative path (e.g. `media/2026-03-16/IMG-20260316-WA0007.jpg`)
- Upserts updated questions back into `questions.db`

**Storage decision for media files:**

| Option | Pros | Cons |
|---|---|---|
| `data/media/` committed to git | Simple, self-contained, works offline | Bloats repo; impractical at scale |
| **`data/media/` via Git LFS** | Repo stays lean, same clone UX | Requires LFS on the remote; bandwidth costs at scale |
| External CDN (e.g. Cloudflare R2, GitHub Releases) | Scales to any size, no git overhead | More ops complexity, requires upload step |

**v2 default:** `data/media/` stored in Git LFS. The `url` field in `MediaAttachment` stores a relative path by default; if files are later migrated to a CDN, `url` is updated to the full CDN URL — the schema handles both.

Run this whenever a WhatsApp media backup is available. Safe to re-run — existing media entries are replaced, not appended. Questions with no matching media file remain unchanged (`question.media == null`, `has_media` stays `true`).

---

## Stage 5 — Store

**Input:** Enriched `KVizzingQuestion` objects from Stage 4

**SQLite schema:**

The full question JSON is stored as a blob for simplicity, alongside indexed scalar columns for fast filtering, and an FTS5 virtual table for full-text search. This avoids a complex normalised schema while keeping common queries and keyword search efficient.

```sql
CREATE TABLE questions (
    id                    TEXT PRIMARY KEY,
    date                  TEXT NOT NULL,        -- YYYY-MM-DD, indexed
    asker                 TEXT NOT NULL,        -- indexed
    solver                TEXT,                 -- indexed, null for collaborative/unanswered
    session_id            TEXT,                 -- indexed, null for ad-hoc
    topic                 TEXT,                 -- indexed
    difficulty            TEXT,                 -- indexed
    extraction_confidence TEXT NOT NULL,        -- indexed
    has_media             INTEGER DEFAULT 0,    -- indexed; 1 if question.has_media is true
    has_reactions         INTEGER DEFAULT 0,
    payload               TEXT NOT NULL         -- full KVizzingQuestion JSON
);

CREATE INDEX idx_questions_date       ON questions(date);
CREATE INDEX idx_questions_asker      ON questions(asker);
CREATE INDEX idx_questions_solver     ON questions(solver);
CREATE INDEX idx_questions_session    ON questions(session_id);
CREATE INDEX idx_questions_topic      ON questions(topic);
CREATE INDEX idx_questions_difficulty ON questions(difficulty);
CREATE INDEX idx_questions_has_media  ON questions(has_media);

-- FTS5 virtual table for pipeline-internal full-text queries (used by Stage 6 upgrade path)
CREATE VIRTUAL TABLE questions_fts USING fts5(
    id UNINDEXED,
    question_text,
    answer_text,
    tags,
    content='questions',
    content_rowid='rowid'
);

-- Triggers to keep FTS5 in sync with the questions table.
-- SQLite content tables do NOT auto-sync on INSERT OR REPLACE — explicit triggers are required.
CREATE TRIGGER questions_ai AFTER INSERT ON questions BEGIN
    INSERT INTO questions_fts(rowid, id, question_text, answer_text, tags)
    VALUES (new.rowid, new.id, json_extract(new.payload, '$.question.text'),
            json_extract(new.payload, '$.answer.text'), new.payload);
END;
CREATE TRIGGER questions_ad AFTER DELETE ON questions BEGIN
    INSERT INTO questions_fts(questions_fts, rowid, id, question_text, answer_text, tags)
    VALUES ('delete', old.rowid, old.id, json_extract(old.payload, '$.question.text'),
            json_extract(old.payload, '$.answer.text'), old.payload);
END;
CREATE TRIGGER questions_au AFTER UPDATE ON questions BEGIN
    INSERT INTO questions_fts(questions_fts, rowid, id, question_text, answer_text, tags)
    VALUES ('delete', old.rowid, old.id, json_extract(old.payload, '$.question.text'),
            json_extract(old.payload, '$.answer.text'), old.payload);
    INSERT INTO questions_fts(rowid, id, question_text, answer_text, tags)
    VALUES (new.rowid, new.id, json_extract(new.payload, '$.question.text'),
            json_extract(new.payload, '$.answer.text'), new.payload);
END;
```

FTS5 is SQLite's built-in full-text search — no extensions, no extra dependencies. The three triggers above are mandatory: SQLite content tables do not auto-sync on `INSERT OR REPLACE` without them, which would silently return stale search results.

**Important SQLite behaviour:** `INSERT OR REPLACE` fires as DELETE + INSERT internally, not as UPDATE. This means `questions_au` (the update trigger) is **never invoked** by `INSERT OR REPLACE` — but that is fine, because `questions_ad` and `questions_ai` handle it correctly. `questions_au` only fires for explicit `UPDATE ... SET ...` statements used during enrichment passes (topic, tags, reactions). All three triggers are needed.

```sql
-- Scores extracted from score announcements in the chat.
-- Covers both per-question snapshots and final session scores.
-- after_question_id = null means final/overall session score.
CREATE TABLE session_scores (
    session_id        TEXT NOT NULL,
    after_question_id TEXT,     -- null = final session score; question ID otherwise
    username          TEXT NOT NULL,
    score             INTEGER NOT NULL
);
CREATE UNIQUE INDEX uq_session_scores
    ON session_scores(session_id, COALESCE(after_question_id, ''), username);
```

Per-question scores (announced after each Q&A) are also stored in `question.scores_after[]` in the question payload — so they travel with the question in `questions.json` and are immediately available to the UI without a separate lookup. The `session_scores` table is the authoritative store; `scores_after` in the payload is derived from it at Stage 6 export time.

Final session scores (from Phase 2c) are session-level only — stored in `session_scores` with `after_question_id = null` and exported to `sessions.json`.

The `embeddings` table is intentionally absent from v2 — see "Future: Semantic Search" in Stage 4 for the extension path.

**What it does:**
- Wraps each day's batch in a **single SQLite transaction** — either all questions for the day are stored or none are (no partial state)
- `INSERT OR REPLACE` on `id` ensures re-runs are always safe
- Updates `data/pipeline_state.json` → sets `last_stored_date` (not `last_exported_date`)

**Output:** `data/questions.db`

---

## Stage 6 — Export

**Input:** `data/questions.db`

**What it does:**
- Queries all questions and exports to `data/questions.json` (sorted by `question.timestamp`)
- Generates `data/questions_by_date/YYYY-MM-DD.json` — per-day slices for calendar queries
- Generates `data/sessions.json` — index of all sessions with metadata (loaded first by calendar sidebar). Each entry contains: `id`, `quizmaster`, `theme`, `date`, `question_count`, `avg_time_to_answer_seconds`, `avg_wrong_attempts`, `participant_count`, and `scores` (final session scores — array of `{username, score}` pairs if a final score announcement was found, otherwise null)
- Populates `scores_after` on each session question in `questions.json` from the `session_scores` table (per-question score snapshots, null if none found)
- Generates `data/stats.json` — pre-aggregated group stats: member participation counts, topic mix, difficulty distribution, session activity over time
- Generates `data/tags.json` — tag → [question_id, ...] index for instant tag filtering
- Generates `data/members.json` — merges `config/members.json` (display names, colours, avatars) with computed per-member stats (questions asked, solved, attempts, sessions hosted, avg solve time). Members present in the data but absent from the config get the raw username as display name; colour is derived client-side via hash fallback.
- *(No search index generated — keyword search is handled client-side by Fuse.js against `questions.json`)*
- *(No per-date or per-month split files generated in v2 — `questions.json` is the single source. If the file grows large enough to warrant splitting, add a `questions_by_month/YYYY-MM.json` generation step here. The UI's `QuestionStore` abstraction isolates components from this change — only the store's fetch logic needs updating.)*
- Updates `data/pipeline_state.json` → sets `last_exported_date`

**Why pre-aggregate:**
The UI is a static site with no backend. Computing group stats or tag indices client-side over thousands of questions on every load is wasteful. Everything is computed once at export time.

**Search capabilities:**

| Search type | How | Asset |
|---|---|---|
| Keyword / full-text | **Fuse.js** in-browser fuzzy search against `questions.json` | `questions.json` (already loaded) |
| Filter by asker | Client-side filter | `questions.json` |
| Filter by tag | Tag → ID lookup | `data/tags.json` |
| Filter by topic / difficulty / type | Client-side filter | `questions.json` |
| Semantic search | **Future** — HNSW index from embeddings | See Stage 4 future section |

**Why Fuse.js, not a pipeline-built search index:** The full archive at scale is a few thousand short-text questions — small enough that Fuse.js builds an in-memory index client-side in under 50ms. Fuzzy matching is a bonus (handles informal spelling). Since `questions.json` is already in the browser for filter operations, there is nothing extra to generate or serve. `search_index.json` is therefore not produced by Stage 6.

**Upgrade path (if Fuse.js is insufficient):**

The SQLite FTS5 table is already populated at Stage 5 — the pipeline is search-ready today. Upgrading search requires only a Stage 6 addition and a UI swap; no other stage changes:

| Step | Current (Fuse.js) | Upgrade option 1 — FTS5 export | Upgrade option 2 — Semantic |
|---|---|---|---|
| Stage 5 | FTS5 table populated (already done) | ← same | ← same + embeddings table |
| Stage 6 | No search export | Add: query FTS5 → emit `search_index.json` (inverted index) | Add: build HNSW index from embeddings |
| UI | Fuse.js against `questions.json` | Client reads `search_index.json` | Client queries HNSW via `transformers.js` |

The search bar component in the UI should treat the search engine as an injected dependency — the input/output contract (query string in, ranked question IDs out) stays identical regardless of which engine is active.

**Output:**
```
data/
  questions.json              ← full archive for the UI (committed to git)
  questions_by_date/
    2025-09-23.json
    2026-03-16.json
    ...
  sessions.json               ← calendar sidebar loads this first
  stats.json                  ← pre-computed group stats + charts
  tags.json                   ← tag → [question_id, ...] index
  members.json                ← member display names, colours, avatars + stats
  questions.db                ← pipeline internal store (gitignored)
  pipeline_state.json         ← tracks last stored + exported dates
```

---

## Stage 7 — Deploy

**Input:** `data/` files + visualizer source (`v2/visualizer/`)

**Stack: SvelteKit + Tailwind CSS**

SvelteKit is chosen over Next.js for this project because:
- Lighter JS bundle → faster on mobile (the primary device)
- Built-in transitions and animations — ideal for the discussion thread replay
- Static adapter is first-class; Next.js static export is an afterthought
- Less boilerplate for a purely read-only, data-driven UI

UI quality is driven by the design system, not the framework. Stack:
- **SvelteKit** (static adapter) — routing, pages, components
- **Tailwind CSS** — utility-first styling, consistent design tokens
- **shadcn-svelte** — accessible, unstyled component primitives (dialogs, popovers, dropdowns)
- **FullCalendar** (Svelte adapter) — the calendar sidebar
- **LayerChart** — lightweight Svelte-native charts for the stats page
- **Custom CSS animations** — discussion thread message reveal, card transitions

**What it does:**
- Copies `data/` into `static/` so JSON files are served as static assets alongside the app
- Runs the SvelteKit build with the static adapter → `dist/`
- Deploys to Netlify (preferred over GitHub Pages: instant cache invalidation, branch previews, better custom domain support)

**Trigger:**

```bash
# Full backfill + deploy (first time)
make backfill && make export && make build && make deploy

# Daily incremental run
make incremental && make export && make build && make deploy

# Reactions enrichment (run when device backup is available)
make enrich-reactions DB=path/to/ChatStorage.sqlite && make export && make build && make deploy

# Media enrichment (run when WhatsApp media backup is available)
make enrich-media MEDIA_DIR=path/to/WhatsApp/Media && make export && make build && make deploy
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

Raw media files from the WhatsApp backup are **never copied into the repo**. The `enrich-media` command reads them from the external `--media-dir` path and copies only matched files into `data/media/YYYY-MM-DD/`. Those matched files are tracked via **Git LFS** (not regular git), so they don't bloat the repo history. Add the LFS tracking rule once:
```bash
git lfs track "data/media/**"
```

The following **should be committed** so the visualizer works immediately on clone:

```
data/questions.json              # the UI's primary data source
data/questions_by_date/          # calendar queries
data/sessions.json
data/stats.json
data/tags.json
data/members.json
data/pipeline_state.json
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
  pipeline_config.json          ← source_timezone and other pipeline settings
  emoji_categories.json         ← emoji → highlight category mapping
  username_aliases.json         ← manual username deduplication (optional)
  members.json                  ← manually maintained: display names, colours, avatar URLs

data/pipeline_state.json             ← last_stored_date + last_exported_date

data/questions.db               ← SQLite: questions + FTS5 index (gitignored)
data/errors/                    ← failed validations for manual review (gitignored)

data/questions.json             ← Stage 6 export (committed to git)
data/questions_by_date/         ← Stage 6 export (committed to git)
data/sessions.json              ← Stage 6 export (committed to git)
data/stats.json                 ← Stage 6 export (committed to git)
data/tags.json                  ← Stage 6 export (committed to git)
data/members.json               ← Stage 6 export (committed to git)

data/media/                     ← matched media files, tracked via Git LFS
  2025-09-23/
    IMG-20250923-WA0003.jpg
  2026-03-16/
    IMG-20260316-WA0007.jpg
    VID-20260316-WA0002.mp4

dist/                           ← Stage 7 output (deployable static site)
```

---

## Resolved Design Decisions

| # | Question | Decision |
|---|---|---|
| 1 | LLM for extraction | **Claude API** — better handling of informal Indian English, emojis, non-obvious confirmations |
| 2 | Full-text search | **SQLite FTS5** — built-in, zero dependencies. Used internally by the pipeline. UI search handled by Fuse.js client-side — no export file needed. |
| 3 | Semantic search | **Out of scope for v2.** Extension path documented in Stage 4. No other stages change when added later. |
| 4 | Reactions enrichment | **v2, optional** — separate `enrich-reactions` command. UI shows empty state gracefully without it. Enables the Highlights page when run. |
| 5 | Frontend framework | **SvelteKit + Tailwind CSS + shadcn-svelte** — lightest bundle, best static adapter, built-in transitions for thread replay |
| 6 | Hosting | **Netlify** — instant cache invalidation, branch previews, better than GitHub Pages for a polished UX |
| 7 | Error review | **Simple CLI** (`pipeline.py review`) — approve/reject/skip per candidate |
| 8 | questions.db in git | **Not committed** — binary diffs bloat repo history. `questions.json` (the export) is committed instead and is sufficient to run the UI |
| 9 | Media storage | **Git LFS** for `data/media/` — keeps the repo lean while preserving the same clone UX. `url` field in `MediaAttachment` stores a relative path; can be updated to a CDN URL later without schema changes. |
| 10 | Media ↔ question matching | **Filename timestamp + EXIF fallback** — `IMG-YYYYMMDD-WAxxxx.jpg` encodes the date; sequence number disambiguates within a day. EXIF `DateTimeOriginal` and file mtime used when filename is ambiguous. |
| 11 | Difficulty assignment | **Heuristic baseline + selective LLM override** — Stage 3 always sets difficulty from `wrong_attempts`. Stage 4 overrides only for unanswered or zero-attempt questions where the heuristic is misleading. |
| 12 | Keyword search | **Fuse.js** client-side — dataset is small enough that in-browser fuzzy search against `questions.json` is fast and sufficient. FTS5 stays in SQLite for pipeline queries. Upgrade path to FTS5 export or semantic search documented in Stage 6. |
