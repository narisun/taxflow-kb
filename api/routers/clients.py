"""Client CRUD endpoints — tenant-scoped, with PII encryption."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.engine import get_session
from api.db.models import ClientModel, FamilyGroupModel
from api.auth.dependencies import get_current_user, require_role
from api.auth.models import UserModel, ROLE_PERMISSIONS
from api.models.client import (
    ClientCreate, ClientUpdate, ClientResponse, ClientListResponse, PIIRevealRequest,
)
from api.services.pii.encryptor import PIIEncryptor, get_pii_encryptor

router = APIRouter(prefix="/api/clients", tags=["clients"])

# PII fields that come in as plaintext on create/update and map to *_enc columns
_PII_FIELDS = {"primary_ssn", "primary_dob", "spouse_ssn", "spouse_dob", "street"}
# Fields that belong to FamilyGroup, not ClientModel directly
_FAMILY_FIELDS = {"family_group_name", "spouse_first_name", "spouse_last_name"}


def _client_query(user: UserModel):
    """Base query filtered by org. Analysts only see own clients."""
    q = select(ClientModel).where(ClientModel.org_id == user.org_id)
    perms = ROLE_PERMISSIONS.get(user.role, {})
    if not perms.get("can_view_all_clients"):
        q = q.where(ClientModel.created_by == user.id)
    return q


def _build_response(client: ClientModel, enc: PIIEncryptor, family_group: FamilyGroupModel | None = None) -> ClientResponse:
    """Build a ClientResponse with masked PII from a DB model."""
    primary_ssn = enc.decrypt(client.primary_ssn_enc) if client.primary_ssn_enc else None
    primary_dob = enc.decrypt(client.primary_dob_enc) if client.primary_dob_enc else None
    spouse_ssn = enc.decrypt(client.spouse_ssn_enc) if client.spouse_ssn_enc else None
    spouse_dob = enc.decrypt(client.spouse_dob_enc) if client.spouse_dob_enc else None
    street = enc.decrypt(client.street_enc) if client.street_enc else None

    return ClientResponse(
        id=client.id,
        name=client.name,
        filing_status=client.filing_status,
        tax_year=client.tax_year,
        dependents=client.dependents,
        workflow_step=client.workflow_step,
        primary_ssn_masked=enc.mask_ssn(primary_ssn),
        primary_dob_masked=enc.mask_dob(primary_dob),
        spouse_first_name=family_group.spouse_first_name if family_group else None,
        spouse_last_name=family_group.spouse_last_name if family_group else None,
        spouse_ssn_masked=enc.mask_ssn(spouse_ssn),
        spouse_dob_masked=enc.mask_dob(spouse_dob),
        street_masked=enc.mask_address(street),
        city=client.city,
        state=client.state,
        zip_code=client.zip_code,
        family_group_name=family_group.display_name if family_group else None,
        org_id=client.org_id,
        created_by=client.created_by,
        created_at=client.created_at,
        updated_at=client.updated_at,
    )


async def _load_family_group(session: AsyncSession, client: ClientModel) -> FamilyGroupModel | None:
    if not client.family_group_id:
        return None
    return await session.get(FamilyGroupModel, client.family_group_id)


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

    enc = get_pii_encryptor()
    items = []
    for c in clients:
        fg = await _load_family_group(session, c)
        items.append(_build_response(c, enc, fg))

    return ClientListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    enc = get_pii_encryptor()

    # Handle family group creation
    family_group = None
    if data.family_group_name or data.spouse_first_name or data.spouse_last_name:
        # Parse primary name from the client name (first/last)
        name_parts = data.name.split(maxsplit=1)
        primary_first = name_parts[0] if name_parts else ""
        primary_last = name_parts[1] if len(name_parts) > 1 else ""
        family_group = FamilyGroupModel(
            display_name=data.family_group_name or data.name,
            primary_first_name=primary_first,
            primary_last_name=primary_last,
            spouse_first_name=data.spouse_first_name,
            spouse_last_name=data.spouse_last_name,
            org_id=user.org_id,
            created_by=user.id,
        )
        session.add(family_group)
        await session.flush()

    # Build client model excluding PII and family fields
    exclude_fields = _PII_FIELDS | _FAMILY_FIELDS
    model_data = data.model_dump(exclude=exclude_fields)
    client = ClientModel(
        **model_data,
        org_id=user.org_id,
        created_by=user.id,
        family_group_id=family_group.id if family_group else None,
    )

    # Encrypt PII fields
    if data.primary_ssn:
        client.primary_ssn_enc = enc.encrypt(data.primary_ssn)
    if data.primary_dob:
        client.primary_dob_enc = enc.encrypt(data.primary_dob)
    if data.spouse_ssn:
        client.spouse_ssn_enc = enc.encrypt(data.spouse_ssn)
    if data.spouse_dob:
        client.spouse_dob_enc = enc.encrypt(data.spouse_dob)
    if data.street:
        client.street_enc = enc.encrypt(data.street)

    session.add(client)
    await session.commit()
    await session.refresh(client)
    return _build_response(client, enc, family_group)


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

    enc = get_pii_encryptor()
    fg = await _load_family_group(session, client)
    return _build_response(client, enc, fg)


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

    enc = get_pii_encryptor()
    updates = data.model_dump(exclude_unset=True)

    # Handle PII fields: encrypt and set on *_enc columns
    pii_map = {
        "primary_ssn": "primary_ssn_enc",
        "primary_dob": "primary_dob_enc",
        "spouse_ssn": "spouse_ssn_enc",
        "spouse_dob": "spouse_dob_enc",
        "street": "street_enc",
    }
    for pii_field, enc_col in pii_map.items():
        if pii_field in updates:
            value = updates.pop(pii_field)
            if value:
                setattr(client, enc_col, enc.encrypt(value))
            else:
                setattr(client, enc_col, None)

    # Handle spouse name fields via family group
    spouse_fields = {}
    for f in ("spouse_first_name", "spouse_last_name"):
        if f in updates:
            spouse_fields[f] = updates.pop(f)

    if spouse_fields:
        fg = await _load_family_group(session, client)
        if fg:
            for f, v in spouse_fields.items():
                setattr(fg, f, v)
        else:
            name_parts = client.name.split(maxsplit=1)
            fg = FamilyGroupModel(
                display_name=client.name,
                primary_first_name=name_parts[0] if name_parts else "",
                primary_last_name=name_parts[1] if len(name_parts) > 1 else "",
                org_id=client.org_id,
                created_by=client.created_by,
                **spouse_fields,
            )
            session.add(fg)
            await session.flush()
            client.family_group_id = fg.id

    # Set remaining non-PII fields directly
    for field, value in updates.items():
        setattr(client, field, value)

    await session.commit()
    await session.refresh(client)
    fg = await _load_family_group(session, client)
    return _build_response(client, enc, fg)


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


@router.post("/{client_id}/reveal-pii")
async def reveal_pii(
    client_id: int,
    req: PIIRevealRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
):
    perms = ROLE_PERMISSIONS.get(user.role, {})
    if not perms.get("can_view_pii"):
        raise HTTPException(status_code=403, detail="Not authorized to view PII")

    result = await session.execute(
        _client_query(user).where(ClientModel.id == client_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    enc = get_pii_encryptor()

    field_map = {
        "primary_ssn": client.primary_ssn_enc,
        "primary_dob": client.primary_dob_enc,
        "spouse_ssn": client.spouse_ssn_enc,
        "spouse_dob": client.spouse_dob_enc,
        "street": client.street_enc,
    }

    valid_fields = set(field_map.keys())
    revealed = {}
    for f in req.fields:
        if f not in valid_fields:
            raise HTTPException(status_code=400, detail=f"Invalid PII field: {f}")
        enc_value = field_map[f]
        revealed[f] = enc.decrypt(enc_value) if enc_value else None

    return revealed
