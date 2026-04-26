from pydantic import BaseModel, Field
from datetime import datetime


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    message_type: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]
    client_id: str
    page: int = 1
    page_size: int = 100
