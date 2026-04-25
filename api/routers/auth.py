"""Auth endpoints — current user info and org details."""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.auth.dependencies import get_current_user, get_user_permissions
from api.auth.models import UserModel, OrganizationModel
from api.models.auth import MeResponse, UserResponse, OrganizationResponse, ProfileUpdatePayload, OnboardingPayload

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me", response_model=MeResponse)
async def get_me(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return the current authenticated user, their org, and permissions."""
    org = None
    if user.org_id is not None:
        org = await session.get(OrganizationModel, user.org_id)
    return MeResponse(
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org) if org else None,
        permissions=get_user_permissions(user),
    )


@router.patch("/profile", response_model=MeResponse)
async def update_profile(
    payload: ProfileUpdatePayload,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update editable profile fields (e.g. timezone)."""
    if payload.timezone is not None:
        user.timezone = payload.timezone
    await session.commit()
    await session.refresh(user)
    org = None
    if user.org_id is not None:
        org = await session.get(OrganizationModel, user.org_id)
    return MeResponse(
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org) if org else None,
        permissions=get_user_permissions(user),
    )


@router.post("/complete-onboarding", response_model=MeResponse)
async def complete_onboarding(
    payload: OnboardingPayload,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Complete the onboarding wizard: create org, link user, set role."""
    # Merge user into this session so we can mutate and commit.
    user = await session.merge(user)

    if user.onboarding_status == "complete":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onboarding already completed.",
        )

    if payload.invite_token is not None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Invite-token flow is not yet implemented.",
        )

    # Generate slug from firm name
    slug = re.sub(r"[^a-z0-9-]", "", payload.firm_name.lower().replace(" ", "-"))

    # Check slug uniqueness; append suffix if taken
    existing = await session.execute(
        select(OrganizationModel.id).where(OrganizationModel.slug == slug)
    )
    if existing.scalar_one_or_none() is not None:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    # Create organization
    org = OrganizationModel(name=payload.firm_name, slug=slug, plan="starter")
    session.add(org)
    await session.flush()  # populate org.id

    # Link user to org
    user.org_id = org.id
    user.role = payload.role
    user.timezone = payload.timezone
    user.onboarding_status = "complete"

    await session.commit()
    await session.refresh(user)
    await session.refresh(org)

    return MeResponse(
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org),
        permissions=get_user_permissions(user),
    )
