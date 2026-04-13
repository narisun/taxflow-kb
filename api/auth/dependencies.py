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
    """Extract and validate JWT, return User from database.

    In dev mode (no token), returns a default dev user.
    On first login, auto-provisions user from Auth0 claims.
    """
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

    result = await session.execute(
        select(UserModel).where(UserModel.auth0_sub == auth0_sub)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = await _provision_user(session, payload)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated")

    user.last_login_at = datetime.utcnow()
    await session.commit()
    return user


async def _get_or_create_dev_user(session: AsyncSession) -> UserModel:
    """For local dev without Auth0 — returns a default admin user."""
    result = await session.execute(
        select(UserModel).where(UserModel.email == "dev@taxflow.local")
    )
    user = result.scalar_one_or_none()
    if user:
        return user

    org = OrganizationModel(name="Dev Organization", slug="dev-org", plan="enterprise")
    session.add(org)
    await session.flush()

    user = UserModel(
        org_id=org.id, auth0_sub="dev|local",
        email="dev@taxflow.local", name="Dev Admin", role="admin",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _provision_user(session: AsyncSession, payload: dict) -> UserModel:
    """Create user + org from Auth0 token claims on first login."""
    ns = "https://taxflow.ai"
    auth0_sub = payload["sub"]
    email = payload.get("email", f"{auth0_sub}@unknown")
    name = payload.get("name", email.split("@")[0])
    org_id_claim = payload.get(f"{ns}/org_id")
    role_claim = payload.get(f"{ns}/role", "preparer")

    org = None
    if org_id_claim:
        org = await session.get(OrganizationModel, org_id_claim)

    if org is None:
        slug = email.split("@")[0].replace(".", "-").replace("+", "-")[:50]
        org = OrganizationModel(name=f"{name}'s Firm", slug=slug)
        session.add(org)
        await session.flush()
        role_claim = "admin"

    user = UserModel(
        org_id=org.id, auth0_sub=auth0_sub, email=email, name=name,
        role=role_claim if role_claim in ROLE_PERMISSIONS else "preparer",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def require_role(*allowed_roles: str):
    """Dependency that checks user has one of the allowed roles."""
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
