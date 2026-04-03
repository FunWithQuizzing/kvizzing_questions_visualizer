"""Config and state helpers."""

from __future__ import annotations

import json
from pathlib import Path


def load_config(config_dir: Path) -> dict:
    path = config_dir / "pipeline_config.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_aliases(config_dir: Path) -> dict:
    path = config_dir / "username_aliases.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("aliases", {})
    return {}


def load_topics(config_dir: Path) -> tuple[set[str], str]:
    """Load topic config from topics.json.

    Returns:
        (valid_ids, topic_list_str)
        - valid_ids: set of valid topic ID strings
        - topic_list_str: comma-separated list of valid IDs for prompts
    """
    path = config_dir / "topics.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    valid_ids = {t["id"] for t in data}
    topic_list_str = ", ".join(t["id"] for t in data)
    return valid_ids, topic_list_str


def load_topic_aliases(_config_dir: Path | None = None) -> dict[str, str]:
    """Return hardcoded topic alias map (LLM typo corrections).
    These are internal pipeline logic, not user-facing config."""
    return {
        # cinema/film/tv → cinema
        "film": "cinema", "movies": "cinema", "tv": "cinema", "television": "cinema",
        # entertainment (gaming, anime, comics remain here)
        "gaming": "entertainment", "anime": "entertainment", "comics": "entertainment",
        # food
        "food": "food_drink", "drink": "food_drink", "cuisine": "food_drink",
        "cooking": "food_drink",
        # art & culture
        "culture": "art_culture", "art": "art_culture",
        # mathematics
        "math": "mathematics", "maths": "mathematics",
        # science (biology, physics, chemistry stay as science)
        "biology": "science", "physics": "science", "chemistry": "science",
        # business
        "economics": "business", "finance": "business",
        # linguistics
        "language": "linguistics",
        # geography
        "travel": "geography",
        # nature
        "wildlife": "nature", "animals": "nature", "ecology": "nature",
        # medicine
        "health": "medicine", "medical": "medicine",
        # meme
        "memes": "meme", "joke": "meme", "humor": "meme", "humour": "meme",
        # politics
        "political": "politics", "election": "politics", "government": "politics",
        "parliament": "politics", "democracy": "politics", "geopolitics": "politics",
        "diplomacy": "politics", "geopolitical": "politics",
        # military
        "defence": "military", "defense": "military", "war": "military",
    }


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}
