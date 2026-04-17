"""Client-scoped agent tools — PII is decrypted then masked before return."""
from __future__ import annotations

import json

from sqlalchemy import select

from api.agent.session import AgentSession
from api.db.models import ClientModel, DependentModel, FamilyGroupModel
from api.services.pii.encryptor import PIIEncryptor


async def get_client_summary(session: AgentSession) -> dict:
    """Load the client record (+ optional family group) and return a
    masked summary dict suitable for the LLM context window."""
    db = session.db_session
    enc = session.pii_encryptor

    stmt = (
        select(ClientModel)
        .where(ClientModel.org_id == session.org_id)
        .where(ClientModel.id == session.client_id)
    )
    result = await db.execute(stmt)
    client: ClientModel | None = result.scalar_one_or_none()
    if client is None:
        return {"error": "client_not_found"}

    # Decrypt then mask PII fields
    primary_ssn = enc.decrypt(client.primary_ssn_enc) if client.primary_ssn_enc else None
    primary_dob = enc.decrypt(client.primary_dob_enc) if client.primary_dob_enc else None
    street = enc.decrypt(client.street_enc) if client.street_enc else None
    spouse_ssn = enc.decrypt(client.spouse_ssn_enc) if client.spouse_ssn_enc else None
    spouse_dob = enc.decrypt(client.spouse_dob_enc) if client.spouse_dob_enc else None

    # Optional family group
    family_group_name: str | None = None
    if client.family_group_id:
        fg_stmt = (
            select(FamilyGroupModel)
            .where(FamilyGroupModel.id == client.family_group_id)
            .where(FamilyGroupModel.org_id == session.org_id)
        )
        fg_result = await db.execute(fg_stmt)
        fg: FamilyGroupModel | None = fg_result.scalar_one_or_none()
        if fg:
            family_group_name = fg.display_name

    filing_states: list[str] = []
    if client.filing_states:
        try:
            filing_states = json.loads(client.filing_states)
        except (json.JSONDecodeError, TypeError):
            filing_states = []

    return {
        "name": client.name,
        "primary_first_name": client.primary_first_name,
        "primary_last_name": client.primary_last_name,
        "filing_status": client.filing_status,
        "tax_year": client.tax_year,
        "dependents": client.dependents,
        "workflow_step": client.workflow_step,
        "primary_ssn": PIIEncryptor.mask_ssn(primary_ssn),
        "primary_dob": PIIEncryptor.mask_dob(primary_dob),
        "street": PIIEncryptor.mask_address(street),
        "city": client.city,
        "state": client.state,
        "zip_code": client.zip_code,
        "email": client.email,
        "phone": client.phone,
        "spouse_ssn": PIIEncryptor.mask_ssn(spouse_ssn),
        "spouse_dob": PIIEncryptor.mask_dob(spouse_dob),
        "spouse_email": client.spouse_email,
        "spouse_phone": client.spouse_phone,
        "filing_states": filing_states,
        "family_group_name": family_group_name,
    }


async def list_dependents(session: AgentSession) -> dict:
    """Return all dependents for the current client with masked PII."""
    db = session.db_session
    enc = session.pii_encryptor

    stmt = (
        select(DependentModel)
        .where(DependentModel.org_id == session.org_id)
        .where(DependentModel.client_id == session.client_id)
    )
    result = await db.execute(stmt)
    rows: list[DependentModel] = list(result.scalars().all())

    dependents = []
    for dep in rows:
        ssn = enc.decrypt(dep.ssn_enc) if dep.ssn_enc else None
        dob = enc.decrypt(dep.dob_enc) if dep.dob_enc else None
        dependents.append({
            "first_name": dep.first_name,
            "last_name": dep.last_name,
            "relationship": dep.relationship,
            "is_qualifying_child": dep.is_qualifying_child,
            "ssn_masked": PIIEncryptor.mask_ssn(ssn),
            "dob_masked": PIIEncryptor.mask_dob(dob),
        })

    return {"dependents": dependents, "count": len(dependents)}
