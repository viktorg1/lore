"""Shared value objects: thresholds, candidates, and the Project a detector inspects."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import ecosystems
import rules
from mapper import LANGS, list_files
from . import scanner


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
    scope: dict
    evidence: str
    kind: str  # config | stats | marker | framework

    def __getitem__(self, key: str):  # dict-style access for CLI/tests
        return getattr(self, key)


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({round(100 * a / b)}%)"


class Project:
    """Everything detectors may look at, computed lazily and once."""

    def __init__(self, root: Path, thresholds: Thresholds | None = None):
        self.root = Path(root)
        self.th = thresholds or Thresholds()
        self.has_editorconfig = False  # set by EditorConfigDetector, read by the style detector

    @cached_property
    def files(self) -> list[str]:
        return list_files(self.root)

    @cached_property
    def sources(self) -> dict[str, str]:
        from .registry import code_extensions
        return scanner.read_sources(self.root, self.files, code_extensions())

    @cached_property
    def facts(self) -> ecosystems.Facts:
        return ecosystems.read_facts(self.root)

    def language_of(self, rel: str) -> str | None:
        return LANGS.get(os.path.splitext(rel)[1].lower())

    def matching(self, glob: str, exclude_tests: bool = False) -> dict[str, str]:
        """Source files whose project-relative path matches the glob."""
        rx = rules._glob_regexes(glob)
        return {r: t for r, t in self.sources.items()
                if any(g.match(r) for g in rx) and not (exclude_tests and scanner.TEST_RX.search(r))}

    def files_of(self, language: str) -> dict[str, str]:
        return {r: t for r, t in self.sources.items() if self.language_of(r) == language}
