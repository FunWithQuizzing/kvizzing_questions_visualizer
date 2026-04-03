"""
Parse rejected-candidate .txt files (thread format) from data/rejected_candidates/
and write a combined JSON array to visualizer/static/data/rejected_candidates.json.

Each entry represents a thread with:
  id              – "<date>-<NNN>" (e.g. "2025-09-24-001")
  date            – "YYYY-MM-DD"
  candidates      – list of {timestamp, username, text, reason_flagged}
  context         – list of context lines (raw, with >>> marker preserved)
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def parse_file(path: Path) -> list[dict]:
    """Parse a single rejected-candidates .txt file into a list of thread dicts."""
    content = path.read_text(encoding="utf-8")
    date_str = path.stem

    entries: list[dict] = []
    blocks = re.split(r"(?=^## Thread )", content, flags=re.MULTILINE)

    for block in blocks:
        if not block.strip().startswith("## Thread"):
            continue

        # Parse candidates within the thread
        candidates: list[dict] = []
        cand_matches = re.finditer(
            r"Candidate:\s*\[(\d{2}:\d{2}:\d{2})\]\s*(.+?)\s+\[(\w+)\]\s*\n\s*Text:\s*(.+?)(?=\n\s*Candidate:|\n\s*Context:|\n\s*$)",
            block, re.DOTALL,
        )
        for m in cand_matches:
            time_str = m.group(1)
            username = m.group(2).strip()
            reason = m.group(3)
            text = m.group(4).strip()
            candidates.append({
                "timestamp": f"{date_str}T{time_str}Z",
                "username": username,
                "text": text[:500],
                "reason_flagged": reason,
            })

        # Parse context
        context: list[str] = []
        ctx_match = re.search(r"Context:\n(.*?)(?=\n---|\Z)", block, re.DOTALL)
        if ctx_match:
            for line in ctx_match.group(1).splitlines():
                stripped = line.strip()
                if stripped:
                    context.append(stripped)

        if candidates:
            idx = len(entries) + 1
            entries.append({
                "id": f"{date_str}-{idx:03d}",
                "date": date_str,
                "candidates": candidates,
                "context": context,
            })

    return entries


def export_rejected(rejected_dir: Path, output_path: Path) -> int:
    all_entries: list[dict] = []
    if not rejected_dir.exists():
        raise FileNotFoundError(f"Rejected candidates directory not found: {rejected_dir}")
    for txt_file in sorted(rejected_dir.glob("*.txt")):
        all_entries.extend(parse_file(txt_file))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(all_entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(all_entries)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Export rejected candidates to JSON")
    parser.add_argument("--rejected-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    v2_dir = Path(__file__).resolve().parent.parent.parent
    rejected_dir = args.rejected_dir or v2_dir / "data" / "rejected_candidates"
    output_path = args.output or v2_dir / "visualizer" / "static" / "data" / "rejected_candidates.json"
    count = export_rejected(rejected_dir, output_path)
    print(f"Wrote {count} thread(s) to {output_path}")


if __name__ == "__main__":
    main()
