"""Elasticsearch index definition: mapping, analyzers, lazy creation.

The index ``<prefix>chunks-v<N>`` sits behind the alias ``<prefix>chunks``;
reindexing builds a new version and swaps the alias atomically. Nothing here
runs at app start: the index is created on first use.
"""

from elasticsearch import AsyncElasticsearch, BadRequestError

from app.core.config import settings
from app.services.es_client import alias_name

# Identifier analyzer: whitespace split keeps "E-4012" together; the delimiter
# filter then emits the original, the catenated form ("e4012") and fragments.
# Queries use ``code_search`` (lowercase only) so a query token must equal an
# indexed token: "E-4012" does not match "E-4013" through the shared "e".
INDEX_SETTINGS = {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
        # "E-4012:" must index the token "e-4012": sentence punctuation next to
        # a code becomes a space before tokenizing.
        "char_filter": {
            "code_edge_punctuation": {
                "type": "pattern_replace",
                "pattern": "[,;:!?()\\[\\]{}\"'`]|\\.(?=\\s|$)",
                "replacement": " ",
            }
        },
        "filter": {
            "code_delimiter": {
                "type": "word_delimiter_graph",
                "preserve_original": True,
                "catenate_all": True,
            }
        },
        "analyzer": {
            "code_analyzer": {
                "type": "custom",
                "char_filter": ["code_edge_punctuation"],
                "tokenizer": "whitespace",
                "filter": ["lowercase", "code_delimiter"],
            },
            "code_search": {
                "type": "custom",
                "tokenizer": "whitespace",
                "filter": ["lowercase"],
            },
        },
    },
}

_CODES = {
    "type": "text",
    "analyzer": "code_analyzer",
    "search_analyzer": "code_search",
}

INDEX_MAPPINGS = {
    "dynamic": "strict",
    "properties": {
        "tenant_id": {"type": "keyword"},
        "document_id": {"type": "keyword"},
        "chunk_index": {"type": "integer"},
        "title": {"type": "text", "analyzer": "english", "fields": {"codes": _CODES}},
        "content": {
            "type": "text",
            "analyzer": "english",
            "fields": {"codes": _CODES},
        },
    },
}


def index_name(version: int) -> str:
    return f"{settings.es_index_prefix}{settings.es_alias}-v{version}"


async def create_index(es: AsyncElasticsearch, name: str) -> None:
    await es.indices.create(
        index=name, settings=INDEX_SETTINGS, mappings=INDEX_MAPPINGS
    )


async def ensure_index(es: AsyncElasticsearch) -> None:
    """Create ``chunks-v1`` and the alias if the alias does not exist yet."""
    alias = alias_name()
    if await es.indices.exists_alias(name=alias):
        return
    name = index_name(1)
    try:
        await create_index(es, name)
    except BadRequestError as exc:
        # A concurrent caller won the race; anything else is a real error.
        if "resource_already_exists_exception" not in str(exc.error):
            raise
    await es.indices.update_aliases(actions=[{"add": {"index": name, "alias": alias}}])
