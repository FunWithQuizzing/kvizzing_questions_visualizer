#!/usr/bin/env python3
"""
run_extraction.py — LLM-powered Q&A extraction for KVizzing compact chat files.

Usage (from repo root KVizzing/):
    python3 v2/pipeline/run_extraction.py [--provider groq|claude|gemini] [--dates DATE [DATE ...]] [--force]

Providers:
    gemini  gemini-2.0-flash          (needs GEMINI_API_KEY;    free tier, recommended)
    claude  claude-haiku-4-5          (needs ANTHROPIC_API_KEY; ~$1 for all 28 dates)
    groq    llama-3.3-70b-versatile   (needs GROQ_API_KEY;      free tier has low token limits)

Default provider: gemini

Reads:  v2/data/extraction_compact/YYYY-MM-DD.txt
Writes: v2/data/extraction_output/YYYY-MM-DD.json
Audits: v2/pipeline/utils/audit_extraction.py after each date

Skips dates that already have an output file unless --force is passed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent  # KVizzing/
COMPACT_DIR = REPO_ROOT / "v2" / "data" / "extraction_compact"
OUTPUT_DIR = REPO_ROOT / "v2" / "data" / "extraction_output"
AUDIT_SCRIPT = REPO_ROOT / "v2" / "pipeline" / "utils" / "audit_extraction.py"

ALL_DATES = [
    "2025-09-25", "2025-09-26", "2025-09-27", "2025-09-28",
    "2025-09-29", "2025-09-30", "2025-10-01", "2025-10-02",
    "2025-10-03", "2025-10-04", "2025-10-05", "2025-10-06",
    "2025-10-07", "2025-10-08", "2025-10-09", "2025-10-10",
    "2025-10-11", "2025-10-12", "2025-10-13", "2025-10-14",
    "2025-10-15", "2025-10-16", "2025-10-17", "2025-10-18",
    "2025-10-19", "2025-10-20", "2025-10-21", "2025-10-22",
]

# ── Provider config ─────────────────────────────────────────────────────────────

PROVIDERS = {
    "gemini": {
        "model":       "gemini-2.0-flash",
        "env_key":     "GEMINI_API_KEY",
        "max_tokens":  8192,
        "delay":       1.0,   # seconds between calls (free tier: 15 RPM)
    },
    "claude": {
        "model":          "claude-haiku-4-5-20251001",
        "fallback_model": "claude-sonnet-4-6",  # used if Haiku truncates; chunking used if Sonnet also truncates
        "env_key":        "ANTHROPIC_API_KEY",
        "max_tokens":     8192,
        "delay":          1.0,
    },
    "groq": {
        "model":       "llama-3.3-70b-versatile",
        "env_key":     "GROQ_API_KEY",
        "max_tokens":  32768,
        "delay":       2.5,   # seconds between calls
    },
}

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are extracting Q&A pairs from the KVizzing WhatsApp trivia group.

You will receive a DATE and a full compact chat file for that day. Your task is to extract all genuine trivia Q&A pairs where question_timestamp starts with that DATE. Messages timestamped the following day are lookahead context only — do not extract them.

---

## INPUT FORMAT

Each line: [ISO8601-UTC-timestamp] username: message text

Multi-line messages are joined with ` ↵ ` (space-arrow-space).

Media markers appear inline: `image omitted`, `GIF omitted`, `video omitted`, `audio omitted`, `document omitted`

`<This message was edited>` (preceded by invisible U+200E) may appear at end of messages.

---

## WHAT TO EXTRACT

Include: direct trivia questions, session questions (numbered sequences), questions never answered or revealed by asker.

Exclude: general chat/memes, questions with zero replies, duplicate posts, questions whose timestamp does NOT start with the given DATE.

---

## OUTPUT SCHEMA

Return a JSON array. Each element is a flat object with EXACTLY these fields:

{
  "question_timestamp": "ISO8601Z string — copy verbatim from file",
  "question_text": "full text after cleaning; if has_media, append [image: brief description]",
  "question_asker": "username exactly as in chat, no leading ~",
  "has_media": true if question message had image/GIF/video/audio/document omitted,
  "is_session_question": true if part of a numbered quizmaster session,
  "session_quizmaster": "username or null",
  "session_theme": "announced theme string or null",
  "session_question_number": integer (quizmaster's label) or null,
  "answer_text": "clean enriched answer string, or null if never revealed",
  "answer_solver": "username of first correct solver, or null",
  "answer_timestamp": "timestamp of answer_solver's is_correct=true attempt, or null",
  "answer_confirmed": true/false,
  "confirmation_text": "exact asker confirmation text, or null",
  "answer_is_collaborative": true if different people solved different parts,
  "answer_parts": null or [{"label": "X", "text": "answer", "solver": "username or null"}],
  "discussion": [ {
    "timestamp": "ISO8601Z",
    "username": "string",
    "text": "string",
    "role": "attempt|hint|confirmation|chat|answer_reveal",
    "is_correct": true/false/null
  } ],
  "scores_after": null or [{"username": "string", "score": integer}],
  "extraction_confidence": "high|medium|low"
}

---

## FIELD-BY-FIELD RULES

### question_text
After cleaning, append [image: brief description inferred from discussion] if has_media=true. If nothing can be inferred, write [image: unknown].

### is_session_question / session detection
A session has: (1) quizmaster announcement, (2) explicitly numbered questions, (3) quizmaster confirming each answer. Mark is_session_question=true for all questions in such a session.

### answer_text
Enrich the solver's winning attempt with context from the asker's confirmation or reveal. Do not copy verbatim if sloppy or hedged. If never answered and never revealed, set null.

### answer_confirmed
true ONLY if the asker sent an explicit text confirmation. Explicit confirms include:
  "correct", "yes", "bingo", "right", "yep", "yess", "yup", "exactly", "indeed", "spot on", "perfect", "well done", "✅", "👍", "💯", or any message containing "!"

Do NOT set true if:
- The asker only reacted with an emoji reaction (not a text message)
- The asker elaborated but never said "correct" or equivalent
- Someone other than the asker confirmed
- The asker expressed amazement without confirming ("wow", "amazing", "awesome crack")

### confirmation_text
Exact text of asker's confirmation. null if answer_confirmed=false.

### answer_timestamp
The timestamp of answer_solver's is_correct=true entry in discussion. NOT the asker's confirmation timestamp. null if answer_solver is null.

### answer_parts
Use for any multi-part question (X/Y/Z, identify A and B, etc.), regardless of how many people solved it.
If answer_parts is present, answer_text must NOT be null — always provide a combined answer string.
If answer_parts entries have more than one distinct solver, answer_is_collaborative must be true.

### discussion roles
- attempt: participant's answer try — is_correct must be true or false (NEVER null)
- hint: asker provides a clue (even if it starts with "nope, but...")
- confirmation: asker's direct yes/no with no new information
- chat: banter, reactions, off-topic
- answer_reveal: asker reveals the answer after a confirm or when no one got it
- All non-attempt roles: is_correct must be null (NEVER true or false)

Discussion entries must be in chronological order (ascending by timestamp).
No discussion entry may have a timestamp earlier than question_timestamp.
answer_solver must appear as a username in the discussion array.

### is_correct logic
- true: this attempt directly led to the asker's explicit confirmation
- false: wrong, or close but NOT the confirmed answer
- If asker says "almost", "close", "nearly" → that attempt is false
- If no explicit confirmation but asker revealed same answer → that attempt may be true

### scores_after
null unless quizmaster explicitly lists per-player running totals right after this question. Point-value labels ("10 points!", "20 points!") are difficulty labels, NOT scores → null.

### extraction_confidence
- "high": answer_confirmed=true (asker gave explicit text confirmation)
- "medium": no explicit confirmation, but strong contextual signal (reveal, continued without dispute, factually obvious)
- "low": no confirmation, weak or ambiguous signal
NOTE: extraction_confidence="high" if and only if answer_confirmed=true. Never "high" without confirmation.

### Text cleaning (applies to ALL text fields)
- Replace ` ↵ ` with a space
- Remove <This message was edited> and the U+200E character preceding it
- Do NOT include media marker text ("image omitted" etc.) in any text field
- Strip stray U+200E characters

---

## SESSION CONTEXT FOR THIS DATE RANGE

**Aditi Bapat's session (2025-09-28, overflow into 2025-09-29):**
- Announces quiz at 14:57:52Z on Sep 28
- Questions numbered implicitly ("Starting with a breezy one." = Q1, "Number 2." = Q2, etc.)
- Skips Q16 (jumps from Q15 to Q17) — use her numbering as-is
- Does NOT announce per-player scores → scores_after = null
- Many questions are image-only → has_media=true, [image: ...] in question_text

**Abhishek S's session (2025-09-29):**
- Assigns point values per question ("10 points!", "20 points!", "50 points!")
- These are difficulty labels, NOT per-player scores → scores_after = null

**For October sessions:** identify by quizmaster announcement + numbered questions pattern.

---

## SELF-CHECK BEFORE OUTPUT

1. Does answer_text actually answer question_text? Verify from your knowledge.
2. Is answer_solver the FIRST person to give the confirmed-correct answer?
3. Does answer_timestamp match the timestamp of answer_solver's is_correct=true entry?
4. Does every attempt entry have is_correct: true or false (never null)?
5. Does every non-attempt entry have is_correct: null?
6. Is answer_confirmed=true only when the ASKER gave explicit text confirmation?
7. Is extraction_confidence="high" if and only if answer_confirmed=true?
8. Are there any ↵ artifacts, media markers, or edit artifacts in text fields?
9. Are discussion entries in chronological order with no entry before question_timestamp?
10. Does answer_solver appear in the discussion array?
11. If answer_parts is present, is answer_text non-null?
12. If answer_parts has multiple distinct solvers, is answer_is_collaborative=true?

---

Return ONLY a valid JSON array. No markdown fences, no explanation, no preamble.
If no Q&A pairs found for this date, return: []
"""


# ── LLM calls ──────────────────────────────────────────────────────────────────

def _user_message(date: str, file_content: str) -> str:
    return (
        f"DATE: {date}\n\n"
        f"Extract all Q&A pairs where question_timestamp starts with {date}.\n\n"
        f"=== COMPACT CHAT FILE ===\n{file_content}"
    )


def call_gemini(date: str, file_content: str, cfg: dict) -> str:
    from openai import OpenAI
    api_key = os.environ.get(cfg["env_key"])
    if not api_key:
        raise RuntimeError(f"{cfg['env_key']} environment variable not set.")
    client = OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    response = client.chat.completions.create(
        model=cfg["model"],
        max_tokens=cfg["max_tokens"],
        temperature=0.0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": _user_message(date, file_content)},
        ],
    )
    return response.choices[0].message.content


def _claude_single(client, model: str, max_tokens: int, date: str, file_content: str) -> tuple[str, str]:
    """Make one Claude call. Returns (text, stop_reason)."""
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_message(date, file_content)}],
        temperature=0.0,
    )
    return response.content[0].text, response.stop_reason


def _claude_chunked(client, model: str, max_tokens: int, date: str, file_content: str) -> str:
    """Split file into 2 overlapping halves, extract each, merge by question_timestamp."""
    lines = file_content.splitlines()
    mid = len(lines) // 2
    overlap = 100  # lines of lookahead context for first chunk

    chunk1 = "\n".join(lines[:mid + overlap])
    chunk2 = "\n".join(lines[mid:])

    print(f"\n    ↳ chunking into 2 halves ({len(lines[:mid + overlap])} / {len(lines[mid:])} lines)…", end=" ", flush=True)

    text1, _ = _claude_single(client, model, max_tokens, date, chunk1)
    time.sleep(1.0)
    text2, _ = _claude_single(client, model, max_tokens, date, chunk2)

    # Merge: parse both, deduplicate by question_timestamp (keep entry with more discussion)
    try:
        pairs1 = json.loads(text1.strip()) if text1.strip() else []
        pairs2 = json.loads(text2.strip()) if text2.strip() else []
    except json.JSONDecodeError:
        # Return whichever chunk parsed successfully
        try:
            return text1
        except Exception:
            return text2

    seen: dict[str, dict] = {}
    for p in pairs1 + pairs2:
        key = p.get("question_timestamp", "")
        if key not in seen or len(p.get("discussion", [])) > len(seen[key].get("discussion", [])):
            seen[key] = p

    return json.dumps(list(seen.values()), ensure_ascii=False)


def call_claude(date: str, file_content: str, cfg: dict) -> str:
    import anthropic
    api_key = os.environ.get(cfg["env_key"])
    if not api_key:
        raise RuntimeError(f"{cfg['env_key']} environment variable not set.")
    client = anthropic.Anthropic(api_key=api_key)

    primary_model   = cfg["model"]
    fallback_model  = cfg.get("fallback_model", primary_model)
    max_tokens      = cfg["max_tokens"]

    # 1. Try primary model
    text, stop_reason = _claude_single(client, primary_model, max_tokens, date, file_content)
    if stop_reason != "max_tokens":
        return text

    # 2. Try fallback model
    print(f"\n    ↳ truncated — retrying with {fallback_model}…", end=" ", flush=True)
    text, stop_reason = _claude_single(client, fallback_model, max_tokens, date, file_content)
    if stop_reason != "max_tokens":
        return text

    # 3. Chunk the file and extract in two halves
    return _claude_chunked(client, fallback_model, max_tokens, date, file_content)


def call_groq(date: str, file_content: str, cfg: dict) -> str:
    from groq import Groq
    api_key = os.environ.get(cfg["env_key"])
    if not api_key:
        raise RuntimeError(f"{cfg['env_key']} environment variable not set.")
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=cfg["model"],
        max_tokens=cfg["max_tokens"],
        temperature=0.0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": _user_message(date, file_content)},
        ],
    )
    return response.choices[0].message.content


CALL_FN = {
    "gemini": call_gemini,
    "claude": call_claude,
    "groq":   call_groq,
}


# ── JSON parsing ───────────────────────────────────────────────────────────────

def parse_json(text: str) -> list:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


# ── Audit ──────────────────────────────────────────────────────────────────────

def run_audit(output_path: Path) -> list[str]:
    result = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), str(output_path)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    issues = [
        l for l in result.stdout.splitlines()
        if l.strip().startswith((
            "CONFIRM", "TIMESTAMP", "SOLVER", "ATTEMPT", "WRONG",
            "ARTIFACT", "MEDIA", "NO_IMG", "DISC", "SCORES",
            "SESSION", "PARTS", "HIGH", "MEDIUM",
        ))
    ]
    return issues


# ── Per-date processing ────────────────────────────────────────────────────────

def process_date(date: str, provider: str, cfg: dict, force: bool = False) -> dict:
    compact_path = COMPACT_DIR / f"{date}.txt"
    output_path = OUTPUT_DIR / f"{date}.json"

    if output_path.exists() and not force:
        print(f"  [{date}] SKIP — output already exists (use --force to re-run)")
        return {"date": date, "status": "skipped"}

    if not compact_path.exists():
        print(f"  [{date}] SKIP — compact file not found: {compact_path}")
        return {"date": date, "status": "missing_input"}

    print(f"  [{date}] Reading compact file…", end=" ", flush=True)
    file_content = compact_path.read_text(encoding="utf-8")
    print(f"{len(file_content.splitlines())} lines")

    print(f"  [{date}] Calling {provider} ({cfg['model']})…", end=" ", flush=True)
    try:
        raw = CALL_FN[provider](date, file_content, cfg)
    except Exception as e:
        print(f"ERROR: {e}")
        return {"date": date, "status": "llm_error", "error": str(e)}

    print("done")

    try:
        pairs = parse_json(raw)
    except json.JSONDecodeError as e:
        print(f"  [{date}] JSON parse error: {e}")
        error_path = OUTPUT_DIR / f"{date}.error.txt"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        error_path.write_text(raw, encoding="utf-8")
        print(f"  [{date}] Raw response saved to {error_path.name}")
        return {"date": date, "status": "json_error", "error": str(e)}

    if not isinstance(pairs, list):
        print(f"  [{date}] Unexpected response type: {type(pairs)}")
        return {"date": date, "status": "bad_response"}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(pairs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  [{date}] Wrote {len(pairs)} Q&A pairs → {output_path.name}")

    issues = run_audit(output_path)
    if issues:
        print(f"  [{date}] ⚠  {len(issues)} audit issue(s):")
        for issue in issues:
            print(f"        {issue}")
        return {"date": date, "status": "audit_issues", "pairs": len(pairs), "issues": issues}
    else:
        print(f"  [{date}] ✓  Audit clean")
        return {"date": date, "status": "ok", "pairs": len(pairs)}


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-powered KVizzing Q&A extraction")
    parser.add_argument(
        "--provider", choices=["gemini", "claude", "groq"], default="gemini",
        help="LLM provider to use (default: gemini).",
    )
    parser.add_argument(
        "--dates", nargs="+", metavar="DATE",
        help="Specific dates to process (YYYY-MM-DD). Default: all 28 dates.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-run dates that already have output files.",
    )
    args = parser.parse_args()

    cfg = PROVIDERS[args.provider]

    if not os.environ.get(cfg["env_key"]):
        print(f"ERROR: {cfg['env_key']} is not set.")
        print(f"  Run: export {cfg['env_key']}=...")
        sys.exit(1)

    dates = args.dates if args.dates else ALL_DATES

    print(f"KVizzing extraction — {len(dates)} date(s) — {args.provider} / {cfg['model']}")
    print("=" * 60)

    results = []
    for i, date in enumerate(dates):
        result = process_date(date, args.provider, cfg, force=args.force)
        results.append(result)
        if i < len(dates) - 1:
            time.sleep(cfg["delay"])

    # Summary
    print("\n" + "=" * 60)
    ok      = sum(1 for r in results if r["status"] == "ok")
    issues  = sum(1 for r in results if r["status"] == "audit_issues")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors  = sum(1 for r in results if r["status"] in ("llm_error", "json_error", "bad_response"))
    total_q = sum(r.get("pairs", 0) for r in results)

    print(f"Done.  ok={ok}  audit_issues={issues}  skipped={skipped}  errors={errors}")
    print(f"Total Q&A pairs written: {total_q}")

    if issues:
        print("\nDates with audit issues (review manually):")
        for r in results:
            if r["status"] == "audit_issues":
                print(f"  {r['date']} — {len(r['issues'])} issue(s)")

    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
