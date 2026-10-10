"""Turn existing instruction documents into scoped rules. Deterministic: no LLM, no tokens."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .export import is_generated
from .globs import split_globs
from .models import Outcome, Scope, Status
from .projects import Project
from .repository import RuleRepository

TEXT_EXTS = {".md", ".mdx", ".mdc", ".txt"}
SPECIAL_NAMES = {".cursorrules", ".windsurfrules"}
MIN_LEN, MAX_LEN = 12, 500
BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _strip_md(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)      # [text](url) -> text
    s = re.sub(r"(\*\*|__)(.*?)\1", r"\2", s)            # bold
    return " ".join(s.split())


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[3:end].splitlines():
        k, sep, v = line.partition(":")
        if sep:
            meta[k.strip()] = v.strip().strip("[]")
    return meta, text[text.find("\n", end + 1) + 1:] if "\n" in text[end + 1:] else ""


@dataclass(frozen=True)
class Extracted:
    text: str
    scope: Scope


def extract(text: str, section_names: list[str]) -> list[Extracted]:
    """The rules found in one instruction document, each with the scope it implies."""
    meta, body = parse_frontmatter(text)
    globs = [g for g in split_globs(meta.get("applyTo") or meta.get("globs") or "")
             if g not in ("**", "**/*")]
    file_scope = Scope.for_globs(*globs) if globs else None

    items: list[tuple[str, list[str]]] = []  # (text, heading chain)
    paragraphs: list[tuple[str, list[str]]] = []
    headings: list[tuple[int, str]] = []
    cur_bullet: list | None = None
    para: list[str] = []
    in_fence = False

    def chain():
        return [h for _, h in headings]

    def flush_bullet():
        nonlocal cur_bullet
        if cur_bullet:
            items.append((" ".join(cur_bullet[0]), cur_bullet[1]))
        cur_bullet = None

    def flush_para():
        nonlocal para
        if para:
            paragraphs.append((" ".join(para), chain()))
        para = []

    for line in body.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            flush_bullet(); flush_para()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            flush_bullet(); flush_para()
            continue
        h = HEADING.match(line)
        if h:
            flush_bullet(); flush_para()
            level = len(h.group(1))
            headings[:] = [x for x in headings if x[0] < level] + [(level, h.group(2))]
            continue
        b = BULLET.match(line)
        if b:
            flush_bullet(); flush_para()
            cur_bullet = ([b.group(2)], chain())
        elif cur_bullet and line.startswith((" ", "\t")):
            cur_bullet[0].append(line.strip())
        else:
            flush_bullet()
            para.append(line.strip())
    flush_bullet(); flush_para()

    source = items or [(t, c) for t, c in paragraphs if not t.lstrip().startswith(("|", ">", "<"))]
    out, seen = [], set()
    for raw, hchain in source:
        t = _strip_md(raw)
        if not (MIN_LEN <= len(t) <= MAX_LEN) or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(Extracted(t, file_scope or _scope_from_headings(hchain, section_names)))
    return out


def _scope_from_headings(chain: list[str], section_names: list[str]) -> Scope:
    """Nearest heading that names exactly one known section wins; otherwise global."""
    for heading in reversed(chain):
        hits = {s for s in section_names
                if s != "root" and re.search(rf"\b{re.escape(s.rsplit('/', 1)[-1])}\b", heading, re.I)}
        if len(hits) == 1:
            return Scope.for_section(hits.pop())
    return Scope.everywhere()


def find_documents(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(
        p for p in target.rglob("*")
        if p.is_file() and (p.suffix.lower() in TEXT_EXTS or p.name in SPECIAL_NAMES)
        and not set(p.relative_to(target).parts[:-1]) & {".git", "node_modules"}
    )


@dataclass
class TrainStats:
    files: int = 0
    added: int = 0
    duplicate: int = 0
    promoted: int = 0
    skipped_generated: int = 0

    def count(self, outcome: Outcome) -> None:
        setattr(self, outcome.value, getattr(self, outcome.value) + 1)

    def merge(self, other: TrainStats) -> None:
        for name in ("files", "added", "duplicate", "promoted", "skipped_generated"):
            setattr(self, name, getattr(self, name) + getattr(other, name))


def train(project: Project, target: Path, scope_override: Scope | None = None,
          status: Status = Status.ACTIVE, base: Path | None = None) -> TrainStats:
    """Ingest every instruction document under target into the project's rules."""
    section_names = project.section_names
    repo = RuleRepository(project.name)
    base = base or (target if target.is_dir() else target.parent)
    stats = TrainStats()
    for doc in find_documents(target):
        text = doc.read_text(encoding="utf-8", errors="replace")
        if is_generated(text):
            stats.skipped_generated += 1
            continue
        stats.files += 1
        try:
            source = str(doc.relative_to(base))
        except ValueError:
            source = doc.name
        for item in extract(text, section_names):
            stats.count(repo.add(item.text, scope_override or item.scope, status=status, source=source).outcome)
    return stats
