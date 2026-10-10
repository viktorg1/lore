"""Review, edit and export a project's rules.

    review.py --name P list [--status pending|active]
    review.py --name P add "Use the repository layer for DB access" [--scope section:api] [--pending]
    review.py --name P approve <id>... | --all
    review.py --name P reject <id>...          (rejected rules are deleted)
    review.py --name P edit <id> [--text "new wording"] [--scope section:api]
    review.py --name P resolve src/api/users.py [more paths]   (what the agent would be told)
    review.py --name P sync                    (write .github/instructions/*.instructions.md)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from core import export, resolver
from core.models import Status
from core.projects import Project
from core.repository import RuleRepository

from .common import CliError, entry, load_project, make_parser, parse_scope


def build_parser():
    ap = make_parser(__doc__)
    ap.add_argument("--name", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--status", choices=[s.value for s in Status])
    p = sub.add_parser("add"); p.add_argument("text"); p.add_argument("--scope", default="global")
    p.add_argument("--pending", action="store_true")
    p = sub.add_parser("approve"); p.add_argument("ids", nargs="*"); p.add_argument("--all", action="store_true")
    p = sub.add_parser("reject"); p.add_argument("ids", nargs="+")
    p = sub.add_parser("edit"); p.add_argument("id"); p.add_argument("--text"); p.add_argument("--scope")
    p = sub.add_parser("resolve"); p.add_argument("paths", nargs="+")
    p.add_argument("--max-tokens", type=int, default=resolver.DEFAULT_MAX_TOKENS)
    sub.add_parser("sync")
    return ap


def _relative(root: Path, p: str) -> str:
    """A user-typed path as the project-relative posix path rules are matched against."""
    path = Path(p).expanduser()
    if path.is_absolute():
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.name
    return os.path.normpath(path).replace(os.sep, "/")


# --- one function per subcommand: (project, parsed args) -> exit code ---

def cmd_list(project: Project, args) -> int:
    shown = [r for r in RuleRepository(project.name).all() if not args.status or r.status.value == args.status]
    for r in shown:
        print(f"{r.id}  {r.status.value:<7} {r.scope.key:<24} {r.text}")
    print(f"-- {len(shown)} rule(s)")
    return 0


def cmd_add(project: Project, args) -> int:
    status = Status.PENDING if args.pending else Status.ACTIVE
    try:
        result = RuleRepository(project.name).add(args.text, parse_scope(args.scope), status, source="manual")
    except ValueError as e:
        raise CliError(str(e))
    print(f"{result.outcome}: {result.rule.id}")
    return 0


def cmd_approve(project: Project, args) -> int:
    repo, ids = RuleRepository(project.name), args.ids
    if args.all:
        ids = [r.id for r in repo.with_status(Status.PENDING)]
    done = repo.set_status(ids, Status.ACTIVE)
    print(f"approved {len(done)} rule(s)")
    if len(done) != len(ids):
        print("warning: some ids were not found", file=sys.stderr)
    return 0


def cmd_reject(project: Project, args) -> int:
    done = RuleRepository(project.name).remove(args.ids)
    print(f"rejected {len(done)} rule(s)")
    if len(done) != len(args.ids):
        print("warning: some ids were not found", file=sys.stderr)
    return 0


def cmd_edit(project: Project, args) -> int:
    if args.text is None and args.scope is None:
        raise CliError("give --text and/or --scope")
    scope = parse_scope(args.scope) if args.scope else None
    try:
        r = RuleRepository(project.name).edit(args.id, args.text, scope)
    except KeyError:
        raise CliError(f"no rule {args.id}")
    except ValueError as e:
        raise CliError(str(e))
    print(f"edited {r.id}: [{r.scope.key}] {r.text}")
    return 0


def cmd_resolve(project: Project, args) -> int:
    rel = [_relative(project.root, p) for p in args.paths]
    print(resolver.resolve(project.name, rel, args.max_tokens).text or "(no rules apply)")
    return 0


def cmd_sync(project: Project, args) -> int:
    result = export.sync_copilot(project)
    if result.skipped:
        print(f"warning: {len(result.skipped)} section rule(s) skipped: section not in map (re-run memorize.py)", file=sys.stderr)
    print("\n".join(str(p) for p in result.written) if result.written else "no active rules to write")
    return 0


COMMANDS = {"list": cmd_list, "add": cmd_add, "approve": cmd_approve, "reject": cmd_reject,
            "edit": cmd_edit, "resolve": cmd_resolve, "sync": cmd_sync}


@entry
def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.cmd](load_project(args.name), args)
