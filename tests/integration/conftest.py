"""Fixtures for the Postgres-backed integration suite.

Runs only when explicitly selected:

    pytest -m integration

Configure via ``TEST_DATABASE_URL`` in ``.env`` (or the process env). If
unset, :class:`api.config.Settings` synthesizes
``postgresql+asyncpg://<POSTGRES_USER>:<POSTGRES_PASSWORD>@<POSTGRES_HOST>:<POSTGRES_PORT>/<POSTGRES_DB>_test``
from the shared primitives.

The suite creates a fresh schema in a transaction-isolated database: tables
are created before the session and dropped afterwards.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.auth.dependencies import get_current_user
from api.auth.models import OrganizationModel, UserModel
from api.config import get_settings
from api.db.base import Base
from api.db.engine import get_session
from api.dependencies import get_ocr_extractor
from api.main import create_app
from api.services.ocr.mock_extractor import MockOCRExtractor


def _resolve_db_url() -> str:
    return get_settings().test_database_url


@pytest.fixture
async def _pg_engine():
    """Function-scoped Postgres engine.

    Function scope avoids the pytest-asyncio cross-loop issue for session
    fixtures. The performance cost is small (a few ms of DDL) and keeps each
    test fully isolated.
    """
    url = _resolve_db_url()
    engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except (OperationalError, DBAPIError) as exc:
        await engine.dispose()
        pytest.skip(
            f"Integration DB not reachable at {url}: {exc}. "
            "Set TEST_DATABASE_URL to a running Postgres with the target "
            "database pre-created."
        )
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def pg_app(_pg_engine):
    """Per-test FastAPI app wired to the integration Postgres."""
    session_factory = async_sessionmaker(
        _pg_engine, class_=AsyncSession, expire_on_commit=False
    )

    app = create_app()

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_ocr_extractor] = lambda: MockOCRExtractor()
    app.state.test_session_factory = session_factory
    return app


@pytest.fixture
async def pg_seeded_user(pg_app) -> UserModel:
    factory = pg_app.state.test_session_factory
    async with factory() as session:
        org = OrganizationModel(name="IT Firm", slug="it-firm", plan="enterprise")
        session.add(org)
        await session.flush()
        user = UserModel(
            org_id=org.id,
            auth0_sub="auth0|it-admin",
            email="it-admin@example.com",
            name="Integration Admin",
            role="admin",
            onboarding_status="complete",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def pg_client(pg_app, pg_seeded_user):
    """Authenticated client hitting the Postgres-backed app."""

    async def _override_current_user() -> UserModel:
        factory = pg_app.state.test_session_factory
        async with factory() as session:
            merged = await session.merge(pg_seeded_user)
            await session.commit()
            return merged

    pg_app.dependency_overrides[get_current_user] = _override_current_user
    transport = ASGITransport(app=pg_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    pg_app.dependency_overrides.pop(get_current_user, None)
