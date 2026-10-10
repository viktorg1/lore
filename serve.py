#!/usr/bin/env python3
"""Entry point; the implementation lives in the web/ package."""
import sys

from web.server import main

if __name__ == "__main__":
    sys.exit(main())
