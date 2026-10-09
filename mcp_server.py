#!/usr/bin/env python3
"""MCP server (stdio, stdlib only) exposing lore to Copilot and other MCP clients.

Tools:
  get_rules(paths)       rules for the files about to be edited (call BEFORE editing)
  record_feedback(rule)  save a correction as a pending rule (call when the user corrects you)

The project is detected from the file paths, so one global registration serves every
project registered with memorize.py. Logs go to stderr; stdout is protocol only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import rules
import store
from mapper import section_of

VERSION = "0.1.0"

TOOLS = [
    {
        "name": "get_rules",
        "description": (
            "Return the project's coding rules that apply to the given files. Call this BEFORE "
            "creating or editing any file, passing every file path you are about to change. "
            "Follow the returned rules; if a rule conflicts with the request, ask the user."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"},
                          "description": "Absolute or workspace-relative paths of files to edit or create."},
                "max_tokens": {"type": "integer", "description": "Budget for the answer (default 800)."},
            },
            "required": ["paths"],
        },
    },
    {
        "name": "record_feedback",
        "description": (
            "Save a lesson as a PENDING rule when the user corrects your code or states a standard "
            "you violated. Write it as one short, imperative, generalizable sentence (what to do or "
            "avoid), not a description of this one edit. The user approves it before it takes effect."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule": {"type": "string", "description": "e.g. 'Use the repository layer for DB access; never query from route handlers.'"},
                "paths": {"type": "array", "items": {"type": "string"},
                          "description": "Files the correction concerned; used to find the project and default scope."},
                "scope": {"type": "string", "description": "global | section:<name> | glob:<pattern,...>. Default: section of the first path, else global."},
                "evidence": {"type": "string", "description": "The user's wording of the correction."},
            },
            "required": ["rule", "paths"],
        },
    },
]


def log(*a):
    print("[lore]", *a, file=sys.stderr, flush=True)


def locate(paths: list[str]) -> tuple[dict | None, list[str]]:
    """Find the registered project for these paths and return (meta, project-relative paths)."""
    cwd = os.getcwd()
    for p in paths:
        ab = os.path.abspath(os.path.join(cwd, os.path.expanduser(p)))
        meta = store.find_project_for_path(ab)
        if meta:
            root = meta["root"]
            rels = []
            for q in paths:
                aq = os.path.abspath(os.path.join(cwd, os.path.expanduser(q)))
                rels.append(os.path.relpath(aq, root).replace(os.sep, "/") if aq.startswith(root) else q.lstrip("/"))
            return meta, rels
    # relative paths with an unrelated cwd: accept a project only if exactly one contains them
    cands = [m for m in store.list_projects() if any((Path(m["root"]) / p).exists() for p in paths if not os.path.isabs(p))]
    if len(cands) == 1:
        return cands[0], [p.lstrip("./") for p in paths]
    return None, paths


def call_get_rules(args: dict) -> str:
    paths = args.get("paths") or []
    meta, rels = locate(paths)
    if not meta:
        return "No lore project matches these paths (run memorize.py --path <project> to register one). Proceed normally."
    res = rules.resolve(meta["name"], rels, int(args.get("max_tokens") or 800))
    return res["text"] or f"No rules apply to {', '.join(res['sections'])} in `{meta['name']}` yet."


def call_record_feedback(args: dict) -> str:
    paths = args.get("paths") or []
    meta, rels = locate(paths)
    if not meta:
        return "Not saved: no lore project matches these paths."
    try:
        if args.get("scope"):
            scope = rules.parse_scope(args["scope"])
        elif rels:
            scope = {"type": "section", "value": section_of(rels[0])}
            if scope["value"] == "root":
                scope = {"type": "global"}
        else:
            scope = {"type": "global"}
        rule, outcome = rules.add_rule(meta["name"], args["rule"], scope, status="pending",
                                       source="feedback", evidence=args.get("evidence", ""))
    except (ValueError, KeyError) as e:
        return f"Not saved: {e}"
    if outcome == "duplicate":
        return f"Already known (rule {rule['id']}, status {rule['status']}); no change."
    return f"Saved as pending rule {rule['id']} ({rules.scope_key(scope)}). The user approves it with review.py."


HANDLERS = {"get_rules": call_get_rules, "record_feedback": call_record_feedback}


def handle(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification
        return None
    def ok(result): return {"jsonrpc": "2.0", "id": mid, "result": result}
    def err(code, text): return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}

    if method == "initialize":
        ver = (msg.get("params") or {}).get("protocolVersion") or "2024-11-05"
        return ok({"protocolVersion": ver, "capabilities": {"tools": {}},
                   "serverInfo": {"name": "lore", "version": VERSION}})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        fn = HANDLERS.get(params.get("name"))
        if not fn:
            return err(-32602, f"unknown tool {params.get('name')!r}")
        try:
            text, is_err = fn(params.get("arguments") or {}), False
        except Exception as e:  # tool failures are results, not protocol errors
            log("tool error:", repr(e))
            text, is_err = f"lore error: {e}", True
        return ok({"content": [{"type": "text", "text": text}], "isError": is_err})
    return err(-32601, f"method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            resp = handle(json.loads(line))
        except json.JSONDecodeError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
