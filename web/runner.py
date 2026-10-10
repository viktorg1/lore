"""Runs lore's own scripts for the web page, safely."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # where the entry-point scripts live
RUN_TIMEOUT = 120          # seconds a script may run
MAX_OUTPUT = 100_000       # characters of script output returned to the page


class Runner:
    """Runs lore's scripts as subprocesses (never through a shell) and reports their output.

    Only the scripts and argument shapes that web.api builds are reachable from the page; arguments are
    passed as an argv list, with option values glued on as --opt=value so a value can never be read as a flag.
    """

    def __init__(self):
        self._lock = threading.Lock()  # one script at a time: they write the same files

    def run(self, argv: list[str], stdin: str | None = None, timeout: int = RUN_TIMEOUT) -> dict:
        shown = shlex.join(["python3", *argv])
        started = time.time()
        with self._lock:
            try:
                p = subprocess.run([sys.executable, *argv], cwd=ROOT, input=stdin, capture_output=True,
                                   text=True, timeout=timeout, env=os.environ.copy())
                code, out = p.returncode, p.stdout + (("\n" + p.stderr) if p.stderr.strip() else "")
            except subprocess.TimeoutExpired:
                code, out = -1, f"timed out after {timeout}s"
            except OSError as e:
                code, out = -1, f"could not start: {e}"
        out = out.strip()
        if len(out) > MAX_OUTPUT:
            out = out[:MAX_OUTPUT] + "\n… (output truncated)"
        return {"ok": code == 0, "code": code, "command": shown, "output": out, "seconds": round(time.time() - started, 1)}
