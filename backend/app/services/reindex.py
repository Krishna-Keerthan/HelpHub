"""Rebuild the Elasticsearch copy from Postgres.

Reads go through ``tenant_transaction`` (the runtime role, RLS applied), one
tenant at a time; the owner connection is never used. Every function is
idempotent: ``_id`` is the chunk id, so re-running overwrites in place.
"""

import logging
import re
import uuid
from dataclasses import dataclass

from elasticsearch import AsyncElasticsearch

from app.db.repositories import documents as documents_repo
from app.db.repositories import tenants as tenants_repo
from app.db.tenant_context import tenant_transaction
from app.services import es_index, search_sync
from app.services.es_client import alias_name

logger = logging.getLogger(__name__)

_VERSION = re.compile(r"-v(\d+)$")


@dataclass
class ReindexSummary:
    documents: int = 0
    indexed: int = 0
    failed: int = 0

    def add(self, indexed: bool) -> None:
        self.documents += 1
        if indexed:
            self.indexed += 1
        else:
            self.failed += 1


async def reindex_document(
    es: AsyncElasticsearch,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    index: str | None = None,
) -> bool:
    return await search_sync.index_document(tenant_id, document_id, es, index=index)


async def reindex_tenant(
    es: AsyncElasticsearch, tenant_id: uuid.UUID, *, index: str | None = None
) -> ReindexSummary:
    """Re-index every READY document of one tenant (this also backfills PENDING)."""
    async with tenant_transaction(tenant_id) as session:
        document_ids = await documents_repo.ready_document_ids(session, tenant_id)
    summary = ReindexSummary()
    for document_id in document_ids:
        summary.add(await reindex_document(es, tenant_id, document_id, index=index))
    return summary


async def _current_version(es: AsyncElasticsearch) -> int:
    alias = alias_name()
    if not await es.indices.exists_alias(name=alias):
        return 0
    versions = [
        int(m.group(1))
        for name in await es.indices.get_alias(name=alias)
        if (m := _VERSION.search(name))
    ]
    return max(versions, default=0)


async def reindex_all(
    es: AsyncElasticsearch, *, tenant_ids: list[uuid.UUID] | None = None
) -> ReindexSummary:
    """Build ``chunks-v<N+1>`` from Postgres, then swap the alias atomically."""
    tenants = tenant_ids if tenant_ids is not None else await tenants_repo.list_ids()
    alias = alias_name()
    old = await _current_version(es)
    new_index = es_index.index_name(old + 1)
    await es_index.create_index(es, new_index)
    summary = ReindexSummary()
    try:
        for tenant_id in tenants:
            part = await reindex_tenant(es, tenant_id, index=new_index)
            summary.documents += part.documents
            summary.indexed += part.indexed
            summary.failed += part.failed
        await es.indices.refresh(index=new_index)
        # One request: the alias never points at zero or two indices.
        actions: list[dict] = [{"add": {"index": new_index, "alias": alias}}]
        if old:
            actions.insert(
                0, {"remove": {"index": es_index.index_name(old), "alias": alias}}
            )
        await es.indices.update_aliases(actions=actions)
    except BaseException:
        await es.indices.delete(index=new_index, ignore_unavailable=True)
        raise
    if old:
        await es.indices.delete(index=es_index.index_name(old), ignore_unavailable=True)
    logger.info(
        "reindexed into %s: documents=%d indexed=%d failed=%d",
        new_index,
        summary.documents,
        summary.indexed,
        summary.failed,
    )
    return summary
