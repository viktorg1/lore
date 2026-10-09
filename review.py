#!/usr/bin/env python3
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

import argparse
import os
import sys
from pathlib import Path

import rules, store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--status", choices=["pending", "active"])
    p = sub.add_parser("add"); p.add_argument("text"); p.add_argument("--scope", default="global")
    p.add_argument("--pending", action="store_true")
    p = sub.add_parser("approve"); p.add_argument("ids", nargs="*"); p.add_argument("--all", action="store_true")
    p = sub.add_parser("reject"); p.add_argument("ids", nargs="+")
    p = sub.add_parser("edit"); p.add_argument("id"); p.add_argument("--text"); p.add_argument("--scope")
    p = sub.add_parser("resolve"); p.add_argument("paths", nargs="+"); p.add_argument("--max-tokens", type=int, default=800)
    sub.add_parser("sync")
    args = ap.parse_args(argv)

    meta = store.project_meta(args.name) if _valid(args.name) else None
    if not meta:
        print(f"error: unknown memory {args.name!r}; run memorize.py --path <project> first", file=sys.stderr)
        return 2

    if args.cmd == "list":
        shown = [r for r in rules.load(args.name) if not args.status or r["status"] == args.status]
        for r in shown:
            print(f"{r['id']}  {r['status']:<7} {rules.scope_key(r['scope']):<24} {r['text']}")
        print(f"-- {len(shown)} rule(s)")
    elif args.cmd == "add":
        try:
            r, outcome = rules.add_rule(args.name, args.text, rules.parse_scope(args.scope),
                                        status="pending" if args.pending else "active", source="manual")
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr); return 2
        print(f"{outcome}: {r['id']}")
    elif args.cmd in ("approve", "reject"):
        ids = args.ids
        if args.cmd == "approve" and args.all:
            ids = [r["id"] for r in rules.load(args.name) if r["status"] == "pending"]
        done = rules.set_status(args.name, ids, "active" if args.cmd == "approve" else None)
        print(f"{args.cmd}d {len(done)} rule(s)")
        if len(done) != len(ids):
            print("warning: some ids were not found", file=sys.stderr)
    elif args.cmd == "edit":
        if args.text is None and args.scope is None:
            print("error: give --text and/or --scope", file=sys.stderr); return 2
        try:
            r = rules.edit_rule(args.name, args.id, args.text, rules.parse_scope(args.scope) if args.scope else None)
        except KeyError:
            print(f"error: no rule {args.id}", file=sys.stderr); return 2
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr); return 2
        print(f"edited {r['id']}: [{rules.scope_key(r['scope'])}] {r['text']}")
    elif args.cmd == "resolve":
        root = Path(meta["root"])
        rel = [_rel(root, p) for p in args.paths]
        print(rules.resolve(args.name, rel, args.max_tokens)["text"] or "(no rules apply)")
    elif args.cmd == "sync":
        files = rules.sync_copilot(args.name, Path(meta["root"]))
        print("\n".join(files) if files else "no active rules to write")
    return 0


def _valid(name: str) -> bool:
    try:
        store.validate_name(name)
        return True
    except ValueError:
        return False


def _rel(root: Path, p: str) -> str:
    path = Path(p).expanduser()
    if path.is_absolute():
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            pass
    return path.name if path.is_absolute() else os.path.normpath(path).replace(os.sep, "/")


if __name__ == "__main__":
    sys.exit(main())
