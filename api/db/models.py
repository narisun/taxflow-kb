"""SQLAlchemy models — multi-tenant with org_id on all data tables."""

from datetime import datetime

from sqlalchemy import String, Integer, Text, Float, ForeignKey, Index, UniqueConstraint, LargeBinary, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base, TenantMixin


class FamilyGroupModel(TenantMixin, Base):
    __tablename__ = "family_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    primary_first_name: Mapped[str] = mapped_column(String(100), default="")
    primary_last_name: Mapped[str] = mapped_column(String(100), default="")
    spouse_first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    spouse_last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ClientModel(TenantMixin, Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    filing_status: Mapped[str] = mapped_column(String(10), default="single")
    tax_year: Mapped[int] = mapped_column(Integer, default=2025)
    dependents: Mapped[int] = mapped_column(Integer, default=0)
    workflow_step: Mapped[str] = mapped_column(String(20), default="intake")

    family_group_id: Mapped[int | None] = mapped_column(ForeignKey("family_groups.id"), nullable=True)
    primary_ssn_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    primary_dob_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    spouse_ssn_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    spouse_dob_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    street_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    documents: Mapped[list["DocumentModel"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ChatMessageModel"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_clients_org_created_by", "org_id", "created_by"),
    )


class DependentModel(TenantMixin, Base):
    __tablename__ = "dependents"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    ssn_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dob_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    relationship: Mapped[str] = mapped_column(String(30))
    months_lived_with: Mapped[int] = mapped_column(Integer, default=12)
    is_student: Mapped[bool] = mapped_column(default=False)
    is_qualifying_child: Mapped[bool] = mapped_column(default=True)
    is_us_citizen: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        Index("ix_dependents_org_client", "org_id", "client_id"),
    )


class DocumentModel(TenantMixin, Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    form_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extracted_data: Mapped[str] = mapped_column(Text, default="{}")
    file_path: Mapped[str] = mapped_column(String(500), default="")
    extracted_data_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    file_content_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    file_content_type: Mapped[str] = mapped_column(String(50), default="application/pdf")
    file_name: Mapped[str] = mapped_column(String(200), default="")
    flags: Mapped[str] = mapped_column(Text, default="[]")

    client: Mapped["ClientModel"] = relationship(back_populates="documents")

    __table_args__ = (
        Index("ix_documents_org_client", "org_id", "client_id"),
    )


class ChatMessageModel(TenantMixin, Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(30), default="text")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    client: Mapped["ClientModel"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_chat_messages_org_client", "org_id", "client_id"),
    )


class TaxReturnDraftModel(TenantMixin, Base):
    __tablename__ = "tax_return_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    tax_year: Mapped[int] = mapped_column(Integer)
    filing_status: Mapped[str] = mapped_column(String(10))
    draft_json: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    client: Mapped["ClientModel"] = relationship()

    __table_args__ = (
        UniqueConstraint("org_id", "client_id", name="uq_draft_org_client"),
        Index("ix_drafts_org_client", "org_id", "client_id"),
    )


class ManualEntryModel(TenantMixin, Base):
    __tablename__ = "manual_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    form_type: Mapped[str] = mapped_column(String(30))
    form_index: Mapped[int] = mapped_column(Integer, default=0)
    field_name: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(Text)
    entered_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        Index("ix_manual_entries_org_client", "org_id", "client_id"),
    )
