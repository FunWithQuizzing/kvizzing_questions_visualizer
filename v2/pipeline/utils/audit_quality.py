"""
Audit extraction quality — find potentially non-question extractions.

Scans questions in the DB for patterns that suggest the LLM extracted
something that isn't a genuine trivia question.

Usage:
    python3 pipeline.py audit-quality [--fix]
    python3 utils/audit_quality.py
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("kvizzing")

# Patterns in question text that suggest non-questions
_NON_QUESTION_PATTERNS = [
    (r"\bjust to share\b", "sharing, not asking"),
    (r"\breminded me of\b", "reminiscence, not question"),
    (r"\bnot a question\b", "explicitly not a question"),
    (r"\boff topic\b", "off-topic"),
    (r"\brandom thought\b", "random thought"),
    (r"\bcheck this out\b", "sharing link/content"),
    (r"\bputting this as a question just to\b", "explicitly not a real question"),
]

# Patterns that look suspicious but are often valid — flag for review
_REVIEW_PATTERNS = [
    (r"\bbtw\b.*\?$", "starts with BTW but ends with question mark — might be valid"),
    (r"\bfun fact\b", "fun fact preamble — often valid with a question after"),
    (r"\bcame across\b", "came across — often valid ('came across this, any guesses?')"),
    (r"\bfound this\b", "found this — often valid ('found this, ID?')"),
    (r"\bsaw this\b", "saw this — often valid ('saw this online, what is it?')"),
]

# Low quality signals
_LOW_QUALITY_CHECKS = [
    ("short_question", lambda q: len(q.get("question", {}).get("text", "")) < 20,
     "Very short question text (< 20 chars)"),
    ("no_answer_no_reveal", lambda q: (
        not q.get("answer", {}).get("text") and
        not any(e.get("role") == "answer_reveal" for e in q.get("discussion", []))
    ), "No answer and no reveal — question may be unanswerable or incomplete"),
    ("zero_discussion", lambda q: len(q.get("discussion", [])) == 0 and q.get("answer", {}).get("text"),
     "Has answer but zero discussion entries"),
]


def audit_quality(questions: list[dict]) -> dict:
    """
    Audit question quality.

    Returns:
        {
            "non_questions": [{"id", "text", "pattern", "reason"}],
            "review": [{"id", "text", "pattern", "reason"}],
            "low_quality": [{"id", "text", "check", "reason"}],
        }
    """
    non_questions = []
    review = []
    low_quality = []

    for q in questions:
        qid = q.get("id", "?")
        text = q.get("question", {}).get("text", "")
        text_lower = text.lower()

        # Check non-question patterns
        for pattern, reason in _NON_QUESTION_PATTERNS:
            if re.search(pattern, text_lower):
                non_questions.append({
                    "id": qid,
                    "text": text[:150],
                    "pattern": pattern,
                    "reason": reason,
                })
                break

        # Check review patterns
        for pattern, reason in _REVIEW_PATTERNS:
            if re.search(pattern, text_lower):
                review.append({
                    "id": qid,
                    "text": text[:150],
                    "pattern": pattern,
                    "reason": reason,
                })
                break

        # Check low quality signals
        for check_name, check_fn, reason in _LOW_QUALITY_CHECKS:
            if check_fn(q):
                low_quality.append({
                    "id": qid,
                    "text": text[:150],
                    "check": check_name,
                    "reason": reason,
                })

    return {
        "non_questions": non_questions,
        "review": review,
        "low_quality": low_quality,
    }


def print_report(results: dict) -> None:
    """Print a human-readable quality report."""
    nq = results["non_questions"]
    rv = results["review"]
    lq = results["low_quality"]

    if nq:
        print(f"\n✗ LIKELY NON-QUESTIONS ({len(nq)}):")
        for item in nq:
            print(f"  {item['id']}: \"{item['text']}\"")
            print(f"    → {item['reason']}")
    else:
        print("\n✓ No obvious non-questions found.")

    if rv:
        print(f"\n⚠ NEEDS REVIEW ({len(rv)}):")
        for item in rv:
            print(f"  {item['id']}: \"{item['text']}\"")
            print(f"    → {item['reason']}")

    if lq:
        print(f"\n⚠ LOW QUALITY ({len(lq)}):")
        for item in lq:
            print(f"  {item['id']}: \"{item['text']}\"")
            print(f"    → {item['reason']}")

    total = len(nq) + len(rv) + len(lq)
    print(f"\nTotal: {len(nq)} non-questions, {len(rv)} to review, {len(lq)} low quality")


def main() -> None:
    v2_dir = Path(__file__).resolve().parent.parent.parent
    questions_path = v2_dir / "visualizer" / "static" / "data" / "questions.json"

    if not questions_path.exists():
        print(f"questions.json not found at {questions_path}")
        return

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    print(f"Auditing {len(questions)} questions…")
    results = audit_quality(questions)
    print_report(results)


if __name__ == "__main__":
    main()
