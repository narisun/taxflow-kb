# Multi-Tenancy & Auth0 Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-tenant org/user/role model with Auth0 OAuth2 + 2FA, PostgreSQL Row-Level Security, and tenant-scoped queries across all existing and new API endpoints.

**Architecture:** Shared PostgreSQL database with `org_id` column on every data table. Auth0 JWT validation via JWKS. Row-Level Security (RLS) policies enforce tenant isolation at the database level. FastAPI dependency injection provides `current_user` context to every route. Role-based access control (RBAC) restricts actions by user role.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16 (pgvector), Auth0 (RS256 JWT), python-jose, Alembic

**Auth0 Domain:** `dev-whd0hxxsqq67rrq8.us.auth0.com`

---

## File Structure

```
api/
├── auth/
│   ├── __init__.py
│   ├── config.py          # Auth0 settings (domain, audience, algorithms)
│   ├── token.py           # JWT decode + Auth0 JWKS verification
│   ├── dependencies.py    # get_current_user, require_role FastAPI deps
│   └── models.py          # Organization, User SQLAlchemy models
├── db/
│   ├── engine.py          # MODIFIED: PostgreSQL + connection pool
│   ├── models.py          # MODIFIED: add org_id, created_by to all models
│   └── base.py            # NEW: TenantBase with org_id + timestamps
├── models/
│   ├── client.py          # MODIFIED: add org_id to responses
│   ├── auth.py            # NEW: Pydantic schemas for auth/user/org
│   └── ... (existing)
├── routers/
│   ├── auth.py            # NEW: /api/auth/me, /api/auth/org
│   ├── clients.py         # MODIFIED: add Depends(get_current_user)
│   ├── documents.py       # MODIFIED: add Depends(get_current_user)
│   ├── chat.py            # MODIFIED: add Depends(get_current_user)
│   ├── tax_returns.py     # MODIFIED: add Depends(get_current_user)
│   └── health.py          # unchanged
├── main.py                # MODIFIED: register auth router
├── alembic/               # NEW: migration directory
│   ├── env.py
│   └── versions/
│       └── 001_add_multi_tenancy.py
└── alembic.ini            # NEW: alembic config
```

---

## Task 1: Add Dependencies & Auth0 Config

**Files:**
- Modify: `requirements-api.txt`
- Create: `api/auth/__init__.py`
- Create: `api/auth/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add python-jose to requirements**

In `requirements-api.txt`, add at the end:

```
# Auth
python-jose[cryptography]>=3.3
```

- [ ] **Step 2: Install the dependency**

Run: `pip install "python-jose[cryptography]>=3.3"`

- [ ] **Step 3: Create auth package init**

```python
# api/auth/__init__.py
```

(Empty file — just makes it a package)

- [ ] **Step 4: Create Auth0 config**

```python
# api/auth/config.py
"""Auth0 configuration — loaded from environment variables."""

import os

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "dev-whd0hxxsqq67rrq8.us.auth0.com")
AUTH0_API_AUDIENCE = os.getenv("AUTH0_API_AUDIENCE", "https://api.taxflow.ai")
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID", "bQLgF5zoUZS0tO5V36PXd4Q6ohHzhUIE")
AUTH0_REDIRECT_URI = os.getenv("AUTH0_REDIRECT_URI", "http://localhost:3000/")
AUTH0_ALGORITHMS = ["RS256"]
AUTH0_ISSUER = f"https://{AUTH0_DOMAIN}/"
AUTH0_JWKS_URL = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
```

- [ ] **Step 5: Add auth env vars to .env.example**

Append to `.env.example`:

```
# ── Auth0 ───────────────────────────────────────────────────────────────
AUTH0_DOMAIN=dev-whd0hxxsqq67rrq8.us.auth0.com
AUTH0_API_AUDIENCE=https://api.taxflow.ai
AUTH0_CLIENT_ID=bQLgF5zoUZS0tO5V36PXd4Q6ohHzhUIE
AUTH0_REDIRECT_URI=http://localhost:3000/
```

- [ ] **Step 6: Verify the import works**

Run: `python -c "from api.auth.config import AUTH0_DOMAIN; print(AUTH0_DOMAIN)"`

Expected: `dev-whd0hxxsqq67rrq8.us.auth0.com`

- [ ] **Step 7: Commit**

```bash
git add requirements-api.txt api/auth/__init__.py api/auth/config.py .env.example
git commit -m "feat(api): add Auth0 config and python-jose dependency"
```

---

## Task 2: JWT Token Verification

**Files:**
- Create: `api/auth/token.py`
- Test: `tests/api/test_token.py`

- [ ] **Step 1: Create JWT verification module**

```python
# api/auth/token.py
"""Verify Auth0 RS256 JWT tokens using JWKS."""

import httpx
from jose import jwt, JWTError
from functools import lru_cache

from api.auth.config import (
    AUTH0_DOMAIN,
    AUTH0_ALGORITHMS,
    AUTH0_API_AUDIENCE,
    AUTH0_ISSUER,
    AUTH0_JWKS_URL,
)


class TokenError(Exception):
    """Raised when token verification fails."""
    def __init__(self, detail: str):
        self.detail = detail


@lru_cache(maxsize=1)
def _fetch_jwks() -> dict:
    """Fetch and cache Auth0 JWKS (JSON Web Key Set)."""
    resp = httpx.get(AUTH0_JWKS_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_signing_key(token: str) -> dict:
    """Extract the signing key from JWKS that matches the token's kid."""
    jwks = _fetch_jwks()
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise TokenError("Invalid token header")

    for key in jwks.get("keys", []):
        if key["kid"] == unverified_header.get("kid"):
            return key

    raise TokenError("Signing key not found in JWKS")


def verify_token(token: str) -> dict:
    """Verify an Auth0 JWT and return the decoded payload.

    Returns dict with at minimum: sub, email, and custom claims
    (https://taxflow.ai/org_id, https://taxflow.ai/role).
    """
    signing_key = _get_signing_key(token)

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=AUTH0_ALGORITHMS,
            audience=AUTH0_API_AUDIENCE,
            issuer=AUTH0_ISSUER,
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("Token has expired")
    except jwt.JWTClaimsError:
        raise TokenError("Invalid token claims")
    except JWTError:
        raise TokenError("Token verification failed")

    return payload


def decode_token_unsafe(token: str) -> dict:
    """Decode a JWT WITHOUT verification — for testing/dev only."""
    return jwt.get_unverified_claims(token)
```

- [ ] **Step 2: Create test for token module**

```python
# tests/api/test_token.py
"""Tests for Auth0 JWT verification (unit tests with mocked JWKS)."""

import pytest
from jose import jwt
from unittest.mock import patch
from api.auth.token import verify_token, decode_token_unsafe, TokenError


# Test RSA key pair for testing (NOT a real key)
TEST_RSA_PRIVATE = {
    "kty": "RSA", "kid": "test-kid-1",
    "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
    "e": "AQAB",
    "d": "X4cTteJY_gn4FYPsXB8rdXix5vwsg1FLN5E3EaG6RJoVH-HLLKD9M7dx5oo7GURknchnrRweUkC7hT5fJLM0WbFAKNLWY2vv7B6NqXSzUvxT0_YSfqijwp3RTzlBaCxWp4doFk5N2o8Gy_nHNKroADIkJ46pRUohsXywbReAdYaMwFs9tv8d_cPVY3i07a3t8MN6TNwm0dSawm9v47UiCl3Sk5ZiG7xojPLu4sbg1U2jx4IBTNBznbJSzFHK66jT8bgkuqsk0GjskDJk19Z4qwjwbsnn4j2WBii3RL-Us2lGVkY8fkFzme1z0HbIkfz0Y6mqnOYjqxnf7Il6yQIDAQAB",
}
TEST_RSA_PUBLIC = {"kty": "RSA", "kid": "test-kid-1", "n": TEST_RSA_PRIVATE["n"], "e": TEST_RSA_PRIVATE["e"]}


def _make_test_token(claims: dict) -> str:
    """Create a signed JWT with test RSA key."""
    return jwt.encode(claims, TEST_RSA_PRIVATE, algorithm="RS256", headers={"kid": "test-kid-1"})


def test_decode_token_unsafe():
    token = _make_test_token({"sub": "auth0|123", "email": "test@test.com"})
    payload = decode_token_unsafe(token)
    assert payload["sub"] == "auth0|123"
    assert payload["email"] == "test@test.com"


def test_verify_token_expired():
    import time
    token = _make_test_token({
        "sub": "auth0|123",
        "aud": "https://api.taxflow.ai",
        "iss": "https://dev-whd0hxxsqq67rrq8.us.auth0.com/",
        "exp": int(time.time()) - 3600,  # expired 1 hour ago
    })
    with patch("api.auth.token._fetch_jwks", return_value={"keys": [TEST_RSA_PUBLIC]}):
        with pytest.raises(TokenError, match="expired"):
            verify_token(token)


def test_verify_token_bad_audience():
    import time
    token = _make_test_token({
        "sub": "auth0|123",
        "aud": "wrong-audience",
        "iss": "https://dev-whd0hxxsqq67rrq8.us.auth0.com/",
        "exp": int(time.time()) + 3600,
    })
    with patch("api.auth.token._fetch_jwks", return_value={"keys": [TEST_RSA_PUBLIC]}):
        with pytest.raises(TokenError, match="claims"):
            verify_token(token)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/api/test_token.py -v`

Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
git add api/auth/token.py tests/api/test_token.py
git commit -m "feat(api): add Auth0 JWT verification with JWKS"
```

---

## Task 3: Organization & User Database Models

**Files:**
- Create: `api/db/base.py`
- Create: `api/auth/models.py`
- Modify: `api/db/models.py`

- [ ] **Step 1: Create TenantBase mixin**

```python
# api/db/base.py
"""Base classes for multi-tenant models."""

import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TenantMixin:
    """Mixin that adds org_id, created_by, and timestamps to any model.
    
    Every data table inherits this to ensure tenant isolation.
    """
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
```

- [ ] **Step 2: Create Organization and User models**

```python
# api/auth/models.py
"""Organization, User, and Role models for multi-tenancy."""

import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class OrganizationModel(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(20), default="starter")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users: Mapped[list["UserModel"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    auth0_sub: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="preparer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization: Mapped["OrganizationModel"] = relationship(back_populates="users")


# Role permissions — stored as a simple lookup dict (no DB table needed)
ROLE_PERMISSIONS = {
    "admin": {
        "can_view_all_clients": True,
        "can_manage_users": True,
        "can_file_returns": True,
        "can_approve_documents": True,
        "can_send_advisory": True,
        "can_view_analytics": True,
    },
    "supervisor": {
        "can_view_all_clients": True,
        "can_manage_users": False,
        "can_file_returns": True,
        "can_approve_documents": True,
        "can_send_advisory": True,
        "can_view_analytics": True,
    },
    "preparer": {
        "can_view_all_clients": False,
        "can_manage_users": False,
        "can_file_returns": True,
        "can_approve_documents": True,
        "can_send_advisory": True,
        "can_view_analytics": False,
    },
    "analyst": {
        "can_view_all_clients": False,
        "can_manage_users": False,
        "can_file_returns": False,
        "can_approve_documents": False,
        "can_send_advisory": False,
        "can_view_analytics": False,
    },
}
```

- [ ] **Step 3: Update existing models to use TenantMixin**

Replace the entire `api/db/models.py` with:

```python
"""SQLAlchemy models — multi-tenant with org_id on all data tables."""

from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Float, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base, TenantMixin


class ClientModel(TenantMixin, Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    filing_status: Mapped[str] = mapped_column(String(10), default="single")
    tax_year: Mapped[int] = mapped_column(Integer, default=2025)
    dependents: Mapped[int] = mapped_column(Integer, default=0)
    workflow_step: Mapped[str] = mapped_column(String(20), default="intake")

    documents: Mapped[list["DocumentModel"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ChatMessageModel"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class DocumentModel(TenantMixin, Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    form_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extracted_data: Mapped[str] = mapped_column(Text, default="{}")
    file_path: Mapped[str] = mapped_column(String(500), default="")
    flags: Mapped[str] = mapped_column(Text, default="[]")

    client: Mapped["ClientModel"] = relationship(back_populates="documents")


class ChatMessageModel(TenantMixin, Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(30), default="text")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    client: Mapped["ClientModel"] = relationship(back_populates="messages")
```

Note: `created_at` and `updated_at` come from `TenantMixin`. `org_id` and `created_by` are inherited automatically.

- [ ] **Step 4: Verify models load**

Run: `python -c "from api.db.models import ClientModel, DocumentModel, ChatMessageModel; from api.auth.models import OrganizationModel, UserModel; print('All models loaded')"`

Expected: `All models loaded`

- [ ] **Step 5: Commit**

```bash
git add api/db/base.py api/auth/models.py api/db/models.py
git commit -m "feat(api): add Organization, User models and TenantMixin with org_id"
```

---

## Task 4: Auth Dependencies (get_current_user, require_role)

**Files:**
- Create: `api/auth/dependencies.py`
- Create: `api/models/auth.py`

- [ ] **Step 1: Create Pydantic schemas for auth**

```python
# api/models/auth.py
"""Pydantic schemas for authentication responses."""

from pydantic import BaseModel
from datetime import datetime


class UserResponse(BaseModel):
    id: str
    org_id: str
    email: str
    name: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user: UserResponse
    organization: OrganizationResponse
    permissions: dict[str, bool]
```

- [ ] **Step 2: Create auth dependencies**

```python
# api/auth/dependencies.py
"""FastAPI dependencies for authentication and authorization."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from api.db.engine import get_session
from api.auth.token import verify_token, TokenError
from api.auth.models import UserModel, OrganizationModel, ROLE_PERMISSIONS

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> UserModel:
    """Extract and validate the JWT, then return the User from the database.
    
    If the user doesn't exist in our DB yet (first login), auto-provision them
    from the Auth0 token claims. This is the standard Auth0 pattern — Auth0
    manages authentication, our DB manages application-level user data.
    """
    # In development mode (no token), return a default dev user
    if credentials is None:
        return await _get_or_create_dev_user(session)

    token = credentials.credentials

    try:
        payload = verify_token(token)
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth0_sub = payload.get("sub")
    if not auth0_sub:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")

    # Look up user by Auth0 subject ID
    result = await session.execute(
        select(UserModel).where(UserModel.auth0_sub == auth0_sub)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Auto-provision user on first login
        user = await _provision_user(session, payload)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated")

    # Update last login
    user.last_login_at = datetime.utcnow()
    await session.commit()

    return user


async def _get_or_create_dev_user(session: AsyncSession) -> UserModel:
    """For local development without Auth0 — returns a default admin user."""
    result = await session.execute(
        select(UserModel).where(UserModel.email == "dev@taxflow.local")
    )
    user = result.scalar_one_or_none()

    if user:
        return user

    # Create dev org + user on first request
    org = OrganizationModel(
        name="Dev Organization",
        slug="dev-org",
        plan="enterprise",
    )
    session.add(org)
    await session.flush()

    user = UserModel(
        org_id=org.id,
        auth0_sub="dev|local",
        email="dev@taxflow.local",
        name="Dev Admin",
        role="admin",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _provision_user(session: AsyncSession, payload: dict) -> UserModel:
    """Create a new user + org from Auth0 token claims on first login."""
    ns = "https://taxflow.ai"
    auth0_sub = payload["sub"]
    email = payload.get("email", f"{auth0_sub}@unknown")
    name = payload.get("name", email.split("@")[0])
    org_id_claim = payload.get(f"{ns}/org_id")
    role_claim = payload.get(f"{ns}/role", "preparer")

    # If org_id is in the token, look it up; otherwise create a new org
    org = None
    if org_id_claim:
        org = await session.get(OrganizationModel, org_id_claim)

    if org is None:
        # Create a new org for this user (solo CPA or first user of an org)
        slug = email.split("@")[0].replace(".", "-").replace("+", "-")[:50]
        org = OrganizationModel(name=f"{name}'s Firm", slug=slug)
        session.add(org)
        await session.flush()
        role_claim = "admin"  # first user in org is always admin

    user = UserModel(
        org_id=org.id,
        auth0_sub=auth0_sub,
        email=email,
        name=name,
        role=role_claim if role_claim in ROLE_PERMISSIONS else "preparer",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def require_role(*allowed_roles: str):
    """Dependency that checks the current user has one of the allowed roles.
    
    Usage:
        @router.post("/admin-only")
        async def admin_endpoint(user: UserModel = Depends(require_role("admin"))):
            ...
    """
    async def check_role(user: UserModel = Depends(get_current_user)) -> UserModel:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not authorized. Required: {', '.join(allowed_roles)}",
            )
        return user
    return check_role


def get_user_permissions(user: UserModel) -> dict[str, bool]:
    """Get the permission dict for a user's role."""
    return ROLE_PERMISSIONS.get(user.role, ROLE_PERMISSIONS["analyst"])
```

- [ ] **Step 3: Verify imports**

Run: `python -c "from api.auth.dependencies import get_current_user, require_role; print('Dependencies loaded')"`

Expected: `Dependencies loaded`

- [ ] **Step 4: Commit**

```bash
git add api/auth/dependencies.py api/models/auth.py
git commit -m "feat(api): add get_current_user and require_role auth dependencies"
```

---

## Task 5: Switch to PostgreSQL & Update Engine

**Files:**
- Modify: `api/db/engine.py`

- [ ] **Step 1: Update engine to use PostgreSQL with connection pool**

```python
# api/db/engine.py
"""Async SQLAlchemy engine — PostgreSQL for production, SQLite for dev fallback."""

import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "APP_DATABASE_URL",
    "postgresql+asyncpg://taxflow:taxflow_dev@localhost:5432/taxflow"
)

# Connection pool settings
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
    from api.db.models import ClientModel, DocumentModel, ChatMessageModel  # noqa: F401
    from api.auth.models import OrganizationModel, UserModel  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    """Yield an async session per request."""
    async with async_session() as session:
        yield session
```

- [ ] **Step 2: Add APP_DATABASE_URL to .env.example**

Append to `.env.example`:

```
# ── Application Database ────────────────────────────────────────────────
APP_DATABASE_URL=postgresql+asyncpg://taxflow:taxflow_dev@localhost:5432/taxflow
```

- [ ] **Step 3: Verify the engine initializes**

Run: `python -c "from api.db.engine import engine; print(engine.url)"`

Expected: `postgresql+asyncpg://taxflow:***@localhost:5432/taxflow`

- [ ] **Step 4: Commit**

```bash
git add api/db/engine.py .env.example
git commit -m "feat(api): switch to PostgreSQL with connection pooling"
```

---

## Task 6: Auth Router (/api/auth/me, /api/auth/org)

**Files:**
- Create: `api/routers/auth.py`
- Modify: `api/main.py`

- [ ] **Step 1: Create auth router**

```python
# api/routers/auth.py
"""Auth endpoints — current user info and org details."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.auth.dependencies import get_current_user, get_user_permissions
from api.auth.models import UserModel, OrganizationModel
from api.models.auth import MeResponse, UserResponse, OrganizationResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me", response_model=MeResponse)
async def get_me(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return the current authenticated user, their org, and permissions."""
    org = await session.get(OrganizationModel, user.org_id)
    return MeResponse(
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org),
        permissions=get_user_permissions(user),
    )
```

- [ ] **Step 2: Register auth router in main.py**

Replace the entire `api/main.py`:

```python
"""FastAPI application factory for Tax Brain API."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.db.engine import init_db
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Tax Brain API",
        description="CPA tax preparation platform backend",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from api.routers import health, clients, chat, documents, tax_returns, auth
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(clients.router)
    app.include_router(chat.router)
    app.include_router(documents.router)
    app.include_router(tax_returns.router)
    return app
```

- [ ] **Step 3: Verify app starts**

Run: `python -c "from api.main import create_app; app = create_app(); print('App created with', len(app.routes), 'routes')"`

Expected: App created with routes (no errors)

- [ ] **Step 4: Commit**

```bash
git add api/routers/auth.py api/main.py
git commit -m "feat(api): add /api/auth/me endpoint and register auth router"
```

---

## Task 7: Update Existing Routers with Auth

**Files:**
- Modify: `api/routers/clients.py`
- Modify: `api/routers/documents.py`
- Modify: `api/routers/chat.py`
- Modify: `api/routers/tax_returns.py`
- Modify: `api/models/client.py`

- [ ] **Step 1: Add org_id to Pydantic client schemas**

```python
# api/models/client.py
from pydantic import BaseModel
from datetime import datetime


class ClientCreate(BaseModel):
    name: str
    filing_status: str = "single"
    tax_year: int = 2025
    dependents: int = 0


class ClientUpdate(BaseModel):
    name: str | None = None
    filing_status: str | None = None
    workflow_step: str | None = None
    dependents: int | None = None


class ClientResponse(BaseModel):
    id: int
    name: str
    filing_status: str
    tax_year: int
    dependents: int
    workflow_step: str
    org_id: str
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ClientListResponse(BaseModel):
    items: list[ClientResponse]
    total: int
```

- [ ] **Step 2: Update clients router with auth + tenant filtering**

```python
# api/routers/clients.py
"""Client CRUD endpoints — tenant-scoped."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ClientModel
from api.auth.dependencies import get_current_user
from api.auth.models import UserModel, ROLE_PERMISSIONS
from api.models.client import ClientCreate, ClientUpdate, ClientResponse, ClientListResponse

router = APIRouter(prefix="/api/clients", tags=["clients"])


def _client_query(user: UserModel):
    """Base query filtered by org. Analysts only see own clients."""
    q = select(ClientModel).where(ClientModel.org_id == user.org_id)
    perms = ROLE_PERMISSIONS.get(user.role, {})
    if not perms.get("can_view_all_clients"):
        q = q.where(ClientModel.created_by == user.id)
    return q


@router.get("", response_model=ClientListResponse)
async def list_clients(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    result = await session.execute(_client_query(user))
    clients = result.scalars().all()
    count_q = select(func.count(ClientModel.id)).where(ClientModel.org_id == user.org_id)
    perms = ROLE_PERMISSIONS.get(user.role, {})
    if not perms.get("can_view_all_clients"):
        count_q = count_q.where(ClientModel.created_by == user.id)
    count_result = await session.execute(count_q)
    total = count_result.scalar() or 0
    return ClientListResponse(items=clients, total=total)


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    client = ClientModel(**data.model_dump(), org_id=user.org_id, created_by=user.id)
    session.add(client)
    await session.commit()
    await session.refresh(client)
    return client


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    result = await session.execute(
        _client_query(user).where(ClientModel.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    data: ClientUpdate,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    result = await session.execute(
        _client_query(user).where(ClientModel.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    await session.commit()
    await session.refresh(client)
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    result = await session.execute(
        _client_query(user).where(ClientModel.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    await session.delete(client)
    await session.commit()
```

- [ ] **Step 3: Update documents router with auth**

In `api/routers/documents.py`, add these changes:
- Add import: `from api.auth.dependencies import get_current_user`
- Add import: `from api.auth.models import UserModel`
- Add `user: UserModel = Depends(get_current_user)` parameter to every endpoint
- In `_get_client_or_404`, add org_id filter: `.where(ClientModel.org_id == user.org_id)`
- In document creation, set `org_id=user.org_id, created_by=user.id`
- In document get/approve, add org_id filter: `.where(DocumentModel.org_id == user.org_id)`

- [ ] **Step 4: Update chat router with auth**

In `api/routers/chat.py`, add the same pattern:
- Add `user: UserModel = Depends(get_current_user)` to both endpoints
- Filter client lookup by `org_id == user.org_id`
- Set `org_id=user.org_id, created_by=user.id` on new messages

- [ ] **Step 5: Update tax_returns router with auth**

In `api/routers/tax_returns.py`, add the same pattern:
- Add `user: UserModel = Depends(get_current_user)` to both endpoints
- Filter client lookup by `org_id == user.org_id`

- [ ] **Step 6: Verify app starts with all changes**

Run: `python -c "from api.main import create_app; app = create_app(); print('App created successfully')"`

Expected: `App created successfully`

- [ ] **Step 7: Commit**

```bash
git add api/routers/clients.py api/routers/documents.py api/routers/chat.py api/routers/tax_returns.py api/models/client.py
git commit -m "feat(api): add auth + tenant filtering to all existing routers"
```

---

## Task 8: Database Initialization & Dev Seed Data

**Files:**
- Modify: `api/db/engine.py`
- Create: `api/db/seed.py`

- [ ] **Step 1: Create seed data script**

```python
# api/db/seed.py
"""Seed the database with a dev organization, user, and sample clients."""

from api.auth.models import OrganizationModel, UserModel
from api.db.models import ClientModel


async def seed_dev_data(session):
    """Create dev org + user + sample clients if the DB is empty."""
    from sqlalchemy import select, func

    # Check if any org exists
    result = await session.execute(select(func.count(OrganizationModel.id)))
    if (result.scalar() or 0) > 0:
        return  # Already seeded

    # Create org
    org = OrganizationModel(
        name="Chen & Associates CPA",
        slug="chen-associates",
        plan="professional",
    )
    session.add(org)
    await session.flush()

    # Create admin user
    user = UserModel(
        org_id=org.id,
        auth0_sub="dev|local",
        email="sarah@chen-cpa.com",
        name="Sarah Chen",
        role="admin",
    )
    session.add(user)
    await session.flush()

    # Create sample clients
    sample_clients = [
        {"name": "Smith, John", "filing_status": "single", "tax_year": 2025, "dependents": 1, "workflow_step": "review"},
        {"name": "Johnson Family", "filing_status": "mfj", "tax_year": 2025, "dependents": 3, "workflow_step": "documents"},
        {"name": "Chen, Wei", "filing_status": "single", "tax_year": 2025, "dependents": 0, "workflow_step": "intake"},
        {"name": "Garcia Household", "filing_status": "mfj", "tax_year": 2025, "dependents": 4, "workflow_step": "filing"},
        {"name": "Patel Family", "filing_status": "mfj", "tax_year": 2025, "dependents": 1, "workflow_step": "filed"},
    ]
    for data in sample_clients:
        client = ClientModel(**data, org_id=org.id, created_by=user.id)
        session.add(client)

    await session.commit()
    print(f"[seed] Created org '{org.name}', user '{user.name}', {len(sample_clients)} clients")
```

- [ ] **Step 2: Call seed on startup (dev only)**

In `api/db/engine.py`, update `init_db()`:

```python
async def init_db():
    """Create all tables and seed dev data on startup."""
    from api.db.base import Base
    from api.db.models import ClientModel, DocumentModel, ChatMessageModel  # noqa: F401
    from api.auth.models import OrganizationModel, UserModel  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed dev data if DB is empty
    from api.db.seed import seed_dev_data
    async with async_session() as session:
        await seed_dev_data(session)
```

- [ ] **Step 3: Add .gitignore entries**

Append to `.gitignore`:

```
taxbrain.db
uploads/
```

- [ ] **Step 4: Commit**

```bash
git add api/db/seed.py api/db/engine.py .gitignore
git commit -m "feat(api): add dev seed data with org, user, and sample clients"
```

---

## Task 9: Test Auth Flow End-to-End

**Files:**
- Create: `tests/api/test_auth_flow.py`

- [ ] **Step 1: Create integration test for auth flow**

```python
# tests/api/test_auth_flow.py
"""Integration tests for multi-tenant auth flow."""

import pytest
from unittest.mock import patch, AsyncMock
from api.auth.models import OrganizationModel, UserModel, ROLE_PERMISSIONS
from api.auth.dependencies import get_user_permissions


def test_role_permissions_admin():
    perms = ROLE_PERMISSIONS["admin"]
    assert perms["can_view_all_clients"] is True
    assert perms["can_manage_users"] is True
    assert perms["can_file_returns"] is True


def test_role_permissions_analyst():
    perms = ROLE_PERMISSIONS["analyst"]
    assert perms["can_view_all_clients"] is False
    assert perms["can_manage_users"] is False
    assert perms["can_file_returns"] is False


def test_role_permissions_preparer():
    perms = ROLE_PERMISSIONS["preparer"]
    assert perms["can_view_all_clients"] is False
    assert perms["can_file_returns"] is True
    assert perms["can_approve_documents"] is True


def test_all_roles_have_permissions():
    for role in ["admin", "supervisor", "preparer", "analyst"]:
        perms = ROLE_PERMISSIONS[role]
        assert isinstance(perms, dict)
        assert "can_view_all_clients" in perms
        assert "can_manage_users" in perms
        assert "can_file_returns" in perms


def test_organization_model_fields():
    org = OrganizationModel(name="Test Firm", slug="test-firm")
    assert org.name == "Test Firm"
    assert org.slug == "test-firm"
    assert org.plan == "starter"
    assert org.is_active is True


def test_user_model_fields():
    user = UserModel(
        org_id="test-org-id",
        auth0_sub="auth0|123",
        email="test@test.com",
        name="Test User",
    )
    assert user.role == "preparer"  # default role
    assert user.is_active is True
    assert user.auth0_sub == "auth0|123"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/api/test_auth_flow.py -v`

Expected: 6 passed

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_auth_flow.py
git commit -m "test(api): add auth flow unit tests for roles and models"
```

---

## Summary

9 tasks, 9 commits:

| Task | What | Files |
|---|---|---|
| 1 | Auth0 config + python-jose | 3 new, 2 modified |
| 2 | JWT verification with JWKS | 1 new, 1 test |
| 3 | Org, User, TenantMixin models | 3 new/modified |
| 4 | get_current_user + require_role | 2 new |
| 5 | PostgreSQL engine + connection pool | 1 modified |
| 6 | Auth router (/api/auth/me) | 1 new, 1 modified |
| 7 | Tenant filtering on all routers | 5 modified |
| 8 | Dev seed data + gitignore | 2 new/modified |
| 9 | Auth integration tests | 1 new |

**After completion:**
- Every API request requires a valid Auth0 JWT (or falls back to dev user in local mode)
- All queries are scoped to `org_id` from the authenticated user
- Analysts can only see clients they created; admin/supervisor see all org clients
- `require_role()` decorator available for endpoint-level RBAC
- PostgreSQL with connection pooling replaces SQLite
- Dev seed data auto-creates on empty DB
