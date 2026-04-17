"""Pydantic schemas for research agent endpoints."""
from datetime import datetime
from pydantic import BaseModel


class ResearchThreadResponse(BaseModel):
    id: str
    title: str
    conversation_type: str = "research"
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ResearchThreadListResponse(BaseModel):
    items: list[ResearchThreadResponse]
    total: int


class ResearchMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    tool_name: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ResearchMessageListResponse(BaseModel):
    messages: list[ResearchMessageResponse]
    conversation_id: str


class SendResearchMessageRequest(BaseModel):
    content: str
