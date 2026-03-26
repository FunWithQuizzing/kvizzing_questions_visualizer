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


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}
