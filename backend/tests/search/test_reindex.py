"""Reindexing from Postgres: per tenant, per document, and a versioned rebuild
with an atomic alias swap. Always the runtime role, never the owner."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.services import es_index, keyword_search, reindex
from app.services.es_client import alias_name, get_es
from tests.conftest import MakeTenant
from tests.helpers.es_helpers import doc_index_state, es_ids, upload

BACKEND = Path(__file__).resolve().parents[2]
CONTENT = "Reindex content about shipping rates. "


async def wipe(tenant_id) -> None:
    es = get_es()
    await es.indices.refresh(index=alias_name())  # delete_by_query sees refreshed docs
    await es.delete_by_query(
        index=alias_name(),
        query={"term": {"tenant_id": str(tenant_id)}},
        conflicts="proceed",
        refresh=True,
    )


async def set_pending(owner_conn: AsyncConnection, tenant_id) -> None:
    await owner_conn.execute(
        text(
            "UPDATE documents SET search_index_status='PENDING' WHERE tenant_id = :tid"
        ),
        {"tid": tenant_id},
    )
    await owner_conn.commit()


async def test_reindex_tenant_restores_the_index_and_is_idempotent(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    doc1 = await upload(client, tenant, "One", CONTENT + "one")
    doc2 = await upload(client, tenant, "Two", CONTENT + "two")
    expected = await es_ids(get_es(), tenant_id=tenant["id"])
    await wipe(tenant["id"])
    await set_pending(owner_conn, tenant["id"])
    assert await es_ids(get_es(), tenant_id=tenant["id"]) == set()

    await reindex.reindex_tenant(get_es(), tenant["id"])
    assert await es_ids(get_es(), tenant_id=tenant["id"]) == expected
    await reindex.reindex_tenant(get_es(), tenant["id"])
    assert await es_ids(get_es(), tenant_id=tenant["id"]) == expected
    for doc in (doc1, doc2):
        assert (await doc_index_state(owner_conn, doc))[
            "search_index_status"
        ] == "INDEXED"


async def test_reindex_document_touches_only_that_document(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    doc1 = await upload(client, tenant, "One", CONTENT + "one")
    doc2 = await upload(client, tenant, "Two", CONTENT + "two")
    await wipe(tenant["id"])
    await set_pending(owner_conn, tenant["id"])

    await reindex.reindex_document(get_es(), tenant["id"], doc1)

    assert await es_ids(get_es(), tenant_id=tenant["id"], document_id=doc1)
    assert await es_ids(get_es(), tenant_id=tenant["id"], document_id=doc2) == set()
    assert (await doc_index_state(owner_conn, doc2))["search_index_status"] == "PENDING"


async def test_reindex_never_crosses_tenants(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    a, b = await make_tenant(), await make_tenant()
    doc_b = await upload(client, b, "B", CONTENT)
    await wipe(b["id"])
    await reindex.reindex_document(get_es(), a["id"], doc_b)  # B's id, A's tenant
    assert await es_ids(get_es(), tenant_id=b["id"]) == set()
    assert await es_ids(get_es(), tenant_id=a["id"]) == set()


async def test_full_rebuild_swaps_the_alias_atomically_to_a_new_version(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Own alias so the shared test alias keeps pointing at chunks-v1.
    monkeypatch.setattr(settings, "es_index_prefix", settings.es_index_prefix + "rb-")
    es = get_es()
    tenant = await make_tenant()
    doc = await upload(client, tenant, "Rebuild", CONTENT + "rebuild")
    before = await es_ids(es, tenant_id=tenant["id"])
    assert list(await es.indices.get_alias(name=alias_name())) == [
        es_index.index_name(1)
    ]
    await set_pending(owner_conn, tenant["id"])  # backfill target

    await reindex.reindex_all(es, tenant_ids=[tenant["id"]])

    aliases = await es.indices.get_alias(name=alias_name())
    assert list(aliases) == [es_index.index_name(2)]  # one target, the new version
    assert not await es.indices.exists(index=es_index.index_name(1))
    assert await es_ids(es, tenant_id=tenant["id"]) == before
    assert (await doc_index_state(owner_conn, doc))["search_index_status"] == "INDEXED"
    hits = await keyword_search.search(tenant["id"], "rebuild", 5, es)
    assert [h.document_title for h in hits] == ["Rebuild"]

    await reindex.reindex_all(es, tenant_ids=[tenant["id"]])  # idempotent
    assert list(await es.indices.get_alias(name=alias_name())) == [
        es_index.index_name(3)
    ]
    assert await es_ids(es, tenant_id=tenant["id"]) == before


async def test_rebuild_lists_tenants_from_the_tenants_table(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "es_index_prefix", settings.es_index_prefix + "all-")
    es = get_es()
    tenant = await make_tenant()
    await upload(client, tenant, "Listed", CONTENT + "listed")
    await reindex.reindex_all(es)  # no tenant filter: every tenant in the table
    assert await es_ids(es, tenant_id=tenant["id"])


async def test_reindex_works_without_the_owner_connection(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()
    doc = await upload(client, tenant, "Runtime", CONTENT)
    await wipe(tenant["id"])
    monkeypatch.setattr(
        type(settings), "migration_database_url", property(lambda self: "invalid://")
    )
    await reindex.reindex_document(get_es(), tenant["id"], doc)
    assert await es_ids(get_es(), tenant_id=tenant["id"], document_id=doc)


def test_reindex_code_never_references_the_owner_url() -> None:
    for path in ("app/services/reindex.py", "scripts/reindex.py"):
        source = (BACKEND / path).read_text()
        assert "migration_database" not in source.lower(), path


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "ES_INDEX_PREFIX": settings.es_index_prefix}
    return subprocess.run(
        [sys.executable, "scripts/reindex.py", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


async def test_cli_reindexes_a_tenant(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await upload(client, tenant, "Cli", CONTENT + "cli")
    expected = await es_ids(get_es(), tenant_id=tenant["id"])
    await wipe(tenant["id"])

    result = run_cli("--tenant", str(tenant["id"]))

    assert result.returncode == 0, result.stderr
    assert await es_ids(get_es(), tenant_id=tenant["id"]) == expected


def test_cli_requires_exactly_one_mode() -> None:
    assert run_cli().returncode == 2
    assert run_cli("--all", "--tenant", "x").returncode == 2
    assert run_cli("--document", "00000000-0000-0000-0000-000000000000").returncode == 2


async def test_rebuild_with_failed_documents_keeps_the_live_index(
    client: AsyncClient,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "es_index_prefix", settings.es_index_prefix + "rf-")
    es = get_es()
    tenant = await make_tenant()
    await upload(client, tenant, "Keep me", CONTENT + "keepme")
    before = await es_ids(es, tenant_id=tenant["id"])
    assert before

    async def always_fails(*args, **kwargs) -> bool:
        return False

    monkeypatch.setattr(reindex, "reindex_document", always_fails)
    with pytest.raises(reindex.ReindexIncompleteError) as err:
        await reindex.reindex_all(es, tenant_ids=[tenant["id"]])

    assert err.value.summary.failed == 1
    assert list(await es.indices.get_alias(name=alias_name())) == [
        es_index.index_name(1)
    ]
    assert not await es.indices.exists(index=es_index.index_name(2))
    assert await es_ids(es, tenant_id=tenant["id"]) == before

    summary = await reindex.reindex_all(
        es, tenant_ids=[tenant["id"]], allow_partial=True
    )
    assert summary.failed == 1
    assert list(await es.indices.get_alias(name=alias_name())) == [
        es_index.index_name(2)
    ]
