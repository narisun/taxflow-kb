"""Dependent CRUD endpoints with PII encryption."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import DependentModel
from api.auth.dependencies import get_current_user
from api.auth.models import UserModel
from api.routers._helpers import get_client_or_404
from api.services.pii.encryptor import get_pii_encryptor, PIIEncryptor

router = APIRouter(prefix="/api/clients/{client_id}/dependents", tags=["dependents"])


class DependentCreate(BaseModel):
    first_name: str
    last_name: str
    ssn: str | None = None
    dob: str | None = None  # ISO: "2015-06-01"
    relationship: str
    months_lived_with: int = 12
    is_student: bool = False
    is_qualifying_child: bool = True
    is_us_citizen: bool = True


class DependentUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    ssn: str | None = None
    dob: str | None = None
    relationship: str | None = None
    months_lived_with: int | None = None
    is_student: bool | None = None
    is_qualifying_child: bool | None = None
    is_us_citizen: bool | None = None


class DependentResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    ssn_masked: str
    dob_masked: str
    relationship: str
    months_lived_with: int
    is_student: bool
    is_qualifying_child: bool
    is_us_citizen: bool


def _build_dep_response(dep: DependentModel, enc: PIIEncryptor) -> DependentResponse:
    ssn = enc.decrypt(dep.ssn_enc) if dep.ssn_enc else None
    dob_str = enc.decrypt(dep.dob_enc) if dep.dob_enc else None
    dob = date.fromisoformat(dob_str) if dob_str else None
    return DependentResponse(
        id=dep.id,
        first_name=dep.first_name,
        last_name=dep.last_name,
        ssn_masked=PIIEncryptor.mask_ssn(ssn),
        dob_masked=PIIEncryptor.mask_dob(dob),
        relationship=dep.relationship,
        months_lived_with=dep.months_lived_with,
        is_student=dep.is_student,
        is_qualifying_child=dep.is_qualifying_child,
        is_us_citizen=dep.is_us_citizen,
    )


@router.post("", response_model=DependentResponse, status_code=status.HTTP_201_CREATED)
async def add_dependent(
    client_id: int,
    data: DependentCreate,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await get_client_or_404(client_id, session, user)
    enc = get_pii_encryptor()
    dep = DependentModel(
        org_id=user.org_id, created_by=user.id, client_id=client_id,
        first_name=data.first_name, last_name=data.last_name,
        relationship=data.relationship, months_lived_with=data.months_lived_with,
        is_student=data.is_student, is_qualifying_child=data.is_qualifying_child,
        is_us_citizen=data.is_us_citizen,
    )
    if data.ssn:
        dep.ssn_enc = enc.encrypt(data.ssn)
    if data.dob:
        dep.dob_enc = enc.encrypt(data.dob)
    session.add(dep)
    await session.commit()
    await session.refresh(dep)
    return _build_dep_response(dep, enc)


@router.get("", response_model=list[DependentResponse])
async def list_dependents(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(DependentModel).where(
            DependentModel.client_id == client_id,
            DependentModel.org_id == user.org_id,
        )
    )
    deps = result.scalars().all()
    enc = get_pii_encryptor()
    return [_build_dep_response(d, enc) for d in deps]


@router.patch("/{dep_id}", response_model=DependentResponse)
async def update_dependent(
    client_id: int,
    dep_id: int,
    data: DependentUpdate,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(DependentModel).where(
            DependentModel.id == dep_id,
            DependentModel.client_id == client_id,
            DependentModel.org_id == user.org_id,
        )
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail="Dependent not found")
    enc = get_pii_encryptor()
    updates = data.model_dump(exclude_unset=True)
    if "ssn" in updates and updates["ssn"] is not None:
        dep.ssn_enc = enc.encrypt(updates.pop("ssn"))
    else:
        updates.pop("ssn", None)
    if "dob" in updates and updates["dob"] is not None:
        dep.dob_enc = enc.encrypt(updates.pop("dob"))
    else:
        updates.pop("dob", None)
    for field, value in updates.items():
        setattr(dep, field, value)
    await session.commit()
    await session.refresh(dep)
    return _build_dep_response(dep, enc)


@router.delete("/{dep_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dependent(
    client_id: int,
    dep_id: int,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    await get_client_or_404(client_id, session, user)
    result = await session.execute(
        select(DependentModel).where(
            DependentModel.id == dep_id,
            DependentModel.client_id == client_id,
            DependentModel.org_id == user.org_id,
        )
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail="Dependent not found")
    await session.delete(dep)
    await session.commit()
