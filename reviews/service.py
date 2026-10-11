"""The whole "learn from code review" pipeline, shared by every interface (CLI, MCP tool, web UI via the CLI)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from core.models import Status
from core.projects import Project
from core.repository import RuleRepository
from core.trainer import TrainStats

from . import text
from .cluster import propose
from .github import LOGIN_RE, ReviewComment, fetch_review_comments
from .ledger import Ledger
from .models import Proposal

SHOWN_COMMENTS = 4

CLI_HINTS = {
    "save": "Re-run with --save to store them as pending rules.",
    "next": "Next: review.py --name {name} list --status pending   (reword each into a rule, then approve)",
}
AGENT_HINTS = {
    "save": "To store them as pending rules, call learn_from_reviews again with save=true.",
    "next": ("They are PENDING: tell the user to reword and approve them (review.py --name {name} list --status pending, "
             "or the lore web UI). Do not treat them as rules yet."),
}


@dataclass
class LearnOptions:
    prs: list[int] = field(default_factory=list)        # exactly these pull requests; empty = recent repository comments
    since_days: int = 90                                # only used when no pull requests are named
    min_repeats: int = 3
    min_prs: int | None = None                          # None: 2, or fewer when fewer pull requests are named
    limit: int = 300
    repo: str | None = None
    reviewers: list[str] = field(default_factory=list)
    include_bots: bool = False
    include_seen: bool = False
    save: bool = False

    @property
    def effective_min_prs(self) -> int:
        return self.min_prs if self.min_prs is not None else min(2, len(self.prs) or 2)

    def validate(self) -> None:
        """Raises ValueError with a message fit for the user."""
        for name, value, lo, hi in (("since", self.since_days, 1, 3650), ("min repeats", self.min_repeats, 2, 100),
                                    ("min prs", self.effective_min_prs, 1, 100), ("limit", self.limit, 10, 1000)):
            if not lo <= value <= hi:
                raise ValueError(f"{name} must be between {lo} and {hi}")
        if any(not LOGIN_RE.match(r) for r in self.reviewers):
            raise ValueError("reviewer must be a GitHub login")


@dataclass
class LearnResult:
    options: LearnOptions
    read: int
    where: str
    proposals: list[Proposal]
    saved: TrainStats | None = None

    def report(self, project_name: str, hints: dict[str, str] = CLI_HINTS) -> str:
        o = self.options
        lines = [f"Read {self.read} review comment(s) from {self.where}."]
        if not self.read:
            lines.append("Nothing to learn from on those pull requests." if o.prs else "Nothing to learn from yet.")
            return "\n".join(lines)
        if not self.proposals:
            lines.append(f"No new recurring themes (needs {o.min_repeats}+ similar comments on {o.effective_min_prs}+ pull requests).")
            return "\n".join(lines)
        for p in self.proposals:
            lines.append(f"\n[{p.scope.key}] {p.text}\n    {p.evidence}")
            for c in p.comments[:SHOWN_COMMENTS]:
                lines.append(f"    - {c.url}  “{text.clean(c.body)[:80]}”")
            if len(p.comments) > SHOWN_COMMENTS:
                lines.append(f"    … and {len(p.comments) - SHOWN_COMMENTS} more")
        if self.saved is None:
            lines.append(f"\n{len(self.proposals)} proposal(s). {hints['save']}")
        else:
            lines.append(f"\nSaved {self.saved.added} new pending rule(s); {self.saved.duplicate} already known.")
            lines.append(hints["next"].format(name=project_name))
        return "\n".join(lines)


def describe_prs(prs: list[int]) -> str:
    return f"pull request(s) {', '.join(f'#{n}' for n in prs[:8])}{', …' if len(prs) > 8 else ''}"


def learn(project: Project, options: LearnOptions,
          fetch: Callable[..., list[ReviewComment]] = fetch_review_comments) -> LearnResult:
    """Read review comments, find the themes, and (with options.save) store them as pending rules.

    Raises ValueError for bad options and reviews.GhError when GitHub cannot be read.
    """
    options.validate()
    comments = fetch(project.root, repo=options.repo, prs=options.prs or None,
                     since_days=options.since_days, limit=options.limit)
    where = describe_prs(options.prs) if options.prs else f"the last {options.since_days} days"
    if not comments:
        return LearnResult(options, 0, where, [])
    ledger = Ledger(project)
    proposals = propose(comments, min_repeats=options.min_repeats, min_prs=options.effective_min_prs,
                        seen=set() if options.include_seen else ledger.seen(), include_bots=options.include_bots,
                        reviewers={r.lower() for r in options.reviewers} or None)
    result = LearnResult(options, len(comments), where, proposals)
    if options.save and proposals:
        repo, stats = RuleRepository(project.name), TrainStats()
        for p in proposals:
            stats.count(repo.add(p.text, p.scope, Status.PENDING, source="review", evidence=p.evidence, refs=p.refs).outcome)
        ledger.add([c.url for p in proposals for c in p.comments])
        result.saved = stats
    return result
