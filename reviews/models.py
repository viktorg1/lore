"""The data reviews work with: one review comment, and one proposed rule distilled from several."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.models import Scope


@dataclass(frozen=True)
class ReviewComment:
    id: int
    url: str                 # link to the comment on GitHub
    pr: int | None           # pull request number
    path: str | None         # file the comment is attached to, relative to the repo root
    body: str
    author: str
    is_bot: bool = False
    is_reply: bool = False   # part of a thread, not the reviewer's original remark
    created: str = ""


@dataclass
class Proposal:
    """A recurring piece of review feedback, ready to be saved as a pending rule."""
    text: str                # the reviewers' wording, tidied: a human turns it into a proper rule
    scope: Scope
    evidence: str
    comments: list[ReviewComment] = field(default_factory=list)

    @property
    def refs(self) -> list[str]:
        return [c.url for c in self.comments][:MAX_REFS]

    @property
    def prs(self) -> list[int]:
        return sorted({c.pr for c in self.comments if c.pr is not None})


MAX_REFS = 10
