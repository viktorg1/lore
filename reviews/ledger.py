"""Remembers which review comments were already proposed, so rejecting a proposal keeps it rejected."""
from __future__ import annotations

from core import store
from core.projects import Project

VERSION = 1


class Ledger:
    def __init__(self, project: Project):
        self._path = project.dir / "review-ledger.json"

    def seen(self) -> set[str]:
        return set(store.load_json(self._path, {"seen": []}).get("seen", []))

    def add(self, urls: list[str]) -> None:
        merged = sorted(self.seen() | set(urls))
        store.save_json(self._path, {"version": VERSION, "seen": merged})
