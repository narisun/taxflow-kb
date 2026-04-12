"""Client CRUD endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ClientModel
from api.models.client import ClientCreate, ClientUpdate, ClientResponse, ClientListResponse

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("", response_model=ClientListResponse)
async def list_clients(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ClientModel))
    clients = result.scalars().all()
    count_result = await session.execute(select(func.count(ClientModel.id)))
    total = count_result.scalar() or 0
    return ClientListResponse(items=clients, total=total)


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(data: ClientCreate, session: AsyncSession = Depends(get_session)):
    client = ClientModel(**data.model_dump())
    session.add(client)
    await session.commit()
    await session.refresh(client)
    return client


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(client_id: int, session: AsyncSession = Depends(get_session)):
    client = await session.get(ClientModel, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int, data: ClientUpdate, session: AsyncSession = Depends(get_session)
):
    client = await session.get(ClientModel, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    await session.commit()
    await session.refresh(client)
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(client_id: int, session: AsyncSession = Depends(get_session)):
    client = await session.get(ClientModel, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    await session.delete(client)
    await session.commit()
