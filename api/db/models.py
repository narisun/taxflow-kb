"""SQLAlchemy models — multi-tenant with org_id on all data tables."""

from sqlalchemy import String, Integer, Text, Float, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base, TenantMixin


class ClientModel(TenantMixin, Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    filing_status: Mapped[str] = mapped_column(String(10), default="single")
    tax_year: Mapped[int] = mapped_column(Integer, default=2025)
    dependents: Mapped[int] = mapped_column(Integer, default=0)
    workflow_step: Mapped[str] = mapped_column(String(20), default="intake")

    documents: Mapped[list["DocumentModel"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ChatMessageModel"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_clients_org_created_by", "org_id", "created_by"),
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
