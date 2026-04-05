# KVizzing

A full-stack platform for extracting, enriching, and visualising trivia questions from the KVizzing WhatsApp group.

---

## What is KVizzing?

KVizzing is a WhatsApp group where members regularly post trivia questions across topics like history, science, literature, technology, sports, cinema, and entertainment. Questions range from quick factual recalls to multi-part identify questions and connect-the-dots puzzles. Members also host curated quiz sessions with themes, scores, and leaderboards.

This project extracts those Q&A threads from raw chat exports and turns them into a structured, searchable archive with a polished web visualizer.

---

## Repository Structure

```
v1/                              # Legacy extraction pipeline (regex + Llama)

v2/
  schema/                        # Pydantic data model (single source of truth)
    schema.py                    # KVizzingQuestion model + all enums
    schema.json                  # Auto-generated JSON Schema
    test_schema.py               # Schema validation tests

  pipeline/                      # Python extraction & enrichment pipeline
    pipeline.py                  # Main orchestrator (backfill, reimport, export, etc.)
    stages/
      stage0_filter.py           # Date filtering & backfill detection
      stage1_parse.py            # WhatsApp chat parsing
      stage2_extract.py          # LLM-based Q&A extraction (Gemini)
      stage3_structure.py        # Raw → Pydantic mapping, ID generation, stats
      stage4_enrich.py           # Topic categorisation via LLM
      stage5_store.py            # SQLite upsert with enrichment preservation
      stage6_export.py           # JSON export for visualizer
    utils/
      audit_extraction.py        # 14-type auto-fix + self-healing LLM micro-calls
      audit_quality.py           # Post-export quality audit
      media_match.py             # WhatsApp media → question timestamp matching
      r2_upload.py               # Cloudflare R2 media upload
      generate_session_images.py # AI session background images (Stable Horde)
      detect_sessions.py         # Post-hoc session detection
      detect_connect_quizzes.py  # LLM-based connect quiz classification
      export_rejected.py         # Rejected candidate export for review
    config/
      pipeline_config.json       # Pipeline parameters
      topics.json                # 23 topic categories
      members.json               # Member display names & colors

  visualizer/                    # SvelteKit web app
    src/
      routes/
        +page.svelte             # Question feed with filters, search, timeline
        sessions/+page.svelte    # Quiz sessions gallery with cards
        session/[id]/+page.svelte # Session detail with answer submission
        question/[id]/+page.svelte # Individual question detail
        highlights/+page.svelte  # Stats, leaderboards, topic distribution
        review/+page.svelte      # Community review of rejected candidates
      lib/
        components/              # Reusable Svelte 5 components
        stores/                  # QuestionStore with filtering & search
        config/ui.ts             # Session image opacity, background URLs
    static/
      data/                      # Exported JSON (questions, sessions, stats, tags, members)
      images/sessions/           # AI-generated session background images
```

---

## Data Model

Each extracted Q&A pair is a `KVizzingQuestion` object:

| Field | Description |
|---|---|
| `id` | Stable timestamp-based ID (`YYYY-MM-DD-HHMMSS`) |
| `question` | Text, asker, type, topics, tags, media attachments |
| `answer` | Text, solver, confirmation, collaborative flag, multi-part breakdown |
| `discussion` | Full ordered message thread (attempts, hints, reveals, elaborations) |
| `stats` | Wrong attempts, hints, time to answer, difficulty |
| `session` | Quizmaster, theme, quiz type, connect answer (null for ad-hoc) |
| `scores_after` | Running scores after each session question |
| `extraction_confidence` | `high` / `medium` / `low` |

See [`v2/schema/schema.py`](v2/schema/schema.py) for the full model.

---

## Pipeline

The pipeline processes WhatsApp chat exports through 7 stages:

1. **Filter** — Select dates to process, detect backfill gaps
2. **Parse** — Extract structured messages from raw chat text
3. **Extract** — LLM-based Q&A pair extraction with smart chunking and self-healing audit
4. **Structure** — Map to Pydantic models, generate IDs, compute stats
5. **Enrich** — LLM topic categorisation (23 topics)
6. **Store** — SQLite upsert with enrichment preservation
7. **Export** — JSON files for the visualizer

Additional pipeline capabilities:
- **Media matching** — Timestamp-based WhatsApp media → question matching
- **R2 upload** — Cloudflare R2 CDN for media files
- **Session images** — AI-generated backgrounds via Stable Horde
- **Quality audit** — Detects non-questions, low quality, and rejected/extracted overlaps
- **Connect quiz detection** — LLM classifier for themed connect sessions

```bash
cd v2/pipeline

# Full backfill (extract → store → media → export per date)
GEMINI_API_KEY=xxx python3 pipeline.py backfill

# Re-export from DB
python3 pipeline.py export

# Topic re-enrichment
GEMINI_API_KEY=xxx python3 pipeline.py reenrich --all

# Quality audit
python3 pipeline.py audit-quality
```

---

## Visualizer

A SvelteKit static site with:

- **Question feed** — Date-grouped timeline, full-text search, topic/tag/media filters
- **Quiz sessions** — Card gallery with AI backgrounds, question count filters
- **Session detail** — Interactive answer submission (multi-part, connect guess)
- **Question detail** — Full discussion thread, media gallery, like/save/flag
- **Highlights** — Topic distribution, member leaderboards, activity stats
- **Review** — Community voting on rejected extraction candidates
- **Marauder's Map auth** — Themed password gate

```bash
cd v2/visualizer
npm install
npm run dev        # http://localhost:5173
npm run build      # Static build for Netlify
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- An LLM API key (Gemini recommended — free tier with 1M token context)

### 1. Clone the repo

```bash
git clone https://github.com/Saumay/kvizzing_questions_visualizer.git
cd kvizzing_questions_visualizer
```

### 2. Set up the pipeline

```bash
cd v2/pipeline
pip install pydantic google-genai boto3 requests imagehash Pillow
```

Place your WhatsApp chat export at the path specified in `config/pipeline_config.json` (default: `data/raw/_chat.txt`). Media files from the export go in the same `data/raw/` directory.

### 3. Run extraction

```bash
# Extract all Q&A pairs from the chat export
GEMINI_API_KEY=your_key python3 pipeline.py backfill
```

This processes each date through all 7 stages and outputs JSON files to `../visualizer/static/data/`. See [`v2/pipeline/RUNNING_GUIDE.md`](v2/pipeline/RUNNING_GUIDE.md) for all commands and workflows.

### 4. Set up the visualizer

```bash
cd ../visualizer
npm install
npm run dev    # http://localhost:5173
```

### 5. Optional: Media & images

```bash
cd ../pipeline

# Match WhatsApp media files to questions
python3 pipeline.py enrich-media --media-dir ../data/raw/

# Upload to Cloudflare R2 (set credentials in .env first)
python3 pipeline.py upload-media --media-dir ../data/raw/

# Generate AI session background images (free, no API key needed)
python3 pipeline.py generate-images

# Re-export after media enrichment
python3 pipeline.py export
```

### 6. Optional: Deploy

The visualizer builds as a static site. Deploy to Netlify:

```bash
cd v2/visualizer
npm run build    # Output in build/
```

The repo includes a `netlify.toml` at the root for automatic Netlify deploys on push.

---

## Tech Stack

| Component | Technology |
|---|---|
| Extraction | Python, Gemini API |
| Data model | Pydantic, SQLite with FTS5 |
| Media CDN | Cloudflare R2 |
| Visualizer | SvelteKit 5, Tailwind CSS 4 |
| Backend | Supabase (votes, saves, likes) |
| Image gen | Stable Horde (free tier) |
| Deploy | Netlify (static adapter) |

---

## Privacy

Raw WhatsApp chat exports, the SQLite database, and derived data files containing personal information are excluded from this repository via `.gitignore`. Only pipeline code, schema definitions, and pre-exported static JSON are tracked.
