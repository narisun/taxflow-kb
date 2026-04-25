"""Shared router helpers.

The canonical implementation of :func:`get_client_or_404` now lives in
:mod:`api.db.queries` (data-access layer). This module re-exports it so
existing router imports keep working without a mass-rename.
"""
from api.db.queries import get_client_or_404  # noqa: F401
