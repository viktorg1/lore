"""Train a project's memory on existing instruction documents.

    train.py --name myapp --from ~/docs/standards

Reads every .md/.mdx/.mdc/.txt (and .cursorrules) under the folder (or a single file),
turns bullets into rules, and scopes them from `applyTo:`/`globs:` frontmatter or from
headings that name a project section. Deterministic: it never calls an LLM.
"""
from __future__ import annotations

import os
from pathlib import Path

from core import trainer
from core.export import is_generated
from core.models import Status

from .common import CliError, entry, load_project, make_parser, parse_scope


@entry
def main(argv=None) -> int:
    ap = make_parser(__doc__)
    ap.add_argument("--name", required=True, help="memory name (as given to memorize.py)")
    ap.add_argument("--from", dest="src", required=True, help="folder or file with instructions")
    ap.add_argument("--scope", help="force one scope for everything: global | section:<n> | glob:<pat,...>")
    ap.add_argument("--pending", action="store_true", help="import as pending (review before activating)")
    ap.add_argument("--dry-run", action="store_true", help="print extracted rules, store nothing")
    args = ap.parse_args(argv)

    project = load_project(args.name)
    scope = parse_scope(args.scope) if args.scope else None
    target = Path(os.path.expanduser(args.src)).resolve()
    if not target.exists():
        raise CliError(f"{target} does not exist")

    if args.dry_run:
        sections = project.section_names
        for doc in trainer.find_documents(target):
            text = doc.read_text(encoding="utf-8", errors="replace")
            if is_generated(text):
                continue
            for item in trainer.extract(text, sections):
                print(f"[{(scope or item.scope).key}] {item.text}   ({doc.name})")
        return 0

    stats = trainer.train(project, target, scope_override=scope,
                          status=Status.PENDING if args.pending else Status.ACTIVE)
    print(f"Read {stats.files} file(s): {stats.added} rule(s) added, "
          f"{stats.duplicate} duplicate(s), {stats.promoted} promoted"
          + (f", {stats.skipped_generated} generated file(s) ignored" if stats.skipped_generated else ""))
    print(f"Review with: review.py --name {args.name} list")
    return 0
