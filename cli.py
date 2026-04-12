#!/usr/bin/env python3
"""Tax Brain CLI — thin wrapper that delegates to cli/main.py."""
import sys
from cli.main import main

if __name__ == "__main__":
    sys.exit(main())
