"""build_query is the only place search bodies are built; the tenant filter in
it cannot be altered by user text (rewritten from the hand-written spec)."""

import json
import uuid

from elasticsearch import AsyncElasticsearch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services.es_client import alias_name, get_es
from app.services.keyword_search import MAX_K, build_query
from tests.conftest import MakeTenant
from tests.helpers.es_helpers import upload_and_index

TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER = "22222222-2222-2222-2222-222222222222"
MALICIOUS = f'x" OR tenant_id:{OTHER} AND {{"match_all": {{}}}} E-4012'
ALLOWED_KEYS = {
    "size", "_source", "query", "bool", "filter", "must", "should", "term",
    "multi_match", "fields", "minimum_should_match", "tenant_id", "boost",
}  # fmt: skip


def walk(node, path=()):
    """Yield (path, key, value) for every dict entry."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            yield from walk(value, (*path, key))
    elif isinstance(node, list):
        for item in node:
            yield from walk(item, path)


def test_exactly_one_tenant_term_filter_and_ids_only() -> None:
    body = build_query(TENANT, MALICIOUS, 5)
    assert body["_source"] is False
    assert body["size"] == 5
    bool_clause = body["query"]["bool"]
    assert bool_clause["filter"] == [{"term": {"tenant_id": str(TENANT)}}]


def test_tenant_id_appears_only_in_the_filter() -> None:
    body = build_query(TENANT, MALICIOUS, 5)
    filter_only = json.dumps(body["query"]["bool"]["filter"])
    rest = dict(body)
    rest["query"] = {"bool": {**body["query"]["bool"], "filter": []}}
    assert str(TENANT) in filter_only
    assert str(TENANT) not in json.dumps(rest)


def test_user_text_only_appears_as_a_query_string_value() -> None:
    body = build_query(TENANT, MALICIOUS, 5)
    keys = {key for _, key, _ in walk(body)}
    assert keys <= ALLOWED_KEYS, keys - ALLOWED_KEYS  # no injected DSL keys
    for _, key, value in walk(body):
        if isinstance(value, str) and "match_all" in value:
            assert key == "query"  # only ever the literal text of a match


def test_no_aggregations_scripts_or_post_filter() -> None:
    dumped = json.dumps(build_query(TENANT, "reports", 5))
    for forbidden in ("aggs", "aggregations", "post_filter", "script", "match_all"):
        assert forbidden not in dumped


def test_k_is_clamped() -> None:
    assert build_query(TENANT, "x", 0)["size"] == 1
    assert build_query(TENANT, "x", 10_000)["size"] == MAX_K


async def test_injection_string_does_not_cross_tenants(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    """Real ES: the raw query hits only the caller's documents."""
    es: AsyncElasticsearch = get_es()
    a, b = await make_tenant(), await make_tenant()
    _, rows_a = await upload_and_index(
        client, owner_conn, es, a, "A doc", "Alpha report about E-4012 errors."
    )
    _, rows_b = await upload_and_index(
        client, owner_conn, es, b, "B doc", "Beta secret about E-4012 errors."
    )
    malicious = f'x" OR tenant_id:{b["id"]} AND {{"match_all": {{}}}} E-4012'

    body = build_query(a["id"], malicious, 50)
    response = await es.search(
        index=alias_name(), query=body["query"], size=body["size"], source=False
    )

    hit_ids = {hit["_id"] for hit in response["hits"]["hits"]}
    assert hit_ids == {str(r["id"]) for r in rows_a}
    assert not hit_ids & {str(r["id"]) for r in rows_b}
