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
