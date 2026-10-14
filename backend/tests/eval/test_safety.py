"""Eval safety: prefix guard, guarded ES client, stale-selection logic, lock."""

import uuid
from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from eval import cleanup, guard, lock


@pytest.mark.parametrize(
    "prefix", ["", "test-abc-", "eval", "chunks", "xeval-1-", "eval-"]
)
def test_bad_prefix_is_refused(monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
    monkeypatch.setattr(settings, "es_index_prefix", prefix)
    with pytest.raises(guard.UnsafePrefix):
        guard.assert_eval_prefix()


def test_good_prefix_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "es_index_prefix", "eval-0123456789ab-")
    guard.assert_eval_prefix()


class FakeIndices:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def refresh(self, **kwargs: Any) -> str:
        self.log.append(f"refresh {kwargs.get('index')}")
        return "ok"

    async def get(self, **kwargs: Any) -> str:
        self.log.append("get")
        return "got"


class FakeEs:
    def __init__(self) -> None:
        self.log: list[str] = []
        self.indices = FakeIndices(self.log)

    async def bulk(self, **kwargs: Any) -> str:
        self.log.append("bulk")
        return "ok"

    async def search(self, **kwargs: Any) -> str:
        self.log.append("search")
        return "hits"

    def options(self, **kwargs: Any) -> "FakeEs":
        return self


async def test_guarded_es_blocks_writes_under_a_bad_prefix_but_allows_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeEs()
    es: Any = guard.GuardedEs(fake)
    monkeypatch.setattr(settings, "es_index_prefix", "")
    assert await es.search(index="x") == "hits"
    assert await es.indices.get(index="x") == "got"
    with pytest.raises(guard.UnsafePrefix):
        await es.bulk(operations=[])
    with pytest.raises(guard.UnsafePrefix):
        await es.indices.refresh(index="chunks")
    assert fake.log == ["search", "get"]


async def test_guarded_es_asserts_again_before_every_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeEs()
    es: Any = guard.GuardedEs(fake)
    monkeypatch.setattr(settings, "es_index_prefix", "eval-aaaaaaaaaaaa-")
    assert await es.bulk(operations=[]) == "ok"
    monkeypatch.setattr(settings, "es_index_prefix", "other-")  # changed mid-run
    with pytest.raises(guard.UnsafePrefix):
        await es.bulk(operations=[])
    assert fake.log == ["bulk"]


async def test_guarded_es_refuses_a_write_aimed_at_a_non_eval_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "es_index_prefix", "eval-aaaaaaaaaaaa-")
    es: Any = guard.GuardedEs(FakeEs())
    with pytest.raises(guard.UnsafePrefix):
        await es.indices.refresh(index="chunks")
    assert await es.indices.refresh(index="eval-aaaaaaaaaaaa-chunks") == "ok"
    assert await es.options(request_timeout=5).bulk() == "ok"
    monkeypatch.setattr(settings, "es_index_prefix", "")
    with pytest.raises(guard.UnsafePrefix):
        await es.options(request_timeout=5).bulk()  # options() stays guarded


def test_only_old_eval_indices_are_selected() -> None:
    now = 10_000_000
    created = {
        "eval-a-chunks-v1": now - 11 * 60_000,
        "eval-b-chunks-v1": now - 5 * 60_000,
        "chunks-v1": now - 99 * 60_000,
        "test-x-chunks-v1": now - 99 * 60_000,
    }
    assert cleanup.select_stale_indices(created, now) == ["eval-a-chunks-v1"]
    assert cleanup.select_stale_indices(created, now, min_age_s=0) == [
        "eval-a-chunks-v1",
        "eval-b-chunks-v1",
    ]


def test_only_eval_slugs_are_selected_for_deletion() -> None:
    a, b, c = (uuid.UUID(int=i) for i in (1, 2, 3))
    rows = [(a, "eval-0123456789ab"), (b, "acme"), (c, "my-eval-corp")]
    assert cleanup.select_eval_tenants(rows) == [a]


def test_lock_refuses_a_second_holder(tmp_path: Path) -> None:
    path = str(tmp_path / "lock")
    with lock.hold_lock(path), pytest.raises(lock.LockHeld), lock.hold_lock(path):
        pass
    with lock.hold_lock(path):  # released afterwards
        pass
