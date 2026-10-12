"""keyword_search.search on real ES + Postgres: ranking, code queries,
failure handling, transaction discipline, pathological chunks."""

import logging
import time
import uuid

import pytest
from elasticsearch import AsyncElasticsearch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services import keyword_search
from app.services.es_client import get_es
from tests.conftest import MakeTenant, SeededTenant
from tests.helpers.es_helpers import upload_and_index
from tests.helpers.ingestion_helpers import idle_in_transaction

CORPUS = {
    "Declined cards": "E-4012: card declined. The payment processor rejected the card.",
    "Expired cards": "E-4013: card expired. Update the payment card on file.",
    "Sizing": "AB-1234-XL fits large people; see the shirt size guide.",
    "Hoodies": "AB-9999-XL is the extra large hoodie.",
    "Billing": "How to update your payment card and download invoices.",
    "Password reset": "Click forgot password to reset your password. ERR_CONN_RESET means retry. Upgrade to v2.3.1 first.",
}


@pytest.fixture
async def corpus(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> tuple[SeededTenant, AsyncElasticsearch]:
    es = get_es()
    tenant = await make_tenant()
    for title, content in CORPUS.items():
        await upload_and_index(client, owner_conn, es, tenant, title, content)
    return tenant, es


async def titles(corpus, query: str, k: int = 10) -> list[str]:
    tenant, es = corpus
    hits = await keyword_search.search(tenant["id"], query, k, es)
    return [h.document_title for h in hits]


async def test_pure_code_query_finds_only_that_code(corpus) -> None:
    assert await titles(corpus, "E-4012") == ["Declined cards"]


async def test_code_inside_a_sentence_finds_the_code_document_first(corpus) -> None:
    tenant, es = corpus
    hits = await keyword_search.search(
        tenant["id"], "why was my card declined with E-4012", 10, es
    )
    assert hits[0].document_title == "Declined cards"
    scores = {h.document_title: h.hit.score for h in hits}
    other = scores.get("Expired cards", 0.0)
    assert other < scores["Declined cards"] / 1.5  # no tie with E-4013


async def test_plain_question_without_a_code_ranks_the_relevant_doc_first(
    corpus,
) -> None:
    assert (await titles(corpus, "how do I update my card"))[0] == "Billing"


async def test_similar_codes_do_not_match_each_other(corpus) -> None:
    assert await titles(corpus, "AB-1234-XL") == ["Sizing"]
    assert await titles(corpus, "E-4013") == ["Expired cards"]


async def test_code_fragment_and_catenated_forms_are_findable(corpus) -> None:
    assert await titles(corpus, "4012") == ["Declined cards"]
    assert await titles(corpus, "E4012") == ["Declined cards"]


@pytest.mark.parametrize("code", ["ERR_CONN_RESET", "err_conn_reset", "v2.3.1"])
async def test_underscore_and_dotted_identifiers(corpus, code: str) -> None:
    assert await titles(corpus, code) == ["Password reset"]


async def test_results_are_in_descending_score_order(corpus) -> None:
    tenant, es = corpus
    hits = await keyword_search.search(tenant["id"], "card payment", 10, es)
    scores = [h.hit.score for h in hits]
    assert len(scores) >= 2 and scores == sorted(scores, reverse=True)


async def test_response_fields_come_from_postgres(corpus) -> None:
    tenant, es = corpus
    (hit,) = await keyword_search.search(tenant["id"], "E-4012", 5, es)
    assert hit.hit.content == CORPUS["Declined cards"]
    assert hit.hit.char_start == 0
    assert hit.hit.char_end == len(CORPUS["Declined cards"])


async def test_tenant_with_nothing_indexed_gets_empty_list(
    make_tenant: MakeTenant,
) -> None:
    t = await make_tenant()
    assert await keyword_search.search(t["id"], "anything at all", 5, get_es()) == []


async def test_es_unreachable_raises_search_unavailable_without_es_text(
    make_tenant: MakeTenant, caplog: pytest.LogCaptureFixture
) -> None:
    from elasticsearch import AsyncElasticsearch as Client

    t = await make_tenant()
    dead = Client("http://127.0.0.1:1", request_timeout=0.5, max_retries=0)
    caplog.set_level(logging.DEBUG)
    try:
        with pytest.raises(keyword_search.SearchUnavailable) as info:
            await keyword_search.search(t["id"], "secret query words", 5, dead)
    finally:
        await dead.close()
    assert str(info.value) == "search unavailable"
    everything = str(info.value) + caplog.text
    for leak in (
        "127.0.0.1",
        "secret query words",
        "Cannot connect",
        "ClientConnector",
        "Connection error",
    ):
        assert leak not in everything
    assert info.value.__cause__ is None or "127.0.0.1" not in str(info.value)


async def test_no_transaction_is_open_during_the_es_call(
    corpus, owner_conn: AsyncConnection
) -> None:
    tenant, es = corpus
    seen: list[int] = []
    real_search = es.search

    async def spy(**kwargs):
        seen.append(await idle_in_transaction(owner_conn))
        return await real_search(**kwargs)

    es.search = spy  # type: ignore[method-assign]
    try:
        await keyword_search.search(tenant["id"], "E-4012", 5, es)
    finally:
        del es.search
    assert seen == [0]


async def test_pathological_chunk_indexes_within_a_time_limit(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    es = get_es()
    tenant = await make_tenant()
    blob = "".join(chr(97 + i % 26) + str(i % 10) for i in range(500))  # 1000 chars
    hexhash = uuid.uuid4().hex * 4 + uuid.uuid4().hex * 4  # 256 hex chars
    content = f"start {blob} middle {hexhash} end"
    started = time.monotonic()
    await upload_and_index(client, owner_conn, es, tenant, "Blob", content)
    assert time.monotonic() - started < 10
    hits = await keyword_search.search(tenant["id"], hexhash, 5, es)
    assert [h.document_title for h in hits] == ["Blob"]
