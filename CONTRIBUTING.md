# Contributing to Lore

Thanks for helping. Lore is small on purpose, so most contributions are short. This page tells you how to get set up,
where things live, and what a good change looks like.

## Ground rules

- **Standard library only.** No third-party dependencies. If you think one is needed, open an issue first.
- **Python 3.10+.** Nothing else to install.
- **Stay small and local.** No background LLM calls, no network use beyond `gh` for review import, and nothing
  inferred or suggested takes effect until a person approves it (rules start as *pending*).
- **Rule text is untrusted.** Anything that stores, shows or serves rule text goes through `core/sanitize.py`. Don't add a
  path that skips it.

## Set up

```bash
git clone <your fork> && cd lore
python3 -m unittest discover -s tests      # should be all green
```

There is nothing to build. Scripts run straight from the checkout (`python3 review.py ...`). To avoid touching your real
rules while trying things, point Lore at a scratch folder:

```bash
export LORE_HOME=$(mktemp -d)
```

## Where things live

| Folder | What it is | May import |
| --- | --- | --- |
| `core/` | Rules, scopes, storage, resolver, export | nothing of Lore's own |
| `discovery/` | Infers rules from code (languages, frameworks, markers) | `core` |
| `reviews/` | Turns PR review comments into proposals | `core` |
| `cli/`, `web/`, `mcpserver/` | The interfaces | everything above |
| root `*.py` | Thin wrappers (16 lines or fewer) that call into `cli/` | |

Layers only depend downwards. `tests/test_architecture.py` fails if you break that. The full tour is in
[README-overly-explained.md](README-overly-explained.md#layout-of-this-repo).

## Easiest first contributions

**Add a convention marker** (a rule Lore can detect from code). Pick the kind that fits and add it to the language or
framework file in `discovery/languages/` or `discovery/frameworks/`:

| Kind | Fires when |
| --- | --- |
| `FileMarker` | almost every applicable file contains a pattern |
| `OccurrenceMarker` | almost every occurrence of X is also Y |
| `AbsentMarker` | almost no non-test file contains a pattern |
| `ChoiceMarker` | one of several styles clearly dominates |

```python
AbsentMarker(id="py-assert", glob="**/*.py", bad=r"^\s*assert\b",
             rule="Raise exceptions instead of using assert in application code."),
```

Marker ids must be unique (a test checks). Write the rule as one short, imperative sentence. Add a test in
`tests/test_discovery.py` with a small fixture project that triggers it and one that doesn't.

**Add a language or framework.** A new file in `discovery/languages/` exports `LANGUAGE = Language(...)`; a framework is
a `Framework(...)` in `discovery/frameworks/`. Both folders are scanned automatically. Look at an existing file and copy it.

**Improve the docs, fix a bug, add a test.** All welcome. If you have your own idea, open an issue and say what you'd like to change.

## Making a change

1. Open an issue first for anything bigger than a small fix, so we agree on the approach.
2. Fork the repo on GitHub, clone your fork, and create a branch in it from `main`. Keep the change focused, one thing per pull request.
3. Add or update tests. Bug fixes need a test that fails without the fix.
4. Run `python3 -m unittest discover -s tests` and make sure it passes.
5. If behaviour changes, update `README.md` (short) and `README-overly-explained.md` (detailed).
6. Push the branch to your fork, then open a pull request from it to this repo's `main` and fill in the template.

## Style

- Match the code around you: naming, comment density, type hints, `from __future__ import annotations`.
- Comments explain *why*, not what. Keep docstrings short.
- Prefer a plain function or small dataclass over a framework or abstraction.
- Keep the web UI dark and simple.

## Security

Lore feeds text to an AI agent, so rule text is a prompt-injection surface. If you find a way to get hidden or
misleading text into what an agent receives, or to write outside the project or `~/.lore`, please report it privately.
See [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your work is released under the [MIT License](LICENSE).
