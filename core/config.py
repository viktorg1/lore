"""Lore's own settings, in ~/.lore/config.json. Everything has a default, so the file is optional.

    {"approval": "auto" | "manual", "auto_register": true, "auto_limit": 25}

approval       "auto": rules the agent proposes are activated at once when they pass the safety screening (no risky
               wording, no contradiction with an existing rule); anything flagged waits for a person.
               "manual": every proposed rule waits for a person.
auto_register  register a git project the first time an agent works in it.
auto_limit     most rules that may be activated automatically in one agent session.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from . import store

DEFAULT_AUTO_LIMIT = 25


@dataclass(frozen=True)
class Config:
    approval: str = "auto"
    auto_register: bool = True
    auto_limit: int = DEFAULT_AUTO_LIMIT

    @property
    def auto_approve(self) -> bool:
        return self.approval == "auto"


def path():
    return store.home() / "config.json"


def load() -> Config:
    """The settings; an unreadable file or a bad value falls back to the default for that setting."""
    try:
        raw = store.load_json(path(), {})
    except ValueError:
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    approval = os.environ.get("LORE_APPROVAL") or raw.get("approval")
    limit = raw.get("auto_limit")
    return Config(
        approval=approval if approval in ("auto", "manual") else Config.approval,
        auto_register=raw.get("auto_register") if isinstance(raw.get("auto_register"), bool) else Config.auto_register,
        auto_limit=limit if isinstance(limit, int) and not isinstance(limit, bool) and 0 <= limit <= 1000 else DEFAULT_AUTO_LIMIT)


def save(**changes) -> Config:
    """Write the given settings (merged into what is there) and return the result."""
    try:
        raw = store.load_json(path(), {})
    except ValueError:
        raw = {}
    raw = {**(raw if isinstance(raw, dict) else {}), **changes}
    store.save_json(path(), raw)
    return load()
