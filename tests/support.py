"""Shared fixtures for the test-suite. Importing this module also puts the repository root on sys.path."""
from __future__ import annotations

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
