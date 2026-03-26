"""
KVizzing Question Schema
========================
Single source of truth for the KVizzing question data model.

Run directly to regenerate schema.json and inject content into README.md:
    python3 schema.py
"""

from __future__ import annotations

import json
import pathlib
import re
from datetime import date as Date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

HERE = pathlib.Path(__file__).parent


# ── Enumerations ──────────────────────────────────────────────────────────────

class QuestionType(str, Enum):
    factual      = "factual"       # recall a fact
    connect      = "connect"       # find common link between a list
    identify     = "identify"      # name the person/thing/place
    fill_in_blank = "fill_in_blank" # FITB style
    multi_part   = "multi_part"    # multiple sub-answers (X/Y/Z style)
    unknown      = "unknown"       # could not be classified


class TopicCategory(str, Enum):
    history       = "history"
    science       = "science"
    literature    = "literature"
    technology    = "technology"
    sports        = "sports"
    geography     = "geography"
    entertainment = "entertainment"
    food_drink    = "food_drink"
    art_culture   = "art_culture"
    business      = "business"
    general       = "general"


class Difficulty(str, Enum):
    easy   = "easy"    # 0 wrong attempts
    medium = "medium"  # 1–3 wrong attempts
    hard   = "hard"    # 4+ wrong attempts


class ExtractionConfidence(str, Enum):
    high   = "high"    # asker gave explicit text confirmation
    medium = "medium"  # strong contextual signal
    low    = "low"     # no confirmation found; question validity uncertain


class DiscussionRole(str, Enum):
    attempt       = "attempt"       # participant answer try
    hint          = "hint"          # asker nudge
    confirmation  = "confirmation"  # asker confirms correct answer
    chat          = "chat"          # non-answer banter in thread
    answer_reveal = "answer_reveal" # asker reveals answer without anyone getting it


# ── Sub-models ────────────────────────────────────────────────────────────────

class Question(BaseModel):
    timestamp: datetime = Field(
        description="ISO 8601 timestamp of the question message"
    )
    text: str = Field(
        description="Full question text, cleaned of WhatsApp artifacts"
    )
    asker: str = Field(
        description="Username of the question poser (normalised, without leading ~)"
    )
    type: QuestionType = Field(
        description=(
            "Question format type — describes the thinking required, independent of medium. "
            "Use has_media=True for image/video questions; they can be any type."
        )
    )
    has_media: bool = Field(
        description="True if the question message included an image/video "
                    "(detected via 'image omitted' / 'video omitted')"
    )
    topic: Optional[TopicCategory] = Field(
        default=None,
        description="Topic category. Null if not yet classified. Best assigned via LLM."
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags for fine-grained categorisation "
                    "(e.g. ['India', 'architecture', 'colonial'])"
    )


class AnswerPart(BaseModel):
    label: str = Field(
        description="Part identifier (e.g. 'X', 'Y', 'Z', or '1', '2', '3')"
    )
    text: str = Field(
        description="The answer for this part"
    )
    solver: Optional[str] = Field(
        default=None,
        description="Who solved this specific part"
    )


class Answer(BaseModel):
    text: Optional[str] = Field(
        default=None,
        description="The correct answer text. Null if answer was never confirmed or revealed."
    )
    solver: Optional[str] = Field(
        default=None,
        description="Username of the first person to give the correct answer. "
                    "Null if asker revealed without anyone getting it."
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the winning answer message. "
                    "For collaborative/answer_reveal cases this is the confirmation message timestamp. "
                    "Null if unanswered."
    )
    confirmed: bool = Field(
        description="Whether the asker explicitly confirmed the answer"
    )
    confirmation_text: Optional[str] = Field(
        default=None,
        description="The exact message the asker used to confirm (e.g. 'correct', 'Bingo', 'Yes!')"
    )
    is_collaborative: bool = Field(
        description="True when multiple participants together produced the full answer"
    )
    parts: Optional[list[AnswerPart]] = Field(
        default=None,
        description="For multi-part questions (X/Y/Z style). Null for single-answer questions."
    )


class DiscussionEntry(BaseModel):
    timestamp: datetime
    username: str
    text: str
    role: DiscussionRole
    is_correct: Optional[bool] = Field(
        default=None,
        description="True if this attempt was the winning answer. Null for non-attempt roles."
    )


class Stats(BaseModel):
    wrong_attempts: int = Field(
        ge=0,
        description="Number of incorrect attempts before the correct answer"
    )
    hints_given: int = Field(
        ge=0,
        description="Number of hints/nudges the asker gave"
    )
    time_to_answer_seconds: Optional[int] = Field(
        default=None,
        ge=0,
        description="Seconds from question timestamp to first correct answer. Null if unanswered."
    )
    unique_participants: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of distinct users who attempted an answer"
    )
    difficulty: Optional[Difficulty] = Field(
        default=None,
        description="Heuristic: easy=0 wrong attempts; medium=1–3; hard=4+. Or LLM-assigned."
    )


class Session(BaseModel):
    id: str = Field(
        description="Session identifier (e.g. date + quizmaster slug: '2026-03-16-pratik')"
    )
    quizmaster: str = Field(
        description="Username of the session host"
    )
    question_number: int = Field(
        ge=1,
        description="Position of this question within the session (1-based)"
    )
    theme: Optional[str] = Field(
        default=None,
        description="Session theme if announced (e.g. 'Hollywood Movies', 'Bollywood')"
    )


class Reaction(BaseModel):
    message_timestamp: datetime = Field(
        description="Timestamp of the reacted-to message. "
                    "FK into question.timestamp (question itself) or discussion[].timestamp."
    )
    username: str = Field(description="Who reacted")
    emoji: str = Field(description="The reaction emoji (e.g. '✅', '👍', '❤️', '😂')")
    reaction_timestamp: datetime = Field(description="When the reaction was placed")


class Highlights(BaseModel):
    reaction_counts: dict[str, int] = Field(
        description="Total count per emoji across all thread messages. "
                    "Keys are emoji characters, values are counts. Open-ended map."
    )
    total_reactions: int = Field(
        ge=0,
        description="Sum of all reaction_counts values. Useful for sorting by engagement."
    )
    categories: list[str] = Field(
        description="Derived category labels from a configurable emoji→category mapping "
                    "(e.g. '😂'→'funny', '❤️'→'crowd_favourite'). "
                    "New categories are added by updating the pipeline config, not this schema."
    )

    @field_validator("reaction_counts")
    @classmethod
    def counts_must_be_positive(cls, v: dict[str, int]) -> dict[str, int]:
        for emoji, count in v.items():
            if count < 1:
                raise ValueError(
                    f"reaction_counts['{emoji}'] must be >= 1, got {count}"
                )
        return v


class Source(BaseModel):
    file: str = Field(
        description="Source daily chat file (e.g. 'chat_2025-09-23.txt')"
    )
    pair_index: int = Field(
        ge=1,
        description="Pair number within the source file (1-based)"
    )


# ── Root model ────────────────────────────────────────────────────────────────

class KVizzingQuestion(BaseModel):
    """A single extracted Q&A pair from the KVizzing WhatsApp group."""

    id: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}-\d+$",
        description="Unique identifier. Format: YYYY-MM-DD-NNN (e.g. '2025-09-23-001')",
        examples=["2025-09-23-001"],
    )
    date: Date = Field(description="Date the question was posted (YYYY-MM-DD)")
    question: Question
    answer: Answer
    discussion: list[DiscussionEntry] = Field(
        description="Ordered list of all relevant messages in the Q&A thread"
    )
    stats: Stats
    extraction_confidence: ExtractionConfidence = Field(
        description="Confidence that this is a genuine Q&A pair with a known answer"
    )
    source: Source
    session: Optional[Session] = Field(
        default=None,
        description="Null for ad-hoc questions; populated for QM-hosted quiz sessions"
    )
    reactions: Optional[list[Reaction]] = Field(
        default=None,
        description="Optional enrichment from WhatsApp SQLite DB "
                    "(iOS: ChatStorage.sqlite; Android: msgstore.db). Null when unavailable."
    )
    highlights: Optional[Highlights] = Field(
        default=None,
        description="Optional enrichment derived from reactions[]. Null when reactions unavailable."
    )


# ── README injection ───────────────────────────────────────────────────────────

def _inject(readme_path: pathlib.Path, marker: str, content: str) -> None:
    """Replace content between <!-- BEGIN:marker --> and <!-- END:marker --> in readme_path."""
    text = readme_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(<!-- BEGIN:{re.escape(marker)} -->).*?(<!-- END:{re.escape(marker)} -->)",
        re.DOTALL,
    )
    replacement = rf"\1\n{content}\n\2"
    new_text, count = pattern.subn(replacement, text)
    if count == 0:
        raise ValueError(f"Markers <!-- BEGIN:{marker} --> / <!-- END:{marker} --> not found in {readme_path}")
    readme_path.write_text(new_text, encoding="utf-8")


# ── Schema export ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 1. Generate schema.json
    schema = KVizzingQuestion.model_json_schema()
    schema_path = HERE / "schema.json"
    schema_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False))
    print(f"Written: {schema_path}")

    # 2. Load examples.json
    examples_path = HERE / "examples.json"
    examples = json.loads(examples_path.read_text(encoding="utf-8"))

    # 3. Inject into README.md
    readme_path = HERE / "README.md"

    # Inject schema.json block
    schema_block = f"```json\n{json.dumps(schema, indent=2, ensure_ascii=False)}\n```"
    _inject(readme_path, "schema.json", schema_block)

    # Inject each example individually
    titles = [
        "1. Factual question (single solver, confirmed)",
        "2. Multi-part identify question (collaborative)",
        "3. Visual question (structured quiz session)",
        "4. Connect question (collaborative solve)",
    ]
    examples_md_parts = []
    for title, example in zip(titles, examples):
        ex = {k: v for k, v in example.items() if k != "_comment"}
        examples_md_parts.append(
            f"### {title}\n\n```json\n{json.dumps(ex, indent=2, ensure_ascii=False)}\n```"
        )
    examples_block = "\n\n".join(examples_md_parts)
    _inject(readme_path, "examples.json", examples_block)

    print(f"Injected into: {readme_path}")
