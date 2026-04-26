"""Regression test: ``users.email`` uniqueness is scoped to ``(org_id, email)``.

Same email across two organizations must be allowed; two users with the same
email in one org must not.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from api.auth.models import OrganizationModel, UserModel

pytestmark = pytest.mark.unit


async def test_same_email_allowed_across_orgs(app):
    factory = app.state.test_session_factory
    async with factory() as session:
        org_a = OrganizationModel(name="Firm A", slug="firm-a")
        org_b = OrganizationModel(name="Firm B", slug="firm-b")
        session.add_all([org_a, org_b])
        await session.flush()

        session.add_all(
            [
                UserModel(
                    org_id=org_a.id,
                    auth0_sub="auth0|a",
                    email="cpa@example.com",
                    name="Alice",
                ),
                UserModel(
                    org_id=org_b.id,
                    auth0_sub="auth0|b",
                    email="cpa@example.com",  # same email, different org
                    name="Bob",
                ),
            ]
        )
        await session.commit()  # must not raise


async def test_duplicate_email_within_org_rejected(app):
    factory = app.state.test_session_factory
    async with factory() as session:
        org = OrganizationModel(name="Firm C", slug="firm-c")
        session.add(org)
        await session.flush()

        session.add(
            UserModel(
                org_id=org.id,
                auth0_sub="auth0|c1",
                email="dup@example.com",
                name="One",
            )
        )
        await session.commit()

        session.add(
            UserModel(
                org_id=org.id,
                auth0_sub="auth0|c2",
                email="dup@example.com",  # collision within same org
                name="Two",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
