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

import json
from pathlib import Path

import discovery
from core.models import Status
from core.projects import Project
from core.repository import RuleRepository
from core.trainer import TrainStats

from .common import CliError, entry, load_project, make_parser

KIND_ORDER = ("config", "stats", "marker", "framework")


def print_candidates(candidates: list[discovery.Candidate]) -> None:
    for kind in KIND_ORDER:
        group = [c for c in candidates if c.kind == kind]
        if group:
            print(f"\n== {kind} ({len(group)}) ==")
        for c in group:
            print(f"[{c.scope.key}] {c.text}\n    evidence: {c.evidence}")


def save_candidates(project: Project, candidates: list[discovery.Candidate], status: Status) -> TrainStats:
    repo, stats = RuleRepository(project.name), TrainStats()
    for c in candidates:
        stats.count(repo.add(c.text, c.scope, status, source="discover", evidence=c.evidence).outcome)
    return stats


@entry
def main(argv=None) -> int:
    ap = make_parser(__doc__)
    ap.add_argument("--name", required=True, help="memory name (as given to memorize.py)")
    ap.add_argument("--save", action="store_true", help="store the candidates (default is preview only)")
    ap.add_argument("--activate", action="store_true", help="with --save: make rules active immediately")
    ap.add_argument("--min-ratio", type=float, default=0.9, help="how lopsided the evidence must be (default 0.9)")
    ap.add_argument("--min-files", type=int, default=5, help="minimum files of evidence (default 5)")
    ap.add_argument("--markers", help="JSON file with extra pattern markers (kind: file|occ|absent|choice; see discovery/markers.py)")
    args = ap.parse_args(argv)

    project = load_project(args.name)
    extra = json.loads(Path(args.markers).read_text()) if args.markers else []
    if not project.root.is_dir():
        raise CliError(f"project root {project.root} no longer exists")

    candidates = discovery.discover(project.root, args.min_ratio, args.min_files, extra)
    if not candidates:
        print("No lopsided conventions found (try --min-ratio 0.8).")
        return 0
    print_candidates(candidates)

    if not args.save:
        print(f"\n{len(candidates)} candidate rule(s). Re-run with --save to store them as pending.")
        return 0
    status = Status.ACTIVE if args.activate else Status.PENDING
    stats = save_candidates(project, candidates, status)
    print(f"\nSaved {stats.added} new {status} rule(s); {stats.duplicate} already known.")
    print(f"Next: review.py --name {args.name} list --status pending")
    return 0
