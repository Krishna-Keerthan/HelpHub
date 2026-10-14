import uuid
from typing import Annotated, Literal

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


class HybridSearchRequest(BaseModel):
    """Unknown fields (notably a body ``tenant_id``) are a 422."""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS
        ),
    ]
    k: Annotated[int, Field(ge=1, le=50)] = DEFAULT_K


class HybridHitRead(BaseModel):
    """Never includes embeddings, raw_text or the fallback flag.

    ``rrf_score`` orders results; ``vector_score`` (cosine) and ``keyword_score``
    (raw BM25) are per-branch and not comparable with each other.
    """

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    rrf_score: float
    found_by: list[Literal["vector", "keyword"]]
    vector_score: float | None
    keyword_score: float | None


class HybridSearchResponse(BaseModel):
    results: list[HybridHitRead]
    degraded: list[Literal["vector", "keyword"]]
