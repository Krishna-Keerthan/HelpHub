import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.services.search import DEFAULT_K, MAX_QUERY_CHARS


class SearchRequest(BaseModel):
    query: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS
        ),
    ]
    k: Annotated[int, Field(ge=1, le=50)] = DEFAULT_K


class KeywordSearchRequest(BaseModel):
    """Unknown fields (notably a body ``tenant_id``) are a 422: the tenant
    comes from the verified token only."""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS
        ),
    ]
    k: Annotated[int, Field(ge=1, le=50)] = DEFAULT_K


class SearchHitRead(BaseModel):
    """Never includes embeddings, raw_text or the fallback flag."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    score: float
