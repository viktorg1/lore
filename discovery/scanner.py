"""Which files count as the team's own code, and how they are read."""
from __future__ import annotations

import os
import re
from pathlib import Path

from mapper import LANGS

SKIP_PARTS = {".history", "playwright-report", "test-results", "build", "dist", "storage"}
VENDORED_RX = re.compile(r"(^|/)public/(js|css|build|vendor|fonts)/|(^|/)(vendor|node_modules)/|\.min\.|\.lock$|package-lock\.json$")
TEST_RX = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs|e2e|scripts?|migrations|config|fixtures|stories)(/|$)"
    r"|\.(test|spec)\.|_test\.|Test\.(php|java|cs|kt)$|conftest\.py$"
)
MAX_BYTES = 300_000
MAX_FILES = 3000


def is_vendored(rel: str) -> bool:
    """Vendored, built or generated paths say nothing about the team's own conventions."""
    return bool(set(rel.split("/")) & SKIP_PARTS or VENDORED_RX.search(rel))


def is_minified(text: str) -> bool:
    lines = text.splitlines()
    return bool(lines) and (max(map(len, lines)) > 1000 or len(text) / len(lines) > 200)


def read_sources(root: Path, files: list[str], extensions: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in files:
        if is_vendored(rel) or os.path.splitext(rel)[1].lower() not in extensions:
            continue
        try:
            fp = root / rel
            if fp.stat().st_size > MAX_BYTES:
                continue
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if is_minified(text):
            continue
        out[rel] = text
        if len(out) >= MAX_FILES:
            break
    return out
