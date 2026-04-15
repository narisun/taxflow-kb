import os
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Use mock extractor in tests (fake PDF bytes don't have text layers)
os.environ.setdefault("OCR_EXTRACTOR", "mock")
from api.db.base import Base
from api.db.engine import get_session
from api.auth.models import OrganizationModel, UserModel  # noqa: F401
from api.db.models import ClientModel, DocumentModel, ChatMessageModel, TaxReturnDraftModel, ManualEntryModel, FamilyGroupModel, DependentModel  # noqa: F401
from api.main import create_app


@pytest.fixture
async def app():
    # Use in-memory SQLite for tests
    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()

    async def override_session():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    yield app

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
