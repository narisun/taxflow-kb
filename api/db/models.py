from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ClientModel(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    filing_status: Mapped[str] = mapped_column(String(10), default="single")
    tax_year: Mapped[int] = mapped_column(Integer, default=2024)
    dependents: Mapped[int] = mapped_column(Integer, default=0)
    workflow_step: Mapped[str] = mapped_column(String(20), default="intake")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    documents: Mapped[list["DocumentModel"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ChatMessageModel"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class DocumentModel(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    form_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extracted_data: Mapped[str] = mapped_column(Text, default="{}")
    file_path: Mapped[str] = mapped_column(String(500), default="")
    flags: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    client: Mapped["ClientModel"] = relationship(back_populates="documents")


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(30), default="text")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    client: Mapped["ClientModel"] = relationship(back_populates="messages")
