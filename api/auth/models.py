"""Organization, User, and Role models for multi-tenancy.

Identity policy matches the rest of the schema — UUIDv7 (time-ordered) PKs.
See ``api/db/ids.py`` for rationale.
"""

from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base
from api.db.ids import new_uuid as _uuid


class OrganizationModel(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(20), default="starter")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    users: Mapped[list["UserModel"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class UserModel(Base):
    __tablename__ = "users"

    # ── Multi-tenant uniqueness ────────────────────────────────────────────
    # Email is unique per (org, email) so the same person can hold distinct
    # accounts across CPA firms. ``auth0_sub`` is globally unique — one Auth0
    # identity ↔ one TaxFlow user row.
    #
    # ── Onboarding state machine ───────────────────────────────────────────
    # First-time Auth0 logins create a row with ``org_id=NULL`` and
    # ``onboarding_status='pending'``. The user must complete the in-app
    # onboarding wizard (POST /api/auth/complete-onboarding), which creates
    # an Organization, links the user, and flips status to 'complete'. All
    # tenant-scoped routes refuse pending users via ``require_onboarded_user``.
    #
    # MIGRATION NOTE (until Alembic lands in Phase C):
    #
    #     ALTER TABLE users DROP CONSTRAINT users_email_key;
    #     DROP INDEX IF EXISTS ix_users_email;
    #     CREATE INDEX ix_users_email ON users (email);
    #     CREATE UNIQUE INDEX uq_users_org_email ON users (org_id, email);
    #     ALTER TABLE users ALTER COLUMN org_id DROP NOT NULL;
    #     ALTER TABLE users ADD COLUMN onboarding_status VARCHAR(20)
    #                       NOT NULL DEFAULT 'pending';
    #     ALTER TABLE users ADD COLUMN timezone VARCHAR(64);
    #     -- existing rows already have orgs, mark them complete:
    #     UPDATE users SET onboarding_status='complete' WHERE org_id IS NOT NULL;
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_users_org_email"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # NULL until the user completes the onboarding wizard.
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )
    auth0_sub: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(200), index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="preparer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    onboarding_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    organization: Mapped["OrganizationModel | None"] = relationship(back_populates="users")


ROLE_PERMISSIONS = {
    "admin": {
        "can_view_all_clients": True,
        "can_manage_users": True,
        "can_file_returns": True,
        "can_approve_documents": True,
        "can_send_advisory": True,
        "can_view_analytics": True,
        "can_view_pii": True,
    },
    "supervisor": {
        "can_view_all_clients": True,
        "can_manage_users": False,
        "can_file_returns": True,
        "can_approve_documents": True,
        "can_send_advisory": True,
        "can_view_analytics": True,
        "can_view_pii": True,
    },
    "preparer": {
        "can_view_all_clients": False,
        "can_manage_users": False,
        "can_file_returns": True,
        "can_approve_documents": True,
        "can_send_advisory": True,
        "can_view_analytics": False,
        "can_view_pii": False,
    },
    "analyst": {
        "can_view_all_clients": False,
        "can_manage_users": False,
        "can_file_returns": False,
        "can_approve_documents": False,
        "can_send_advisory": False,
        "can_view_analytics": False,
        "can_view_pii": False,
    },
}
