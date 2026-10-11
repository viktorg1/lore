"""How often each rule was actually handed to an agent, and when last.

Kept apart from rules.json on purpose: rules are curated by a person (CLI, web UI), usage is written by the agent's
traffic. Separate files mean the two never overwrite each other, and a damaged usage file costs counters, not rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from . import store
from .projects import Project

VERSION = 1


@dataclass(frozen=True)
class Usage:
    served: int = 0
    last_served: str = ""     # same local-time format as every other timestamp in lore


class UsageLog:
    def __init__(self, project: Project | str):
        name = project.name if isinstance(project, Project) else project
        self._path = store.project_dir(name) / "usage.json"
        self._lock = store.project_dir(name) / ".usage.lock"

    def all(self) -> dict[str, Usage]:
        """Usage by rule id. Anything unreadable counts as 'no usage recorded'."""
        try:
            raw = store.load_json(self._path, {}).get("rules", {})
        except (ValueError, AttributeError):
            return {}
        out: dict[str, Usage] = {}
        for rule_id, entry in (raw.items() if isinstance(raw, dict) else []):
            try:
                out[rule_id] = Usage(int(entry["served"]), str(entry.get("last_served", "")))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
        return out

    def get(self, rule_id: str) -> Usage:
        return self.all().get(rule_id, Usage())

    def record(self, rule_ids: Iterable[str], when: str | None = None) -> None:
        """Count one delivery for each rule (a rule listed twice counts once)."""
        ids = list(dict.fromkeys(rule_ids))
        if not ids:
            return
        with store.locked(self._lock):
            usage, stamp = self.all(), when or store.now()
            for rule_id in ids:
                usage[rule_id] = Usage(usage.get(rule_id, Usage()).served + 1, stamp)
            self._write(usage)

    def forget(self, rule_ids: Iterable[str]) -> None:
        """Drop the entries of deleted rules."""
        with store.locked(self._lock):
            usage = self.all()
            gone = [i for i in rule_ids if i in usage]
            if gone:
                for rule_id in gone:
                    del usage[rule_id]
                self._write(usage)

    def _write(self, usage: dict[str, Usage]) -> None:
        store.save_json(self._path, {"version": VERSION, "rules": {
            i: {"served": u.served, "last_served": u.last_served} for i, u in sorted(usage.items())}})
