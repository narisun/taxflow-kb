"""Alembic environment.

Wired to:
* pull the DB URL from :class:`api.config.Settings` (the same source the app
  uses) — keeps migrations and runtime in lock-step
* import every ORM module so ``Base.metadata`` carries every table — this is
  what ``--autogenerate`` diffs against the live DB
"""
from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Make the project root importable so we can pick up `api.*` modules.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Importing the models registers them on Base.metadata. ORDER MATTERS only for
# autogenerate determinism (alphabetical) — runtime FK resolution is fine.
from api.config import get_settings  # noqa: E402
from api.db.base import Base  # noqa: E402
from api.auth import models as _auth_models  # noqa: E402, F401
from api.db import models as _domain_models  # noqa: E402, F401

config = context.config

# Override sqlalchemy.url from our Settings so .env / vault sources flow
# through to migrations the same way they do at runtime.
config.set_main_option("sqlalchemy.url", get_settings().app_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection (e.g. for CI dry-runs)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against either a caller-supplied connection or a fresh one.

    The app's startup hook (``api.db.engine.init_db``) passes its existing
    sync-bound connection via ``cfg.attributes["connection"]``. Running
    Alembic standalone (``alembic upgrade head`` from the shell) takes the
    async path and opens its own engine.
    """
    connection = config.attributes.get("connection")
    if connection is not None:
        do_run_migrations(connection)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
