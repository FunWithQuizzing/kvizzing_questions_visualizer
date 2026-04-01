"""
Audit an extraction output file for schema and consistency errors.

Run after writing each extraction output file:

    python3 audit_extraction.py data/extraction_output/2025-09-25.json

Exits with code 0 if clean, code 1 if issues found.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

FORMAT_TAGS = {
    "identify", "anagram", "wordplay", "connect", "clickbait",
    "real life", "naming", "weird", "pun", "battle",
    "fill in the blank", "multi-part", "factual",
}

EXPLICIT_CONFIRMS = [
    "correct", "yes", "bingo", "right", "yep", "yess", "yup",
    "✅", "👍", "💯", "perfect", "well done", "!", "exactly",
    "indeed", "spot on",
]
MEDIA_MARKERS = [
    "image omitted", "gif omitted", "video omitted",
    "audio omitted", "document omitted",
]
ARTIFACTS = ["<this message was edited>", "↵"]


def audit_data(data: list) -> list[str]:
    issues: list[str] = []

    if not data:
        return []  # empty file is valid (no Q&A that day)

    for i, q in enumerate(data):
        ts = q.get("question_timestamp", f"entry#{i}")
        label = f"[{ts[11:19] if len(ts) >= 19 else ts}]"
        disc = q.get("discussion", [])
        disc_ts = [e.get("timestamp") for e in disc]
        collab = q.get("answer_is_collaborative", False)
        solver = q.get("answer_solver")
        ans_ts = q.get("answer_timestamp")

        # 1. answer_confirmed=true but confirmation_text not explicitly positive
        if q.get("answer_confirmed") and q.get("confirmation_text"):
            ct = q["confirmation_text"].lower()
            if not any(w in ct for w in EXPLICIT_CONFIRMS):
                issues.append(f"CONFIRM_IMPLICIT    {label}: \"{q['confirmation_text']}\"")

        # 2. answer_confirmed=true but no confirmation role in discussion
        if q.get("answer_confirmed") and not any(e.get("role") == "confirmation" for e in disc):
            issues.append(f"CONFIRM_NO_ROLE     {label}")

        # 3. confirmation_text set but answer_confirmed=false
        if q.get("confirmation_text") and not q.get("answer_confirmed"):
            issues.append(f"CONFIRM_TEXT_FALSE  {label}: \"{q['confirmation_text']}\"")

        # 4. extraction_confidence=high but answer_confirmed=false
        if q.get("extraction_confidence") == "high" and not q.get("answer_confirmed"):
            issues.append(f"HIGH_NOT_CONFIRMED  {label}")

        # 5. extraction_confidence=medium but answer_confirmed=true (should be high)
        if q.get("extraction_confidence") == "medium" and q.get("answer_confirmed"):
            issues.append(f"MEDIUM_BUT_CONFIRMED {label}")

        # 6. answer_is_collaborative=false but answer_parts has multiple distinct solvers
        parts = q.get("answer_parts") or []
        if parts and not collab:
            solvers = {p["solver"] for p in parts if p.get("solver")}
            if len(solvers) > 1:
                issues.append(f"COLLAB_MISMATCH     {label}: {solvers}")

        # 7. answer_solver doesn't match first is_correct=true in discussion
        if solver and not collab:
            first_correct = next(
                (e["username"] for e in disc if e.get("is_correct") is True), None
            )
            if first_correct and first_correct != solver:
                issues.append(
                    f"SOLVER_MISMATCH     {label}: solver={solver!r} first_correct={first_correct!r}"
                )

        # 8. answer_timestamp doesn't match the winning attempt's timestamp
        if solver and ans_ts and not collab:
            winning_ts = next(
                (e["timestamp"] for e in disc
                 if e.get("is_correct") is True and e["username"] == solver),
                None,
            )
            if winning_ts and winning_ts != ans_ts:
                issues.append(
                    f"TIMESTAMP_MISMATCH  {label}: stored={ans_ts[11:19]} winning={winning_ts[11:19]}"
                )

        # 9. answer_timestamp refers to no actual discussion entry
        if ans_ts and ans_ts not in disc_ts:
            issues.append(f"TIMESTAMP_PHANTOM   {label}: {ans_ts[11:19]} not in discussion")

        # 10. attempt entries with is_correct=null
        for e in disc:
            if e.get("role") == "attempt" and e.get("is_correct") is None:
                issues.append(
                    f"ATTEMPT_NULL        {label} {e['username']}: \"{e.get('text','')[:60]}\""
                )

        # 11. non-attempt roles with non-null is_correct
        for e in disc:
            if e.get("role") != "attempt" and e.get("is_correct") is not None:
                issues.append(
                    f"WRONG_IS_CORRECT    {label} role={e['role']} {e['username']}"
                )

        # 12. ↵ or edit artifacts remaining in text fields
        for field in ["question_text", "answer_text", "confirmation_text"]:
            val = (q.get(field) or "").lower()
            for art in ARTIFACTS:
                if art in val:
                    issues.append(f"ARTIFACT            {label} {field}: {art!r}")
            for m in MEDIA_MARKERS:
                if m in val:
                    issues.append(f"MEDIA_MARKER        {label} {field}: {m!r}")
        for e in disc:
            val = (e.get("text") or "").lower()
            for art in ARTIFACTS:
                if art in val:
                    issues.append(f"ARTIFACT            {label} disc/{e['username']}: {art!r}")
            for m in MEDIA_MARKERS:
                if m in val:
                    issues.append(f"MEDIA_MARKER        {label} disc/{e['username']}: {m!r}")

        # 13. has_media=true but no [image: description] in question_text
        if q.get("has_media") and "[image" not in q.get("question_text", "").lower():
            issues.append(f"NO_IMG_DESC         {label}: \"{q.get('question_text','')[:70]}\"")

        # 14. discussion not in chronological order
        try:
            dts = [datetime.fromisoformat(e["timestamp"].rstrip("Z")) for e in disc]
            if dts != sorted(dts):
                issues.append(f"DISC_NOT_SORTED     {label}")
        except (KeyError, ValueError):
            pass

        # 15. discussion entry before the question itself
        try:
            q_dt = datetime.fromisoformat(ts.rstrip("Z"))
            for e in disc:
                e_dt = datetime.fromisoformat(e["timestamp"].rstrip("Z"))
                if e_dt < q_dt:
                    issues.append(
                        f"DISC_BEFORE_Q       {label}: {e['username']} at {e['timestamp'][11:19]}"
                    )
        except ValueError:
            pass

        # 16. scores_after populated for non-session question
        if q.get("scores_after") and not q.get("is_session_question"):
            issues.append(f"SCORES_NON_SESSION  {label}")

        # 17. is_session_question=true but session_quizmaster is null
        if q.get("is_session_question") and not q.get("session_quizmaster"):
            issues.append(f"SESSION_NO_QM       {label}")

        # 18. answer_solver not present in discussion at all
        if solver and not any(e.get("username") == solver for e in disc):
            issues.append(f"SOLVER_NOT_IN_DISC  {label}: {solver!r}")

        # 19. answer_solver has no is_correct=true entry (non-collaborative)
        if solver and not collab:
            if not any(e["username"] == solver and e.get("is_correct") is True for e in disc):
                issues.append(f"SOLVER_NO_CORRECT   {label}: {solver!r}")

        # 20. answer_parts present but answer_text is null
        if q.get("answer_parts") and not q.get("answer_text"):
            issues.append(f"PARTS_NO_TEXT       {label}")

        # 21. answer_solver set but answer_timestamp is null
        if solver and not ans_ts:
            issues.append(f"SOLVER_NO_TIMESTAMP {label}: {solver!r}")

        # 22. tags contain question-format descriptors (not subject categories)
        for tag in q.get("tags") or []:
            if tag.lower() in FORMAT_TAGS:
                issues.append(f"FORMAT_TAG          {label}: {tag!r}")

        # 23. "badly explained" variant inconsistency
        tags_lower = [t.lower() for t in (q.get("tags") or [])]
        if "badly explained plots" in tags_lower:
            issues.append(f"TAG_VARIANT         {label}: use 'badly explained' not 'badly explained plots'")

        # 24. ans_ts < question_timestamp
        q_ts = q.get("question_timestamp")
        if ans_ts and q_ts and ans_ts < q_ts:
            issues.append(f"CHRONOLOGY_ERROR    {label}: answer ({ans_ts[11:19]}) before question ({q_ts[11:19]})")

        # 25. question_asker missing
        if not q.get("question_asker"):
            issues.append(f"MISSING_ASKER       {label}: question_asker is critically missing")

        # 26. Empty discussion for answered question
        if q.get("answer_text") and not disc:
            issues.append(f"EMPTY_DISCUSSION    {label}: answered question has no discussion elements")

        # 27. Topic format must be exact
        valid_topics = {"history", "science", "literature", "technology", "sports", "geography", "entertainment", "food_drink", "art_culture", "business", "etymology", "general"}
        for t in (q.get("topics") or []):
            if t.lower() not in valid_topics:
                issues.append(f"INVALID_TOPIC       {label}: '{t}' is not a permitted schema topic value")
                
        # 28. Orphaned session fields
        if not q.get("is_session_question"):
            for f in ["session_quizmaster", "session_theme", "session_quiz_type", "session_question_number"]:
                if q.get(f):
                    issues.append(f"ORPHAN_SESSION_VAR  {label}: '{f}' is populated but is_session_question is false")

    return issues


def audit(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return [f"PARSE_ERROR: {e}"]

    if not isinstance(data, list):
        return ["NOT_A_LIST: root element must be a JSON array"]

    return audit_data(data)


def main() -> None:
    if len(sys.argv) < 2:
        # Default: audit all files in data/extraction_output/
        output_dir = Path(__file__).parent.parent / "data" / "extraction_output"
        paths = sorted(output_dir.glob("????-??-??.json"))
        if not paths:
            print("No extraction output files found.")
            sys.exit(0)
    else:
        paths = [Path(p) for p in sys.argv[1:]]

    total_issues = 0
    for path in paths:
        issues = audit(path)
        if issues:
            print(f"\n{path.name} — {len(issues)} issue(s):")
            for issue in issues:
                print(f"  {issue}")
            total_issues += len(issues)
        else:
            print(f"{path.name} — OK")

    print(f"\n{'All clear.' if total_issues == 0 else f'{total_issues} issue(s) found.'}")
    sys.exit(0 if total_issues == 0 else 1)


if __name__ == "__main__":
    main()
