<p align="center">
  <img src="assets/logo.svg" width="120" alt="Lore logo">
</p>

<h1 align="center">Lore</h1>

<p align="center">
  <b>Your coding rules, remembered per project and handed to your AI agent right before it edits. </b><br>
   Local. No dependencies. No extra LLM calls.
</p>

<p align="center">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-6b5fd6">
  <img alt="Dependencies: none" src="https://img.shields.io/badge/dependencies-none-2ea44f">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-ready-ff9e5e">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue">
</p>

---

## Why

Agents forget your standards and repeat the mistakes you already corrected. Long instruction files fix that badly:
they are noisy, they go stale, and the model skims them.

Lore keeps a small set of **rules per project** and gives the agent **only the ones that apply to the files it is
about to change**. After a one-minute setup you don't run anything: the agent registers projects, learns rules from your
corrections and your code review, and fetches the right ones before each edit.

> Lore is retrieval memory, not model training. Rules are plain JSON you can read, edit and delete.

## Set it up (once)

Requires Python 3.10+.

```bash
git clone <this repo> ~/projects/lore
python3 ~/projects/lore/install.py
```

That connects Lore to Claude Code and Copilot CLI if they are installed (`--client claude|copilot` to pick one,
`--dry-run` to preview, `--uninstall` to undo). Start a new agent session and you're done.

From then on:

- **Projects register themselves** the first time an agent works in a git repository.
- **The agent gets its instructions from Lore** when it connects. There is nothing to paste into config files.
- **Rules learn themselves.** When you correct the agent it saves a rule. On a new project it reads the code, and your
  pull-request review comments if `gh` is set up, and saves the conventions worth keeping. It also writes the title and
  trigger words that decide when each rule is sent, so you never pin or tag anything.
- **Each edit gets only the rules it needs**, not the whole list, and never the same rule twice in a session.

```
 you correct the agent ─┐
 your code ─────────────┼─▶ agent proposes rules ─▶ Lore screens them ─▶ active ─▶ get_rules(paths, task) before each edit
 PR review comments ────┘                                  │
                                                           └─ flagged ─▶ waits for you
```

<p align="center">
  <img width="900" alt="Lore web UI" src="https://github.com/user-attachments/assets/6ad8b77a-cb79-4998-af07-07036a223f93" />
</p>

You only need to look when something is flagged. `python3 serve.py` opens a simple dark UI to browse, edit or delete rules,
and `python3 review.py --name myapp list --auto` shows what Lore activated by itself.

## Safe by default

Rules the agent proposes are **activated automatically only in your own repositories, and only if they pass screening**.
Everything is reversible:

- **Your repositories only.** A repository counts as yours when it has no remote, or when your `gh` login can push to it.
  In anything else (a project you cloned from someone else, another git host) rules wait for you, and Lore does not read
  its review comments by itself. `review.py --name myapp trust` / `untrust` overrides that.
- **The project you're working on.** Rules are saved to the project whose files the agent is editing, never to another
  one by name, and are only activated there.

- **Screened.** A rule waits for you if it looks like an attack on the agent ("ignore previous instructions", `curl | sh`,
  key files, links), if it may contradict an existing rule, or if its text hides characters. Hidden Unicode, HTML comments
  and anything over 500 characters are refused outright.
- **Limited.** At most 25 rules can be activated automatically per session (`auto_limit`).
- **Visible and undoable.** The agent tells you what it saved. Each one is marked *auto-activated* in the UI and in
  `review.py list`, and `review.py --name myapp reject <id>` removes it.
- **Only your team counts.** Review comments from people outside the repository's team (owners, members, collaborators)
  are ignored, because anyone can comment on a public repo. Instruction files already in a repository are not imported
  automatically.
- **You can turn it off.** `python3 install.py --approval manual` makes every proposed rule wait for your approval.

This is a trade-off: a screened rule is not a reviewed rule, and the screening is simple pattern matching. If you work in
repositories you don't trust, use manual mode. Details in [SECURITY.md](SECURITY.md).

Also: contradictions are flagged rather than merged, the agent sees a one-line title for every rule it didn't get so it can
ask for one, and everything is stored locally in `~/.lore` (set `LORE_HOME` to move it).

## Settings

`~/.lore/config.json`, all optional:

```json
{ "approval": "auto", "auto_register": true, "auto_limit": 25 }
```

`approval` is `auto` or `manual`, `auto_register` controls whether git projects register themselves, `auto_limit` caps
automatic activations per session. `LORE_APPROVAL=manual` overrides the file for one run.

## By hand

Everything the agent does is also available as commands, for scripting or when you'd rather decide yourself:

```bash
python3 memorize.py --path ~/projects/myapp           # register a project
python3 discover.py --name myapp --save               # infer rules from its code (pending)
python3 learn.py --name myapp --pr 120 --save         # rule drafts from one pull request (pending)
python3 review.py --name myapp list --status pending  # read them
python3 review.py --name myapp approve --all          # asks first; never bulk-approves risky-looking rules
```

VS Code: add the server (`python3 /path/to/lore/mcp_server.py`, type stdio) to your user MCP configuration; the full guide
walks through it.

## Learn more

The detailed guide has every command, option, troubleshooting tips and the repo layout:
**[README-overly-explained.md](README-overly-explained.md)**.

## Contributing

Contributions are welcome, and adding a convention marker for your favourite language is a great first one.
See [CONTRIBUTING.md](CONTRIBUTING.md). Run the tests with `python3 -m unittest discover -s tests`.

## License

[MIT](LICENSE)
