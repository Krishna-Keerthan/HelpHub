"""Eval safety: prefix guard, guarded ES client, stale-selection logic, lock."""

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


async def test_guarded_es_blocks_every_operation_under_a_bad_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeEs()
    es: Any = guard.GuardedEs(fake)
    monkeypatch.setattr(settings, "es_index_prefix", "")
    with pytest.raises(guard.UnsafePrefix):
        await es.search(index="eval-aaaaaaaaaaaa-chunks")
    with pytest.raises(guard.UnsafePrefix):
        await es.bulk(operations=[])
    with pytest.raises(guard.UnsafePrefix):
        await es.indices.refresh(index="chunks")
    assert fake.log == []


async def test_guarded_es_asserts_again_before_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeEs()
    es: Any = guard.GuardedEs(fake)
    monkeypatch.setattr(settings, "es_index_prefix", "eval-aaaaaaaaaaaa-")
    assert await es.search(index="eval-aaaaaaaaaaaa-chunks") == "hits"
    monkeypatch.setattr(settings, "es_index_prefix", "other-")  # changed mid-run
    with pytest.raises(guard.UnsafePrefix):
        await es.search(index="eval-aaaaaaaaaaaa-chunks")
    assert fake.log == ["search"]


async def test_guarded_es_refuses_an_index_outside_eval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "es_index_prefix", "eval-aaaaaaaaaaaa-")
    es: Any = guard.GuardedEs(FakeEs())
    with pytest.raises(guard.UnsafePrefix):
        await es.indices.refresh(index="chunks")
    assert await es.indices.refresh(index="eval-aaaaaaaaaaaa-chunks") == "ok"
    assert await es.options(request_timeout=5).search(index="eval-a-x") == "hits"
    with pytest.raises(guard.UnsafePrefix):  # options() stays guarded
        await es.options(request_timeout=5).search(index="chunks")


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


def test_lock_refuses_a_second_holder(tmp_path: Path) -> None:
    path = str(tmp_path / "lock")
    with lock.hold_lock(path), pytest.raises(lock.LockHeld), lock.hold_lock(path):
        pass
    with lock.hold_lock(path):  # released afterwards
        pass
