# KVizzing Visualizer — Product Requirements Document

## Overview

A web app for browsing, exploring, and celebrating the KVizzing question archive. The audience is the KVizzing WhatsApp group — members who've been part of this, want to revisit memorable questions, discover ones they missed, and just have fun with the history of the group.

The tone throughout should be warm and playful — this is a group of friends quizzing together, not a competitive platform. Numbers and stats are there to spark curiosity and nostalgia, not to rank people.

The primary entry point is the **Feed** — a searchable, filterable archive of every question. A persistent calendar sidebar on the right provides temporal navigation — sessions appear as named events, ad-hoc question dates as markers. The two complement each other: the Feed is for searching and browsing across the full archive; the calendar is for navigating by when things happened. Sessions are the primary unit of organisation; individual questions are always surfaced in the context of where they came from.

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

**Data loading abstraction (important):** All components must access question data through a single `QuestionStore` module — never by fetching JSON files directly. The store exposes a fixed interface (`getQuestions(filters)`, `getById(id)`, etc.). In v2, the store loads `questions.json` in full. If the file ever grows large enough to warrant splitting (e.g. per-month files), only the store's internal fetch logic changes — no component code is affected. This is the only design constraint required to make the split easy later.

---

## Layout

### Desktop

```
┌────────────────────────────────────────┬─────────────────┐
│                                        │                 │
│           Main content area            │    Calendar     │
│  (Feed / Session / Question /          │    Sidebar      │
│   Sessions List / Highlights)          │                 │
│                                        │   (persistent)  │
└────────────────────────────────────────┴─────────────────┘
```

Content is left-primary. The calendar sits on the right — it's a navigation tool, not content, so it doesn't compete for the reader's first attention.

### Mobile

The calendar collapses into a horizontal strip showing the current month with dot indicators per day. A "Calendar" button opens a full-screen calendar overlay. The strip is a **custom component** (not FullCalendar) — FullCalendar is used only for the full-screen overlay and the desktop sidebar.

---

## Calendar Sidebar

The primary navigation mechanism. Present on all pages — Feed, Session View, Question Detail, Sessions List, and Highlights. Always visible on desktop, collapsible on mobile.

The calendar's visual weight adapts to context so it never feels out of place:
- On the Feed (landing page) it is prominent — the page is about browsing and navigating the archive, and the calendar is a key tool for that.
- On Session View and Question Detail it steps back visually — slightly narrower, header minimised. It stays present so users can jump to a nearby date or session without leaving the page.
- On Sessions List and Highlights it stays present at the same reduced weight as Session View — useful for jumping to a specific period, but the page content takes priority.

The calendar never dominates pages where the primary content is a specific session or question. On those pages, the active date/session is highlighted in the calendar to maintain orientation.

### View toggle

A **Week / Month** toggle in the calendar header switches between views. Month is the default — it gives the best overview of when sessions happened. Week view shows more granular detail for a specific period.

- **Month view** — full month grid, sessions as named event blocks, ad-hoc dots per day
- **Week view** — 7-day strip, same event rendering but more space per day for session names and details

On mobile (full-screen overlay), the same toggle is available.

### What appears on the calendar

| Event type | Display |
|---|---|
| **Session** | Named event block — quizmaster name + theme (e.g. "Pratik · Hollywood Movies"). Colour-coded per quizmaster using the colour from `data/members.json`. |
| **Multiple sessions on same day** | Both shown as stacked named blocks. Each is independently clickable. |
| **Ad-hoc questions** | Small dot/badge with count on the date (e.g. `●3`). Not named individually. |
| **Both on same day** | Session event(s) take the main slot; ad-hoc dot appears below. |
| **Before archive start** | Dates prior to the earliest question in the archive are rendered in a muted/greyed style — visually distinct from active dates with no activity. |

### Interactions

- **Click a session event** → opens Session View for that session
- **Click an ad-hoc date marker** → opens Feed filtered to that date, showing only non-session questions
- **Click an empty date** → no action
- **Week / Month toggle** → switches calendar view; persisted in `localStorage`
- **Prev / next navigation** → moves one week or one month depending on active view; "Today" button resets
- **Year jump** → dropdown to jump to a year directly (useful as the archive grows)

### Visual indicators

- Dates with sessions: highlighted background
- Dates with only ad-hoc questions: subtle dot
- Today: outlined
- Selected date/session: accent colour

---

## Navigation

**Nav items:** `Sessions · Highlights` — 2 items. The **logo links to `/`** (the Feed, which is also the landing page). No separate "Feed" or "Home" nav item needed — the logo covers it.

On **desktop**, the nav bar sits above the content + calendar layout. Sessions and Highlights are the two destinations not reachable from the landing page directly.

On **mobile**, the nav bar is a **bottom tab bar** (thumb-friendly). Items: Home (logo/house icon → `/`), Sessions, Highlights.

Session View and Question Detail are never top-level nav destinations — you always arrive contextually (via calendar, sessions list, or feed).

---

## Design Principle — Clean Execution

All features described in this PRD are in scope. "Clean" refers to how they are built and presented, not what is included. Specifically:
- Use generous whitespace and readable typography — never cram content into dense blocks
- Each page has a clear primary focus; secondary information is visually subordinate, not hidden
- Progressive disclosure: show the most relevant information first, with details available on demand (e.g. answer collapsed by default in the feed, expanded on click)
- Smooth transitions and micro-interactions — navigating between questions or expanding a thread should feel fluid, not jarring
- Consistent visual language across cards, badges, and thread entries — the UI should feel like one coherent product

---

## Pages & Views

### 0. Feed *(Landing page)*

The entry point and primary browse surface. Looks and feels like a landing page at the top, transitions into a full question browser below.

**Hero section (top of page):**
- **Tagline** — e.g. "Every question the group ever asked. Right here." (copy TBD)
- **Archive snapshot** — one quiet line: e.g. "847 questions · 23 sessions · since Sep 2025"
- **"Surprise me" button** — large, prominent, directly below the tagline. Picks a random question (excluding `extraction_confidence: "low"`) and opens Question Detail.

**Recent sessions strip:**
Immediately below the hero — the last 2–3 sessions as compact cards (title, date, question count). Shown only when no search or filters are active. Disappears once the user starts filtering, replaced by the filtered results.

**Search bar:**
Full-width, below the recent sessions strip. Fuse.js client-side fuzzy search across question text, answer text, and tags.

**Filter bar:**

Filters are split into two tiers. Primary filters are always visible below the search bar. Secondary filters are tucked behind a **"More filters"** button that expands a panel.

*Primary filters (always visible):*

| Filter | Field | Notes |
|---|---|---|
| **Date range** | `date` | Date picker. Pre-sets: This month, Last 3 months, All time. |
| **Asker** | `question.asker` | Dropdown of all askers |
| **Solver** | `answer.solver` + `answer.parts[].solver` | Dropdown of all solvers, with **"Collaborative"** option at top |
| **Difficulty** | `stats.difficulty` | Easy / Medium / Hard |

*Secondary filters (behind "More filters" toggle):*

| Filter | Field | Notes |
|---|---|---|
| **Topic** | `question.topic` | Multi-select. Only shown if topic enrichment has run. |
| **Tags** | `question.tags` | Multi-select, drawn from `data/tags.json` |
| **Question type** | `question.type` | Factual / Connect / Identify / Fill in blank / Multi-part |
| **Has media** | `question.has_media` | Toggle — show only image/video questions |
| **Unanswered** | `answer.text == null` | Toggle — show questions never solved |
| **Session** | `session.id` | Dropdown of all sessions, plus "Ad-hoc only" toggle |
| **Extraction confidence** | `extraction_confidence` | Default: hide `low`. Opt-in toggle to reveal. |

When secondary filters are active, the "More filters" button shows a badge with the count of active secondary filters so users know something is applied even when the panel is collapsed.

Active filters reflected in URL as query params. Multi-select filters use repeated keys (e.g. `topic=history&topic=science`). Booleans use `1`/`0`.

**Question cards:**

Each card shows:
- Question text (truncated)
- Asker name + date
- Session badge if applicable (e.g. `Pratik Session · Q7`)
- Topic badge, difficulty badge
- Answer — simple reveal only ("Show answer" button, expands inline). Full submission experience is in Question Detail.
- Key stats: wrong attempts, time to answer, participant count
- Reaction summary (e.g. `😂 ×3  ❤️ ×2`) if available
- Highlight badges if present

**Sort options:** Newest, Oldest, Most appreciated, Trickiest, Quickest solve, Most discussed

**URL format:** `/` (landing page) — active filters appended as query params (e.g. `/?topic=history&solver=Saumay`)

---

### 1. Session View (Primary)

The most important view. Opened by clicking a session on the calendar or from the Sessions list.

**Session title:**
`<Theme> by <Quizmaster> · <Date>` — e.g. "Hollywood Movies by Pratik · 16 Mar 2026". If no theme is set, falls back to "Quiz by Pratik · 16 Mar 2026".

**Header:**
- Session title (format above)
- Session at a glance: total questions, how many people joined in (computed from `unique_participants` across all session questions), average time to answer, overall difficulty

**Question tiles:**
- All questions displayed as a **tile grid** in `question_number` order — compact preview format, not full expanded cards
- Each tile shows: question number (Q1, Q2…), question text (truncated to 2 lines), difficulty badge, topic badge, and a subtle solved/unsolved indicator once the user has attempted it
- Clicking a tile opens Question Detail for that question
- The full answer submission block and discussion thread live in Question Detail only — Session View is a navigation surface, not a play surface

**Scores (conditional):**
If `scores` is present in `sessions.json` for this session (i.e. the quizmaster posted a score announcement in the chat), show the scores exactly as extracted — a simple line per participant with their score. Not a ranked table, just a casual read-out. If `scores` is null, this section is hidden entirely — no empty state, no mention of scores.

**"Reveal all" toggle:**
A toggle in the session header — **default OFF**. When ON, all tiles expand to show the answer text inline. When OFF, all tiles collapse. Simple show/hide with no per-tile memory.

**Implementation note:** Each tile should own a local `revealed` boolean, and the toggle should drive all tiles by setting that boolean. This separation means adding per-tile memory later (e.g. "stay expanded once visited") only requires changing how the toggle interacts with tile state — the tile component itself is already structured correctly.

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
- **Answer submission block** (see below)
- Discussion thread — hidden until answer is revealed; chronological replay of all `discussion[]` entries, styled by role:
  - `attempt` — speech bubble (green if `is_correct`, grey otherwise)
  - `hint` — italicised nudge from asker
  - `confirmation` — highlighted confirmation message
  - `answer_reveal` — asker reveals without anyone getting it
  - `chat` — muted banter
- Stats panel — wrong attempts, hints given, time to answer, unique participants, difficulty
- Reactions panel — per-emoji counts + category labels (if available)

**Answer submission block:**

The answer area is interactive by default on every question — users try the question before seeing the answer. The discussion thread is hidden until the answer is revealed (it contains confirmations and answer reveals that would give it away).

*Single-answer questions:*
- One text input + Submit button
- Small **Reveal** button alongside (always visible)
- Up to **3 attempts**, with an attempt counter shown ("Attempt 2 of 3")
- After 3 failed attempts, the input is disabled and the Reveal button becomes prominent — no further submission is possible

*Multi-part questions (X/Y/Z):*
- One input per part, each independently submittable
- Each part has its own attempt counter and its own small **Reveal** button
- Parts can be answered in any order
- Solving all parts reveals the discussion thread

*Feedback per submission:*

| Result | Condition | Display |
|---|---|---|
| **Correct** | Exact match (case-insensitive, articles stripped) | Green indicator, input locked, answer text shown |
| **Almost** | Close match (fuzzy — similar spelling, minor typo) | Yellow "Almost — try again" indicator, answer stays hidden. Does **not** consume an attempt — try again freely. |
| **Wrong** | No match | Red indicator, attempt counter incremented |

After all parts are solved or revealed, the full discussion thread is shown.

**State persistence:** Answer submission state is not persisted. Navigating away from a question (back to session, feed, or another question) resets all attempt state. On return, the question starts fresh with a clean input.

**Navigation:**
- If opened from a session (via session card or session URL context): Prev / Next arrows navigate within that session in `question_number` order
- If opened from the Question Feed: Prev / Next arrows navigate chronologically through the current filtered result set
- If opened via direct URL (deep link with no prior context): Prev / Next arrows navigate chronologically through the full archive — no arrows are hidden, so deep-linked questions are always explorable

**URL format:** `/question/2025-09-23-111845`

---

### 3. Sessions List

A reverse-chronological list of all sessions, as an alternative to finding them on the calendar.

**Each session card shows:**
- Session title in the standard format: `<Theme> by <Quizmaster> · <Date>`
- Number of questions
- Average time to answer, average wrong attempts
- Participant count

**URL format:** `/sessions`

---

### 4. Highlights

A single page that celebrates the group's quizzing history — the best questions and the story of how the group plays. Two sections, scrolled through in order.

**Section 1 — Best moments:**
The questions the group loved most, sorted by total reactions. A feel-good browse through the archive's highlights: the ones that made everyone laugh, stumped everyone, or sparked a conversation.

- Sorted by total reactions by default
- Category filter: driven by whatever categories exist in the data — not hardcoded (e.g. `funny`, `crowd_favourite`, `spicy`, `surprising`, `confirmed_correct`). Each category gets a friendly label (e.g. "Made everyone laugh", "Group favourite").
- Empty state (no reactions data): a friendly message explaining reactions come from WhatsApp and will appear once enriched. Not a dead end.

**Section 2 — Group story:**
Numbers and charts that tell the story of KVizzing — not a scoreboard, just a fun look at how the group plays.

*Member spotlights:*

| Tab | What it shows |
|---|---|
| Quiz setters | Members who have set the most questions — a nod to the people who keep the group going |
| Answer getters | Members who've cracked the most questions |
| Quickest on the draw | Members with the fastest average solve time (shown only for members with 5+ solves) |
| Most in the mix | Members who attempt the most answers, regardless of whether they get it right |

Shown as fun facts about the group, not a ranked table. Numbers visible but emphasis on participation.

*Charts:*
- Topic mix — how questions break down by topic across the full archive
- How tricky have questions been? — rolling average wrong attempts by month
- Question styles — breakdown of question types (factual, connect, identify, etc.)
- Session activity — how often sessions happen, bar chart by month

**Note:** The exact schema of `data/stats.json` is an implementation-time decision — define it when Stage 6 is built, driven by exactly what this page needs.

**URL format:** `/highlights`

---

## App Config

All tunable values for the visualizer live in `v2/visualizer/config/app_config.json`. Components read from this file via a shared config module — no magic numbers hardcoded in components. Full schema:

```json
{
  "site": {
    "tagline": "Every question the group ever asked. Right here.",
    "robots": "noindex"
  },

  "feed": {
    "recent_sessions_count": 3
  },

  "answer_submission": {
    "max_attempts": 3,
    "fuzzy_match_threshold": 0.75
  },

  "highlights": {
    "min_solves_for_speed_leaderboard": 5
  },

  "calendar": {
    "default_view": "month"
  },

  "members": {
    "color_palette": [
      "#F97316", "#3B82F6", "#10B981", "#8B5CF6",
      "#EF4444", "#F59E0B", "#06B6D4", "#EC4899",
      "#84CC16", "#6366F1", "#14B8A6", "#F43F5E",
      "#A855F7", "#0EA5E9", "#22C55E", "#FB923C"
    ]
  }
}
```

Any value here can be changed without touching component code.

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Framework | **SvelteKit** (static adapter) | Lightest bundle for mobile, first-class static export, built-in transitions for thread replay |
| Styling | **Tailwind CSS** | Utility-first, consistent design tokens, easy responsive layouts |
| Components | **shadcn-svelte** | Accessible, unstyled primitives — full control over appearance |
| Calendar | **FullCalendar** (Svelte adapter) | Battle-tested, handles month/week views, event rendering |
| Search | **Fuse.js** | Client-side fuzzy search; runs against `questions.json` already in memory — no extra index file |
| Charts | **LayerChart** | Svelte-native, lightweight, covers bar/donut/line for stats page |
| Dates | **date-fns + date-fns-tz** | Timezone-aware formatting; `Intl.DateTimeFormat` for detection, date-fns for display formatting |
| Hosting | **Netlify** | Instant cache invalidation, branch previews, better than GitHub Pages |

---

## Members

Member data is maintained in two layers:

**`config/members.json`** — manually maintained, committed to the repo. One entry per known member:
```json
[
  { "username": "pratik.s.chandarana", "display_name": "Pratik", "color": "#F97316", "avatar_url": null }
]
```
`avatar_url` is null until a photo is available. `color` is any valid CSS colour — used for quizmaster session blocks on the calendar, member spotlight cards, and filter dropdowns.

**`data/members.json`** — pipeline-generated at Stage 6. Merges `config/members.json` with computed stats:
```json
[
  {
    "username": "pratik.s.chandarana",
    "display_name": "Pratik",
    "color": "#F97316",
    "avatar_url": null,
    "questions_asked": 47,
    "questions_solved": 23,
    "total_attempts": 156,
    "sessions_hosted": 8,
    "avg_solve_time_seconds": 45
  }
]
```

**Colour fallback:** If a username has no entry in `config/members.json`, the UI derives a colour client-side by hashing the username string against a curated palette of 16 visually distinct colours. The same username always produces the same colour. This means every member has a consistent colour from day one — the config only needs to be updated if you want to override a specific person's colour.

**Avatar fallback:** If `avatar_url` is null, show initials in a coloured circle (using the member's assigned or hash-derived colour).

---

## Timezone

WhatsApp exports timestamps in the phone's local time with no timezone offset. The pipeline converts all timestamps to UTC during Stage 1 using the configured source timezone (`America/Chicago` — handles CST/CDT transitions automatically). All timestamps in `questions.json` are therefore UTC ISO 8601. Since the KVizzing group has members across time zones, timestamps should always be displayed in the user's local time.

**Behaviour:**
- On first load, detect the user's timezone via `Intl.DateTimeFormat().resolvedOptions().timeZone` (browser API — no prompt, no permission needed)
- Use the detected timezone as the default for all timestamp displays
- A **timezone selector** is available in the site settings (accessible from the nav bar). The dropdown lists all IANA timezone names, grouped by region, with the current selection highlighted
- The selected timezone is persisted in `localStorage` so it survives page reloads
- Every timestamp displayed in the UI — question timestamps, discussion thread times, session dates, reaction timestamps — is formatted in the active timezone

**Scope:**
- Calendar dates on the sidebar reflect the timezone (a question posted at 11:45 PM UTC may fall on a different calendar day for a user in IST). FullCalendar must be configured with the active timezone and updated whenever the user changes it — this is a specific integration requirement, not automatic.
- Time-to-answer calculations are unaffected — those are relative durations, not timestamps
- The raw `id` format (`YYYY-MM-DD-HHMMSS`) is derived from UTC and never changes — it is an identifier, not a display value

---

## Non-Functional Requirements

| Requirement | Detail |
|---|---|
| **Static / no backend** | All data loaded from pre-built JSON files. No server required. |
| **Fast initial load** | `sessions.json` loaded first (small, powers calendar). `questions.json` lazy-loaded via `QuestionStore`. All filtering (including date range) operates on the in-memory array once loaded. |
| **Mobile-first** | Members primarily use phones. Calendar collapses to horizontal strip; cards and thread views optimised for small screens. |
| **Extremely good UI** | Smooth transitions on card expand, thread message reveal animation, micro-interactions on filter changes. Not a data dump — feels like a product. |
| **Private by default** | `<meta name="robots" content="noindex">`. Shared only with members via URL. |
| **No login required** | Access by URL only. Frictionless. |
| **Deep linking** | Every session and question has a stable shareable URL. |
| **Timezone-aware** | All timestamps displayed in the user's local timezone (auto-detected; overridable via settings). Persisted in `localStorage`. |
| **Accessible** | Keyboard-navigable throughout. Colour contrast meets WCAG AA. Interactive elements have visible focus states. Screen reader support for key content (question text, answer, discussion thread). |

---

## Random Question & Gamification

### v2: Random Question Button

A **"Surprise me"** button on the Feed (landing page). Picks a random question from the current filter context and navigates to its Question Detail view.

**Behaviour:**
- No active filters: picks from the full archive, excluding `extraction_confidence: "low"` questions
- With active filters: picks only from the filtered result set — e.g. "Surprise me with a hard history question"
- The button is visually prominent — not buried in the filter bar

**Question Detail in "surprise" mode:**
- Uses the same answer submission UI as every other Question Detail — answer hidden, input active, 3 attempts, per-part reveal buttons
- A **"Next random"** button appears below the question, picking another from the same filter context without going back to the feed
- The filter context is carried in the URL (e.g. `/question/2025-09-23-111845?from=surprise&topic=history&difficulty=hard`) so it survives page loads and direct sharing
- No separate UI state needed — surprise mode is just the navigation flow, not a different layout

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

## Out of Scope (v2)

- Editing or correcting extracted questions
- Adding new questions manually
- User accounts or personalisation
- Real-time updates from WhatsApp
- Comments or reactions within the visualizer

---

## Resolved Design Decisions

| # | Decision | Resolution |
|---|---|---|
| Calendar scope | Does the calendar appear on all pages? | Yes — persistent on all pages. Visually steps back (narrower, minimised header) on Session View, Question Detail, Sessions List, and Highlights. Active date/session highlighted for orientation. |
| Filter bar presentation | Show all 12 filters inline or collapse secondary ones? | Primary filters (Date range, Asker, Solver, Difficulty) always visible. Secondary filters behind a "More filters" toggle panel. Active secondary filters count shown as a badge on the button. |
