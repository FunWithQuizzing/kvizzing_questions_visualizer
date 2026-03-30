"""
normalize_tags.py — Fix existing tag data in questions.json files.

Applies:
  - Merge format variants: "badly explained plots" → "badly explained"
  - Remove pure question-format tags that describe HOW a question is asked,
    not WHAT it is about.
  - Merge near-duplicate tags: "pun"/"puns" → "puns"

Run:
    python3 normalize_tags.py [path/to/questions.json ...]

Defaults to patching both:
    v2/data/questions.json
    v2/visualizer/static/data/questions.json
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

HERE = pathlib.Path(__file__).parent

# Tags to remove entirely — they describe question format, not subject matter
FORMAT_TAGS = {
    "identify",
    "anagram",
    "wordplay",
    "connect",
    "clickbait",
    "real life",
    "naming",
    "weird",
}

# Tags to rename: old → new
RENAME_TAGS: dict[str, str] = {
    "badly explained plots": "badly explained",
    "pun": "puns",
}


def normalize(tags: list[str]) -> list[str]:
    result = []
    seen = set()
    for tag in tags:
        tag = RENAME_TAGS.get(tag, tag)
        if tag in FORMAT_TAGS:
            continue
        if tag not in seen:
            result.append(tag)
            seen.add(tag)
    return result


def patch_file(path: pathlib.Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    tag_changes: Counter[str] = Counter()

    for q in data:
        qtags = (q.get("question") or {}).get("tags")
        if not qtags:
            continue
        new_tags = normalize(qtags)
        if new_tags != qtags:
            for old in qtags:
                new = RENAME_TAGS.get(old, old)
                if new in FORMAT_TAGS or old in FORMAT_TAGS:
                    tag_changes[f"remove:{old}"] += 1
                elif old != new:
                    tag_changes[f"rename:{old}→{new}"] += 1
            q["question"]["tags"] = new_tags
            changed += 1

    if changed:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{path.name}: patched {changed} questions")
        for change, count in sorted(tag_changes.items(), key=lambda x: -x[1]):
            print(f"  {count:4d}  {change}")
    else:
        print(f"{path.name}: nothing to change")


def main() -> None:
    if len(sys.argv) > 1:
        paths = [pathlib.Path(p) for p in sys.argv[1:]]
    else:
        root = HERE.parent
        paths = [
            root / "data" / "questions.json",
            root / "visualizer" / "static" / "data" / "questions.json",
        ]

    for path in paths:
        if not path.exists():
            print(f"SKIP (not found): {path}")
            continue
        patch_file(path)


if __name__ == "__main__":
    main()
