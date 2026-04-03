"""
Reclassify discussion entries: detect 'elaboration' role among 'chat' entries.

Scans extraction_output files for chat entries that appear AFTER the answer
is confirmed/revealed and asks a small LLM call whether each is elaboration
(additional context, trivia, explanation) or just banter.

Usage:
    python3 utils/reclassify_elaboration.py [--dry-run]
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

log = logging.getLogger("kvizzing")


def find_elaboration_candidates(data: list[dict]) -> list[tuple[int, int, dict, dict]]:
    """Find chat entries that might be elaboration.

    Returns list of (question_idx, disc_idx, question, disc_entry) for chat entries
    that appear after the answer is confirmed/revealed.
    """
    candidates = []
    for qi, q in enumerate(data):
        disc = q.get("discussion", [])
        if not disc:
            continue

        # Find the timestamp of the last confirmation/answer_reveal/correct attempt
        answer_resolved_idx = -1
        for di, e in enumerate(disc):
            if e.get("role") in ("confirmation", "answer_reveal"):
                answer_resolved_idx = di
            elif e.get("role") == "attempt" and e.get("is_correct") is True:
                answer_resolved_idx = di

        if answer_resolved_idx < 0:
            continue

        # Check chat entries after the answer was resolved
        asker = q.get("question_asker", "")
        for di in range(answer_resolved_idx + 1, len(disc)):
            e = disc[di]
            if e.get("role") != "chat":
                continue
            text = (e.get("text") or "").strip()
            # Skip very short messages (reactions, emojis)
            if len(text) < 15:
                continue
            candidates.append((qi, di, q, e))

    return candidates


def reclassify_with_llm(
    candidates: list[tuple[int, int, dict, dict]],
    llm_client,
    model: str,
    rate_limit_sleep: float = 13.0,
) -> list[tuple[int, int]]:
    """Ask LLM to classify each candidate as elaboration or chat.

    Returns list of (question_idx, disc_idx) that should be reclassified to elaboration.
    """
    to_reclassify: list[tuple[int, int]] = []

    # Batch candidates to reduce LLM calls — group by question
    by_question: dict[int, list[tuple[int, dict, dict]]] = {}
    for qi, di, q, e in candidates:
        by_question.setdefault(qi, []).append((di, q, e))

    for qi, entries in by_question.items():
        q = entries[0][1]
        q_text = (q.get("question_text") or "")[:200]
        answer = (q.get("answer_text") or "")[:100]
        asker = q.get("question_asker") or ""

        # Build batch prompt for all candidates in this question
        candidate_texts = []
        for di, _, e in entries:
            candidate_texts.append(f"  [{di}] {e.get('username', '?')}: \"{(e.get('text') or '')[:200]}\"")

        prompt = (
            f"Question: \"{q_text}\"\n"
            f"Answer: \"{answer}\"\n"
            f"Asker: {asker}\n\n"
            f"The following messages appeared AFTER the answer was confirmed. "
            f"For each, classify as 'elaboration' (additional context, trivia, explanation, "
            f"fun facts about the answer/topic) or 'chat' (banter, jokes, reactions, off-topic).\n\n"
            + "\n".join(candidate_texts) + "\n\n"
            f"Reply with a JSON array of objects: [{{\"idx\": N, \"role\": \"elaboration\" or \"chat\"}}]\n"
            f"Only return the JSON array, nothing else."
        )

        try:
            resp = llm_client.messages.create(
                model=model,
                max_tokens=512,
                system="You classify quiz discussion messages. Return only JSON.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (resp.content[0].text or "").strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw).strip()
            if not raw:
                continue
            results = json.loads(raw)
            for r in results:
                if r.get("role") == "elaboration":
                    to_reclassify.append((qi, r["idx"]))
        except Exception as e:
            log.warning("  Reclassify LLM call failed for Q#%d: %s", qi, e)

        time.sleep(rate_limit_sleep)

    return to_reclassify


def reclassify_without_llm(candidates: list[tuple[int, int, dict, dict]]) -> list[tuple[int, int]]:
    """Heuristic-only reclassification (no LLM). Catches obvious cases."""
    to_reclassify: list[tuple[int, int]] = []

    info_patterns = re.compile(
        r"\b("
        r"fun fact|did you know|interesting|trivia|actually|because|reason|"
        r"story behind|history of|named after|originated|derived from|"
        r"also known as|full form|stands for|abbreviation|acronym|"
        r"the answer is|answer was|it refers to|this is because|"
        r"for those who don.t know|for context|fyi|btw.*fun"
        r")\b",
        re.IGNORECASE,
    )

    for qi, di, q, e in candidates:
        text = (e.get("text") or "").strip()
        asker = q.get("question_asker", "")
        username = e.get("username", "")

        # Asker elaborating on their own question/answer is very likely elaboration
        if username == asker and len(text) > 30:
            to_reclassify.append((qi, di))
            continue

        # Pattern-based detection
        if info_patterns.search(text):
            to_reclassify.append((qi, di))

    return to_reclassify


def apply_reclassification(data: list[dict], reclassify: list[tuple[int, int]]) -> int:
    """Apply reclassification to data. Returns count of changed entries."""
    changed = 0
    for qi, di in reclassify:
        entry = data[qi]["discussion"][di]
        if entry.get("role") == "chat":
            entry["role"] = "elaboration"
            changed += 1
    return changed


def run_on_file(
    file_path: Path,
    llm_client=None,
    model: str = "",
    dry_run: bool = False,
) -> int:
    """Process one extraction file. Returns number of entries reclassified."""
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not data:
        return 0

    candidates = find_elaboration_candidates(data)
    if not candidates:
        return 0

    if llm_client and model:
        to_reclassify = reclassify_with_llm(candidates, llm_client, model)
    else:
        to_reclassify = reclassify_without_llm(candidates)

    if not to_reclassify:
        return 0

    if dry_run:
        for qi, di in to_reclassify:
            e = data[qi]["discussion"][di]
            log.info("  [%s] Q#%d disc#%d %s: \"%s\"",
                     file_path.stem, qi, di, e.get("username", "?"),
                     (e.get("text") or "")[:60])
        return len(to_reclassify)

    changed = apply_reclassification(data, to_reclassify)
    if changed:
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return changed


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Reclassify chat→elaboration in extraction files")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-llm", action="store_true", help="Use LLM for classification (default: heuristic only)")
    args = parser.parse_args()

    ext_dir = Path(__file__).parent.parent.parent / "data" / "extraction_output"
    total = 0

    llm_client = None
    model = ""
    if args.use_llm:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from clients.llm import get_client
        from utils.config import load_config
        llm_client = get_client()
        config = load_config(Path(__file__).parent.parent / "config")
        model = config.get("stage2", {}).get("llm_model", "")

    for f in sorted(ext_dir.glob("????-??-??.json")):
        count = run_on_file(f, llm_client=llm_client, model=model, dry_run=args.dry_run)
        if count:
            log.info("  %s: %d entries %s", f.stem, count,
                     "would be reclassified" if args.dry_run else "reclassified")
            total += count

    print(f"\n{total} entries {'would be' if args.dry_run else ''} reclassified to elaboration.")


if __name__ == "__main__":
    main()
