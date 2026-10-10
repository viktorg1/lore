"""Small text helpers shared by rules, dedupe and ids."""
from __future__ import annotations

import difflib
import hashlib
import re

# High on purpose: a wrong merge silently loses a rule, while a missed duplicate is only clutter.
SIMILARITY = 0.92


def squash(text: str) -> str:
    """Collapse all whitespace runs to single spaces."""
    return " ".join(text.split())


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace: the form used to compare rules."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def similar(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio() >= SIMILARITY


def short_hash(text: str, length: int = 8) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:length]
