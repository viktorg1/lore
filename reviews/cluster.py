"""Group review comments that ask for the same thing, and turn recurring groups into rule proposals.

Deterministic and offline: words in common, not a language model. A group only becomes a proposal if
reviewers said it enough times (`min_repeats`, default 1: every actionable comment is a candidate).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from core import sanitize
from core.mapper import section_of
from core.models import Scope

from . import text
from .models import Proposal, ReviewComment

SIMILARITY = 0.3   # how alike two comments' words must be to count as the same ask


@dataclass
class _Item:
    comment: ReviewComment
    cleaned: str
    words: frozenset[str]


def usable(comments: list[ReviewComment], *, include_bots: bool = False, reviewers: set[str] | None = None,
           include_external: bool = False) -> list[_Item]:
    """Comments that carry a reviewer's own, actionable remark, in a stable order.

    Comments by people outside the repository's team (anyone can comment on a public repository) are left out unless
    `include_external`: they must not be able to write rules.
    """
    items = []
    for c in sorted(comments, key=lambda c: (c.created, c.id)):
        if c.is_reply or (c.is_bot and not include_bots) or sanitize.hidden_count(c.body):
            continue          # a comment hiding characters is never evidence for a rule
        if reviewers and c.author.lower() not in reviewers:
            continue
        if not c.is_team and not include_external:
            continue
        cleaned = text.clean(c.body)
        if text.is_actionable(cleaned):
            items.append(_Item(c, cleaned, text.tokens(cleaned)))
    return items


def group(items: list[_Item], threshold: float = SIMILARITY) -> list[list[_Item]]:
    """Connected groups: two comments are in the same group if a chain of similar comments links them."""
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(items):
        for j in range(i + 1, len(items)):
            if text.similarity(a.words, items[j].words) >= threshold:
                parent[find(j)] = find(i)
    groups: dict[int, list[_Item]] = {}
    for i, item in enumerate(items):
        groups.setdefault(find(i), []).append(item)
    return list(groups.values())


def representative(members: list[_Item]) -> _Item:
    """The member most like the others; ties go to the one that reads most like an instruction."""
    def key(i: _Item):
        closeness = sum(text.similarity(i.words, o.words) for o in members if o is not i)
        return (round(closeness, 6), text.imperative_score(i.cleaned), -len(i.cleaned))
    return max(members, key=key)


def _extension(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else None


def scope_for(comments: list[ReviewComment]) -> Scope:
    """A section if every commented file lives in one, else one file extension, else everywhere."""
    paths = [c.path for c in comments if c.path]
    if not paths:
        return Scope.everywhere()
    sections = {section_of(p) for p in paths}
    if len(sections) == 1 and "root" not in sections:
        try:
            return Scope.for_section(sections.pop())
        except ValueError:      # a file path with line breaks, quotes or hidden characters is not a usable section name
            return Scope.everywhere()
    exts = {_extension(p) for p in paths}
    if len(exts) == 1 and None not in exts:
        try:
            return Scope.for_globs(f"**/*.{exts.pop()}")
        except ValueError:
            return Scope.everywhere()
    return Scope.everywhere()


def propose(comments: list[ReviewComment], *, min_repeats: int = 1, min_prs: int = 1,
            seen: frozenset[str] | set[str] = frozenset(), include_bots: bool = False,
            reviewers: set[str] | None = None, include_external: bool = False,
            threshold: float = SIMILARITY) -> list[Proposal]:
    """Recurring review themes as proposals, most repeated first.

    `seen` holds comment URLs already proposed before; a theme that is mostly made of them is skipped.
    """
    out = []
    for members in group(usable(comments, include_bots=include_bots, reviewers=reviewers,
                                include_external=include_external), threshold):
        cs = [m.comment for m in members]
        prs = sorted({c.pr for c in cs if c.pr is not None})
        if len(members) < min_repeats or len(prs) < min_prs:
            continue
        if sum(c.url in seen for c in cs) * 2 >= len(cs):
            continue
        rep = representative(members)
        shown = ", ".join(f"#{p}" for p in prs[:5]) + (", …" if len(prs) > 5 else "")
        disagree = any(text.prohibits(m.cleaned) != text.prohibits(rep.cleaned) for m in members)
        out.append(Proposal(
            text=text.rule_text(rep.cleaned), scope=scope_for(cs), comments=cs,
            evidence=f"{len(cs)} similar review comments on {len(prs)} PRs ({shown})"
                     + ("; check them: some may ask for the opposite" if disagree else "")))
    return sorted(out, key=lambda p: (-len(p.comments), p.text))
