"""The projects lore knows about: ~/.lore/<name>/{project.json, map.json, rules.json}."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import store


class UnknownProject(LookupError):
    pass


class NameTaken(ValueError):
    pass


@dataclass
class Project:
    name: str
    root: Path
    created: str = ""
    updated: str = ""

    # --- locations ---
    @property
    def dir(self) -> Path:
        return store.project_dir(self.name)

    @property
    def map_path(self) -> Path:
        return self.dir / "map.json"

    # --- persistence ---
    @classmethod
    def from_dict(cls, d: dict) -> Project:
        return cls(d["name"], Path(d["root"]), d.get("created", ""), d.get("updated", ""))

    def save(self) -> None:
        self.created = self.created or store.now()
        self.updated = store.now()
        store.save_json(self.dir / "project.json", {
            "name": self.name, "root": str(self.root), "created": self.created, "updated": self.updated})

    def load_map(self) -> dict:
        return store.load_json(self.map_path, {"sections": {}})

    def save_map(self, project_map: dict) -> None:
        store.save_json(self.map_path, project_map)

    @property
    def section_names(self) -> list[str]:
        return list(self.load_map()["sections"])


def get(name: str) -> Project | None:
    """The registered project with this name, or None (also for names that could never be valid)."""
    try:
        meta = store.load_json(store.project_dir(name) / "project.json", None)
    except ValueError:
        return None
    return Project.from_dict(meta) if meta else None


def require(name: str) -> Project:
    project = get(name)
    if project is None:
        raise UnknownProject(f"unknown memory {name!r}; run memorize.py --path <project> first")
    return project


def all_projects() -> list[Project]:
    base = store.home()
    if not base.is_dir():
        return []
    out = []
    for d in sorted(base.iterdir()):
        meta = store.load_json(d / "project.json", None) if d.is_dir() else None
        if meta:
            out.append(Project.from_dict(meta))
    return out


def find_for_path(abs_path: str) -> Project | None:
    """The registered project whose root contains abs_path (the deepest one wins)."""
    p = os.path.abspath(abs_path)
    best: Project | None = None
    for project in all_projects():
        root = str(project.root).rstrip("/")
        if p == root or p.startswith(root + os.sep):
            if best is None or len(root) > len(str(best.root).rstrip("/")):
                best = project
    return best


def claim(name: str, root: Path) -> Project:
    """A Project for (name, root), keeping its creation date; refuses a name that belongs to another folder.

    Raises ValueError for an invalid name and NameTaken when the name is used by a different root.
    """
    store.validate_name(name)
    existing = get(name)
    if existing and existing.root != root:
        raise NameTaken(f"memory {name!r} already belongs to {existing.root}; pick another --name")
    return Project(name, root, existing.created if existing else "")
