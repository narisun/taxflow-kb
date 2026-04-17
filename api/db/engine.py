"""Async SQLAlchemy engine + lifespan migrations.

On startup we run ``alembic upgrade head`` so the running app and the schema
are always in lock-step. Tests bypass this — they create their own in-memory
SQLite engine via ``Base.metadata.create_all`` (see ``tests/api/conftest.py``).
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _build_engine(settings: Settings):
    return create_async_engine(
        settings.app_database_url,
        echo=False,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle_seconds,
    )


# Module-level engine/session are kept for backwards compatibility with the
# many existing call sites that import them directly. They are built from the
# cached Settings instance, so tests that swap settings before import (or
# override ``get_session`` via FastAPI) can still run against a test DB.
_settings = get_settings()
engine = _build_engine(_settings)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _run_alembic_upgrade(connection) -> None:
    """Synchronous Alembic upgrade — must run inside ``run_sync``.

    Uses Alembic's programmatic API so we don't shell out to the CLI.
    """
    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).resolve().parent.parent.parent
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    # env.py reads sqlalchemy.url from Settings, but Alembic still wants a
    # value here at config-resolution time. The connection-bound override
    # below makes the actual URL irrelevant for this run.
    cfg.set_main_option("sqlalchemy.url", _settings.app_database_url)
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


async def init_db() -> None:
    """Bring the database to the latest schema, then (in non-prod) seed."""
    async with engine.begin() as conn:
        await conn.run_sync(_run_alembic_upgrade)
    logger.info("Alembic upgrade head complete")

    settings = get_settings()
    if settings.app_env != "production":
        from api.db.seed import seed_dev_data

        async with async_session() as session:
            await seed_dev_data(session)


async def get_session():
    """Yield an async session per request."""
    async with async_session() as session:
        yield session


async def get_rls_session(session: AsyncSession, org_id: str) -> AsyncSession:
    """Activate PostgreSQL RLS for this transaction.

    Uses ``SET LOCAL`` so the tenant variable is scoped to the current
    transaction and cannot leak across connection pool reuse. Called by
    routers that have already resolved the authenticated user.
    """
    from sqlalchemy import text
    await session.execute(
        text("SET LOCAL app.current_org_id = :oid"),
        {"oid": org_id},
    )
    return session
