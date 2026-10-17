"""Learn from code review: turn recurring pull-request comments into pending rules.

    learn.py --name myapp                  # preview the themes reviewers keep repeating (last 90 days)
    learn.py --name myapp --save           # save them as PENDING rules; reword and approve with review.py
    learn.py --name myapp --pr 120 --pr 124-130 --min-repeats 2      # read exactly these pull requests
    learn.py --name myapp --since 30 --min-repeats 2 --reviewer alice --repo owner/name

Reads inline review comments of the project's GitHub repository through the GitHub CLI (`gh`, logged in):
the recent ones, or exactly the pull requests you name with --pr (a number, a list "12,15" or a range "15-18";
repeatable). Comments that say the same thing on several pull requests become one proposal, scoped to the files
they were about and linked to the comments behind it. The wording is the reviewers', not yours: edit it before
approving. Comments already proposed are remembered, so a rejected proposal stays rejected.
"""
from __future__ import annotations

from reviews import GhError, LearnOptions, learn, parse_pr_numbers

from .common import CliError, entry, load_project, make_parser

@entry
def main(argv=None) -> int:
    ap = make_parser(__doc__)
    ap.add_argument("--name", required=True, help="memory name (as given to memorize.py)")
    ap.add_argument("--save", action="store_true", help="store the proposals as pending rules (default is preview only)")
    ap.add_argument("--pr", action="append", default=[], metavar="N",
                    help="read only these pull requests (12, 12,15 or 15-18; repeatable). Ignores --since")
    ap.add_argument("--since", type=int, default=90, help="without --pr: only comments from the last N days (default 90)")
    ap.add_argument("--min-repeats", type=int, default=1, help="similar comments needed for a proposal (default 1: every actionable comment)")
    ap.add_argument("--min-prs", type=int, default=None,
                    help="distinct pull requests they must span (default 1)")
    ap.add_argument("--limit", type=int, default=300, help="most comments to read (default 300)")
    ap.add_argument("--repo", help="OWNER/NAME (default: the repository of the project's git checkout)")
    ap.add_argument("--reviewer", action="append", default=[], metavar="LOGIN", help="only comments by this reviewer (repeatable)")
    ap.add_argument("--include-bots", action="store_true", help="also use comments written by bots")
    ap.add_argument("--include-external", action="store_true",
                    help="also use comments by people outside the repository's team (default: owners, members, collaborators)")
    ap.add_argument("--include-seen", action="store_true", help="propose comments that were proposed before too")
    args = ap.parse_args(argv)

    project = load_project(args.name)
    if not project.root.is_dir():
        raise CliError(f"project root {project.root} no longer exists")
    try:
        options = LearnOptions(prs=parse_pr_numbers(*args.pr), since_days=args.since, min_repeats=args.min_repeats,
                               min_prs=args.min_prs, limit=args.limit, repo=args.repo, reviewers=args.reviewer,
                               include_bots=args.include_bots, include_seen=args.include_seen,
                               include_external=args.include_external, save=args.save)
        result = learn(project, options)
    except (ValueError, GhError) as e:
        raise CliError(str(e))
    print(result.report(project.name))
    return 0
