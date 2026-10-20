import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.services.search import DEFAULT_K, MAX_QUERY_CHARS


class SearchRequest(BaseModel):
    query: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS
        ),
    ]
    k: Annotated[int, Field(ge=1, le=50)] = DEFAULT_K
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid"


class SearchHitRead(BaseModel):
    """Never includes embeddings, raw_text or the fallback flag."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    score: float | None  # cosine similarity to the query; null in keyword mode
    rrf_score: float  # orders the results
    found_by: list[Literal["vector", "keyword"]]
    vector_rank: int | None  # 1-based rank among vector candidates, if found there
    keyword_rank: int | None  # 1-based rank among keyword candidates, if found there
