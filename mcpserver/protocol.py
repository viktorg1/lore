"""A minimal MCP server over stdio (newline-delimited JSON-RPC 2.0), stdlib only. Knows nothing about lore."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Callable, TextIO

DEFAULT_PROTOCOL_VERSION = "2024-11-05"


def log(*args) -> None:
    """Logs go to stderr; stdout is protocol only."""
    print("[lore]", *args, file=sys.stderr, flush=True)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], str]

    def listing(self) -> dict:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


class McpServer:
    def __init__(self, name: str, version: str, tools: list[Tool]):
        self.name, self.version = name, version
        self.tools = {t.name: t for t in tools}

    def handle(self, msg: dict) -> dict | None:
        """The reply to one JSON-RPC message, or None for notifications."""
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:
            return None

        def ok(result):
            return {"jsonrpc": "2.0", "id": mid, "result": result}

        def err(code, text):
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}

        if method == "initialize":
            version = (msg.get("params") or {}).get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
            return ok({"protocolVersion": version, "capabilities": {"tools": {}},
                       "serverInfo": {"name": self.name, "version": self.version}})
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": [t.listing() for t in self.tools.values()]})
        if method == "tools/call":
            params = msg.get("params") or {}
            tool = self.tools.get(params.get("name"))
            if tool is None:
                return err(-32602, f"unknown tool {params.get('name')!r}")
            try:
                text, is_error = tool.handler(params.get("arguments") or {}), False
            except Exception as e:  # tool failures are results, not protocol errors
                log("tool error:", repr(e))
                text, is_error = f"{self.name} error: {e}", True
            return ok({"content": [{"type": "text", "text": text}], "isError": is_error})
        return err(-32601, f"method not found: {method}")

    def serve(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
        stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                reply = self.handle(json.loads(line))
            except json.JSONDecodeError:
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            if reply is not None:
                stdout.write(json.dumps(reply) + "\n")
                stdout.flush()
        return 0
