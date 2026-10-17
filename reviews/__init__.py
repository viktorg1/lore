"""Learn from code review: turn recurring pull-request comments into pending rule proposals.

    comments = fetch_review_comments(project.root)       # needs `gh`; or build ReviewComment objects yourself
    proposals = propose(comments, min_repeats=2)

Depends on `core` only. Nothing here stores anything: the caller saves proposals as pending rules.
"""
from __future__ import annotations

from .cluster import propose
from .github import GhError, fetch_review_comments, parse_pr_numbers
from .ledger import Ledger
from .models import Proposal, ReviewComment
from .service import AGENT_HINTS, LearnOptions, LearnResult, learn

__all__ = ["propose", "fetch_review_comments", "parse_pr_numbers", "learn", "LearnOptions", "LearnResult", "AGENT_HINTS", "GhError", "Ledger", "Proposal", "ReviewComment"]
