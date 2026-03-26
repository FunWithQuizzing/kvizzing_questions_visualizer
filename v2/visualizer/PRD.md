# KVizzing Visualizer — Product Requirements Document

## Overview

A web app for browsing, exploring, and celebrating the KVizzing question archive. The audience is the KVizzing WhatsApp group — members who've been part of this, want to revisit memorable questions, discover ones they missed, and just have fun with the history of the group.

The tone throughout should be warm and playful — this is a group of friends quizzing together, not a competitive platform. Numbers and stats are there to spark curiosity and nostalgia, not to rank people.

The core navigation model is **calendar-first**: a persistent calendar sidebar gives a temporal overview of all activity, with sessions as named events and ad-hoc question dates as markers. Clicking into a date or session opens the relevant view. Sessions are the primary unit of organisation; individual questions are always surfaced in the context of where they came from.

---

## Goals

1. Make the question archive **browsable and searchable** without needing to scroll WhatsApp
2. Give sessions **first-class treatment** — they are the main events in the group's quiz history
3. Provide a **per-question view** that replays the full discussion thread in context
4. Surface **fun stats** — how the group quizzes, what topics come up, which questions got everyone talking
5. Celebrate **highlights** — the questions that made everyone laugh, stumped everyone, or sparked a moment
6. **Make it playable** — random question button as the seed for a lightweight quiz-like experience

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
- Session at a glance: total questions, how many people joined in, average time to answer, how tricky it was overall

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
Keyword search backed by `data/search_index.json` (pre-built from SQLite FTS5). Searches across question text, answer text, and tags.

**Filter bar — full set:**

| Filter | Field | Notes |
|---|---|---|
| **Asker** | `question.asker` | Dropdown of all askers. "Questions by Pratik." |
| **Solver** | `answer.solver` + `answer.parts[].solver` | Dropdown of all solvers. Matches single-solver answers and any part of multi-part answers. Collaborative questions (no single solver) appear when "Collaborative" is selected. |
| **Topic** | `question.topic` | Multi-select. Only shown if topic enrichment has run. |
| **Tags** | `question.tags` | Multi-select, drawn from `data/tags.json`. |
| **Difficulty** | `stats.difficulty` | Easy / Medium / Hard |
| **Question type** | `question.type` | Factual / Connect / Identify / Fill in blank / Multi-part |
| **Has media** | `question.has_media` | Toggle — show only image/video questions |
| **Collaborative** | `answer.is_collaborative` | Toggle — show only questions solved as a group |
| **Unanswered** | `answer.text == null` | Toggle — show questions that were never solved |
| **Date range** | `date` | Date picker. Pre-sets: This month, Last 3 months, All time. |
| **Session** | `session.id` | Dropdown of all sessions, plus "Ad-hoc only" toggle |
| **Extraction confidence** | `extraction_confidence` | Default: hide `low`. Opt-in toggle to reveal uncertain extractions. |

Active filters are reflected in the URL as query params (e.g. `/feed?topic=history&solver=Saumay`) so filtered views can be shared.

**Sort options:** Newest, Oldest, Most appreciated (most reactions), Trickiest (most wrong attempts), Quickest solve, Most discussed (most participants)

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

### 5. Group Stats

A celebration of the group's quizzing history. Numbers and charts that tell the story of KVizzing — not a scoreboard, just a fun look at how the group plays.

**Member spotlight tabs:**

| Tab | What it shows |
|---|---|
| Quiz setters | Members who have set the most questions — a nod to the people who keep the group going |
| Answer getters | Members who've cracked the most questions |
| Quickest on the draw | Members with the fastest average solve time (shown only for members with 5+ solves, so it's meaningful) |
| Most in the mix | Members who jump in and attempt the most answers, regardless of whether they get it right |

Framing note: these are shown as fun facts about the group, not a ranked table with 1st/2nd/3rd. Numbers are visible but the emphasis is on participation, not winning.

**Group history charts:**
- Topic mix — how questions break down by topic across the full archive
- How tricky have questions been? — rolling average wrong attempts by month
- Question styles — breakdown of question types (factual, connect, identify, etc.)
- Session activity — how often sessions happen, shown as a bar chart by month

**URL format:** `/stats`

---

### 6. Highlights Reel

The questions the group loved most — sorted by total reactions. A feel-good browse through the archive's best moments: the ones that made everyone laugh, the ones that stumped everyone, the ones that sparked a conversation.

**Category filter:** driven by whatever categories exist in the data — not hardcoded (e.g. `funny`, `crowd_favourite`, `spicy`, `surprising`, `confirmed_correct`). Each category gets a friendly label in the UI rather than the raw key (e.g. "Made everyone laugh" instead of `funny`, "Group favourite" instead of `crowd_favourite`).

**Empty state (no reactions data):** A friendly message explaining that reactions come from WhatsApp and will appear here once enriched. Not a dead end.

**URL format:** `/highlights`

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Framework | **SvelteKit** (static adapter) | Lightest bundle for mobile, first-class static export, built-in transitions for thread replay |
| Styling | **Tailwind CSS** | Utility-first, consistent design tokens, easy responsive layouts |
| Components | **shadcn-svelte** | Accessible, unstyled primitives — full control over appearance |
| Calendar | **FullCalendar** (Svelte adapter) | Battle-tested, handles month/week views, event rendering |
| Charts | **LayerChart** | Svelte-native, lightweight, covers bar/donut/line for stats page |
| Hosting | **Netlify** | Instant cache invalidation, branch previews, better than GitHub Pages |

---

## Non-Functional Requirements

| Requirement | Detail |
|---|---|
| **Static / no backend** | All data loaded from pre-built JSON files. No server required. |
| **Fast initial load** | `sessions.json` loaded first (small, powers calendar). `questions.json` lazy-loaded. Per-day files used for date-range queries. |
| **Mobile-first** | Members primarily use phones. Calendar collapses to horizontal strip; cards and thread views optimised for small screens. |
| **Extremely good UI** | Smooth transitions on card expand, thread message reveal animation, micro-interactions on filter changes. Not a data dump — feels like a product. |
| **Private by default** | `<meta name="robots" content="noindex">`. Shared only with members via URL. |
| **No login required** | Access by URL only. Frictionless. |
| **Deep linking** | Every session and question has a stable shareable URL. |

---

## Random Question & Gamification

### v2: Random Question Button

A **"Surprise me"** button available on the home screen and the Question Feed. Picks a random question from the current filter context and navigates to its Question Detail view.

**Behaviour:**
- On the home screen (no active filters): picks from the full archive
- Inside the feed with active filters: picks only from the filtered result set — e.g. "Surprise me with a hard history question"
- The button is visually prominent — not buried in the filter bar

**Question Detail in "surprise" mode:**
- Answer is **hidden by default** when arriving via the Random Question button
- A "Reveal answer" button shows the answer + discussion thread
- A "Next random" button picks another question from the same filter context without going back to the feed

This creates a lightweight quiz-like experience: set your filters, hit "Surprise me", try to recall the answer, then reveal.

---

### Future: Gamification Extensions

The random question mechanic is the foundation for future game modes. Planned for post-v2:

| Feature | Description |
|---|---|
| **Quiz mode** | Timer shown while answer is hidden. Score tracked locally (fast / slow / gave up). Session summary at the end. |
| **Daily challenge** | One featured question per day, same for all members. Shareable result card ("I got today's KVizzing question in 15 seconds!"). |
| **Streak tracking** | Browser localStorage tracks how many days in a row a member has visited and attempted a question. |
| **Share to WhatsApp** | Deep link that opens the question in the app with a pre-filled message ("Can you get this one? [link]"). |
| **"Try the archive"** | Pick a random question from a specific session — replay a past quiz solo. |

These require no backend — all state (streaks, scores) lives in `localStorage`. The only exception is the daily challenge featured question, which is determined by a pre-built `data/daily.json` generated by the pipeline.

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
3. **Quizmaster colours**: Assign a consistent colour per quizmaster for session events on the calendar — derive from name hash, or let it be configurable?
4. **Highlights page without reactions**: Show an empty state with instructions to run `enrich-reactions`, or hide the page entirely until reactions data is present?
