"""Tenant-scoped BM25 keyword search.

Elasticsearch only proposes chunk ids and scores (``_source`` is off). Every
id is re-read from Postgres with an explicit tenant filter plus RLS, so a
stale or poisoned index entry can never surface another tenant's text. The ES
call runs with no transaction open; one short tenant transaction hydrates.
"""

import logging
import re
import uuid
from typing import Any

from elasticsearch import AsyncElasticsearch, NotFoundError

from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.repositories.chunks import SearchHit
from app.db.tenant_context import tenant_transaction
from app.services.es_client import alias_name
from app.services.search import TitledHit

logger = logging.getLogger(__name__)

MAX_K = chunks_repo.MAX_K
MAX_CODE_TOKENS = 20
MAX_CODE_TOKEN_CHARS = 128
# Share of the question's words a chunk must contain (code tokens excluded).
WORDS_MINIMUM_SHOULD_MATCH = "50%"
_INNER_DASH = re.compile(r"[A-Za-z0-9]-[A-Za-z0-9]")
_EDGE_PUNCTUATION = ".,;:!?()[]{}\"'"


class SearchUnavailable(Exception):
    """Elasticsearch could not answer. Carries no ES text."""


def _is_code_like(token: str) -> bool:
    return (
        any(ch.isdigit() for ch in token)
        or "_" in token
        or bool(_INNER_DASH.search(token))
    )


def _split_query(query: str) -> tuple[str, list[str]]:
    """(plain words, identifier-like tokens such as E-4012, ERR_CONN_RESET, v2.3.1)."""
    words: list[str] = []
    codes: list[str] = []
    for raw in query.split():
        token = raw.strip(_EDGE_PUNCTUATION)
        if token and _is_code_like(token) and len(token) <= MAX_CODE_TOKEN_CHARS:
            if len(codes) < MAX_CODE_TOKENS:
                codes.append(token)
        else:
            words.append(raw)
    return " ".join(words), codes


def build_query(tenant_id: uuid.UUID, query: str, k: int) -> dict[str, Any]:
    """The only place search bodies are built.

    ``tenant_id`` goes into one ``term`` filter and nowhere else; user text only
    ever appears as the ``query`` value of a ``multi_match``. Identifier-like
    tokens are matched exactly in the ``.codes`` subfields, plain words are
    matched with a minimum_should_match, so "E-4012" never matches "E-4013"
    through a shared fragment.
    """
    words, codes = _split_query(query)
    should: list[dict[str, Any]] = []
    if codes:
        should.append(
            {
                "multi_match": {
                    "query": " ".join(codes),
                    "fields": ["content.codes^3", "title.codes^4"],
                }
            }
        )
    if words:
        should.append(
            {
                "multi_match": {
                    "query": words,
                    "fields": ["content", "title^1.5"],
                    "minimum_should_match": WORDS_MINIMUM_SHOULD_MATCH,
                }
            }
        )
    return {
        "size": max(1, min(k, MAX_K)),
        "_source": False,
        "query": {
            "bool": {
                "filter": [{"term": {"tenant_id": str(tenant_id)}}],
                "must": [{"bool": {"should": should, "minimum_should_match": 1}}],
            }
        },
    }


async def search(
    tenant_id: uuid.UUID, query: str, k: int, es: AsyncElasticsearch
) -> list[TitledHit]:
    body = build_query(tenant_id, query, k)
    try:
        response = await es.search(
            index=alias_name(),
            query=body["query"],
            size=body["size"],
            source=False,
        )
        hits = [
            (uuid.UUID(h["_id"]), float(h["_score"])) for h in response["hits"]["hits"]
        ]
    except NotFoundError:
        return []  # nothing has been indexed yet
    except Exception as exc:  # noqa: BLE001 - any ES/transport failure
        logger.warning("keyword search failed: %s", type(exc).__name__)
        raise SearchUnavailable("search unavailable") from None
    if not hits:
        return []
    scores = dict(hits)
    async with tenant_transaction(tenant_id) as session:
        rows = await chunks_repo.hydrate_chunks(
            session, tenant_id, [i for i, _ in hits]
        )
        titles = await documents_repo.titles_for(
            session, tenant_id, list({row.document_id for row in rows})
        )
    return [
        TitledHit(
            SearchHit(
                chunk_id=row.id,
                document_id=row.document_id,
                chunk_index=row.chunk_index,
                content=row.content,
                char_start=row.char_start,
                char_end=row.char_end,
                score=scores[row.id],
            ),
            titles[row.document_id],
        )
        for row in rows
        if row.document_id in titles
    ]
