"""Integration tests for multi-tenant auth flow."""

import pytest
from api.auth.models import OrganizationModel, UserModel, ROLE_PERMISSIONS
from api.auth.dependencies import get_user_permissions


def test_role_permissions_admin():
    perms = ROLE_PERMISSIONS["admin"]
    assert perms["can_view_all_clients"] is True
    assert perms["can_manage_users"] is True
    assert perms["can_file_returns"] is True


def test_role_permissions_analyst():
    perms = ROLE_PERMISSIONS["analyst"]
    assert perms["can_view_all_clients"] is False
    assert perms["can_manage_users"] is False
    assert perms["can_file_returns"] is False


def test_role_permissions_preparer():
    perms = ROLE_PERMISSIONS["preparer"]
    assert perms["can_view_all_clients"] is False
    assert perms["can_file_returns"] is True
    assert perms["can_approve_documents"] is True


def test_all_roles_have_permissions():
    for role in ["admin", "supervisor", "preparer", "analyst"]:
        perms = ROLE_PERMISSIONS[role]
        assert isinstance(perms, dict)
        assert "can_view_all_clients" in perms
        assert "can_manage_users" in perms
        assert "can_file_returns" in perms


def test_organization_model_fields():
    org = OrganizationModel(name="Test Firm", slug="test-firm", plan="starter", is_active=True)
    assert org.name == "Test Firm"
    assert org.slug == "test-firm"
    assert org.plan == "starter"
    assert org.is_active is True


def test_user_model_fields():
    user = UserModel(
        org_id="test-org-id",
        auth0_sub="auth0|123",
        email="test@test.com",
        name="Test User",
        role="preparer",
        is_active=True,
    )
    assert user.role == "preparer"
    assert user.is_active is True
    assert user.auth0_sub == "auth0|123"


def test_get_user_permissions_returns_dict():
    user = UserModel(
        org_id="test", auth0_sub="auth0|x",
        email="x@x.com", name="X", role="supervisor",
    )
    perms = get_user_permissions(user)
    assert perms["can_view_all_clients"] is True
    assert perms["can_manage_users"] is False


def test_get_user_permissions_unknown_role():
    user = UserModel(
        org_id="test", auth0_sub="auth0|y",
        email="y@y.com", name="Y", role="unknown_role",
    )
    perms = get_user_permissions(user)
    # Should fall back to analyst permissions
    assert perms["can_view_all_clients"] is False
    assert perms["can_file_returns"] is False
