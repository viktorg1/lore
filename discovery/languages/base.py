"""A Language: which files it owns, how its style is checked, and its vanilla markers."""
from __future__ import annotations

from dataclasses import dataclass

from core.models import Scope

from ..markers import Marker


@dataclass(frozen=True)
class Language:
    name: str                          # must equal mapper.LANGS[ext]
    extensions: tuple[str, ...]        # without dots
    markers: tuple[Marker, ...] = ()   # framework-independent conventions
    formatter_enforced: bool = False   # gofmt/rustfmt/... decide layout: skip indent & line length
    check_quotes: bool = False         # single vs double quote statistics make sense
    check_semicolons: bool = False     # semicolon statistics make sense

    @property
    def glob(self) -> str:
        e = sorted(self.extensions)
        return "**/*." + (e[0] if len(e) == 1 else "{" + ",".join(e) + "}")

    def scope(self) -> Scope:
        return Scope.for_globs(self.glob)
