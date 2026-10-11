import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.core.config import settings


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=settings.max_message_chars
        ),
    ]


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatMessageRead(BaseModel):
    """Never includes tenant_id or seq."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    status: str
    sources: list[dict[str, Any]]
    model: str | None
    created_at: datetime
