"""Organization, User, and Role models for multi-tenancy."""

import uuid
from datetime import datetime, UTC
from sqlalchemy import String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class OrganizationModel(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(20), default="starter")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    users: Mapped[list["UserModel"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    auth0_sub: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="preparer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    organization: Mapped["OrganizationModel"] = relationship(back_populates="users")


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
