"""Remembers which review comments were already proposed, so rejecting a proposal keeps it rejected."""
from __future__ import annotations

from core import store
from core.projects import Project

VERSION = 1


class Ledger:
    def __init__(self, project: Project):
        self._path = project.dir / "review-ledger.json"

    def _data(self) -> dict:
        try:
            data = store.load_json(self._path, {"seen": []})
        except ValueError:                 # a damaged file costs the memory of what was proposed, not the run
            return {"seen": []}
        return data if isinstance(data, dict) else {"seen": []}

    def seen(self) -> set[str]:
        seen = self._data().get("seen")
        return {u for u in seen if isinstance(u, str)} if isinstance(seen, list) else set()

    def last_run(self) -> str:
        """When review comments were last read for this project (local time), or empty if never."""
        return str(self._data().get("last_run") or "")

    def last_attempt(self) -> str:
        """When reading review comments was last tried, whether or not it worked."""
        data = self._data()
        return max(str(data.get("last_run") or ""), str(data.get("last_attempt") or ""))

    def touch(self) -> None:
        store.save_json(self._path, {**self._data(), "version": VERSION, "last_run": store.now()})

    def failed(self, error: str) -> None:
        """Remember a failed attempt, so an agent is not sent to retry it every session."""
        store.save_json(self._path, {**self._data(), "version": VERSION, "last_attempt": store.now(),
                                     "last_error": error[:300]})

    def add(self, urls: list[str]) -> None:
        store.save_json(self._path, {**self._data(), "version": VERSION, "seen": sorted(self.seen() | set(urls))})
