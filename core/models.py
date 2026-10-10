"""The vocabulary of lore: scopes, rules, and their statuses.

Persisted as JSON exactly as before (scope as {"type": ...}, status as a string), but handled in code as
typed objects instead of loose dicts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum

from . import textutil
from .globs import glob_match, split_globs
from .mapper import section_of


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ScopeKind(_StrEnum):
    GLOBAL = "global"
    SECTION = "section"
    GLOB = "glob"


class Status(_StrEnum):
    ACTIVE = "active"      # approved: handed to the agent
    PENDING = "pending"    # proposed: waits for a human


class Outcome(_StrEnum):
    ADDED = "added"
    DUPLICATE = "duplicate"
    PROMOTED = "promoted"  # a duplicate that moved a pending rule to active


class Level(IntEnum):
    """How precisely a rule's scope targets a file; lower is more specific and is listed first."""
    FILE = 0
    SECTION = 1
    GLOBAL = 2

    @property
    def label(self) -> str:
        return self.name.lower()


def section_matches(wanted: str, section_id: str) -> bool:
    """`api` matches the sections `src/api` and `api`; `src` matches `src` and everything below it."""
    v = wanted.strip("/")
    return section_id == v or section_id.endswith("/" + v) or section_id.startswith(v + "/")


@dataclass(frozen=True)
class Scope:
    """Where a rule applies: everywhere, in a folder-level section, or on files matching globs."""
    kind: ScopeKind
    section: str = ""
    globs: tuple[str, ...] = ()

    # --- construction ---
    @classmethod
    def everywhere(cls) -> Scope:
        return cls(ScopeKind.GLOBAL)

    @classmethod
    def for_section(cls, name: str) -> Scope:
        return cls(ScopeKind.SECTION, section=name.strip().strip("/"))

    @classmethod
    def for_globs(cls, *globs: str) -> Scope:
        return cls(ScopeKind.GLOB, globs=tuple(globs))

    @classmethod
    def parse(cls, spec: str | None) -> Scope:
        """`global`, `section:<name>` or `glob:<pattern>[,<pattern>...]`; raises ValueError otherwise."""
        spec = (spec or "global").strip()
        if spec == "global":
            return cls.everywhere()
        kind, _, val = spec.partition(":")
        if kind == "section" and val.strip():
            return cls.for_section(val)
        if kind == "glob" and val.strip():
            return cls.for_globs(*split_globs(val))
        raise ValueError(f"bad scope {spec!r}: use global, section:<name> or glob:<pattern,...>")

    @classmethod
    def from_dict(cls, d: dict) -> Scope:
        kind = ScopeKind(d["type"])
        if kind is ScopeKind.SECTION:
            return cls(kind, section=d["value"])
        if kind is ScopeKind.GLOB:
            return cls(kind, globs=tuple(d["globs"]))
        return cls(kind)

    def to_dict(self) -> dict:
        if self.kind is ScopeKind.SECTION:
            return {"type": "section", "value": self.section}
        if self.kind is ScopeKind.GLOB:
            return {"type": "glob", "globs": list(self.globs)}
        return {"type": "global"}

    # --- behaviour ---
    @property
    def key(self) -> str:
        """The scope as users write it; also what makes two scopes 'the same'."""
        if self.kind is ScopeKind.SECTION:
            return f"section:{self.section}"
        if self.kind is ScopeKind.GLOB:
            return "glob:" + ",".join(self.globs)
        return "global"

    def __str__(self) -> str:
        return self.key

    def level_for(self, rel: str) -> Level | None:
        """How this scope applies to a project-relative path, or None if it does not."""
        if self.kind is ScopeKind.GLOBAL:
            return Level.GLOBAL
        if self.kind is ScopeKind.SECTION:
            return Level.SECTION if section_matches(self.section, section_of(rel)) else None
        return Level.FILE if any(glob_match(g, rel) for g in self.globs) else None

    def covers_section(self, section_id: str) -> bool:
        return self.kind is ScopeKind.SECTION and section_matches(self.section, section_id)


@dataclass
class Rule:
    id: str
    text: str
    scope: Scope
    status: Status = Status.PENDING
    source: str = "manual"
    evidence: str = ""
    created: str = ""
    hits: int = 0
    edited: str | None = None
    extra: dict = field(default_factory=dict)   # unknown keys from the file survive a load/save round-trip

    _KNOWN = ("id", "text", "scope", "status", "source", "evidence", "created", "hits", "edited")

    @staticmethod
    def make_id(text: str, scope: Scope) -> str:
        return textutil.short_hash(textutil.normalize(text) + "|" + scope.key)

    @classmethod
    def from_dict(cls, d: dict) -> Rule:
        return cls(
            id=d["id"], text=d["text"], scope=Scope.from_dict(d["scope"]), status=Status(d["status"]),
            source=d.get("source", ""), evidence=d.get("evidence", ""), created=d.get("created", ""),
            hits=d.get("hits", 0), edited=d.get("edited"),
            extra={k: v for k, v in d.items() if k not in cls._KNOWN},
        )

    def to_dict(self) -> dict:
        d = {"id": self.id, "text": self.text, "scope": self.scope.to_dict(), "status": self.status.value,
             "source": self.source, "evidence": self.evidence, "created": self.created, "hits": self.hits}
        if self.edited:
            d["edited"] = self.edited
        return {**d, **self.extra}
