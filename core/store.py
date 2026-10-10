"""Low-level storage: the data folder (~/.lore), project folder names, and atomic JSON files."""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def home() -> Path:
    """Base folder for all projects: $LORE_HOME, else ~/.lore."""
    return Path(os.environ.get("LORE_HOME") or Path.home() / ".lore")


def validate_name(name: str) -> str:
    if not NAME_RE.match(name) or name in (".", ".."):
        raise ValueError(
            f"invalid project name {name!r}: use letters, digits, '.', '_' or '-'"
        )
    return name


def project_dir(name: str) -> Path:
    return home() / validate_name(name)


def load_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
