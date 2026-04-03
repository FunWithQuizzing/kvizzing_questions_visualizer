# KVizzing Pipeline — Running Guide

## Subcommands

| Command | What it does |
|---|---|
| `backfill` | Process all dates not yet in the DB. Full pipeline: extract → structure → enrich → store → export → media → R2 upload → session images |
| `incremental` | Process only dates after the last stored date (same stages as backfill) |
| `export` | Re-generate JSON files from the DB (no LLM, no DB writes) |
| `reimport [DATES...]` | Re-import extraction_output files into DB (auto-fixes + stages 3-6, no LLM extraction). If no dates given, reimports all |
| `reenrich [--dry-run] [--all]` | Re-run LLM topic enrichment. Default: questions with < 3 topics. `--all`: recategorize everything |
| `detect-sessions [--dry-run]` | Detect informal quiz sessions in extraction files |
| `normalize-tags [--dry-run]` | Strip format tags, fix near-duplicate tag names in the DB |
| `assign-topics [--dry-run]` | Assign primary + secondary topics via rules (no LLM) |
| `enrich-media --media-dir PATH [--dry-run]` | Match exported media files to questions by timestamp |
| `upload-media --media-dir PATH [--dry-run]` | Upload matched media files to Cloudflare R2 |
| `cleanup-r2 [--dry-run]` | Delete R2 objects not referenced by any question in the DB |
| `check-r2` | Check R2 free-tier usage; warns at 80% of each limit |
| `export-rejected` | Export rejected candidates from .txt files to JSON |
| `check-coverage` | Check for missed dates or suspiciously low extraction counts |
| `generate-images` | Generate background images for new sessions |

All commands are run from `v2/pipeline/`:
```bash
python3 pipeline.py <command> [flags]
```

---

## backfill vs incremental

Both skip dates already in the DB. The difference is how they find new dates:

- **`backfill`** — scans the entire chat file, collects every date present, subtracts what's already stored. Catches gaps anywhere in history.
- **`incremental`** — only looks at dates strictly after `MAX(date)` in the DB. Faster, but won't catch gaps in the middle of history.

**When to use which:**
- Day-to-day use → `incremental`
- After manually deleting rows to re-process a specific old date → `backfill`
- First run on a fresh DB → `backfill`

---

## What is NOT overwritten by normal runs

| Artifact | `backfill` | `incremental` | `export` |
|---|---|---|---|
| Questions already in DB | Skipped | Skipped | Untouched |
| `extraction_output/` files | Respected (LLM skipped) | Respected | Ignored |
| Manual topic edits in DB | Preserved | Preserved | Preserved |
| `questions.json` / other JSON | Regenerated | Regenerated | Regenerated |

---

## extraction_output/ files

`data/extraction_output/YYYY-MM-DD.json` is the LLM cache for each date.

- If the file exists for a date, **the LLM call is skipped** and the cached extraction is used instead.
- After stage 4 enrichment, topics/tags are **written back** into the file so they survive future DB rebuilds.
- To force re-extraction for a date, delete its file and remove the date from the DB (see below).

These files are your safety net — manually correct one and it will always win over the LLM.

---

## Common workflows

### First-time setup
```bash
python3 pipeline.py backfill
```

### Routine update (new chat messages added)
```bash
python3 pipeline.py incremental
```

### Re-export UI data without touching the DB
```bash
python3 pipeline.py export
```
Use this after manually editing `extraction_output/` files or making direct DB edits.

### Fix topics on questions that have 0 or 1 (rule-based, no LLM)
```bash
python3 pipeline.py assign-topics --dry-run   # preview first
python3 pipeline.py assign-topics
```

### Fix topics via LLM
```bash
python3 pipeline.py reenrich --dry-run   # shows how many qualify
python3 pipeline.py reenrich
```
Requires `GEMINI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, or `USE_OLLAMA=1`.

### Strip format tags / rename near-duplicate tags
```bash
python3 pipeline.py normalize-tags --dry-run
python3 pipeline.py normalize-tags
```

### Match media files to questions
```bash
python3 pipeline.py enrich-media --media-dir ../data/raw/ --dry-run   # preview matches
python3 pipeline.py enrich-media --media-dir ../data/raw/
```

Scans the export directory for `NNNNNN-PHOTO/VIDEO/GIF-YYYY-MM-DD-HH-MM-SS.ext` files and
matches them to questions with `has_media=True` by timestamp proximity (default ±90 s window).
Populates `question.media[].filename` in the DB; `url` stays `null` until files are uploaded to a CDN.

Near-duplicate burst shots (perceptual hash distance ≤ 8) are automatically dropped so only
visually distinct images are stored. Requires `imagehash` + `Pillow` (`pip3 install imagehash`);
dedup is skipped silently if the packages are absent.

Tune the match window in `config/pipeline_config.json` → `media_enrichment.match_window_seconds`
if you see unmatched questions (the WhatsApp filename timestamp runs ~39 s before the chat timestamp).

### Upload matched media to Cloudflare R2
Credentials are loaded automatically from `v2/pipeline/.env` (gitignored).
Fill in `R2_PUBLIC_URL` once you enable public access on the bucket, then:

```bash
python3 pipeline.py upload-media --media-dir ../data/raw/ --dry-run   # preview first
python3 pipeline.py upload-media --media-dir ../data/raw/             # upload
```

Env vars in `.env` are never overridden by the file if already set in the shell,
so you can still pass one-off overrides on the command line.

After uploading, `question.media[].url` is populated in the DB and re-exported to JSON.
The usage check runs automatically after each upload. You can also run it standalone:

### Re-run deduplication on already-matched questions

If you've already run `enrich-media` and `upload-media` but want to apply perceptual dedup
to questions already in the DB, run this sequence from `v2/pipeline/`:

```bash
# 1. Clear matched media from the DB (doesn't touch R2)
sqlite3 ../data/questions.db "UPDATE questions SET payload = json_set(payload, '$.question.media', json('null')) WHERE has_media = 1;"

# 2. Re-match with dedup applied
python3 pipeline.py enrich-media --media-dir ../data/raw/

# 3. Upload any newly-referenced files (already-uploaded files are skipped)
python3 pipeline.py upload-media --media-dir ../data/raw/

# 4. Delete orphaned objects from R2 (files no longer referenced after dedup)
python3 pipeline.py cleanup-r2 --dry-run   # preview first
python3 pipeline.py cleanup-r2             # delete
```

```bash
# Storage check (no extra token needed):
R2_ACCOUNT_ID=xxx R2_ACCESS_KEY_ID=xxx R2_SECRET_ACCESS_KEY=xxx R2_BUCKET=kvizzing-media \
python3 pipeline.py check-r2

# Full check including Class A/B operation counts (requires Cloudflare API token
# with "Account Analytics:Read" permission — create at dash.cloudflare.com → My Profile → API Tokens):
CLOUDFLARE_API_TOKEN=xxx ... python3 pipeline.py check-r2
```

Free-tier limits (warnings fire at 80%):
- Storage: 10 GB/month
- Class A ops (writes/lists): 1 million/month
- Class B ops (reads): 10 million/month

---

## Overriding existing data

### Nuke everything and start fresh
```bash
rm ../data/questions.db
rm ../data/pipeline_state.json
python3 pipeline.py backfill
```
Reprocesses every date. Cached `extraction_output/` files are reused; everything else is re-run.

### Reprocess specific dates (keep extraction cache)
```bash
sqlite3 ../data/questions.db "DELETE FROM questions WHERE date IN ('2024-11-15', '2024-11-16');"
sqlite3 ../data/questions.db "DELETE FROM questions_fts WHERE id NOT IN (SELECT id FROM questions);"
python3 pipeline.py backfill
```

### Reprocess a date AND re-run LLM extraction
```bash
rm ../data/extraction_output/2024-11-15.json
sqlite3 ../data/questions.db "DELETE FROM questions WHERE date = '2024-11-15';"
sqlite3 ../data/questions.db "DELETE FROM questions_fts WHERE id NOT IN (SELECT id FROM questions);"
python3 pipeline.py backfill
```

### Re-import extraction files after manual edits
```bash
python3 pipeline.py reimport 2025-10-05 2025-09-26   # specific dates
python3 pipeline.py reimport                           # all extraction files
```
Runs auto-fixes (topics, solver, confirmations, etc.) + stages 3-6. No LLM extraction needed.

### Recategorize all questions (after adding new topic categories)
1. Edit `config/topics.json` to add the new category
2. Edit `utils/config.py → load_topic_aliases()` to update alias mappings
3. Re-run LLM enrichment on all questions:
```bash
GEMINI_API_KEY=xxx python3 pipeline.py reenrich --all
```

### Re-run enrichment on questions with few topics
```bash
python3 pipeline.py reenrich --dry-run   # preview
python3 pipeline.py reenrich             # default: questions with < 3 topics
python3 pipeline.py reenrich --all       # ALL questions (for recategorization)
```
Requires `GEMINI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, or `USE_OLLAMA=1`.

### Rule-based topic assignment (no LLM)
```bash
python3 pipeline.py assign-topics --dry-run
python3 pipeline.py assign-topics
```

### Bulk extraction of historical compact files
If you have many `data/extraction_compact/YYYY-MM-DD.txt` files without corresponding
`extraction_output/` files, `backfill` handles them all:
```bash
GEMINI_API_KEY=your_key python3 pipeline.py backfill
```
The pipeline checks for an existing `extraction_output/YYYY-MM-DD.json` before calling
the LLM — so already-extracted dates are skipped automatically. Gemini's 1M token context
handles the largest days without chunking and is free.

To re-extract a specific date from scratch:
```bash
rm ../data/extraction_output/2024-11-15.json
sqlite3 ../data/questions.db "DELETE FROM questions WHERE date = '2024-11-15';"
sqlite3 ../data/questions.db "DELETE FROM questions_fts WHERE id NOT IN (SELECT id FROM questions);"
python3 pipeline.py backfill
```

---

## LLM provider selection

The pipeline auto-selects a provider based on available credentials:

| Priority | Provider | How to enable | Best for |
|---|---|---|---|
| 1 | Ollama (local) | `USE_OLLAMA=1` | Day-to-day incremental (small context, free, private) |
| 2 | Gemini | `GEMINI_API_KEY` | Backfill (free tier, 1M token context, 15 RPM) |
| 3 | Groq | `GROQ_API_KEY` | Backfill (free tier, fast, lower token limits) |
| 4 | Anthropic | `ANTHROPIC_API_KEY` | Any (paid, reliable) |

### Backfill (recommended: Gemini)

Gemini's free tier has a 1M token context window — handles the largest quiz days without chunking. Get a key at [aistudio.google.com](https://aistudio.google.com).

```bash
GEMINI_API_KEY=your_key python3 pipeline.py backfill
```

### Backfill (alternative: Groq)

```bash
GROQ_API_KEY=your_key python3 pipeline.py backfill
```

### Day-to-day incremental (Ollama, local)

```bash
USE_OLLAMA=1 python3 pipeline.py incremental
```

Override Ollama model or context window:
```bash
USE_OLLAMA=1 OLLAMA_MODEL=qwen3.5:latest OLLAMA_NUM_CTX=32768 python3 pipeline.py incremental
```

---

## Full pipeline flow (backfill/incremental)

When you run `backfill` or `incremental`, the pipeline executes these stages in order:

1. **Stage 0 — Filter**: Read chat file, determine which dates need processing
2. **Stage 1 — Parse**: Parse raw WhatsApp lines into structured messages
3. **Stage 2 — Extract**: LLM extraction of Q&A pairs (with auto-fixes, self-healing, chunked fallback)
4. **Stage 3 — Structure**: Validate extraction into Pydantic models
5. **Stage 4 — Enrich**: LLM topic/tag enrichment
6. **Stage 5 — Store**: Upsert to SQLite DB
7. **Reclassify elaboration**: Detect post-answer context entries in discussions
8. **Stage 6 — Export**: Generate questions.json, sessions.json, stats.json, etc.
9. **Rejected candidates**: Write + export rejected candidate threads
10. **Media enrichment**: Match local media files to questions (if `data/raw/` exists)
11. **R2 upload**: Upload new media to Cloudflare R2 (if R2 env vars are set)
12. **Session images**: Generate background images for new sessions (via Stable Horde)

Steps 7-12 are non-fatal — if any fails, the pipeline continues.

---

## Configuration files

| File | Purpose |
|---|---|
| `config/pipeline_config.json` | Core pipeline settings (chat file path, heuristic thresholds, LLM model, etc.) |
| `config/topics.json` | Topic categories (id, label, color). Single source of truth — used by schema, prompt, audit, and frontend |
| `config/members.json` | Member display names and avatars |
| `config/session_overrides.json` | Manual corrections for session themes, quizmasters |
| `config/username_aliases.json` | Map alternative usernames to canonical names |
| `utils/config.py → load_topic_aliases()` | Topic alias map (LLM typo corrections like "film" → "cinema") |
| `.env` | R2 credentials (gitignored) |

### Adding a new topic category

1. Add entry to `config/topics.json`:
   ```json
   { "id": "new_topic", "label": "New Topic", "color": "emerald" }
   ```
2. Update aliases in `utils/config.py → load_topic_aliases()` if the LLM might use synonyms
3. Recategorize existing questions:
   ```bash
   GEMINI_API_KEY=xxx python3 pipeline.py reenrich --all
   ```
