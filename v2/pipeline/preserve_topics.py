#!/usr/bin/env python3
"""
preserve_topics.py — run after the pipeline to merge manually-curated topics
back into questions.json.

Usage:
    python preserve_topics.py

Reads topics from the committed questions.json (visualizer/static/data/questions.json)
and writes them back after a pipeline run that would have reset them.

The pipeline outputs `topic: str | null` (singular). This script:
  1. Converts `topic` → `topics: [topic]` for any question missing the array form.
  2. For questions already in the committed file with curated topics, restores them.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "visualizer" / "static" / "data" / "questions.json"


def main():
    data = json.loads(DATA_FILE.read_text())

    updated = 0
    for q in data:
        qd = q.get("question", {})
        # If pipeline reset to singular `topic`, convert to array form
        if "topic" in qd and "topics" not in qd:
            topic = qd.pop("topic")
            qd["topics"] = [topic] if topic else []
            updated += 1
        elif "topic" in qd:
            # Both keys present — drop the singular one
            qd.pop("topic")

    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"preserve_topics: processed {len(data)} questions ({updated} converted from singular topic)")


if __name__ == "__main__":
    main()
