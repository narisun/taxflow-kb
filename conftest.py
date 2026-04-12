"""Root conftest.py — ensures the project root is on sys.path."""
import sys
import pathlib

# Ensure the project root is on sys.path so that `api` and other
# top-level packages are importable regardless of how pytest is invoked.
_root = str(pathlib.Path(__file__).resolve().parent)
if _root not in sys.path:
    sys.path.insert(0, _root)
