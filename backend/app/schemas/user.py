import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.types import NewPassword, NormalizedEmail

Role = Literal["admin", "agent", "viewer"]


class UserCreate(BaseModel):
    email: NormalizedEmail
    password: NewPassword
    role: Role = "agent"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role: Role
    is_active: bool
    created_at: datetime
