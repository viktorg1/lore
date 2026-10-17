"""Map a project and register it in ~/.lore/<name>.

    memorize.py --path ~/projects/myapp [--name <name>]
"""
from __future__ import annotations

import os
from pathlib import Path

from core import registration
from core.models import Status

from .common import CliError, entry, make_parser

@entry
def main(argv=None) -> int:
    ap = make_parser(__doc__)
    ap.add_argument("--path", required=True, help="project root to map")
    ap.add_argument("--name", help="memory name (default: last component of --path)")
    ap.add_argument("--no-import", action="store_true",
                    help="do not import existing instruction files (AGENTS.md, copilot-instructions.md, ...)")
    ap.add_argument("--import-active", action="store_true",
                    help="import them as active rules instead of pending ones that wait for your approval")
    args = ap.parse_args(argv)

    root = Path(os.path.expanduser(args.path)).resolve()
    if not root.is_dir():
        raise CliError(f"{args.path!r} is not a directory (resolved to {root})")
    try:
        done = registration.register(root, args.name, import_instructions=not args.no_import,
                                     status=Status.ACTIVE if args.import_active else Status.PENDING)
    except ValueError as e:   # invalid name, or NameTaken
        raise CliError(str(e))
    project, project_map, total = done.project, done.project_map, done.imported

    langs = ", ".join(f"{k} ({v})" for k, v in project_map["languages"].items()) or "none detected"
    print(f"Mapped {project.name}: {project_map['files_total']} files, {len(project_map['sections'])} sections; languages: {langs}")
    for sec, info in project_map["sections"].items():
        print(f"  {sec:<28} {info['files']:>5} files  {', '.join(info['languages']) or '-'}")

    if total.files:
        state = "active" if args.import_active else "pending (approve them with review.py or the web UI)"
        print(f"Imported {total.added} rule(s) from {total.files} existing instruction file(s) as {state}; "
              f"{total.duplicate} duplicates skipped")
        for line in total.problems():
            print(line)

    print(f"Memory: {project.dir}")
    print(f"Next: train.py --name {project.name} --from <folder>   |   review.py --name {project.name} list")
    return 0
