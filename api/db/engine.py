"""Async SQLAlchemy engine — PostgreSQL for production, configurable via env."""

import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "APP_DATABASE_URL",
    "postgresql+asyncpg://taxflow:taxflow_dev@localhost:5432/taxflow"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables on startup (dev convenience — use Alembic in production)."""
    from api.db.base import Base
    from api.db.models import ClientModel, DocumentModel, ChatMessageModel, TaxReturnDraftModel  # noqa: F401
    from api.auth.models import OrganizationModel, UserModel  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed dev data only in development
    app_env = os.getenv("APP_ENV", "development")
    if app_env != "production":
        from api.db.seed import seed_dev_data
        async with async_session() as session:
            await seed_dev_data(session)


async def get_session():
    """Yield an async session per request."""
    async with async_session() as session:
        yield session
