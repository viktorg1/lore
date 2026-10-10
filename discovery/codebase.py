"""The codebase a detector inspects: its files, source texts and manifest facts, computed lazily and once."""
from __future__ import annotations

import os
from functools import cached_property
from pathlib import Path

from core.globs import glob_regexes
from core.mapper import LANGS, list_files

from . import ecosystems, scanner
from .models import Thresholds


class Codebase:
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
        rx = glob_regexes(glob)
        return {r: t for r, t in self.sources.items()
                if any(g.match(r) for g in rx) and not (exclude_tests and scanner.TEST_RX.search(r))}

    def files_of(self, language: str) -> dict[str, str]:
        return {r: t for r, t in self.sources.items() if self.language_of(r) == language}
