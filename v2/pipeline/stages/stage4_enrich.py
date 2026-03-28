"""
Stage 4 — Enrich

Assigns topic and tags to each KVizzingQuestion via LLM.

Questions that already have a topic are skipped (idempotent).
Questions are sent to the LLM in batches for efficiency.

Input:  list of KVizzingQuestion objects from Stage 3
Output: list of KVizzingQuestion objects with topic + tags populated
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


_ENRICH_SYSTEM_PROMPT = """\
You are classifying quiz questions from a WhatsApp trivia group.

For each question you receive, assign:
1. topic — one of: history, science, literature, technology, sports, geography,
   entertainment, food_drink, art_culture, business, general
2. tags — 2–5 lowercase free-form tags for fine-grained categorisation
   (e.g. ["india", "colonial history", "economics"])

You will receive a JSON array of questions. Return a JSON array of the same length,
in the same order, where each element is:
{"id": "<question id>", "topic": "<topic>", "tags": ["tag1", "tag2"]}

Return ONLY a valid JSON array. No explanation, no markdown fences.
"""


def _build_batch_prompt(questions: list[KVizzingQuestion]) -> str:
    items = [
        {
            "id": q.id,
            "question": q.question.text,
            "answer": q.answer.text,
        }
        for q in questions
    ]
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
                max_tokens=2048,
                system=_ENRICH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return _parse_json(response.content[0].text)
        except json.JSONDecodeError as e:
            log.warning("Stage4 LLM returned invalid JSON: %s", e)
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
    """Return a copy of question with topic and tags applied."""
    topic_str = enrichment.get("topic", "")
    tags = enrichment.get("tags", [])

    try:
        topic = TopicCategory(topic_str)
    except ValueError:
        topic = TopicCategory.general

    # Pydantic v2: model_copy(update=...) for nested field replacement
    updated_question = question.question.model_copy(
        update={"topic": topic, "tags": tags}
    )
    return question.model_copy(update={"question": updated_question})


def enrich(
    questions: list[KVizzingQuestion],
    config: dict,
    llm_client,
) -> list[KVizzingQuestion]:
    """
    Enrich a list of questions with topic and tags via LLM.
    Already-enriched questions (topic is not None) are skipped.
    """
    batch_size: int = config["stage4"]["llm_batch_size"]

    # Separate questions that need enrichment from those already done
    to_enrich = [q for q in questions if not q.question.topics]
    already_done = {q.id: q for q in questions if q.question.topics}

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
