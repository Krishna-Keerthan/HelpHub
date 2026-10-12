"""One shared AsyncElasticsearch, created lazily and closed at shutdown.

Nothing here contacts Elasticsearch at import or app start: the app (and
/health) work with ES down. Errors are logged by class name only; ES response
bodies and messages can echo documents or queries.
"""

import logging

from elasticsearch import AsyncElasticsearch

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 2

_client: AsyncElasticsearch | None = None


def alias_name() -> str:
    return f"{settings.es_index_prefix}{settings.es_alias}"


def get_es() -> AsyncElasticsearch:
    """The shared client (FastAPI dependency and plain accessor)."""
    global _client
    if _client is None:
        _client = AsyncElasticsearch(
            settings.es_endpoint,
            request_timeout=settings.es_timeout_seconds,
            max_retries=MAX_RETRIES,
            retry_on_timeout=True,
        )
    return _client


async def close_es() -> None:
    global _client
    client, _client = _client, None
    if client is not None:
        await client.close()


async def es_ready(es: AsyncElasticsearch | None = None) -> bool:
    """True when the cluster answers with at least yellow health."""
    client = es or get_es()
    try:
        health = await client.cluster.health(wait_for_status="yellow", timeout="2s")
        return health["status"] in ("yellow", "green")
    except Exception as exc:  # noqa: BLE001 - any failure means "not ready"
        logger.warning("elasticsearch not ready: %s", type(exc).__name__)
        return False
