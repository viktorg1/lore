"""Putting a project on the map: its sections, its languages and (optionally) the instruction files it already has."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import projects, store, textutil, trainer
from .mapper import build_map
from .models import Status
from .projects import Project

# Instruction files other tools already use.
KNOWN_INSTRUCTION_FILES = [
    ".github/copilot-instructions.md", ".github/instructions", "AGENTS.md", "CLAUDE.md",
    ".cursorrules", ".cursor/rules", ".windsurfrules",
]
_SYSTEM_DIRS = ("/", "/bin", "/boot", "/dev", "/etc", "/lib", "/proc", "/root", "/run", "/sbin", "/sys", "/usr", "/var", "/opt", "/home")

@dataclass
class Registration:
    project: Project
    project_map: dict
    imported: trainer.TrainStats = field(default_factory=trainer.TrainStats)

def register(root: Path, name: str | None = None, import_instructions: bool = True,
             status: Status = Status.PENDING) -> Registration:
    """Map `root` and register it under `name` (default: the folder's name). Raises ValueError (bad or taken name)."""
    project = projects.claim(name or root.name, root)
    project_map = build_map(project.name, root)
    project_map["generated"] = store.now()
    project.save_map(project_map)
    project.save()
    total = trainer.TrainStats()
    if import_instructions:
        for rel in KNOWN_INSTRUCTION_FILES:
            target = root / rel
            if target.exists():
                total.merge(trainer.train(project, target, base=root, status=status))
    return Registration(project, project_map, total)

def git_root(path: str) -> Path | None:
    """The top of the git work tree containing `path`, or None. Never the home folder, `/`, a system folder or lore's own data."""
    p = Path(os.path.abspath(os.path.expanduser(path)))
    home, data = Path.home().resolve(), store.home().resolve()
    for candidate in [p, *p.parents]:
        if candidate.is_dir() and (candidate / ".git").exists():
            real = candidate.resolve()
            unsafe = real == home or str(real) in _SYSTEM_DIRS or real == data or data in real.parents
            return None if unsafe else real
    return None

def register_automatically(path: str) -> Registration | None:
    """Register the git project containing `path` without asking, or return None when it is not one (or cannot be).

    Instruction files already in the repository are not imported: the agent's own client loads them, and a freshly cloned
    repository is not yet trusted to write rules.
    """
    root = git_root(path)
    if root is None or projects.find_for_path(str(root)):
        return None
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", root.name).strip("-._") or "project"
    for name in (base, f"{base}-{textutil.short_hash(str(root), 6)}"):
        try:
            return register(root, name, import_instructions=False)
        except ValueError:
            continue
    return None
