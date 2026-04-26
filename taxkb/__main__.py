#!/usr/bin/env python3
"""TaxKB CLI entry point.

Invoke with:
    python -m taxkb ingest --csv ...
    make kb.ingest
"""
import sys

from taxkb.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
