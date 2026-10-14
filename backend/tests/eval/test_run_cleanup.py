"""Teardown logic of the evaluation runner, with fakes (no database)."""

import uuid
from typing import Any

import pytest

from eval import run_eval

TENANT = uuid.UUID(int=7)


class FakeIndices:
    def __init__(self, fail: bool = False) -> None:
        self.deleted: list[list[str]] = []
        self.fail = fail

    async def get(self, **kwargs: Any) -> dict[str, Any]:
        return {"eval-x-chunks-v1": {}}

    async def delete(self, **kwargs: Any) -> None:
        if self.fail:
            raise ConnectionError("down")
        self.deleted.append(kwargs["index"])


class FakeEs:
    def __init__(self, fail: bool = False) -> None:
        self.indices = FakeIndices(fail)


async def test_keep_removes_nothing() -> None:
    es, deleted = FakeEs(), []

    async def delete_tenant(t: uuid.UUID) -> None:
        deleted.append(t)

    await run_eval.teardown(
        keep=True,
        prefix="eval-x-",
        tenant_id=TENANT,
        raw_es=es,
        es=es,
        delete_tenant=delete_tenant,
    )
    assert es.indices.deleted == [] and deleted == []


async def test_teardown_deletes_indices_then_tenant() -> None:
    es, deleted = FakeEs(), []

    async def delete_tenant(t: uuid.UUID) -> None:
        deleted.append(t)

    await run_eval.teardown(
        keep=False,
        prefix="eval-x-",
        tenant_id=TENANT,
        raw_es=es,
        es=es,
        delete_tenant=delete_tenant,
    )
    assert es.indices.deleted == [["eval-x-chunks-v1"]] and deleted == [TENANT]


async def test_tenant_is_deleted_even_when_index_deletion_fails() -> None:
    es, deleted = FakeEs(fail=True), []

    async def delete_tenant(t: uuid.UUID) -> None:
        deleted.append(t)

    with pytest.raises(ConnectionError):
        await run_eval.teardown(
            keep=False,
            prefix="eval-x-",
            tenant_id=TENANT,
            raw_es=es,
            es=es,
            delete_tenant=delete_tenant,
        )
    assert deleted == [TENANT]


async def test_teardown_without_a_tenant_still_removes_indices() -> None:
    es = FakeEs()

    async def delete_tenant(t: uuid.UUID) -> None:
        raise AssertionError("no tenant was created")

    await run_eval.teardown(
        keep=False,
        prefix="eval-x-",
        tenant_id=None,
        raw_es=es,
        es=es,
        delete_tenant=delete_tenant,
    )
    assert es.indices.deleted == [["eval-x-chunks-v1"]]
