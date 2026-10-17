"""Shared fixtures for the test-suite. Importing this module also puts the repository root on sys.path."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import projects  # noqa: E402
from core.models import Scope, Status  # noqa: E402
from core.repository import RuleRepository  # noqa: E402


def run_script(name: str, *args, stdin: str | None = None, env: dict | None = None, cwd: Path = ROOT):
    """Run one of the entry-point scripts (memorize.py, review.py, ...) as a subprocess."""
    return subprocess.run([sys.executable, str(ROOT / name), *map(str, args)], capture_output=True, text=True,
                          input=stdin, env=env, cwd=cwd)

FAKE_GH = """#!/usr/bin/env python3
import json, os, re, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(json.dumps({"args": args, "cwd": os.getcwd()}) + "\\n")
if os.environ.get("FAKE_GH_FAIL"):
    sys.stderr.write(os.environ["FAKE_GH_FAIL"] + "\\n")
    sys.exit(1)
page = int((re.search(r"[&?]page=(\\d+)", args[-1]) or [0, 1])[1])
data = json.load(open(os.environ["FAKE_GH_DATA"]))
only = re.search(r"/pulls/(\\d+)/comments", args[-1])
if only:
    data = [c for c in data if str(c.get("pull_request_url", "")).endswith("/pulls/" + only.group(1))]
print(json.dumps(data[(page - 1) * 100: page * 100]))
"""

def api_comment(cid: int, pr: int, path: str, body: str, login: str = "ann", bot: bool = False,
                reply_to: int | None = None) -> dict:
    """A pull-request review comment shaped like GitHub's REST API returns it."""
    return {"id": cid, "html_url": f"https://github.com/acme/shop/pull/{pr}#discussion_r{cid}",
            "pull_request_url": f"https://api.github.com/repos/acme/shop/pulls/{pr}", "path": path, "body": body,
            "user": {"login": login, "type": "Bot" if bot else "User"}, "in_reply_to_id": reply_to,
            "author_association": "MEMBER",
            "created_at": f"2026-01-{cid % 28 + 1:02d}T10:00:00Z"}

# three themes reviewers keep repeating, mixed with the usual noise and look-alike but different asks
THEMES = [
    ("src/api/users.py", "Please don't query the database directly in the controller, use the repository."),
    ("src/api/orders.py", "We should go through the repository layer here instead of calling the DB from the controller"),
    ("src/api/items.py", "Same as before: controllers shouldn't talk to the database, use the UserRepository."),
    ("src/api/cart.py", "nit: this DB call belongs in the repository, not in the controller"),
    ("src/api/a.py", "Missing return type annotation on this function."),
    ("src/services/pay.py", "Please add a return type here."),
    ("src/api/x.py", "Can we add type hints / return types to new functions?"),
    ("src/ui/y.py", "Add a return type annotation"),
    ("src/api/b.py", "Use the logger instead of print()"),
    ("src/api/c.py", "print() shouldn't be used in app code, use logging"),
    ("src/api/d.py", "please use logging instead of print"),
]
NOISE = [
    "LGTM", "why did you rename this?", "nit: typo in the heading", "This could be simplified a bit.",
    "Could you explain what this block does?", "Use a constant instead of a magic number here.",
    "Use a constant instead of a hardcoded string here.", "Please use async/await instead of .then() chains.",
    "Add a test for this function.", "Add docs for this function.", "This function is too long, split it up.",
    "Use a dataclass instead of a plain dict here.", "Do not mutate the argument, return a new list.",
    "Remove the unused import.", "Remove this dead code.", "Rename this variable, it is not descriptive.",
    "Name tests after the behaviour they check, not the function.", "Tests should not depend on the order they run in.",
    "Use early returns to reduce nesting.", "Avoid mutable default arguments.",
]

def review_corpus() -> list[dict]:
    """API-shaped comments: each theme comment on its own PR, plus one-off noise and a bot and a reply."""
    out, cid = [], 100
    for i, (path, body) in enumerate(THEMES):
        out.append(api_comment(cid, 10 + i, path, body, login=("ann", "bob", "cy")[i % 3]))
        cid += 1
    for i, body in enumerate(NOISE):
        out.append(api_comment(cid, 40 + i, f"src/api/n{i}.py", body, login=("ann", "bob", "cy")[i % 3]))
        cid += 1
    out.append(api_comment(cid, 99, "src/api/b.py", "Use the logger instead of print()", login="copilot[bot]", bot=True))
    out.append(api_comment(cid + 1, 98, "src/api/b.py", "Use the logger instead of print()", reply_to=100))
    return out

class TempHome(unittest.TestCase):
    """A throw-away LORE_HOME plus a scratch folder, active in this process and in subprocesses."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scratch = Path(self.tmp.name)
        self.home = self.scratch / "mem"
        os.environ["LORE_HOME"] = str(self.home)
        self.addCleanup(os.environ.pop, "LORE_HOME", None)
        self.env = {**os.environ}

    def write(self, rel: str, text: str = "x") -> Path:
        path = self.scratch / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def script(self, name: str, *args, stdin: str | None = None):
        return run_script(name, *args, stdin=stdin, env=self.env)

    def use_fake_gh(self, comments: list[dict] | None = None, fail: str | None = None) -> Path:
        """Put a stand-in `gh` first on PATH (here and in subprocesses). Returns the file logging its calls."""
        bindir = self.scratch / "bin"
        bindir.mkdir(exist_ok=True)
        (bindir / "gh").write_text(FAKE_GH)
        (bindir / "gh").chmod(0o755)
        data, log = self.scratch / "gh-data.json", self.scratch / "gh-log.jsonl"
        data.write_text(json.dumps(review_corpus() if comments is None else comments))
        changes = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_DATA": str(data), "FAKE_GH_LOG": str(log)}
        if fail:
            changes["FAKE_GH_FAIL"] = fail
        for key, value in changes.items():
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(os.environ.pop if old is None else os.environ.__setitem__, key, *([] if old is None else [old]))
        self.env = {**os.environ}
        return log

class RegisteredProject(TempHome):
    """TempHome plus a registered project "app" with one pending and one active rule."""

    def setUp(self):
        super().setUp()
        self.root = self.scratch / "app"
        (self.root / "src").mkdir(parents=True)
        self.project = projects.claim("app", self.root)
        self.project.save()
        self.project.save_map({"sections": {"src": {"path": "src"}, "tests": {"path": "tests"}}})
        self.repo = RuleRepository("app")
        self.pending = self.repo.add("Validate input at the boundary", Scope.everywhere(), Status.PENDING,
                                     "discover", "12/12 files").rule
        self.active = self.repo.add("Name files in snake_case", Scope.for_section("src"), Status.ACTIVE, "manual").rule
