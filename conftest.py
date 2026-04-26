"""Root conftest.py — runs before any test module is collected.

Two responsibilities:

1. Add project root to ``sys.path`` so ``api`` / ``taxkb`` imports work.
2. Load ``tests/.env.test`` into ``os.environ`` BEFORE the first import of
   ``api.config`` or ``taxkb.config`` (their Settings classes are strict
   and refuse to instantiate without all required vars).

If ``tests/.env.test`` is missing the test session aborts with a clear error.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# ─── Load the test environment file BEFORE any application import ────────
_TEST_ENV = _root / "tests" / ".env.test"
if not _TEST_ENV.exists():
    sys.stderr.write(
        f"\nFATAL: Required test config file is missing: {_TEST_ENV}\n"
        f"This file provides the env vars that pydantic-settings needs to "
        f"instantiate api.config.Settings and taxkb.config.Settings.\n"
        f"See .env.example for the full variable list.\n\n"
    )
    raise SystemExit(2)

# Use python-dotenv (transitive dep of pydantic-settings) to populate
# os.environ. We pass override=True so .env.test wins over the developer's
# personal .env when running the test suite.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_TEST_ENV, override=True)

# Print the active test config once per session so test runs are auditable.
def pytest_configure(config) -> None:  # noqa: D401
    """Pytest hook: print Settings banner at session start."""
    if config.getoption("verbose") < 0:
        return
    try:
        from api.config import print_settings_banner

        print_settings_banner(title="TaxFlow AI — Test Session (api Settings)")
    except Exception as exc:  # pragma: no cover — defensive
        sys.stderr.write(f"[conftest] Could not print API banner: {exc}\n")
