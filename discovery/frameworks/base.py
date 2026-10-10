"""A Framework: how to tell a codebase uses it, and the conventions to look for if it does."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..codebase import Codebase
from ..markers import Marker


@dataclass(frozen=True)
class Framework:
    name: str
    languages: tuple[str, ...]            # languages whose files the signatures are searched in
    deps: tuple[str, ...] = ()            # dependency names (lowercase) from any manifest
    signatures: tuple[str, ...] = ()      # regexes found in source, for frameworks without a manifest entry
    signature_files: int = 3              # how many files must match a signature
    markers: tuple[Marker, ...] = ()

    def detect(self, codebase: Codebase) -> str | None:
        """Return the evidence that the codebase uses this framework, or None."""
        for dep in self.deps:
            if dep.lower() in codebase.facts.deps:
                return f"{dep} in {codebase.facts.deps[dep.lower()]}"
        if self.signatures:
            rxs = [re.compile(s, re.M) for s in self.signatures]
            n = sum(1 for lang in self.languages for t in codebase.files_of(lang).values()
                    if any(rx.search(t) for rx in rxs))
            if n >= self.signature_files:
                return f"source signature in {n} files"
        return None
