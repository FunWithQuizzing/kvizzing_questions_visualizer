"""
Generate low-opacity background images for each session using Stable Horde (free, no key needed).

Run from anywhere:
  python3 v2/pipeline/generate_session_images.py

Images saved to: v2/visualizer/static/images/sessions/{session_id}.jpg
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
import requests

V2_DIR = Path(__file__).parent.parent
SESSIONS_JSON = V2_DIR / "visualizer" / "static" / "data" / "sessions.json"
OUTPUT_DIR = V2_DIR / "visualizer" / "static" / "images" / "sessions"

API_BASE = "https://stablehorde.net/api/v2"
ANON_KEY = "0000000000"  # Free anonymous key — works but slower queue

THEME_PROMPTS: dict[str, str] = {
    "Historical Indian Flags": (
        "historical Indian flags through the ages, artistic watercolor illustration, "
        "warm earthy tones, detailed and elegant, wide banner"
    ),
    "River Capitals": (
        "scenic aerial panorama of world capitals on rivers, soft painterly illustration, "
        "blue and green tones, wide landscape banner"
    ),
    "Badly explained plots": (
        "whimsical collage of famous movie scenes depicted in confusing abstract ways, "
        "pop art style, vibrant colors, wide banner"
    ),
    "Top 10 most populated cities in India": (
        "aerial panorama of Indian megacities skyline, Mumbai Delhi Bangalore Hyderabad, "
        "golden hour light, modern architecture meets ancient temples, wide banner"
    ),
    "Prathamesh's Quiz": (
        "eclectic collage of science geography history art, planets ocean waves ancient maps, "
        "rich jewel tones teal amber indigo, painterly illustration, wide banner"
    ),
}

FALLBACK_PROMPT = (
    "colorful abstract illustration of quiz night, general knowledge trivia, "
    "warm orange tones, geometric patterns, wide banner"
)

NEGATIVE_PROMPT = "text, watermark, logo, signature, blurry, low quality"


HEADERS = {"apikey": ANON_KEY, "Content-Type": "application/json"}


def _post(path: str, payload: dict) -> dict:
    resp = requests.post(f"{API_BASE}{path}", json=payload, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _get(path: str) -> dict:
    resp = requests.get(f"{API_BASE}{path}", headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def generate(prompt: str, seed: int) -> bytes | None:
    # Submit job
    payload = {
        "prompt": f"{prompt} ### {NEGATIVE_PROMPT}",
        "params": {
            "width": 512,
            "height": 256,
            "steps": 25,
            "sampler_name": "k_euler_a",
            "seed": str(seed),
            "n": 1,
        },
        "r2": False,
        "nsfw": False,
    }
    result = _post("/generate/async", payload)
    job_id = result.get("id")
    if not job_id:
        print(f"  Failed to submit: {result}")
        return None

    print(f"  Job ID: {job_id} — waiting in queue...")

    # Poll until done
    for attempt in range(60):
        time.sleep(5)
        try:
            status = _get(f"/generate/check/{job_id}")
        except Exception as e:
            print(f"  Poll error: {e}")
            continue

        done = status.get("done", False)
        queue_pos = status.get("queue_position", "?")
        wait = status.get("wait_time", "?")

        if done:
            break
        print(f"  Queue pos: {queue_pos}, est wait: {wait}s...")
    else:
        print("  Timed out waiting for generation.")
        return None

    # Fetch result
    result = _get(f"/generate/status/{job_id}")
    generations = result.get("generations", [])
    if not generations:
        print("  No generations returned.")
        return None

    img_b64 = generations[0].get("img", "")
    if not img_b64:
        return None

    return base64.b64decode(img_b64)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sessions = json.loads(SESSIONS_JSON.read_text(encoding="utf-8"))
    print(f"Found {len(sessions)} sessions.\n")

    for i, session in enumerate(sessions):
        sid = session["id"]
        theme = session.get("theme") or f"{session['quizmaster']}'s Quiz"
        dest = OUTPUT_DIR / f"{sid}.jpg"

        if dest.exists():
            print(f"[{sid}] Already exists — skipping.")
            continue

        prompt = THEME_PROMPTS.get(theme, FALLBACK_PROMPT)
        print(f"[{sid}] Theme: {theme!r}")
        print(f"  Prompt: {prompt[:80]}...")

        img_bytes = None
        for attempt in range(3):
            if attempt > 0:
                print(f"  Retrying in 30s (attempt {attempt + 1}/3)...")
                time.sleep(30)
            try:
                img_bytes = generate(prompt, seed=i + 42 + attempt)
                if img_bytes:
                    break
            except Exception as e:
                print(f"  Error: {e}")

        if img_bytes:
            dest.write_bytes(img_bytes)
            print(f"  Saved ({len(img_bytes) // 1024} KB) → {dest.relative_to(V2_DIR)}\n")
        else:
            print(f"  Failed after retries — skipping.\n")


if __name__ == "__main__":
    main()
