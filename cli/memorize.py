"""Map a project and register it in ~/.lore/<name>.

    memorize.py --path ~/projects/myapp [--name <name>]
"""
from __future__ import annotations

import os
from pathlib import Path

from core import projects, store, trainer
from core.mapper import build_map

from .common import CliError, entry, make_parser

# Instruction files other tools already use; imported as active rules on first run.
KNOWN_INSTRUCTION_FILES = [
    ".github/copilot-instructions.md", ".github/instructions", "AGENTS.md", "CLAUDE.md",
    ".cursorrules", ".cursor/rules", ".windsurfrules",
]


@entry
def main(argv=None) -> int:
    ap = make_parser(__doc__)
    ap.add_argument("--path", required=True, help="project root to map")
    ap.add_argument("--name", help="memory name (default: last component of --path)")
    ap.add_argument("--no-import", action="store_true",
                    help="do not import existing instruction files (AGENTS.md, copilot-instructions.md, ...)")
    args = ap.parse_args(argv)

    root = Path(os.path.expanduser(args.path)).resolve()
    if not root.is_dir():
        raise CliError(f"{args.path!r} is not a directory (resolved to {root})")
    try:
        project = projects.claim(args.name or root.name, root)
    except ValueError as e:   # invalid name, or NameTaken
        raise CliError(str(e))

    project_map = build_map(project.name, root)
    project_map["generated"] = store.now()
    project.save_map(project_map)
    project.save()

    langs = ", ".join(f"{k} ({v})" for k, v in project_map["languages"].items()) or "none detected"
    print(f"Mapped {project.name}: {project_map['files_total']} files, {len(project_map['sections'])} sections; languages: {langs}")
    for sec, info in project_map["sections"].items():
        print(f"  {sec:<28} {info['files']:>5} files  {', '.join(info['languages']) or '-'}")

    if not args.no_import:
        total = trainer.TrainStats()
        for rel in KNOWN_INSTRUCTION_FILES:
            target = root / rel
            if target.exists():
                total.merge(trainer.train(project, target, base=root))
        if total.files:
            print(f"Imported {total.added} rule(s) from {total.files} existing instruction file(s) "
                  f"({total.duplicate} duplicates skipped)")

    print(f"Memory: {project.dir}")
    print(f"Next: train.py --name {project.name} --from <folder>   |   review.py --name {project.name} list")
    return 0
