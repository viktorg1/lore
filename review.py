#!/usr/bin/env python3
"""Entry point; the implementation (and --help text) lives in cli/review.py."""
import sys

from cli.review import main

if __name__ == "__main__":
    sys.exit(main())
