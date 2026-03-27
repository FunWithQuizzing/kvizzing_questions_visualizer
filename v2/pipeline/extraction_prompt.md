# KVizzing Q&A Extraction — Manual Extraction Prompt

Use this prompt verbatim in a new Claude session to extract 28 dates of Q&A pairs.

---

## COPY EVERYTHING BELOW THIS LINE INTO A NEW CLAUDE SESSION

---

You are extracting Q&A pairs from the KVizzing WhatsApp trivia group. You will read compact daily chat files one at a time and write a structured JSON output file for each date.

Work through all 28 dates in order. Do not skip any date, even if it appears to have few or no questions.

---

## INPUT FILE FORMAT

Files live at: `v2/data/extraction_compact/YYYY-MM-DD.txt`

Each line is a single WhatsApp message:

```
[2025-09-28T15:01:19Z] Aditi Bapat: Starting with a breezy one. ‎image omitted
```

Format: `[ISO8601-UTC-timestamp] username: message text`

**Multi-line messages** — parts joined by ` ↵ ` (space-arrow-space):
```
[2025-09-28T15:22:26Z] Aditi Bapat: Line one ↵ Line two ↵ Line three
```

**Media markers** — appear inline in the message text when the original had an attachment:
- `image omitted` — question had a photo
- `GIF omitted` — question had a GIF
- `video omitted` — question had a video
- `audio omitted` — question had a voice note or audio clip
- `document omitted` — question had a PDF or document

**Edit artifact** — `<This message was edited>` appended to edited messages.

**Invisible character** — WhatsApp inserts a U+200E Left-to-Right Mark (`\u200e`, looks like a space but isn't) immediately before media markers and before `<This message was edited>`. Strip it together with the marker it precedes.

**File sizes**: 200–2200 lines. Each file's window overlaps into the next day (messages sent after midnight UTC appear at the top of the next date's file).

---

## WHAT TO EXTRACT

Extract every genuine trivia Q&A pair. A Q&A pair is a message that poses a trivia question, followed by discussion where participants attempt to answer.

**Include:**
- Direct trivia questions asked to the group
- Session questions (numbered sequences hosted by a quizmaster)
- Questions that were never answered or whose answers were revealed by the asker

**Exclude:**
- General chat, memes, off-topic discussion
- Questions with no corresponding discussion (pure announcements with zero replies)
- Repeat/duplicate posts of a question already extracted
- Any question whose `question_timestamp` does **not** start with the file's date (e.g. when processing `2025-09-25.txt`, skip any message timestamped `2025-09-26T...`). Each compact file contains the next day's messages as a lookahead context buffer — do not extract them as new questions here; they will be extracted when you process the next date's file.

---

## OUTPUT FORMAT

**All paths in this document are relative to the repo root `KVizzing/`.** Set your working directory to `KVizzing/` before running any commands.

Write one JSON file per date at: `v2/data/extraction_output/YYYY-MM-DD.json`

Each file is a JSON array. Each element is a flat object with exactly these fields:

```json
{
  "question_timestamp": "2025-09-28T15:01:19Z",
  "question_text": "...",
  "question_asker": "Aditi Bapat",
  "has_media": true,
  "is_session_question": true,
  "session_quizmaster": "Aditi Bapat",
  "session_theme": null,
  "session_question_number": 1,
  "answer_text": "...",
  "answer_solver": "Akshay",
  "answer_timestamp": "2025-09-28T15:02:03Z",
  "answer_confirmed": true,
  "confirmation_text": "Correct!!",
  "answer_is_collaborative": false,
  "answer_parts": null,
  "discussion": [
    {
      "timestamp": "2025-09-28T15:02:03Z",
      "username": "Akshay",
      "text": "Mona Lisa",
      "role": "attempt",
      "is_correct": true
    },
    {
      "timestamp": "2025-09-28T15:02:15Z",
      "username": "Aditi Bapat",
      "text": "Correct!!",
      "role": "confirmation",
      "is_correct": null
    }
  ],
  "scores_after": null,
  "extraction_confidence": "high"
}
```

---

## FIELD-BY-FIELD RULES

### question_timestamp
The exact UTC timestamp of the question message. Copy verbatim from the file, preserving the `Z` suffix.

### question_text
The full text of the question message, after applying the text cleaning rules (see discussion section). Additionally:
- If `has_media=true`, append `[image: brief description of what the image likely shows based on context]` at the end of question_text. Use surrounding discussion to infer the content (e.g. if people say "is that the Eiffel Tower?" write `[image: landmark, possibly Eiffel Tower]`). If you cannot infer anything, write `[image: unknown]`.

### question_asker
The username exactly as it appears in the chat, without a leading `~`.

### has_media
`true` if the question message contained `image omitted`, `GIF omitted`, `video omitted`, `audio omitted`, or `document omitted`. Otherwise `false`.

### is_session_question
`true` if the question was posted as part of a structured quiz session (a quizmaster hosting a numbered sequence). `false` for ad-hoc individual questions.

**How to identify sessions:**
- A quizmaster announces they will run a quiz
- Questions are explicitly numbered ("Number 1.", "Q2.", etc.)
- The quizmaster responds to each question with confirmation/scores
- A score tally is announced at the end

### session_quizmaster
The username of the session host. `null` for ad-hoc questions.

### session_theme
The announced theme of the session (e.g. `"Bollywood"`, `"Science"`), if stated. `null` otherwise.

### session_question_number
The number the quizmaster assigns to the question. `null` for ad-hoc questions. Use the quizmaster's label exactly — if they skip from Q15 to Q17, record `17` not `16`.

### answer_text
A clean, complete answer string. Use the solver's winning attempt as the basis, but enrich it with context from the asker's confirmation or reveal to produce a full, accurate answer. Do not copy the solver's text verbatim if it is sloppy, hedged, or incomplete.

Examples of enrichment:
- Solver said "Astronauts" → asker revealed "Class of 2025 selected from 8000 candidates" → `"NASA Astronaut class of 2025, selected from 8000 candidates"`
- Solver said "he would draw ulta?" → asker revealed context → `"Drawing/sketching upside down (so clients who were uncomfortable sitting next to a Black man would sit opposite him)"`
- Solver said "Free trade?" → `"Free trade"` (just clean up, no extra context needed)

If the question was never answered and the asker never revealed the answer, set to `null`.

### answer_solver
The username of the **first person** to give the correct (or substantially correct) answer. `null` if the asker revealed the answer without anyone getting it.

For collaborative questions: set `answer_solver` to the person who gave the core/primary correct answer if one person got there first. Only use `null` when no single person produced a satisfactory answer before the asker revealed it.

### answer_timestamp
**The timestamp of `answer_solver`'s first confirmed-correct attempt in discussion.** NOT the asker's confirmation. NOT the asker's reveal message. A "confirmed-correct attempt" means the attempt that directly led to the asker's confirmation — not a partial or intermediate answer the asker said "almost" to.

- If `answer_solver` is set: copy the `timestamp` of their `is_correct=true` entry from the discussion list
- If `answer_solver` is `null` (no one got it, asker revealed): `null`

This rule applies uniformly — single-solver, collaborative, and answer_reveal cases all follow it.

### answer_confirmed
`true` **only** if the asker sent an explicit text message confirming the answer correct. The confirmation must be a clear, positive signal — not contextually implied.

Explicit confirms: "correct", "yes", "bingo", "right", "yep", "yess", "yup", "exactly", "indeed", "spot on", "perfect", "well done", "✅", "👍", "💯", "!" — or any unambiguously affirmative message from the asker.

**Do NOT set true if:**
- The asker only reacted with an emoji (not a text message)
- The asker added context or elaboration but never said "correct" or equivalent
- Someone other than the asker confirmed
- The asker's message sounds like amazement/commentary rather than confirmation ("wow", "took me so long to type", "that's exactly what I was thinking")

### confirmation_text
The exact text of the asker's confirmation message. `null` if `answer_confirmed=false`.

### answer_is_collaborative
`true` when multiple participants together produced the complete answer (e.g. person A answered part X, person B answered part Y). `false` for all other cases.

### answer_parts
For **any** multi-part question (X/Y/Z style, or "guess who + achievement", etc.) — whether solved by one person or collaboratively. `null` for single-answer questions.

Use descriptive labels that match the question (e.g. `"X"`, `"Y"`, `"Entity"`, `"First flag"`, `"King"`, `"Daughter"`). Set `solver` to the username who answered that part, or `null` if that part was not solved.

Example — collaborative (different solvers):
```json
[
  {"label": "Territory name", "text": "BIOT", "solver": "Kartikey Pradhan"},
  {"label": "Island group", "text": "Chagos", "solver": "Kartikey Pradhan"},
  {"label": "US base", "text": "Diego Garcia", "solver": "Nikhil Borra"}
]
```

Example — single solver, multi-part question:
```json
[
  {"label": "Entity", "text": "British India", "solver": "Pavan Pamidimarri"},
  {"label": "First flag", "text": "British Indian Ensign", "solver": "Pavan Pamidimarri"}
]
```

### discussion
An ordered list (chronological) of all relevant messages in the Q&A thread. Include:
- All answer attempts by participants
- Hints from the asker
- The asker's confirmation message
- The asker's answer reveal (if they revealed it)
- Closely related chat (reactions, commentary on the question)

Each entry:
```json
{
  "timestamp": "2025-09-28T15:02:03Z",
  "username": "Akshay",
  "text": "Mona Lisa",
  "role": "attempt",
  "is_correct": true
}
```

**role values:**
- `attempt` — participant's answer try
- `hint` — asker provides a clue or guiding information (whether standalone or tagged onto a rejection: "Nope, but close — same universe" is `hint`)
- `confirmation` — asker's direct yes/no response to an attempt, without substantive new clues:
  - Positive: "Correct!", "Bingo", "Yes", "Yes! Fermat's Last Theorem"
  - Negative: "no", "nope" (bare rejection with no additional guiding info)
  - Tip: if the message primarily gives a clue, it's `hint`, even if it starts with "nope"
- `chat` — banter, reactions, non-answer commentary
- `answer_reveal` — asker reveals the answer (after no one got it, or after confirming, to explain further)

**is_correct rules (critical):**
- `attempt` entries: **always** `true` or `false`, **never** `null`
  - `true` = this attempt directly led to the asker's confirmation (the winning answer)
  - `false` = wrong, or partially correct but NOT the confirmed answer
- All other roles (`hint`, `confirmation`, `chat`, `answer_reveal`): always `null`

**Deciding is_correct for intermediate attempts:** If the asker responds to an attempt with "almost", "not quite", "close", "nearly", "getting warmer" or anything other than an explicit confirmation, that attempt is `is_correct: false` — even if it looks close. Only the attempt the asker explicitly confirms gets `is_correct: true`. If no attempt was confirmed but you are certain an attempt is factually correct (e.g. the asker revealed the same answer), that attempt may be `is_correct: true`. When two people answer correctly at the same second or within a second of each other, the one that appears first in the file gets `is_correct: true`; subsequent identical correct answers also get `is_correct: true` (mark all correct, but `answer_solver` is the first).

**Text cleaning — applies to ALL text fields** (`question_text`, `answer_text`, `confirmation_text`, and every discussion entry `text`):
- Strip ` ↵ ` separators (replace with space or newline)
- Remove `\u200e<This message was edited>` entirely (the invisible LRM character comes right before it)
- Do NOT copy media marker text (`image omitted`, `GIF omitted`, etc.) into any text field
- Strip any stray `\u200e` (U+200E) characters

### scores_after
Only for session questions where the quizmaster explicitly announces per-player running totals immediately after this question. Populate as:
```json
[
  {"username": "Akshay", "score": 3},
  {"username": "Nikhil Borra", "score": 2}
]
```

Set to `null` in all of these cases:
- Ad-hoc (non-session) questions
- Session questions where no score is announced after this specific question
- The quizmaster only announces the **point value** of the question ("That was a 20-pointer!") without naming per-player totals — that is a question difficulty label, not a score
- The quizmaster announces a winner at the end of the session without per-question breakdowns

### extraction_confidence
Your confidence that this is a genuine Q&A pair with a clearly known answer:

- `"high"` — The asker gave an explicit text confirmation. You are certain the answer is correct.
- `"medium"` — No explicit text confirmation, but strong contextual signals: the asker continued to the next question without dispute, the attempted answer perfectly matches the question, or the answer was revealed by the asker.
- `"low"` — No confirmation, weak or ambiguous signals. The answer may be wrong or the question may not be genuine trivia.

**Note on media questions:** You cannot see the attached image/video yourself. For image-based questions, rely solely on chat signals:
- If the asker explicitly confirmed with text → `answer_confirmed=true` → `extraction_confidence="high"` (the confirmation is the signal)
- If the asker never confirmed → `answer_confirmed=false` → `extraction_confidence="medium"` or `"low"` (you cannot verify the answer without the image, so do not upgrade to `"high"`)

---

## LLM SELF-CHECK

Before finalising each Q&A pair, verify the answer independently:

1. **Does the answer actually answer the question?** Re-read the question and check that the extracted `answer_text` is a plausible, correct answer. Use your knowledge to verify.
2. **Is the winner correctly identified?** The `answer_solver` should be the first person whose attempt message contains the correct answer (or close enough that the asker confirmed it). If multiple people gave partial credit, use `answer_is_collaborative=true`.
3. **Is `answer_timestamp` pointing to the solver's attempt?** Check the discussion list — the `answer_timestamp` must match the `timestamp` of `answer_solver`'s `is_correct=true` entry, not the asker's confirmation.
4. **Flag genuine uncertainty.** If you cannot verify the answer from your knowledge, lower `extraction_confidence` to `"medium"` or `"low"` accordingly.

---

## WORKFLOW PER DATE

For each date:

1. **Read** the compact file with the Read tool. If the file is long (>1000 lines), read it in 250-line chunks using `offset` and `limit` parameters.
2. **Scan** for all Q&A pairs. Note the timestamps. **Only process questions whose timestamp starts with the file's date** (e.g. `2025-09-25T...` for `2025-09-25.txt`). Messages timestamped the following day are context only — stop extraction there.
3. **Extract** each pair into the JSON structure.
4. **Self-check** each pair (answer correctness, solver, timestamp).
5. **Write** the output file to `v2/data/extraction_output/YYYY-MM-DD.json`.
6. **Run the audit script** (from the repo root `KVizzing/`):
   ```
   python3 v2/pipeline/audit_extraction.py v2/data/extraction_output/YYYY-MM-DD.json
   ```
   Fix any issues reported before moving to the next date.

---

## SESSIONS IN THIS DATE RANGE

The first KVizzing hosted session starts on **2025-09-28**, hosted by **Aditi Bapat**. She announces the session at 14:57:52Z and posts numbered questions ("Starting with a breezy one.", "Number 2.", etc.). She had 28 questions prepared.

**Aditi's session specifics:**
- She **does not announce per-player scores** after questions — `scores_after = null` for all her questions.
- She skips Q16 (numbering jumps from Q15 to Q17) — use her numbering as-is.
- Many questions are image-only or image + brief text. These get `has_media: true` and an `[image: ...]` description in `question_text`.
- The session runs on **2025-09-28**. Any questions from her session whose timestamp falls on 2025-09-29 should be extracted in the **2025-09-29** output file (normal date-matching rule applies).

**Abhishek S's session on 2025-09-29**: He assigns point values per question ("10 points!", "20 points!", "50 points!"). These are difficulty labels, NOT per-player scores — `scores_after = null` for all his questions too.

Look for additional sessions in October — identify them by quizmaster announcement + numbered questions pattern.

---

## FILES TO PROCESS

Process in this exact order:

| # | Date | File |
|---|------|------|
| 1 | 2025-09-25 | `v2/data/extraction_compact/2025-09-25.txt` |
| 2 | 2025-09-26 | `v2/data/extraction_compact/2025-09-26.txt` |
| 3 | 2025-09-27 | `v2/data/extraction_compact/2025-09-27.txt` |
| 4 | 2025-09-28 | `v2/data/extraction_compact/2025-09-28.txt` |
| 5 | 2025-09-29 | `v2/data/extraction_compact/2025-09-29.txt` |
| 6 | 2025-09-30 | `v2/data/extraction_compact/2025-09-30.txt` |
| 7 | 2025-10-01 | `v2/data/extraction_compact/2025-10-01.txt` |
| 8 | 2025-10-02 | `v2/data/extraction_compact/2025-10-02.txt` |
| 9 | 2025-10-03 | `v2/data/extraction_compact/2025-10-03.txt` |
| 10 | 2025-10-04 | `v2/data/extraction_compact/2025-10-04.txt` |
| 11 | 2025-10-05 | `v2/data/extraction_compact/2025-10-05.txt` |
| 12 | 2025-10-06 | `v2/data/extraction_compact/2025-10-06.txt` |
| 13 | 2025-10-07 | `v2/data/extraction_compact/2025-10-07.txt` |
| 14 | 2025-10-08 | `v2/data/extraction_compact/2025-10-08.txt` |
| 15 | 2025-10-09 | `v2/data/extraction_compact/2025-10-09.txt` |
| 16 | 2025-10-10 | `v2/data/extraction_compact/2025-10-10.txt` |
| 17 | 2025-10-11 | `v2/data/extraction_compact/2025-10-11.txt` |
| 18 | 2025-10-12 | `v2/data/extraction_compact/2025-10-12.txt` |
| 19 | 2025-10-13 | `v2/data/extraction_compact/2025-10-13.txt` |
| 20 | 2025-10-14 | `v2/data/extraction_compact/2025-10-14.txt` |
| 21 | 2025-10-15 | `v2/data/extraction_compact/2025-10-15.txt` |
| 22 | 2025-10-16 | `v2/data/extraction_compact/2025-10-16.txt` |
| 23 | 2025-10-17 | `v2/data/extraction_compact/2025-10-17.txt` |
| 24 | 2025-10-18 | `v2/data/extraction_compact/2025-10-18.txt` |
| 25 | 2025-10-19 | `v2/data/extraction_compact/2025-10-19.txt` |
| 26 | 2025-10-20 | `v2/data/extraction_compact/2025-10-20.txt` |
| 27 | 2025-10-21 | `v2/data/extraction_compact/2025-10-21.txt` |
| 28 | 2025-10-22 | `v2/data/extraction_compact/2025-10-22.txt` |

---

## FINAL CHECKLIST BEFORE SUBMITTING EACH FILE

Before writing each output file, verify:

- [ ] All `question_timestamp` values in this file start with the file's date (no next-day questions)
- [ ] No discussion entry has a timestamp earlier than its question's `question_timestamp`
- [ ] Every `attempt` entry has `is_correct: true` or `false` — never `null`
- [ ] Every non-`attempt` entry has `is_correct: null`
- [ ] `answer_timestamp` equals the `timestamp` of `answer_solver`'s `is_correct: true` entry — or `null` if `answer_solver` is `null`
- [ ] `answer_confirmed: true` only if the **asker** sent an explicit text confirmation
- [ ] `confirmation_text` is set iff `answer_confirmed: true`
- [ ] `extraction_confidence: "high"` if and only if `answer_confirmed: true` (high↔confirmed; medium/low↔not confirmed)
- [ ] `has_media: true` → `[image: ...]` tag present in `question_text`
- [ ] No `↵` artifacts in any text field
- [ ] No `<This message was edited>` in any text field
- [ ] No `image omitted` / `GIF omitted` / `video omitted` etc. in any text field
- [ ] Discussion entries are in chronological order
- [ ] `scores_after` is `null` for all ad-hoc questions
- [ ] `session_quizmaster` is set for all session questions
