"""Plain value objects of discovery: how lopsided evidence must be, and what a finding looks like."""
from __future__ import annotations

from dataclasses import dataclass

from core.models import Scope


@dataclass(frozen=True)
class Thresholds:
    min_ratio: float = 0.9      # how lopsided a convention must be
    min_files: int = 5          # minimum files of evidence
    free_ratio: float = 0.95    # share of files that must be clean for an "absent" marker
    min_occurrences: int = 15   # minimum matches for occurrence/choice markers


@dataclass
class Candidate:
    """A proposed rule plus the evidence behind it."""
    text: str
    scope: Scope
    evidence: str
    kind: str  # config | stats | marker | framework


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({round(100 * a / b)}%)"
