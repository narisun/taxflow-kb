"""Auth endpoints — current user info, org details, and onboarding completion."""
from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user, get_user_permissions
from api.auth.models import OrganizationModel, ROLE_PERMISSIONS, UserModel
from api.auth.token import TokenError, verify_token
from api.config import Settings, get_settings
from api.db.engine import get_session
from api.models.auth import (
    MeResponse,
    OnboardingPayload,
    OrganizationResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_security = HTTPBearer(auto_error=False)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Generate a URL-safe slug from a free-text firm name."""
    base = _SLUG_RE.sub("-", name.lower()).strip("-")
    return (base or "firm")[:42]  # leave headroom for the 8-char dedupe suffix


async def _unique_slug(session: AsyncSession, base: str) -> str:
    """Find a slug that doesn't collide with an existing organization."""
    candidate = base
    while True:
        result = await session.execute(
            select(OrganizationModel.id).where(OrganizationModel.slug == candidate)
        )
        if result.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{secrets.token_hex(3)}"


# ════════════════════════════════════════════════════════════════════════════
# /me — read identity, onboarding state, and (optionally) the linked org
# ════════════════════════════════════════════════════════════════════════════

@router.get("/me", response_model=MeResponse)
async def get_me(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return the current user, their organization (if onboarded), and permissions.

    Pending users (still need to complete the onboarding wizard) get
    ``organization=null`` and ``user.onboarding_status="pending"``.
    """
    org = (
        await session.get(OrganizationModel, user.org_id)
        if user.org_id
        else None
    )
    return MeResponse(
        user=UserResponse.model_validate(user),
        organization=(
            OrganizationResponse.model_validate(org) if org else None
        ),
        permissions=get_user_permissions(user),
    )


# ════════════════════════════════════════════════════════════════════════════
# /complete-onboarding — first-time wizard submission
# ════════════════════════════════════════════════════════════════════════════

@router.post("/complete-onboarding", response_model=MeResponse)
async def complete_onboarding(
    payload: OnboardingPayload,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """Wire a freshly-signed-up user to a brand-new Organization.

    Refuses if the user is already onboarded (409). Refuses if the JWT lacks
    ``email_verified=true`` in production-equivalent envs (403). The created
    org becomes the user's tenant; subsequent logins return MeResponse with
    ``organization`` populated.
    """
    if user.onboarding_status == "complete" and user.org_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already onboarded",
        )

    # Email verification gate — only enforce in production. In development,
    # Auth0 email/password signups are unverified until the user clicks the
    # verification link, which blocks onboarding. Skip the check in dev so
    # testers can complete the wizard immediately.
    if credentials is not None and settings.is_production:
        try:
            jwt_payload = verify_token(credentials.credentials)
        except TokenError:
            jwt_payload = {}
        verified = bool(jwt_payload.get("email_verified", False))
        if not verified and settings.auth0_domain:
            from api.auth.dependencies import _fetch_auth0_userinfo
            info = await _fetch_auth0_userinfo(
                credentials.credentials, settings.auth0_domain
            )
            verified = bool(info.get("email_verified", False))
        if not verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Verify your email address with Auth0 before completing onboarding",
            )

    # Phase 2 placeholder — joining an existing firm via invite token.
    if payload.invite_token:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Joining an existing firm by invite is not implemented yet",
        )

    # Generate a unique slug; keep firm_name as-typed for display.
    base_slug = _slugify(payload.firm_name)
    slug = await _unique_slug(session, base_slug)

    org = OrganizationModel(name=payload.firm_name, slug=slug, plan="starter")
    session.add(org)
    await session.flush()

    # The user instance came from a (possibly different) session via Depends.
    # Merge it into the request session so attribute mutations + refresh work.
    user = await session.merge(user)

    # Bind the user to the new org. The role from the wizard wins over the
    # placeholder role assigned at provisioning time.
    user.org_id = org.id
    user.role = (
        payload.role if payload.role in ROLE_PERMISSIONS else "admin"
    )
    user.timezone = payload.timezone
    user.onboarding_status = "complete"
    await session.commit()
    await session.refresh(user)
    await session.refresh(org)

    # Suppress "unused import" for Settings — it documents that this endpoint
    # honours the central Settings (e.g. is_production via the dependency).
    _ = settings

    return MeResponse(
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org),
        permissions=get_user_permissions(user),
    )
