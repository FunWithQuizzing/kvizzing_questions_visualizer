# KVizzing Visualizer — Product Requirements Document

## Overview

A web app for browsing, filtering, and exploring the KVizzing question archive. The primary audience is the KVizzing WhatsApp group members — people who asked or answered these questions and want to relive, search, and discover them.

The core navigation model is **calendar-first**: a persistent calendar sidebar gives a temporal overview of all activity, with sessions as named events and ad-hoc question dates as markers. Clicking into a date or session opens the relevant view. Sessions are the primary unit of organisation; individual questions are always surfaced in the context of where they came from.

---

## Goals

1. Make the question archive **browsable and searchable** without needing to scroll WhatsApp
2. Give sessions **first-class treatment** — they are the main events in the group's quiz history
3. Provide a **per-question view** that replays the full discussion thread in context
4. Surface **stats and patterns** — who asks the most, what topics come up, which questions were hardest
5. Celebrate **highlights** — funniest questions, crowd favourites, fastest solves

---

## Data Source

All data comes from `KVizzingQuestion` JSON objects conforming to `v2/schema/schema.json`. The visualizer is read-only — it consumes pre-extracted data, it does not write back.

Primary input: `data/questions.json` — array of all questions sorted by `question.timestamp`.

---

## Layout

### Desktop

```
┌─────────────────┬────────────────────────────────────────┐
│                 │                                        │
│    Calendar     │           Main content area            │
│    Sidebar      │   (Feed / Session / Question / Stats)  │
│                 │                                        │
│   (persistent)  │                                        │
└─────────────────┴────────────────────────────────────────┘
```

### Mobile

The calendar collapses into a horizontal strip showing the current month with dot indicators per day. A "Calendar" button opens a full-screen calendar overlay.

---

## Calendar Sidebar

The primary navigation mechanism. Always visible on desktop, collapsible on mobile.

### What appears on the calendar

| Event type | Display |
|---|---|
| **Session** | Named event block — quizmaster name + theme (e.g. "Pratik · Hollywood Movies"). Colour-coded per quizmaster. |
| **Ad-hoc questions** | Small dot/badge with count on the date (e.g. `●3`). Not named individually. |
| **Both on same day** | Session event takes the main slot; ad-hoc dot appears below it. |

### Interactions

- **Click a session event** → opens Session View for that session
- **Click an ad-hoc date marker** → opens Question Feed filtered to that date, showing only non-session questions
- **Click an empty date** → no action
- **Month navigation** → prev/next month arrows; "Today" button
- **Year jump** → dropdown to jump to a year directly (useful as the archive grows)

### Visual indicators

- Dates with sessions: highlighted background
- Dates with only ad-hoc questions: subtle dot
- Today: outlined
- Selected date/session: accent colour

---

## Pages & Views

### 1. Session View (Primary)

The most important view. Opened by clicking a session on the calendar or from the Sessions list.

**Header:**
- Session ID, date, quizmaster name, theme (if set)
- Session-level stats: total questions, total participants (unique across all questions), average time to answer, average difficulty

**Question list:**
- All questions in `question_number` order
- Each question rendered as an expanded card (not collapsed) since the user is browsing a specific quiz
- Cards show: question text, answer (revealed), solver, time taken, wrong attempts, difficulty badge, topic badge
- Highlight badges if reactions available
- Clicking a question card opens the Question Detail view

**Navigation:**
- Prev session / Next session arrows (chronological order)
- "Back to Calendar" breadcrumb

**URL format:** `/session/2026-03-16-pratik`

---

### 2. Question Detail

Full view of a single question. Reachable from a session card, the question feed, or a direct URL.

**Context bar (top):**
- If part of a session: `Session: Pratik · Hollywood Movies > Q7` with a link back to the session
- If ad-hoc: `Date: 23 Sep 2025` with a link to the day's question feed

**Sections:**
- Full question text (+ media placeholder if `has_media: true`)
- Answer block — text, solver, confirmation message, collaborative flag, parts breakdown for multi-part questions
- Discussion thread — chronological replay of all `discussion[]` entries, styled by role:
  - `attempt` — speech bubble (green if `is_correct`, grey otherwise)
  - `hint` — italicised nudge from asker
  - `confirmation` — highlighted confirmation message
  - `answer_reveal` — asker reveals without anyone getting it
  - `chat` — muted banter
- Stats panel — wrong attempts, hints given, time to answer, unique participants, difficulty
- Reactions panel — per-emoji counts + category labels (if available)

**Navigation (within session):**
- If opened from a session: Prev question / Next question arrows within that session

**URL format:** `/question/2025-09-23-003`

---

### 3. Question Feed

A filtered/sorted list of questions. Not the primary entry point, but useful for searching across the full archive regardless of session.

**Each card shows:**
- Question text (truncated)
- Asker name + date
- Session badge if applicable (e.g. `Pratik Session · Q7`)
- Topic badge, difficulty badge
- Answer (collapsed by default, expandable)
- Key stats: wrong attempts, time to answer, participant count
- Reaction summary (e.g. `😂 ×3  ❤️ ×2`) if available
- Highlight badges if present

**Search bar (top of feed):**
- **Keyword search** — full-text via Pagefind (indexes all question text at build time)
- **Semantic search** — natural language query (e.g. "Indian history questions") embedded in-browser via `transformers.js`, matched against a pre-built HNSW vector index. Toggle between keyword and semantic mode.

**Filter bar:**
- Topic (multi-select)
- Tags (multi-select, drawn from `data/tags.json`)
- Asker (dropdown)
- Difficulty
- Question type
- Has media (toggle)
- Date range picker
- Session (dropdown — or "Ad-hoc only" toggle)
- Extraction confidence (default: hide `low`)

**Sort options:** Newest, Oldest, Most reactions, Hardest, Fastest solve

**URL format:** `/feed` (with query params for active filters, e.g. `/feed?topic=history&difficulty=hard`)

---

### 4. Sessions List

A reverse-chronological list of all sessions, as an alternative to finding them on the calendar.

**Each session card shows:**
- Date, quizmaster, theme
- Number of questions
- Average time to answer, average wrong attempts
- Participant count

**URL format:** `/sessions`

---

### 5. Stats & Leaderboards

Aggregate views derived from the full archive.

**Leaderboard tabs:**

| Tab | Metric |
|---|---|
| Top Solvers | Most correct answers |
| Top Askers | Most questions posed |
| Fastest | Lowest average `time_to_answer_seconds` (min 5 questions) |
| Most Engaged | Highest total attempts across questions |

**Charts:**
- Topic breakdown — bar/donut chart of question count by `TopicCategory`, average difficulty per topic
- Difficulty over time — rolling average `wrong_attempts` by month
- Question type distribution — donut chart of `QuestionType`
- Session frequency — bar chart of sessions per month

**URL format:** `/stats`

---

### 6. Highlights Reel

A curated feed of questions with `highlights` populated, sorted by `total_reactions` descending.

**Category filter:** driven by whatever categories exist in the data — not hardcoded (e.g. `funny`, `crowd_favourite`, `spicy`, `surprising`, `confirmed_correct`)

**URL format:** `/highlights`

---

## Non-Functional Requirements

| Requirement | Detail |
|---|---|
| **Static / no backend** | All data loaded from pre-built JSON files. No server required. Deployable to GitHub Pages or Netlify. |
| **Fast initial load** | Lazy-load `questions.json`. Use per-day JSON files (`data/questions_by_date/`) for calendar and date-range queries to avoid loading the full archive upfront. |
| **Mobile-first** | Members primarily use phones. Calendar collapses gracefully; cards and thread views must be readable on small screens. |
| **Private by default** | No public indexing (`<meta name="robots" content="noindex">`). The group is private; the site is shared only with members via URL. |
| **No login required** | Access by URL only. Keep it frictionless. |
| **Deep linking** | Every session and question has a stable URL that can be shared in WhatsApp. |

---

## Out of Scope (v1)

- Editing or correcting extracted questions
- Adding new questions manually
- User accounts or personalisation
- Real-time updates from WhatsApp
- Comments or reactions within the visualizer

---

## Open Questions

1. **Media**: `has_media: true` questions reference images/videos not present in `.txt` exports. Show a placeholder, or hide media questions from the feed by default with an opt-in toggle?
2. **Low-confidence questions**: Hide `extraction_confidence: "low"` by default with an opt-in toggle to reveal them?
3. **Hosting**: GitHub Pages (free, simple) vs Netlify vs self-hosted?
4. **Framework**: SvelteKit or Next.js static export are both good fits given the calendar + routing requirements. Vanilla JS is feasible but the calendar component would need a library either way.
5. **Calendar library**: [`cal-heatmap`](https://cal-heatmap.com) for the activity heatmap view, plus a standard month-grid calendar (e.g. `fullcalendar.io` or a lightweight custom component)?
6. **Quizmaster colours**: Assign a consistent colour per quizmaster for session events on the calendar — derive from name hash, or let it be configurable?
