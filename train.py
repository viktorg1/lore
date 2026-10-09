#!/usr/bin/env python3
"""Train a project's memory on existing instruction documents.

    train.py --name myapp --from ~/docs/standards

Reads every .md/.mdx/.mdc/.txt (and .cursorrules) under the folder (or a single file),
turns bullets into rules, and scopes them from `applyTo:`/`globs:` frontmatter or from
headings that name a project section. Deterministic: it never calls an LLM.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import rules, store, trainer


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="memory name (as given to memorize.py)")
    ap.add_argument("--from", dest="src", required=True, help="folder or file with instructions")
    ap.add_argument("--scope", help="force one scope for everything: global | section:<n> | glob:<pat,...>")
    ap.add_argument("--pending", action="store_true", help="import as pending (review before activating)")
    ap.add_argument("--dry-run", action="store_true", help="print extracted rules, store nothing")
    args = ap.parse_args(argv)

    try:
        store.validate_name(args.name)
        scope = rules.parse_scope(args.scope) if args.scope else None
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not store.project_meta(args.name):
        print(f"error: unknown memory {args.name!r}; run memorize.py --path <project> first", file=sys.stderr)
        return 2
    target = Path(os.path.expanduser(args.src)).resolve()
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return 2

    if args.dry_run:
        amap = store.load_json(store.project_dir(args.name) / "map.json", {"sections": {}})
        for doc in trainer.find_documents(target):
            text = doc.read_text(encoding="utf-8", errors="replace")
            if rules.is_generated(text):
                continue
            for item in trainer.extract(text, list(amap["sections"])):
                print(f"[{rules.scope_key(scope or item['scope'])}] {item['text']}   ({doc.name})")
        return 0

    stats = trainer.train(args.name, target, scope_override=scope,
                          status="pending" if args.pending else "active")
    print(f"Read {stats['files']} file(s): {stats['added']} rule(s) added, "
          f"{stats['duplicate']} duplicate(s), {stats['promoted']} promoted"
          + (f", {stats['skipped_generated']} generated file(s) ignored" if stats["skipped_generated"] else ""))
    print(f"Review with: review.py --name {args.name} list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
