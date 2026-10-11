"""Fetch pull-request review comments with the GitHub CLI (`gh`), which already knows how you are logged in."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .models import ReviewComment

PER_PAGE = 100
MAX_PAGES = 10
MAX_PRS = 50
REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*(\[bot\])?$")


def parse_pr_numbers(*specs: str) -> list[int]:
    """Pull-request numbers from specs like "12", "#12", "12,15" or "15-18"; order kept, duplicates dropped.

    Raises ValueError with a readable message for anything else, or for more than MAX_PRS numbers.
    """
    numbers: list[int] = []
    for spec in specs:
        for token in re.split(r"[,\s]+", spec.strip()):
            if not token:
                continue
            m = re.fullmatch(r"#?(\d+)(?:-#?(\d+))?", token)
            if not m:
                raise ValueError(f"bad pull request {token!r}: use numbers like 12, 15-18")
            lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
            if lo < 1 or hi < lo or hi - lo >= MAX_PRS:
                raise ValueError(f"bad pull request {token!r}: numbers start at 1 and a range has at most {MAX_PRS} PRs")
            numbers += [n for n in range(lo, hi + 1) if n not in numbers]
            if len(numbers) > MAX_PRS:
                raise ValueError(f"too many pull requests (at most {MAX_PRS} at a time)")
    return numbers


class GhError(Exception):
    """gh is missing, not logged in, or GitHub refused: the message says what to do."""


Runner = Callable[[list[str], Path | None], str]


def run_gh(args: list[str], cwd: Path | None = None, timeout: int = 60) -> str:
    try:
        p = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise GhError("the GitHub CLI (gh) is not installed; install it from https://cli.github.com and run `gh auth login`")
    except subprocess.TimeoutExpired:
        raise GhError(f"gh timed out after {timeout}s")
    if p.returncode != 0:
        raise GhError((p.stderr or p.stdout).strip() or f"gh exited with status {p.returncode}")
    return p.stdout


def _comment(item) -> ReviewComment | None:
    """One API item as a ReviewComment, or None if it is not shaped like a review comment."""
    if not isinstance(item, dict):
        return None
    try:
        pr_url = item.get("pull_request_url") or ""
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        login = user.get("login") or ""
        return ReviewComment(
            id=int(item["id"]), url=item["html_url"], pr=int(pr_url.rsplit("/", 1)[1]) if "/pulls/" in pr_url else None,
            path=item.get("path"), body=item.get("body") or "", author=login,
            is_bot=user.get("type") == "Bot" or login.endswith("[bot]"),
            is_reply=item.get("in_reply_to_id") is not None, created=item.get("created_at") or "")
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _fetch_endpoint(endpoint: str, query: str, cwd: Path | None, limit: int, runner: Runner) -> list[ReviewComment]:
    comments: list[ReviewComment] = []
    for page in range(1, MAX_PAGES + 1):
        raw = runner(["api", "-H", "Accept: application/vnd.github+json",
                      f"{endpoint}?{query}&per_page={PER_PAGE}&page={page}"], cwd)
        try:
            items = json.loads(raw)
        except ValueError:
            raise GhError("GitHub returned something that is not JSON")
        if not isinstance(items, list):
            raise GhError(str(items.get("message", "unexpected answer from GitHub")) if isinstance(items, dict) else "unexpected answer from GitHub")
        comments += [c for c in map(_comment, items) if c]
        if len(items) < PER_PAGE or len(comments) >= limit:
            break
    return comments[:limit]


def fetch_review_comments(cwd: Path | None = None, *, repo: str | None = None, prs: list[int] | None = None,
                          since_days: int | None = 90, limit: int = 300, runner: Runner = run_gh) -> list[ReviewComment]:
    """Inline review comments, newest first: of the given pull requests, or else of the whole repository.

    Without `repo`, gh uses the repository of the git checkout it is run in (`cwd`). `since_days` only narrows the
    repository-wide read: pull requests you name are read in full.
    """
    if repo is not None and not REPO_RE.match(repo):
        raise GhError(f"bad repository {repo!r}: use OWNER/NAME")
    base = f"repos/{repo}" if repo else "repos/{owner}/{repo}"
    query = "sort=created&direction=desc"
    if not prs:
        if since_days:
            since = datetime.now(timezone.utc) - timedelta(days=since_days)
            query += "&since=" + since.strftime("%Y-%m-%dT%H:%M:%SZ")
        return _fetch_endpoint(f"{base}/pulls/comments", query, cwd, limit, runner)
    comments: dict[int, ReviewComment] = {}
    for pr in prs:
        try:
            found = _fetch_endpoint(f"{base}/pulls/{pr}/comments", query, cwd, limit - len(comments), runner)
        except GhError as e:
            raise GhError(f"pull request #{pr}: {e}")
        comments.update({c.id: c for c in found})
        if len(comments) >= limit:
            break
    return list(comments.values())[:limit]
