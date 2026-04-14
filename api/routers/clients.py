"""Client CRUD endpoints — tenant-scoped."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ClientModel
from api.auth.dependencies import get_current_user, require_role
from api.auth.models import UserModel, ROLE_PERMISSIONS
from api.models.client import ClientCreate, ClientUpdate, ClientResponse, ClientListResponse
from api.routers._helpers import get_client_or_404

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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    q = _client_query(user)
    count_q = select(func.count()).select_from(q.subquery())
    count_result = await session.execute(count_q)
    total = count_result.scalar() or 0

    paginated = q.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(paginated)
    clients = result.scalars().all()
    return ClientListResponse(items=clients, total=total, page=page, page_size=page_size)


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
    user: UserModel = Depends(require_role("admin", "supervisor")),
):
    result = await session.execute(
        _client_query(user).where(ClientModel.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    await session.delete(client)
    await session.commit()
