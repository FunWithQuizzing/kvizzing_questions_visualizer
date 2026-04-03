"""
Stage 4 — Enrich

Assigns primary + secondary topic and tags to each KVizzingQuestion via LLM.

Questions that already have 2+ topics are skipped (idempotent).
Questions with 0 or 1 topic are (re-)enriched so both categories are populated.
Questions are sent to the LLM in batches for efficiency.

Input:  list of KVizzingQuestion objects from Stage 3
Output: list of KVizzingQuestion objects with topics + tags populated
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
import sys
import time
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "schema"))
from schema import KVizzingQuestion, TopicCategory

log = logging.getLogger("kvizzing")


def _parse_json(text: str) -> list:
    """Parse JSON from LLM output, stripping markdown fences if present."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


# ── Tag normalisation ─────────────────────────────────────────────────────────
# Tags that describe question FORMAT, not subject matter — never store these.
_FORMAT_TAGS = {
    "identify", "anagram", "wordplay", "connect", "clickbait",
    "real life", "naming", "weird", "multi-part", "factual",
    "battle", "pun", "fill in the blank",
}

# Tags to rename on ingest
_RENAME_TAGS: dict[str, str] = {
    "badly explained plots": "badly explained",
    "pun": "puns",
}


def _normalize_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for tag in tags:
        tag = _RENAME_TAGS.get(tag, tag)
        if tag in _FORMAT_TAGS:
            continue
        if tag not in seen:
            result.append(tag)
            seen.add(tag)
    return result


_ENRICH_SYSTEM_PROMPT = """\
You are classifying quiz questions from a WhatsApp trivia group.

For each question you receive, assign:
1. primary_topic — the single best-fitting topic from:
   history, science, literature, technology, sports, geography,
   entertainment, food_drink, art_culture, business, etymology, mythology, geology, general
2. secondary_topic — a second topic from the same list if the question genuinely
   spans two domains (e.g. a science question set in a historical context).
   Use null if no meaningful second category applies. Do NOT force one — most
   questions need only a primary topic.
3. tags — 2–5 lowercase subject/category tags for fine-grained categorisation
   (e.g. ["india", "colonial history", "economics"])

Tag rules — CRITICAL:
- Tags must describe the SUBJECT MATTER of the question (what it is about), never the question format or style.
- NEVER use question-format words as tags: identify, anagram, wordplay, connect, fill in the blank,
  multi-part, factual, battle, clickbait, pun, puns, weird, real life, naming, or any other
  descriptor that describes how the question is asked rather than what it is about.
- Exception: "badly explained" is an accepted subject-style tag for questions in that format.
- Tags should be specific enough to be useful (e.g. "bollywood" not just "india", "ww2" not just "war").
- Use consistent singular/plural forms and avoid near-duplicates (e.g. only "puns", not both "pun" and "puns").

You will receive a JSON array of questions. Return a JSON array of the same length,
in the same order, where each element is:
{"id": "<question id>", "primary_topic": "<topic>", "secondary_topic": "<topic> or null", "tags": ["tag1", "tag2"]}

Return ONLY a valid JSON array. No explanation, no markdown fences.
"""


def _build_batch_prompt(questions: list[KVizzingQuestion]) -> str:
    items = []
    for q in questions:
        item: dict = {
            "id": q.id,
            "question": q.question.text,
            "answer": q.answer.text,
        }
        # If primary topic already assigned (re-enrichment for secondary), include it
        if q.question.topics:
            item["primary_topic_already_assigned"] = q.question.topics[0].value
        items.append(item)
    return json.dumps(items, ensure_ascii=False)


def _call_llm(
    questions: list[KVizzingQuestion],
    config: dict,
    llm_client,
) -> list[dict]:
    """
    Call the LLM with a batch of questions and return enrichment dicts.
    Retries on rate limit with exponential backoff.
    Returns empty list on unrecoverable failure.
    """
    model: str = config["stage4"]["llm_model"]
    max_retries: int = config["stage4"]["llm_max_retries"]
    base_delay: float = config["stage4"]["llm_retry_base_delay_seconds"]

    user_prompt = _build_batch_prompt(questions)

    for attempt in range(max_retries):
        try:
            response = llm_client.messages.create(
                model=model,
                max_tokens=4096,
                system=_ENRICH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw_text = response.content[0].text
            return _parse_json(raw_text)
        except json.JSONDecodeError as e:
            log.warning(
                "Stage4 LLM returned invalid JSON (attempt %d/%d): %s\nRaw response (first 500 chars): %s",
                attempt + 1, max_retries, e, raw_text[:500] if 'raw_text' in dir() else "<no response>",
            )
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                log.warning("Stage4 retrying in %.1fs…", delay)
                time.sleep(delay)
                continue
            return []
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower() or "resource_exhausted" in err_str.lower():
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    log.warning("Stage4 rate-limited — retrying in %.1fs (attempt %d/%d)…", delay, attempt + 1, max_retries)
                    time.sleep(delay)
                    continue
            log.error("Stage4 LLM call failed: %s", e, exc_info=True)
            raise
    return []


def _apply_enrichment(
    question: KVizzingQuestion,
    enrichment: dict,
) -> KVizzingQuestion:
    """Return a copy of question with primary + optional secondary topic and tags applied."""
    primary_str = enrichment.get("primary_topic", "") or enrichment.get("topic", "")
    secondary_str = enrichment.get("secondary_topic") or ""
    tags = _normalize_tags(enrichment.get("tags", []))

    try:
        primary = TopicCategory(primary_str)
    except ValueError:
        primary = TopicCategory.general

    topics: list[TopicCategory] = [primary]
    if secondary_str:
        try:
            secondary = TopicCategory(secondary_str)
            if secondary != primary:
                topics.append(secondary)
        except ValueError:
            pass

    # Pydantic v2: model_copy(update=...) for nested field replacement
    updated_question = question.question.model_copy(
        update={"topics": topics, "tags": tags}
    )
    return question.model_copy(update={"question": updated_question})


def enrich(
    questions: list[KVizzingQuestion],
    config: dict,
    llm_client,
) -> list[KVizzingQuestion]:
    """
    Enrich a list of questions with primary + secondary topics and tags via LLM.
    Questions with 2+ topics already are skipped; questions with 0 or 1 topic are (re-)enriched.
    """
    batch_size: int = config["stage4"]["llm_batch_size"]

    # Separate questions that need enrichment from those already done.
    # Questions with fewer than 2 topics need (re-)enrichment to get a secondary topic.
    to_enrich = [q for q in questions if len(q.question.topics) < 2]
    already_done = {q.id: q for q in questions if len(q.question.topics) >= 2}

    # Build an id→result map for the enriched ones
    enriched_map: dict[str, KVizzingQuestion] = dict(already_done)

    # Process in batches
    for batch_start in range(0, len(to_enrich), batch_size):
        batch = to_enrich[batch_start : batch_start + batch_size]
        try:
            results = _call_llm(batch, config, llm_client)
        except Exception:
            log.warning("Stage4: enrichment batch failed — storing questions without topics.")
            for q in batch:
                enriched_map[q.id] = q
            continue

        # Index results by id
        results_by_id = {r["id"]: r for r in results if isinstance(r, dict) and "id" in r}

        for q in batch:
            if q.id in results_by_id:
                enriched_map[q.id] = _apply_enrichment(q, results_by_id[q.id])
            else:
                # LLM didn't return this question — keep as-is
                enriched_map[q.id] = q

    # Return in original order
    return [enriched_map[q.id] for q in questions]


def run(
    questions: list[KVizzingQuestion],
    config: dict,
    llm_client=None,
) -> list[KVizzingQuestion]:
    """
    Stage 4 entry point. If llm_client is None (test mode), returns questions unchanged.
    """
    if llm_client is None:
        return questions

    return enrich(questions, config, llm_client)
