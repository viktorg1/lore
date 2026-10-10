"""Plumbing shared by every command: parser, error handling, project lookup."""
from __future__ import annotations

import argparse
import functools
import sys

from core import projects, store
from core.models import Scope
from core.projects import Project


class CliError(Exception):
    """A user-facing failure: printed as `error: <message>` and turned into an exit code."""

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def entry(fn):
    """Decorator for a command's `main(argv)`: report CliError nicely instead of a traceback."""
    @functools.wraps(fn)
    def wrapper(argv=None) -> int:
        try:
            return fn(argv) or 0
        except CliError as e:
            print(f"error: {e}", file=sys.stderr)
            return e.code
    return wrapper


def make_parser(doc: str) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)


def load_project(name: str) -> Project:
    """The registered project, or a CliError saying how to register it."""
    try:
        store.validate_name(name)
        return projects.require(name)
    except (ValueError, projects.UnknownProject) as e:
        raise CliError(str(e))


def parse_scope(spec: str | None) -> Scope:
    try:
        return Scope.parse(spec)
    except ValueError as e:
        raise CliError(str(e))
