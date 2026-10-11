"""Review, edit and export a project's rules.

    review.py --name P list [--status pending|active] [--details]
    review.py --name P add "Use the repository layer for DB access" [--scope section:api] [--pending]
    review.py --name P approve <id>... | --all [--yes]   (asks first; --all skips rules that look risky)
    review.py --name P unapprove <id>...       (back to pending)
    review.py --name P reject <id>...          (rejected rules are deleted)
    review.py --name P edit <id> [--text "new wording"] [--scope section:api]
    review.py --name P usage                   (which approved rules the agent actually receives; unused first)
    review.py --name P resolve src/api/users.py [more paths]   (what the agent would be told)
    review.py --name P sync                    (write .github/instructions/*.instructions.md)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from core import export, resolver, sanitize
from core.models import Status
from core.projects import Project
from core.repository import RuleRepository
from core.usage import Usage, UsageLog

from .common import CliError, entry, load_project, make_parser, parse_scope


def build_parser():
    ap = make_parser(__doc__)
    ap.add_argument("--name", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--status", choices=[s.value for s in Status])
    p.add_argument("--details", action="store_true", help="also show where each rule came from")
    p = sub.add_parser("add"); p.add_argument("text"); p.add_argument("--scope", default="global")
    p.add_argument("--pending", action="store_true")
    p = sub.add_parser("approve"); p.add_argument("ids", nargs="*"); p.add_argument("--all", action="store_true")
    p.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    p = sub.add_parser("unapprove"); p.add_argument("ids", nargs="+")
    p = sub.add_parser("reject"); p.add_argument("ids", nargs="+")
    p = sub.add_parser("edit"); p.add_argument("id"); p.add_argument("--text"); p.add_argument("--scope")
    p = sub.add_parser("resolve"); p.add_argument("paths", nargs="+")
    p.add_argument("--max-tokens", type=int, default=resolver.DEFAULT_MAX_TOKENS)
    sub.add_parser("usage")
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
    hidden = risky = 0
    for r in shown:
        flag = f"  [!! {r.hidden} hidden character(s) shown as <U+XXXX>]" if r.hidden else ""
        if r.risks:
            flag += f"  [!! looks risky: {'; '.join(r.risks)}]"
            risky += 1
        hidden += bool(r.hidden)
        print(f"{r.id}  {r.status.value:<7} {r.scope.key:<24} {sanitize.reveal(r.text)}{flag}")
        if args.details:
            bits = [f"source: {r.source or '-'}", f"created: {r.created or '-'}"]
            if r.edited:
                bits.append(f"edited: {r.edited}")
            if r.hits:
                bits.append(f"re-proposed {r.hits}x")
            print("          " + "  ".join(bits))
            if r.evidence:
                print(f"          evidence: {r.evidence}")
            for ref in r.refs[:5]:
                print(f"          link: {ref}")
    print(f"-- {len(shown)} rule(s)")
    if hidden:
        print(f"warning: {hidden} rule(s) contain hidden characters; they are never served or exported, and cannot be "
              "approved until you edit or reject them.", file=sys.stderr)
    if risky:
        print(f"warning: {risky} rule(s) look like an attack on the agent rather than a convention. Read them "
              "before approving; `approve --all` skips them.", file=sys.stderr)
    return 0


def cmd_add(project: Project, args) -> int:
    status = Status.PENDING if args.pending else Status.ACTIVE
    try:
        result = RuleRepository(project.name).add(args.text, parse_scope(args.scope), status, source="manual")
    except ValueError as e:
        raise CliError(str(e))
    print(f"{result.outcome}: {result.rule.id}")
    for other in result.conflicts:
        print(f"warning: may contradict rule {other.id} ({other.status}): {other.text}", file=sys.stderr)
    return 0


def _confirm(question: str, args) -> bool:
    """True after `--yes` or a typed yes. Reads one line from stdin, so a script that gives none is answered 'no'."""
    if args.yes:
        return True
    print(question + " [y/N] ", end="", flush=True)
    try:
        return input().strip().lower() in ("y", "yes")
    except EOFError:
        print()
        return False


def _describe(r) -> str:
    return f"  {r.id}  {r.scope.key:<22} {sanitize.reveal(r.text)}\n          from: {r.source or '-'}"


def cmd_approve(project: Project, args) -> int:
    repo = RuleRepository(project.name)
    if args.all:
        pending = repo.with_status(Status.PENDING)
        safe = [r for r in pending if not r.hidden and not r.risks]
        held = [r for r in pending if r not in safe]
        if safe:
            print(f"About to approve {len(safe)} pending rule(s). Once approved, the agent is told to follow them:")
            print("\n".join(_describe(r) for r in safe))
            if not _confirm(f"Approve these {len(safe)} rule(s)?", args):
                raise CliError("nothing approved")
        ids = [r.id for r in safe]
        for r in held:
            why = "hidden characters" if r.hidden else "; ".join(r.risks)
            print(f"warning: not approved, {r.id}: {why}. Review it, then `approve {r.id}` on its own.", file=sys.stderr)
    else:
        ids = args.ids
        for r in (repo.get(i) for i in ids):
            if r and r.risks and not r.hidden:
                print(f"{r.id} looks risky: {'; '.join(r.risks)}\n{_describe(r)}")
                if not _confirm("Approve it anyway?", args):
                    raise CliError("nothing approved")
    try:
        done = repo.set_status(ids, Status.ACTIVE)
    except ValueError as e:
        raise CliError(str(e))
    print(f"approved {len(done)} rule(s)")
    if len(done) != len(ids):
        print("warning: some ids were not found", file=sys.stderr)
    return 0


def cmd_unapprove(project: Project, args) -> int:
    done = RuleRepository(project.name).set_status(args.ids, Status.PENDING)
    print(f"moved {len(done)} rule(s) back to pending")
    if len(done) != len(args.ids):
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


def cmd_usage(project: Project, args) -> int:
    """Approved rules, least used first: never served, then longest since last served."""
    usage = UsageLog(project.name).all()
    rules = RuleRepository(project.name).with_status(Status.ACTIVE)
    rules.sort(key=lambda r: (usage.get(r.id, Usage()).served > 0, usage.get(r.id, Usage()).last_served, r.created))
    print(f"{'served':<7} {'last served':<19} {'id':<8}  {'scope':<24} rule")
    for r in rules:
        u = usage.get(r.id, Usage())
        print(f"{u.served or 'never':<7} {u.last_served or '-':<19} {r.id:<8}  {r.scope.key:<24} {r.text}")
    unused = sum(1 for r in rules if usage.get(r.id, Usage()).served == 0)
    print(f"-- {len(rules)} approved rule(s); {unused} never served")
    if len(rules) > resolver.MAX_RULES:
        print(f"note: the agent receives at most {resolver.MAX_RULES} rules per call (most specific first); with "
              f"{len(rules)} approved, some will rarely be served. Consider pruning the unused ones.")
    if rules and unused == len(rules):
        print("Nothing has been served yet: this counts what an agent receives through the MCP server's get_rules "
              "(not previews such as `review.py resolve`).")
    return 0


def cmd_sync(project: Project, args) -> int:
    result = export.sync_copilot(project)
    if result.skipped:
        print(f"warning: {len(result.skipped)} section rule(s) skipped: section not in map (re-run memorize.py)", file=sys.stderr)
    if result.withheld:
        print(f"warning: {len(result.withheld)} rule(s) not exported: hidden characters in their text", file=sys.stderr)
    if result.refused:
        print("warning: left alone because they are symlinks: " + ", ".join(result.refused), file=sys.stderr)
    print("\n".join(str(p) for p in result.written) if result.written else "no active rules to write")
    return 0


COMMANDS = {"list": cmd_list, "add": cmd_add, "approve": cmd_approve, "unapprove": cmd_unapprove, "reject": cmd_reject,
            "edit": cmd_edit, "resolve": cmd_resolve, "usage": cmd_usage, "sync": cmd_sync}


@entry
def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.cmd](load_project(args.name), args)
