"""Conversation Pydantic schemas."""
from datetime import datetime

from pydantic import BaseModel


class ConversationResponse(BaseModel):
    id: str
    client_id: str
    user_id: str
    title: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int


class ConversationMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    tool_name: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ConversationMessageListResponse(BaseModel):
    messages: list[ConversationMessageResponse]
    conversation_id: str


class SendMessageRequest(BaseModel):
    content: str
