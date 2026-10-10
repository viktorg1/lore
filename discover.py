#!/usr/bin/env python3
"""Entry point; the implementation (and --help text) lives in cli/discover.py."""
import sys

from cli.discover import main

if __name__ == "__main__":
    sys.exit(main())
