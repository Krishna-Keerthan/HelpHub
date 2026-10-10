import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Status = Literal["PENDING", "READY", "FAILED"]


class DocumentCreate(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    # Emptiness and size are checked by the service, after NUL stripping.
    content: str


class DocumentRead(BaseModel):
    """Never includes raw_text."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: Status
    error: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
