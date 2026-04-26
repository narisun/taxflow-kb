"""FastAPI dependencies for authentication and authorization.

Three layers of access control:

* :func:`get_current_user` — resolves a JWT (or dev-bypass) to a ``UserModel``.
  Pure identity. Routes that operate on a user *regardless* of onboarding
  state (``/api/auth/me``, ``/api/auth/complete-onboarding``) depend on this.

* :func:`require_onboarded_user` — wraps :func:`get_current_user` and rejects
  users whose ``onboarding_status`` is still ``"pending"`` (no org). Used by
  every tenant-scoped route.

* :func:`require_role` — wraps :func:`require_onboarded_user` and additionally
  rejects users whose ``role`` is not in ``allowed_roles``.

The split keeps the onboarding flow callable while protecting tenant data
from un-onboarded identities.
"""
from __future__ import annotations

import logging
from datetime import datetime, UTC

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.models import OrganizationModel, ROLE_PERMISSIONS, UserModel
from api.auth.token import TokenError, verify_token
from api.config import Settings, get_settings
from api.db.engine import get_session

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


async def _fetch_auth0_userinfo(token: str, domain: str) -> dict:
    """Call Auth0's /userinfo endpoint to fetch the full user profile.

    The access token JWT only carries minimal claims by default (``sub``,
    ``aud``, ``exp``, etc.). Fields like ``email``, ``name``,
    ``email_verified`` live in the ID token OR can be fetched from
    ``/userinfo`` using the access token. We use /userinfo here because
    it works with zero Auth0 dashboard configuration.

    For zero-extra-HTTP-call performance, configure an Auth0 Post-Login
    Action that mirrors these fields into the access token under a custom
    namespace (e.g. ``https://taxflow.ai/email``); ``_provision_user``
    will pick them up automatically and skip this fetch.
    """
    if not domain:
        return {}
    url = f"https://{domain}/userinfo"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {token}"}
            )
        if resp.status_code != 200:
            logger.warning(
                "Auth0 /userinfo returned %s for token (truncated): %s",
                resp.status_code, token[:24],
            )
            return {}
        return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Auth0 /userinfo fetch failed: %s", exc)
        return {}


# ════════════════════════════════════════════════════════════════════════════
# Layer 1 — identity
# ════════════════════════════════════════════════════════════════════════════

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> UserModel:
    """Validate the Bearer token and return the corresponding ``UserModel``.

    Behaviour with no Bearer token:
      * production:                  always 401
      * other envs + dev-bypass on:  return seeded dev user (already onboarded)
      * other envs + dev-bypass off: 401
    """
    if credentials is None:
        if settings.is_production or not settings.auth0_allow_dev_bypass:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
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

    result = await session.execute(
        select(UserModel).where(UserModel.auth0_sub == auth0_sub)
    )
    user = result.scalar_one_or_none()
    if user is None:
        # First-time signup: enrich the JWT payload with /userinfo claims
        # (email, name, email_verified, picture) before creating the user row.
        # Skipped for non-Auth0 tokens (no domain configured = dev shortcut).
        if settings.auth0_domain:
            userinfo = await _fetch_auth0_userinfo(token, settings.auth0_domain)
            for k, v in userinfo.items():
                payload.setdefault(k, v)
        user = await _provision_user(session, payload)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated")

    # Column is TIMESTAMP WITHOUT TIME ZONE (matches the rest of the schema —
    # see TenantMixin in api/db/base.py). Strip tzinfo before persisting.
    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    return user


# ════════════════════════════════════════════════════════════════════════════
# Layer 2 — onboarded
# ════════════════════════════════════════════════════════════════════════════

async def require_onboarded_user(
    user: UserModel = Depends(get_current_user),
) -> UserModel:
    """Reject users who haven't completed the onboarding wizard.

    Tenant-scoped endpoints depend on this so a freshly-signed-up user (with
    ``org_id=NULL``) cannot reach domain data. The frontend's ``OnboardingGate``
    routes such users to the wizard before they can see the app.
    """
    if user.onboarding_status != "complete" or user.org_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Onboarding required",
        )
    return user


# ════════════════════════════════════════════════════════════════════════════
# Layer 3 — role-based
# ════════════════════════════════════════════════════════════════════════════

def require_role(*allowed_roles: str):
    """Allow only users whose role is one of ``allowed_roles`` AND onboarded."""

    async def check_role(
        user: UserModel = Depends(require_onboarded_user),
    ) -> UserModel:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not authorized. "
                       f"Required: {', '.join(allowed_roles)}",
            )
        return user

    return check_role


def get_user_permissions(user: UserModel) -> dict[str, bool]:
    """Get the permission dict for a user's role."""
    return ROLE_PERMISSIONS.get(user.role, ROLE_PERMISSIONS["analyst"])


# ════════════════════════════════════════════════════════════════════════════
# Provisioning
# ════════════════════════════════════════════════════════════════════════════

async def _get_or_create_dev_user(session: AsyncSession) -> UserModel:
    """Local-dev fallback when AUTH0_ALLOW_DEV_BYPASS=true.

    Returns the seeded dev user (already onboarded).
    """
    result = await session.execute(
        select(UserModel).where(UserModel.auth0_sub == "dev|local")
    )
    user = result.scalar_one_or_none()
    if user:
        return user

    # No dev user exists — create org + user, mark onboarded.
    org = OrganizationModel(name="Dev Organization", slug="dev-org", plan="enterprise")
    session.add(org)
    await session.flush()

    user = UserModel(
        org_id=org.id,
        auth0_sub="dev|local",
        email="dev@taxflow.local",
        name="Dev Admin",
        role="admin",
        onboarding_status="complete",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _provision_user(session: AsyncSession, payload: dict) -> UserModel:
    """Create a fresh user row from Auth0 claims.

    Industry-standard split: Auth0 only owns identity. The user lands here
    with ``org_id=NULL`` and ``onboarding_status='pending'``; the in-app
    OnboardingWizard then creates the Organization and links it.
    """
    auth0_sub = payload["sub"]
    email = payload.get("email", f"{auth0_sub}@unknown")
    name = payload.get("name", email.split("@")[0])

    user = UserModel(
        org_id=None,
        auth0_sub=auth0_sub,
        email=email,
        name=name,
        role="preparer",  # placeholder — wizard sets the real role
        onboarding_status="pending",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
