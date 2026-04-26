"""Onboarding flow — first-time signup, wizard completion, gates."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.auth.dependencies import get_current_user
from api.auth.models import OrganizationModel, UserModel

pytestmark = pytest.mark.unit


def _override_user_factory(app, user: UserModel):
    """Build a fresh override that re-attaches the user to a clean session."""
    async def _override():
        session_factory = app.state.test_session_factory
        async with session_factory() as session:
            return await session.merge(user)
    return _override


async def _make_pending_user(app, *, sub: str = "auth0|new-user") -> UserModel:
    """Insert a user mid-onboarding (no org, status=pending)."""
    factory = app.state.test_session_factory
    async with factory() as session:
        user = UserModel(
            org_id=None,
            auth0_sub=sub,
            email=f"{sub.split('|')[1]}@example.com",
            name="New User",
            role="preparer",
            onboarding_status="pending",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


# ─────────────────────────────────────────────────────────────────────────────
# /me — returns onboarding state for both pending and complete users
# ─────────────────────────────────────────────────────────────────────────────


async def test_me_for_pending_user_has_no_org(app):
    user = await _make_pending_user(app)
    app.dependency_overrides[get_current_user] = _override_user_factory(app, user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/auth/me")
    app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["organization"] is None
    assert body["user"]["onboarding_status"] == "pending"
    assert body["user"]["org_id"] is None


async def test_me_for_complete_user_includes_org(authenticated_client, seeded_user):
    resp = await authenticated_client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["onboarding_status"] == "complete"
    assert body["organization"] is not None
    assert body["organization"]["id"] == seeded_user.org_id


# ─────────────────────────────────────────────────────────────────────────────
# Tenant-scoped routes refuse pending users
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/clients"),
        ("POST", "/api/clients"),
        ("GET", "/api/clients/1/documents"),
        ("GET", "/api/clients/1/chat"),
        ("GET", "/api/clients/1/returns/draft"),
    ],
)
async def test_pending_user_blocked_from_tenant_routes(app, method, path):
    user = await _make_pending_user(app, sub=f"auth0|{method}-{hash(path)}")
    app.dependency_overrides[get_current_user] = _override_user_factory(app, user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        if method == "POST":
            resp = await c.post(
                path,
                json={"name": "X", "filing_status": "single", "tax_year": 2025},
            )
        else:
            resp = await c.request(method, path)
    app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 403
    assert "onboarding" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/complete-onboarding
# ─────────────────────────────────────────────────────────────────────────────


async def test_complete_onboarding_creates_org_and_links_user(app):
    user = await _make_pending_user(app, sub="auth0|wizard-1")
    app.dependency_overrides[get_current_user] = _override_user_factory(app, user)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/auth/complete-onboarding",
            json={
                "firm_name": "Acme Tax Partners",
                "role": "admin",
                "timezone": "America/Los_Angeles",
            },
        )
    app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["onboarding_status"] == "complete"
    assert body["user"]["timezone"] == "America/Los_Angeles"
    assert body["user"]["role"] == "admin"
    assert body["organization"]["name"] == "Acme Tax Partners"
    assert body["organization"]["slug"] == "acme-tax-partners"
    assert body["user"]["org_id"] == body["organization"]["id"]


async def test_complete_onboarding_dedupes_slug(app):
    """Two firms can pick the same display name; slugs must stay unique."""
    user_a = await _make_pending_user(app, sub="auth0|firm-a")
    app.dependency_overrides[get_current_user] = _override_user_factory(app, user_a)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp_a = await c.post(
            "/api/auth/complete-onboarding",
            json={"firm_name": "Smith Tax LLC"},
        )

    user_b = await _make_pending_user(app, sub="auth0|firm-b")
    app.dependency_overrides[get_current_user] = _override_user_factory(app, user_b)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp_b = await c.post(
            "/api/auth/complete-onboarding",
            json={"firm_name": "Smith Tax LLC"},
        )
    app.dependency_overrides.pop(get_current_user, None)

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    slug_a = resp_a.json()["organization"]["slug"]
    slug_b = resp_b.json()["organization"]["slug"]
    assert slug_a == "smith-tax-llc"
    assert slug_b != slug_a
    assert slug_b.startswith("smith-tax-llc-")


async def test_cannot_complete_onboarding_twice(authenticated_client):
    """Already-onboarded user gets 409 if they POST again."""
    resp = await authenticated_client.post(
        "/api/auth/complete-onboarding",
        json={"firm_name": "Second Firm"},
    )
    assert resp.status_code == 409


async def test_invite_token_returns_not_implemented(app):
    user = await _make_pending_user(app, sub="auth0|invitee")
    app.dependency_overrides[get_current_user] = _override_user_factory(app, user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/auth/complete-onboarding",
            json={"firm_name": "Joining Firm", "invite_token": "abc"},
        )
    app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 501


async def test_blank_firm_name_rejected(app):
    user = await _make_pending_user(app, sub="auth0|blank")
    app.dependency_overrides[get_current_user] = _override_user_factory(app, user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/auth/complete-onboarding",
            json={"firm_name": "   "},
        )
    app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 422


async def test_first_time_provisioned_user_lands_in_pending(app):
    """When AUTH0_ALLOW_DEV_BYPASS is on, no token resolves to a seeded admin
    that's already complete — verified elsewhere. This test instead ensures
    that a freshly inserted pending user can fetch /me without a 403."""
    user = await _make_pending_user(app, sub="auth0|bare")
    app.dependency_overrides[get_current_user] = _override_user_factory(app, user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        me = await c.get("/api/auth/me")
    app.dependency_overrides.pop(get_current_user, None)

    assert me.status_code == 200
    body = me.json()
    assert body["user"]["onboarding_status"] == "pending"
    assert body["organization"] is None


async def test_pending_user_org_is_created_with_starter_plan(app):
    user = await _make_pending_user(app, sub="auth0|plan-check")
    app.dependency_overrides[get_current_user] = _override_user_factory(app, user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/auth/complete-onboarding",
            json={"firm_name": "Default Plan Co"},
        )
    app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    assert resp.json()["organization"]["plan"] == "starter"
