"""SQLAlchemy models — multi-tenant with org_id on all data tables.

Identity policy: every domain entity uses a UUIDv7 primary key (see
:func:`api.db.ids.new_uuid`). Stored as ``String(36)`` for cross-dialect
portability (Postgres + SQLite-in-tests). Reasons explained in
``api/db/ids.py``.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base, TenantMixin
from api.db.ids import new_uuid


class FamilyGroupModel(TenantMixin, Base):
    __tablename__ = "family_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    display_name: Mapped[str] = mapped_column(String(200))
    primary_first_name: Mapped[str] = mapped_column(String(100), default="")
    primary_last_name: Mapped[str] = mapped_column(String(100), default="")
    spouse_first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    spouse_last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ClientModel(TenantMixin, Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # ``name`` is the human-readable display label (e.g. "Doe Family" or
    # "Sarah Chen"). ``primary_first_name`` / ``primary_last_name`` are the
    # source of truth for the primary taxpayer's identity — they round-trip
    # exactly through edit without any name-parsing heuristics.
    name: Mapped[str] = mapped_column(String(200))
    primary_first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary_last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    filing_status: Mapped[str] = mapped_column(String(10), default="single")
    tax_year: Mapped[int] = mapped_column(Integer, default=2025)
    dependents: Mapped[int] = mapped_column(Integer, default=0)
    workflow_step: Mapped[str] = mapped_column(String(20), default="intake")

    family_group_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("family_groups.id"), nullable=True
    )
    primary_ssn_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    primary_dob_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    spouse_ssn_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    spouse_dob_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    street_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # ── Contact details (plaintext — used for email/SMS routing) ──────────
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    spouse_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    spouse_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Filing requirements ──────────────────────────────────────────────
    # ``filing_federal`` toggles whether a federal return is needed.
    # ``filing_states`` is a JSON-encoded list of 2-letter state codes
    # (e.g. ``["CA","NY"]``) for which a state return is needed. Stored as
    # Text rather than a relational table because the list is small,
    # opaque to other queries, and tied 1:1 to the client.
    filing_federal: Mapped[bool] = mapped_column(default=True)
    filing_states: Mapped[str] = mapped_column(Text, default="[]")

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

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), index=True
    )
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

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), index=True
    )
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

    # Review audit trail. ``reviewed_by`` is the user who flipped status to
    # ``approved``; ``reviewed_at`` is when. Both NULL until first approval.
    # We deliberately keep these on the document row (instead of a generic
    # audit-log table) because the most common consumer is the review-docs
    # chip, which needs to show "reviewed by X on Y" inline per document.
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    client: Mapped["ClientModel"] = relationship(back_populates="documents")

    __table_args__ = (
        Index("ix_documents_org_client", "org_id", "client_id"),
    )


class ChatMessageModel(TenantMixin, Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), index=True
    )
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

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), index=True
    )
    tax_year: Mapped[int] = mapped_column(Integer)
    filing_status: Mapped[str] = mapped_column(String(10))
    draft_json: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="computed")
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id"), nullable=True
    )

    client: Mapped["ClientModel"] = relationship()

    __table_args__ = (
        UniqueConstraint("org_id", "client_id", "tax_year", name="uq_draft_org_client_year"),
        Index("ix_drafts_org_client", "org_id", "client_id"),
    )


class ConversationModel(TenantMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    client_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("clients.id"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    is_active: Mapped[bool] = mapped_column(default=True)
    conversation_type: Mapped[str] = mapped_column(String(20), default="client")

    messages: Mapped[list["ConversationMessageModel"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        order_by="ConversationMessageModel.created_at",
    )

    __table_args__ = (
        Index("ix_conv_org_client_user", "org_id", "client_id", "user_id"),
        Index("ix_conv_type_user", "conversation_type", "user_id", "org_id"),
    )


class ConversationMessageModel(TenantMixin, Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user|assistant|tool_call|tool_result
    content: Mapped[str] = mapped_column(Text, default="")
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    conversation: Mapped["ConversationModel"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_conv_msg_conv_created", "conversation_id", "created_at"),
        Index("ix_conv_msg_org", "org_id"),
    )


class ManualEntryModel(TenantMixin, Base):
    __tablename__ = "manual_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.id"), index=True
    )
    form_type: Mapped[str] = mapped_column(String(30))
    form_index: Mapped[int] = mapped_column(Integer, default=0)
    field_name: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))

    __table_args__ = (
        Index("ix_manual_entries_org_client", "org_id", "client_id"),
    )
