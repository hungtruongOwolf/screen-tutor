"""Loads a local .env file into the process environment (git-ignored)."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env_file(path: Path | None = None) -> None:
    """Set variables from KEY=VALUE lines. Existing environment values win."""
    target = path or ROOT / ".env"
    if not target.exists():
        return
    for line in target.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not match:
            continue
        key, value = match.groups()
        value = re.sub(r"^(['\"])(.*)\1$", r"\2", value)
        os.environ.setdefault(key, value)
