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
- Keeps everything inferred or suggested *pending* until a person approves it.
- Asks for confirmation before `review.py approve --all`, and never bulk-approves a rule that looks like an attack on the
  agent (a pipe-to-shell command, "ignore previous instructions", key-file paths, web addresses and similar). Those need
  an individual, explicit confirmation in the CLI and in the web UI. This is a tripwire, not a filter: a carefully worded
  malicious rule will not be flagged, so read what you approve.
- Spells out line breaks and hidden characters in folder names before showing them to the agent.
- Refuses to write export files through symlinks or outside the project.
- Binds the web UI to `127.0.0.1` only (the loopback IP, never `0.0.0.0`), so nothing else on your network can reach it.
- Requires a random token on every API call, printed at startup and carried in the URL.
- Accepts only `127.0.0.1:<port>` as the `Host` and `Origin`, not the name `localhost`, which defends against DNS
  rebinding and other websites calling the UI. Open the UI with the printed `127.0.0.1` address.

This is defence in depth, not a guarantee: a visible but malicious instruction still needs a human to judge it.

Not covered: other programs running as you on the same machine can still reach the port, and anything that can read the
token can use it. Treat the UI as a convenience for your own machine, not a service to expose.
