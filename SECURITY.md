# Security

Lore hands text to AI agents, so the main risks are prompt injection through rule text and unsafe file writes.

## Report a problem

Please **do not open a public issue** for a vulnerability. Use GitHub's "Report a vulnerability" button on the
repository's Security tab (private advisory). Include what you did, what you expected and what happened.

Good examples of reports: hidden or invisible text reaching an agent, a way to write outside the project or the data
folder, the web UI being driven from another website, a rule being activated without approval.

## What Lore already does

- Rejects rule text with hidden Unicode, HTML comments or more than 500 characters.
- Never serves or exports stored rules that contain hidden characters.
- Screens every rule the agent proposes. By default (`approval: auto`) a rule is activated without a person only if the
  repository is the user's own (no remote, or one the user's `gh` login can push to; see `reviews/trust.py`), the project is
  the one the agent is working on, the rule shows no sign of an attack on the agent, does not contradict an existing rule,
  and is within the per-session limit (`auto_limit`, 25); anything else stays *pending* until a person approves it. Tools
  that save rules decide the project from the files they are given and never accept a project name. Automatically activated rules are marked,
  listed (`review.py list --auto`) and reported by the agent, and `review.py reject <id>` undoes them. Set `approval: manual`
  (`install.py --approval manual`) to make every proposed rule wait. Scripts you run yourself (`discover.py`, `learn.py`,
  `memorize.py`) always save pending rules.
- Uses only review comments written by a repository's owners, members and collaborators (GitHub's `author_association`);
  anyone can comment on a public repository, so outsiders cannot teach Lore unless you pass `--include-external`.
- Registers a git project automatically but never your home folder, `/`, system folders or `~/.lore`, and does not import
  instruction files from a repository it has just met.
- Asks for confirmation before `review.py approve --all`, and never bulk-approves a rule that looks like an attack on the
  agent (a pipe-to-shell command, "ignore previous instructions", key-file paths, web addresses and similar). Those need
  an individual, explicit confirmation in the CLI and in the web UI. This is a tripwire, not a filter: a carefully worded
  malicious rule will not be flagged, so read what you approve.
- Lets the agent set a rule's `title`, `triggers` and `always`, but only as metadata: `tag_rules` never changes text, scope or
  status, can switch `always` on but not off, and the fields are limited in size and refused if they hide characters or look
  like an instruction to the agent. A person can see and change them (`review.py list --details`, the web UI).
- Spells out line breaks and hidden characters in folder names before showing them to the agent.
- Refuses to write export files through symlinks or outside the project.
- Binds the web UI to `127.0.0.1` only (the loopback IP, never `0.0.0.0`), so nothing else on your network can reach it.
- Requires a random token on every API call, printed at startup and carried in the URL.
- Accepts only `127.0.0.1:<port>` as the `Host` and `Origin`, not the name `localhost`, which defends against DNS
  rebinding and other websites calling the UI. Open the UI with the printed `127.0.0.1` address.

This is defence in depth, not a guarantee. In automatic mode a visible but malicious instruction that avoids the risk
patterns can become an active rule without a human seeing it first; the limits above (your repositories only, the project being
worked on, screening, the session cap, team-only review comments, no imports from new repositories, undo) reduce that, they
do not remove it. Text inside your own repository (a dependency's README, a pasted log) can still steer the agent; if that
worries you, use manual mode.

Not covered: other programs running as you on the same machine can still reach the port, and anything that can read the
token can use it. Treat the UI as a convenience for your own machine, not a service to expose.
