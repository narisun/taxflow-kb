"""Identity tokens for domain entities.

We use UUIDv7 (RFC 9562) for every domain entity primary key. The reasoning:

* **Globally unique.** Mock data, dev DB rows, and prod rows can never collide
  on a small integer the way they did when ids were sequential. The class of
  bug that surfaced as "client #6 ⇒ Marcus Williams" (a hardcoded mock dict
  keyed on the integer 6) is impossible with random 128-bit identifiers.

* **Time-ordered prefix.** UUIDv7 packs a millisecond timestamp into the high
  bits, so newly-inserted rows still cluster together in B-tree indexes. We
  get write-locality close to a sequential int without leaking a row count.

* **Schema-portable.** Stored as ``String(36)`` rather than the Postgres
  ``uuid`` type so the same models work against SQLite (in tests) without a
  dialect-specific column type.

Generation lives in one place so the policy is easy to swap (e.g. to a
prefixed string like ``cli_<uuid>`` later) without touching the models.
"""
from __future__ import annotations

from uuid6 import uuid7


def new_uuid() -> str:
    """Return a stringified UUIDv7 (length 36, lowercase hex with dashes)."""
    return str(uuid7())
