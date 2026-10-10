#!/usr/bin/env python3
"""MCP server (stdio, stdlib only) exposing lore to Copilot and other MCP clients.

Tools:
  get_rules(paths)       rules for the files about to be edited (call BEFORE editing)
  record_feedback(rule)  save a correction as a pending rule (call when the user corrects you)

The project is detected from the file paths, so one global registration serves every project
registered with memorize.py. Logs go to stderr; stdout is protocol only.
Implementation: the mcpserver/ package.
"""
import sys

from mcpserver import main

if __name__ == "__main__":
    sys.exit(main())
