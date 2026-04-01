# KVizzing Pipeline — Running Guide

## Subcommands

| Command | What it does |
|---|---|
| `backfill` | Process all dates in the chat file not yet in the DB |
| `incremental` | Process only dates after the last stored date |
| `export` | Re-generate JSON files from the DB (no LLM, no DB writes) |
| `reenrich [--dry-run]` | Re-run LLM enrichment on questions with fewer than 2 topics |
| `normalize-tags [--dry-run]` | Strip format tags, fix near-duplicate tag names in the DB |
| `assign-topics [--dry-run]` | Assign primary + secondary topics via rules (no LLM) |
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

### Fix topics on questions that only have 1 (rule-based, no LLM)
```bash
python3 pipeline.py assign-topics --dry-run   # preview first
python3 pipeline.py assign-topics
```

### Fix topics via LLM
```bash
python3 pipeline.py reenrich --dry-run   # shows how many qualify
python3 pipeline.py reenrich
```
Requires `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, or `USE_OLLAMA=1`.

### Strip format tags / rename near-duplicate tags
```bash
python3 pipeline.py normalize-tags --dry-run
python3 pipeline.py normalize-tags
```

---

## Overriding existing data

### Nuke everything and start fresh
```bash
rm v2/data/questions.db
rm v2/data/pipeline_state.json
python3 pipeline.py backfill
```
Reprocesses every date. Cached `extraction_output/` files are reused; everything else is re-run.

### Reprocess specific dates (keep extraction cache)
```bash
sqlite3 v2/data/questions.db "DELETE FROM questions WHERE date IN ('2024-11-15', '2024-11-16');"
sqlite3 v2/data/questions.db "DELETE FROM questions_fts WHERE id NOT IN (SELECT id FROM questions);"
python3 pipeline.py backfill
```

### Reprocess a date AND re-run LLM extraction
```bash
rm v2/data/extraction_output/2024-11-15.json
sqlite3 v2/data/questions.db "DELETE FROM questions WHERE date = '2024-11-15';"
sqlite3 v2/data/questions.db "DELETE FROM questions_fts WHERE id NOT IN (SELECT id FROM questions);"
python3 pipeline.py backfill
```

### Re-run enrichment on all questions (without touching extraction)
```bash
python3 pipeline.py reenrich        # LLM-based
python3 pipeline.py assign-topics   # rule-based, no LLM needed
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
