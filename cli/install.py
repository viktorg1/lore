"""Connect Lore to the agents on this machine, once. After that nothing needs doing.

    install.py                      # detect Claude Code and Copilot CLI and set up what is found
    install.py --client claude      # only Claude Code           (or: copilot)
    install.py --approval manual    # rules the agent proposes wait for you (default: auto, with safety screening)
    install.py --dry-run            # show what would change
    install.py --uninstall          # remove what this script added

Claude Code gets the server (`claude mcp add`); the server sends its own instructions when it connects, so no instruction
file is written. Copilot CLI gets an entry in ~/.copilot/mcp-config.json and a marked block in
~/.copilot/copilot-instructions.md. VS Code: add the server to your user MCP configuration by hand (see the README).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from core import config, instructions, store

from .common import CliError, entry, make_parser

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server.py"
BEGIN, END = "<!-- lore:begin (managed by install.py) -->", "<!-- lore:end -->"

def _say(message: str) -> None:
    print(message)

def claude(dry: bool, uninstall: bool) -> None:
    binary = shutil.which("claude")
    if not binary:
        return _say("Claude Code: not found on PATH, skipped.")
    current = subprocess.run([binary, "mcp", "get", "lore"], capture_output=True, text=True)
    installed = current.returncode == 0
    if uninstall:
        if not installed:
            return _say("Claude Code: Lore was not installed.")
        _say("Claude Code: would remove the lore server." if dry else "Claude Code: removed the lore server.")
        if not dry:
            subprocess.run([binary, "mcp", "remove", "lore", "-s", "user"], capture_output=True, text=True)
        return
    if installed and str(SERVER) in current.stdout:
        return _say("Claude Code: already set up.")
    command = [binary, "mcp", "add", "--scope", "user", "lore", "--", sys.executable, str(SERVER)]
    if dry:
        return _say("Claude Code: would run: " + " ".join(command))
    if installed:
        subprocess.run([binary, "mcp", "remove", "lore", "-s", "user"], capture_output=True, text=True)
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0:
        raise CliError("claude mcp add failed: " + (done.stderr.strip() or done.stdout.strip()))
    _say("Claude Code: server added (it sends Lore's instructions itself; nothing else to write).")

def _write_block(path: Path, text: str | None) -> bool:
    """Put `text` between our markers in `path`, keeping everything else (or remove the block when text is None).

    True if the file changed.
    """
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if BEGIN in old and END in old:
        before, rest = old.split(BEGIN, 1)
        after = rest.split(END, 1)[1]
    else:
        before, after = old, ""
    block = f"{BEGIN}\n{text}\n{END}" if text is not None else ""
    parts = [p for p in (before.strip("\n"), block, after.strip("\n")) if p]
    new = "\n\n".join(parts) + ("\n" if parts else "")
    if new == old:
        return False
    if not parts:
        path.unlink(missing_ok=True)         # nothing else was in the file
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8")
    return True

def copilot(dry: bool, uninstall: bool, home: Path) -> None:
    folder = home / ".copilot"
    if not folder.exists() and not shutil.which("copilot"):
        return _say("Copilot CLI: not found, skipped.")
    mcp_path, doc_path = folder / "mcp-config.json", folder / "copilot-instructions.md"
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8")) if mcp_path.exists() else {}
    except ValueError:
        raise CliError(f"{mcp_path} is not valid JSON; fix or remove it, then run this again")
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise CliError(f"{mcp_path} is not a JSON object with an \"mcpServers\" object; fix or remove it, then run this again")
    servers = data.setdefault("mcpServers", {})
    entry_ = {"type": "local", "command": sys.executable, "args": [str(SERVER)], "env": {}, "tools": ["*"]}
    if uninstall:
        _say(f"Copilot CLI: would remove Lore from {mcp_path} and {doc_path}." if dry else "Copilot CLI: removed Lore.")
        if not dry:
            if "lore" in servers:
                del servers["lore"]
                store.save_json(mcp_path, data)
            _write_block(doc_path, None)
        return
    if dry:
        return _say(f"Copilot CLI: would add the lore server to {mcp_path} and a marked block to {doc_path}.")
    changed = servers.get("lore") != entry_
    servers["lore"] = entry_
    if changed:
        store.save_json(mcp_path, data)
    changed |= _write_block(doc_path, instructions.text(config.load().approval))
    _say("Copilot CLI: " + ("set up." if changed else "already set up."))

@entry
def main(argv=None) -> int:
    ap = make_parser(__doc__)
    ap.add_argument("--client", choices=["auto", "claude", "copilot"], default="auto")
    ap.add_argument("--approval", choices=["auto", "manual"], help="save this approval mode in ~/.lore/config.json")
    ap.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args(argv)

    if args.approval and not args.dry_run and not args.uninstall:
        config.save(approval=args.approval)          # first: the Copilot instruction block below depends on it
        _say(f"Approval mode: {args.approval}.")
    if args.client in ("auto", "claude"):
        claude(args.dry_run, args.uninstall)
    if args.client in ("auto", "copilot"):
        copilot(args.dry_run, args.uninstall, Path.home())
    if not args.uninstall and not args.dry_run:
        _say("Done. Start a new agent session; projects register themselves the first time an agent works in them.")
    return 0
