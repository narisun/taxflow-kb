"""Seed the database with a dev organization, user, and sample clients."""

from api.auth.models import OrganizationModel, UserModel
from api.db.models import ClientModel


async def seed_dev_data(session):
    """Create dev org + user + sample clients if the DB is empty."""
    from sqlalchemy import select, func

    result = await session.execute(select(func.count(OrganizationModel.id)))
    if (result.scalar() or 0) > 0:
        return

    org = OrganizationModel(
        name="Chen & Associates CPA",
        slug="chen-associates",
        plan="professional",
    )
    session.add(org)
    await session.flush()

    user = UserModel(
        org_id=org.id,
        auth0_sub="dev|local",
        email="sarah@chen-cpa.com",
        name="Sarah Chen",
        role="admin",
        onboarding_status="complete",
    )
    session.add(user)
    await session.flush()

    sample_clients = [
        {"name": "Smith, John", "filing_status": "single", "tax_year": 2025, "dependents": 1, "workflow_step": "tax_return"},
        {"name": "Johnson Family", "filing_status": "mfj", "tax_year": 2025, "dependents": 3, "workflow_step": "documents"},
        {"name": "Chen, Wei", "filing_status": "single", "tax_year": 2025, "dependents": 0, "workflow_step": "intake"},
        {"name": "Garcia Household", "filing_status": "mfj", "tax_year": 2025, "dependents": 4, "workflow_step": "tax_return"},
        {"name": "Patel Family", "filing_status": "mfj", "tax_year": 2025, "dependents": 1, "workflow_step": "filed"},
    ]
    for data in sample_clients:
        client = ClientModel(**data, org_id=org.id, created_by=user.id)
        session.add(client)

    await session.commit()
    print(f"[seed] Created org '{org.name}', user '{user.name}', {len(sample_clients)} clients")
