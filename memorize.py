#!/usr/bin/env python3
"""Map a project and register it in ~/lore/<name>.

    memorize.py --path ~/projects/myapp [--name <name>]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import store, trainer
from mapper import build_map

# Instruction files other tools already use; imported as active rules on first run.
KNOWN_INSTRUCTION_FILES = [
    ".github/copilot-instructions.md", ".github/instructions", "AGENTS.md", "CLAUDE.md",
    ".cursorrules", ".cursor/rules", ".windsurfrules",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", required=True, help="project root to map")
    ap.add_argument("--name", help="memory name (default: last component of --path)")
    ap.add_argument("--no-import", action="store_true",
                    help="do not import existing instruction files (AGENTS.md, copilot-instructions.md, ...)")
    args = ap.parse_args(argv)

    root = Path(os.path.expanduser(args.path)).resolve()
    if not root.is_dir():
        print(f"error: {args.path!r} is not a directory (resolved to {root})", file=sys.stderr)
        return 2
    name = args.name or root.name
    try:
        store.validate_name(name)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    meta = store.project_meta(name)
    if meta and Path(meta["root"]) != root:
        print(f"error: memory {name!r} already belongs to {meta['root']}; pick another --name", file=sys.stderr)
        return 2

    pdir = store.project_dir(name)
    amap = build_map(name, root)
    amap["generated"] = store.now()
    store.save_json(pdir / "map.json", amap)
    store.save_json(pdir / "project.json", {
        "name": name, "root": str(root),
        "created": (meta or {}).get("created") or store.now(), "updated": store.now(),
    })

    langs = ", ".join(f"{k} ({v})" for k, v in amap["languages"].items()) or "none detected"
    print(f"Mapped {name}: {amap['files_total']} files, {len(amap['sections'])} sections; languages: {langs}")
    for sec, info in amap["sections"].items():
        print(f"  {sec:<28} {info['files']:>5} files  {', '.join(info['languages']) or '-'}")

    if not args.no_import:
        total = {"files": 0, "added": 0, "duplicate": 0, "promoted": 0}
        for rel in KNOWN_INSTRUCTION_FILES:
            target = root / rel
            if target.exists():
                s = trainer.train(name, target, base=root)
                for k in total:
                    total[k] += s[k]
        if total["files"]:
            print(f"Imported {total['added']} rule(s) from {total['files']} existing instruction file(s) "
                  f"({total['duplicate']} duplicates skipped)")

    print(f"Memory: {pdir}")
    print(f"Next: train.py --name {name} --from <folder>   |   review.py --name {name} list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
