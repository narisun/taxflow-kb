"""Shared fixtures for API tests.

Design notes:
- Each test gets a fresh in-memory SQLite DB (fast, isolated).
- OCR is overridden to the :class:`MockOCRExtractor` via DI, not env vars.
- Two client fixtures:

    ``client``                — current-user falls back to the seeded dev user
                                (exercises the dev-mode auth code path).
    ``authenticated_client``  — FastAPI dependency for ``get_current_user`` is
                                overridden to return a pre-seeded ``UserModel``.
                                Preferred for new tests as it exercises the
                                real dependency graph with a stable, known
                                identity.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.auth.dependencies import get_current_user
from api.auth.models import OrganizationModel, UserModel
from api.db.base import Base
from api.db.engine import get_session
from api.dependencies import get_ocr_extractor
from api.main import create_app
from api.services.ocr.mock_extractor import MockOCRExtractor

# Registering all model modules ensures Base.metadata.create_all picks them up.
from api.db.models import (  # noqa: F401
    ChatMessageModel,
    ClientModel,
    ConversationMessageModel,
    ConversationModel,
    DependentModel,
    DocumentModel,
    FamilyGroupModel,
    ManualEntryModel,
    TaxReturnDraftModel,
)


@pytest.fixture
async def app():
    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    test_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()

    async def override_session():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    # Force mock OCR regardless of host env.
    app.dependency_overrides[get_ocr_extractor] = lambda: MockOCRExtractor()

    # Expose the session factory to fixtures that want to seed data.
    app.state.test_session_factory = test_session

    yield app

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def seeded_user(app) -> UserModel:
    """Insert a deterministic org + admin user into the test DB and return it.

    Independent of the dev-user fallback so tests know exactly who they are.
    """
    session_factory = app.state.test_session_factory
    async with session_factory() as session:
        org = OrganizationModel(
            name="Test CPA Firm", slug="test-firm", plan="professional"
        )
        session.add(org)
        await session.flush()

        user = UserModel(
            org_id=org.id,
            auth0_sub="auth0|test-admin",
            email="admin@test-firm.example",
            name="Test Admin",
            role="admin",
            onboarding_status="complete",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def authenticated_client(app, seeded_user):
    """A client whose requests are authenticated as ``seeded_user``.

    Overrides :func:`api.auth.dependencies.get_current_user` — the full HTTP
    stack still runs, including ``require_role`` checks.
    """
    async def _override_current_user() -> UserModel:
        # Re-attach to a fresh session so downstream mutations persist.
        session_factory = app.state.test_session_factory
        async with session_factory() as session:
            merged = await session.merge(seeded_user)
            await session.commit()
            return merged

    app.dependency_overrides[get_current_user] = _override_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)
