"""Index mapping, settings and the identifier analyzer, on the real ES."""

import uuid

import pytest
from elasticsearch import AsyncElasticsearch, BadRequestError

from app.core.config import settings
from app.services import es_index
from app.services.es_client import alias_name, get_es

CODES = ["E-4012", "AB-1234-XL", "ERR_CONN_RESET", "v2.3.1"]


async def analyze(es: AsyncElasticsearch, text: str, field: str) -> set[str]:
    result = await es.indices.analyze(index=alias_name(), field=field, text=text)
    return {t["token"] for t in result["tokens"]}


async def test_ensure_index_is_lazy_idempotent_and_aliased() -> None:
    es = get_es()
    await es_index.ensure_index(es)
    await es_index.ensure_index(es)
    aliases = await es.indices.get_alias(name=alias_name())
    assert list(aliases) == [es_index.index_name(1)]
    assert es_index.index_name(1) == f"{settings.es_index_prefix}chunks-v1"


async def test_settings_and_strict_mapping() -> None:
    es = get_es()
    await es_index.ensure_index(es)
    name = es_index.index_name(1)
    got = (await es.indices.get(index=name))[name]
    assert got["settings"]["index"]["number_of_shards"] == "1"
    assert got["settings"]["index"]["number_of_replicas"] == "0"
    assert got["mappings"]["dynamic"] == "strict"
    assert set(got["mappings"]["properties"]) == {
        "tenant_id", "document_id", "chunk_index", "title", "content",
    }  # fmt: skip
    assert got["mappings"]["properties"]["tenant_id"]["type"] == "keyword"


async def test_unmapped_field_is_rejected() -> None:
    es = get_es()
    await es_index.ensure_index(es)
    with pytest.raises(BadRequestError):
        await es.index(
            index=alias_name(),
            id=str(uuid.uuid4()),
            document={"tenant_id": "t", "surprise_field": "x"},
        )


@pytest.mark.parametrize("code", CODES)
async def test_identifier_analyzer_keeps_the_whole_code_as_one_token(
    code: str,
) -> None:
    es = get_es()
    await es_index.ensure_index(es)
    tokens = await analyze(es, f"see {code} now", "content.codes")
    assert code.lower() in tokens  # the original survives (preserve_original)
    assert code.lower().replace("-", "").replace("_", "").replace(".", "") in tokens


async def test_identifier_analyzer_also_indexes_the_fragments() -> None:
    es = get_es()
    await es_index.ensure_index(es)
    assert {"ab", "1234", "xl"} <= await analyze(es, "AB-1234-XL", "content.codes")
    assert {"err", "conn", "reset"} <= await analyze(
        es, "ERR_CONN_RESET", "content.codes"
    )


async def test_content_field_is_english_stemmed() -> None:
    es = get_es()
    await es_index.ensure_index(es)
    assert "declin" in await analyze(es, "declined", "content")
