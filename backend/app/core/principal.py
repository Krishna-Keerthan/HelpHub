import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """The authenticated user as plain data; holds no session."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
