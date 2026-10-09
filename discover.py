#!/usr/bin/env python3
"""Infer a project's conventions from its code and tooling config, as rules.

    discover.py --name myapp              # preview candidates, saves nothing
    discover.py --name myapp --save       # save as PENDING rules (approve with review.py)
    discover.py --name myapp --save --activate

Sources: .editorconfig, manifests and linter configs, statistics over the code itself (indentation,
quotes, semicolons, line length, file naming), vanilla language markers, and the markers of every
framework the project uses (Laravel, React, Django, Spring, Rails, ...). A convention is
reported only when it is lopsided (default: >= 90% over >= 5 files). Nothing is sent anywhere.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import discovery, rules, store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="memory name (as given to memorize.py)")
    ap.add_argument("--save", action="store_true", help="store the candidates (default is preview only)")
    ap.add_argument("--activate", action="store_true", help="with --save: make rules active immediately")
    ap.add_argument("--min-ratio", type=float, default=0.9, help="how lopsided the evidence must be (default 0.9)")
    ap.add_argument("--min-files", type=int, default=5, help="minimum files of evidence (default 5)")
    ap.add_argument("--markers", help="JSON file with extra pattern markers (kind: file|occ|absent|choice; see lore/discovery/markers.py)")
    args = ap.parse_args(argv)

    meta = store.project_meta(args.name) if _valid(args.name) else None
    if not meta:
        print(f"error: unknown memory {args.name!r}; run memorize.py --path <project> first", file=sys.stderr)
        return 2
    extra = json.loads(Path(args.markers).read_text()) if args.markers else []
    root = Path(meta["root"])
    if not root.is_dir():
        print(f"error: project root {root} no longer exists", file=sys.stderr)
        return 2

    cands = discovery.discover(root, args.min_ratio, args.min_files, extra)
    if not cands:
        print("No lopsided conventions found (try --min-ratio 0.8).")
        return 0
    for kind in ("config", "stats", "marker", "framework"):
        group = [c for c in cands if c["kind"] == kind]
        if group:
            print(f"\n== {kind} ({len(group)}) ==")
        for c in group:
            print(f"[{rules.scope_key(c['scope'])}] {c['text']}\n    evidence: {c['evidence']}")

    if not args.save:
        print(f"\n{len(cands)} candidate rule(s). Re-run with --save to store them as pending.")
        return 0
    counts = {"added": 0, "duplicate": 0, "promoted": 0}
    for c in cands:
        _, outcome = rules.add_rule(args.name, c["text"], c["scope"], "active" if args.activate else "pending",
                                    source="discover", evidence=c["evidence"])
        counts[outcome] += 1
    state = "active" if args.activate else "pending"
    print(f"\nSaved {counts['added']} new {state} rule(s); {counts['duplicate']} already known.")
    print(f"Next: review.py --name {args.name} list --status pending")
    return 0


def _valid(name: str) -> bool:
    try:
        store.validate_name(name)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    sys.exit(main())
