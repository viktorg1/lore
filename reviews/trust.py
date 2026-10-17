"""Whether a project's repository is the user's own, so that rules may be activated in it without a person.

    trusted     no git remote (local work), or a GitHub repository the user's `gh` login can push to
    untrusted   anything else: someone else's GitHub repository, another host, or when it cannot be checked

The answer is cached for TTL_DAYS in ~/.lore/<name>/trust.json. A person can settle it for good with
`review.py trust` / `review.py untrust`; `review.py trust --reset` hands the decision back to the check.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass

from core import store
from core.projects import Project

from .github import GhError, Runner, run_gh

TTL_DAYS = 7
_GITHUB = re.compile(r"^(?:https?://|ssh://)?(?:[^@/]+@)?github\.com[:/]([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")

@dataclass(frozen=True)
class Trust:
    trusted: bool
    reason: str
    checked: str = ""
    manual: bool = False

def _path(project: Project):
    return project.dir / "trust.json"

def _remote(project: Project) -> str | None:
    """The URL of `origin` (or the first remote); "" when the repository has no remote; None when it cannot be read."""
    if not (project.root / ".git").exists():
        return ""
    try:
        out = subprocess.run(["git", "-C", str(project.root), "config", "--local", "--get-regexp", r"^remote\..*\.url$"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode not in (0, 1):            # 1: no remote configured; anything else: not a readable repository
        return None
    urls = dict(line.split(None, 1) for line in out.stdout.splitlines() if " " in line)
    return urls.get("remote.origin.url") or next(iter(urls.values()), "")

def check(project: Project, runner: Runner = run_gh) -> Trust:
    """Decide afresh, without the cache."""
    url = _remote(project)
    if url is None:
        return Trust(False, "its git remotes could not be read")
    if url == "":
        return Trust(True, "a local repository without a remote")
    m = _GITHUB.match(url.strip())
    if not m:
        return Trust(False, "its remote is not on GitHub, so Lore cannot check that it is yours")
    owner, repo = m.group(1), m.group(2)
    try:
        perms = json.loads(runner(["api", f"repos/{owner}/{repo}", "--jq", ".permissions"], project.root) or "null")
    except (GhError, ValueError) as e:
        return Trust(False, f"GitHub could not confirm you can push to {owner}/{repo} ({str(e)[:120]})")
    if isinstance(perms, dict) and (perms.get("push") or perms.get("maintain") or perms.get("admin")):
        return Trust(True, f"you can push to {owner}/{repo}")
    return Trust(False, f"you cannot push to {owner}/{repo} (someone else's repository)")

def _age_days(stamp: str) -> float:
    try:
        return (time.time() - time.mktime(time.strptime(stamp, "%Y-%m-%dT%H:%M:%S"))) / 86400
    except (ValueError, OverflowError):
        return float("inf")

def stored(project: Project) -> Trust | None:
    """The last answer (a person's or a check's), without checking again; None if there is none yet."""
    try:
        raw = store.load_json(_path(project), {})
    except ValueError:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("trusted"), bool):
        return None
    return Trust(raw["trusted"], str(raw.get("reason", "")), str(raw.get("checked", "")), bool(raw.get("manual")))

def get(project: Project, runner: Runner = run_gh) -> Trust:
    """The project's trust: a person's decision if there is one, else the cached check, else a fresh check."""
    cached = stored(project)
    if cached and (cached.manual or _age_days(cached.checked) <= TTL_DAYS):
        return cached
    fresh = check(project, runner)
    fresh = Trust(fresh.trusted, fresh.reason, store.now())
    store.save_json(_path(project), {"trusted": fresh.trusted, "reason": fresh.reason, "checked": fresh.checked})
    return fresh

def set_manual(project: Project, trusted: bool | None) -> None:
    """A person's decision (None: forget it and let the check decide again)."""
    if trusted is None:
        _path(project).unlink(missing_ok=True)
        return
    store.save_json(_path(project), {"trusted": trusted, "manual": True, "checked": store.now(),
                                     "reason": "set by you with review.py " + ("trust" if trusted else "untrust")})
