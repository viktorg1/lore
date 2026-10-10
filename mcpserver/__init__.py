"""lore as an MCP server: `protocol` is generic JSON-RPC plumbing, `tools` is what lore offers."""
from __future__ import annotations

from .tools import create_server


def main() -> int:
    return create_server().serve()
