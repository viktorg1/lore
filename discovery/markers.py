"""Pattern markers: the extension point for teaching discovery a new convention.

Add one object to a language module (languages/<lang>.py) or a framework module
(frameworks/<name>.py). Four kinds cover almost everything:

  FileMarker        "~every applicable file contains X"            (strict_types, <script setup>)
  OccurrenceMarker  "~every X occurrence is also Y"                (functions that have return types)
  AbsentMarker      "~no file contains X"                          (console.log, .unwrap())
  ChoiceMarker      "one of several styles clearly dominates"      (function vs class components)

A marker only yields a rule when the evidence is lopsided; the rule carries its numbers.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from core.models import Scope

from .codebase import Codebase
from .models import Candidate, pct

FLAGS = re.MULTILINE


@dataclass(kw_only=True)
class Marker(ABC):
    id: str
    glob: str                      # which files it looks at, e.g. "**/*.{ts,tsx}"
    rule: str = ""                 # text of the proposed rule
    exclude_tests: bool = False
    min_ratio: float | None = None       # override Thresholds.min_ratio
    min_applicable: int | None = None    # override Thresholds.min_files

    kind: str = field(default="marker", init=False)

    def scope(self) -> Scope:
        return Scope.for_globs(self.glob)

    def _candidate(self, evidence: str, rule: str | None = None) -> Candidate:
        return Candidate(rule or self.rule, self.scope(), f"{evidence} [{self.id}]", self.kind)

    def _ratio(self, codebase: Codebase) -> float:
        return self.min_ratio if self.min_ratio is not None else codebase.th.min_ratio

    @abstractmethod
    def evaluate(self, codebase: Codebase) -> list[Candidate]: ...


@dataclass(kw_only=True)
class FileMarker(Marker):
    has: str                       # regex a conforming file contains
    when: str | None = None        # regex that makes a file applicable at all

    def evaluate(self, codebase: Codebase) -> list[Candidate]:
        files = codebase.matching(self.glob, self.exclude_tests).values()
        when = re.compile(self.when, FLAGS) if self.when else None
        applicable = [t for t in files if when is None or when.search(t)]
        need = self.min_applicable or codebase.th.min_files
        if len(applicable) < need:
            return []
        has = re.compile(self.has, FLAGS)
        hit = sum(1 for t in applicable if has.search(t))
        if hit / len(applicable) < self._ratio(codebase):
            return []
        return [self._candidate(f"{pct(hit, len(applicable))} of applicable files")]


@dataclass(kw_only=True)
class OccurrenceMarker(Marker):
    total: str                     # regex matching every occurrence
    has: str                       # regex matching the conforming ones

    def evaluate(self, codebase: Codebase) -> list[Candidate]:
        files = codebase.matching(self.glob, self.exclude_tests).values()
        tot_rx, has_rx = re.compile(self.total, FLAGS), re.compile(self.has, FLAGS)
        b = sum(len(tot_rx.findall(t)) for t in files)
        a = sum(len(has_rx.findall(t)) for t in files)
        if b < (self.min_applicable or codebase.th.min_occurrences) or a / b < self._ratio(codebase):
            return []
        return [self._candidate(f"{pct(a, b)} of occurrences")]


@dataclass(kw_only=True)
class AbsentMarker(Marker):
    bad: str                       # regex nobody should use
    exclude_tests: bool = True

    def evaluate(self, codebase: Codebase) -> list[Candidate]:
        files = list(codebase.matching(self.glob, self.exclude_tests).values())
        if len(files) < (self.min_applicable or max(codebase.th.min_files, 8)):
            return []
        bad = re.compile(self.bad, FLAGS)
        clean = sum(1 for t in files if not bad.search(t))
        if clean / len(files) < codebase.th.free_ratio:
            return []
        return [self._candidate(f"{pct(clean, len(files))} of non-test files contain none")]


@dataclass(frozen=True)
class Option:
    label: str
    pattern: str
    rule: str | None = None        # None: a known style, but not worth a rule when it wins


@dataclass(kw_only=True)
class ChoiceMarker(Marker):
    options: tuple[Option, ...]

    def evaluate(self, codebase: Codebase) -> list[Candidate]:
        files = list(codebase.matching(self.glob, self.exclude_tests).values())
        counts = [(o, sum(len(re.findall(o.pattern, t, FLAGS)) for t in files)) for o in self.options]
        total = sum(c for _, c in counts)
        if total < (self.min_applicable or codebase.th.min_occurrences):
            return []
        win, c = max(counts, key=lambda oc: oc[1])
        if c / total < self._ratio(codebase) or not win.rule:
            return []
        others = ", ".join(f"{o.label} {n}" for o, n in counts if o is not win and n)
        return [self._candidate(f"{win.label}: {pct(c, total)} of occurrences" + (f" (vs {others})" if others else ""), win.rule)]


def marker_from_dict(d: dict) -> Marker:
    """Build a marker from user JSON (--markers file). `kind` is file|occ|absent|choice."""
    d = dict(d)
    kind = d.pop("kind", "file")
    if kind == "choice":
        d["options"] = tuple(Option(**o) for o in d["options"])
        return ChoiceMarker(**d)
    cls = {"file": FileMarker, "occ": OccurrenceMarker, "absent": AbsentMarker}[kind]
    return cls(**d)
