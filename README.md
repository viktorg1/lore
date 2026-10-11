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
about to change**. You stay in control: nothing the tool guesses takes effect until you approve it.

> Lore is retrieval memory, not model training. Rules are plain JSON you can read, edit and delete.

## How it works

```
 your docs ──┐
 your code ──┼──▶  rules (pending / active)  ──▶  you review  ──▶  agent calls get_rules(paths)
 PR reviews ─┘                                                      before it edits
```

| Where rules come from | Command | Starts as |
| --- | --- | --- |
| Rules you write, or your own docs | `train.py`, `review.py add` | active |
| Conventions inferred from the code | `discover.py` | pending |
| Recurring PR review comments | `learn.py` | pending |
| Corrections you give the agent | `record_feedback` (MCP) | pending |
| Existing instruction files | `memorize.py` | pending |

Each rule has a scope: `global`, a folder-level `section`, or a `glob` like `**/*.{ts,tsx}`.
The most specific rules come first.

## Quick start

Requires Python 3.10+.

```bash
git clone <this repo> ~/projects/lore && cd ~/projects/lore

python3 memorize.py --path ~/projects/myapp           # register a project
python3 discover.py --name myapp --save               # infer rules from its code
python3 review.py --name myapp list --status pending  # read them
python3 review.py --name myapp approve --all          # keep what you agree with
```

Prefer a browser? Run `python3 serve.py` and do all of it from a dark, simple UI.

<p align="center">
  <img width="900" alt="Lore web UI" src="https://github.com/user-attachments/assets/6ad8b77a-cb79-4998-af07-07036a223f93" />
</p>

## Connect your agent

Lore is an MCP server with three tools: `get_rules`, `record_feedback`, `learn_from_reviews`.

**Copilot CLI** (`~/.copilot/mcp-config.json`):

```json
{
  "mcpServers": {
    "lore": {
      "type": "local",
      "command": "python3",
      "args": ["/home/YOU/projects/lore/mcp_server.py"],
      "tools": ["*"]
    }
  }
}
```

**VS Code**: add the same server to your user MCP configuration. Both setups are walked through in
[the full guide](README-overly-explained.md#3-connect-your-agent).

Then tell the agent to use it (`~/.copilot/copilot-instructions.md`):

```text
Before creating or editing any file, call get_rules from the lore server with the absolute paths
you are about to change, and follow the rules it returns. When I correct your code, call
record_feedback with one short, general, imperative rule.
```

## Learn from code review

```bash
python3 learn.py --name myapp --pr 120-140 --save
```

Reads inline review comments through the `gh` CLI, groups the ones that keep repeating, and proposes them as
pending rules with links back to the comments. Reject one and it stays rejected.

## Safe by default

- **Pending until you approve.** Anything inferred or suggested has no effect until you say so.
- **Risky rules need a second look.** `approve --all` asks first, and rules that look like attacks ("ignore previous instructions", `curl | sh`, key files, links) are never bulk-approved.
- **No hidden text.** Rules containing invisible Unicode, HTML comments or more than 500 characters are refused.
- **Contradictions are flagged**, not silently merged ("use tabs" next to "use spaces").
- **Small on purpose.** The agent gets at most 20 rules and 2,000 tokens per request.
- **Everything is local** in `~/.lore` (set `LORE_HOME` to move it).

## Learn more

The detailed guide has every command, option, troubleshooting tips and the repo layout:
**[README-overly-explained.md](README-overly-explained.md)**.

## Contributing

Contributions are welcome, and adding a convention marker for your favourite language is a great first one.
See [CONTRIBUTING.md](CONTRIBUTING.md). Run the tests with `python3 -m unittest discover -s tests`.

## License

[MIT](LICENSE)
