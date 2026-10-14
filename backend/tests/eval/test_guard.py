"""GuardedEs validates the target of every operation; eval/ has no other ES door."""

import re
from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from eval import guard

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"
RUN = "eval-0123456789ab-"
GOOD = f"{RUN}chunks"


class Recorder:
    transport = type("T", (), {"serializers": "s"})()

    def __init__(self, log: list[str], ns: str = "") -> None:
        self._log, self._ns = log, ns

    def __getattr__(self, name: str) -> Any:
        if name == "indices":
            return Recorder(self._log, "indices.")
        if name == "options":
            return lambda **kw: self

        async def call(**kwargs: Any) -> str:
            self._log.append(f"{self._ns}{name}")
            return "ok"

        return call


@pytest.fixture(autouse=True)
def run_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "es_index_prefix", RUN)


def _doc_ops(index: str) -> list[dict[str, Any]]:
    return [{"index": {"_index": index, "_id": "1"}}, {"field": "x"}]


def _actions(index: str) -> list[dict[str, Any]]:
    return [{"add": {"index": index, "alias": GOOD}}]


# (dotted method, kwargs builder taking an index name)
CASES = [
    ("search", lambda i: {"index": i}),
    ("count", lambda i: {"index": i}),
    ("index", lambda i: {"index": i, "document": {}}),
    ("delete", lambda i: {"index": i, "id": "1"}),
    ("delete_by_query", lambda i: {"index": i, "query": {}}),
    ("bulk", lambda i: {"index": i, "operations": _doc_ops(i)}),
    ("bulk", lambda i: {"operations": _doc_ops(i)}),  # target only in the action line
    ("indices.create", lambda i: {"index": i}),
    ("indices.delete", lambda i: {"index": i}),
    ("indices.exists", lambda i: {"index": i}),
    ("indices.exists_alias", lambda i: {"name": i}),
    ("indices.get", lambda i: {"index": i}),
    ("indices.get_alias", lambda i: {"name": i}),
    ("indices.get_settings", lambda i: {"index": i}),
    ("indices.put_settings", lambda i: {"index": i, "settings": {}}),
    ("indices.refresh", lambda i: {"index": i}),
    ("indices.update_aliases", lambda i: {"actions": _actions(i)}),
]
IDS = [f"{method}-{n}" for n, (method, _) in enumerate(CASES)]


def _call(es: Any, dotted: str) -> Any:
    target = es
    for part in dotted.split("."):
        target = getattr(target, part)
    return target


@pytest.mark.parametrize(("method", "kwargs"), CASES, ids=IDS)
@pytest.mark.parametrize("bad", ["chunks", "chunks-v1", "test-abc-chunks", "eval", ""])
async def test_every_operation_rejects_a_bad_index(
    method: str, kwargs: Any, bad: str
) -> None:
    log: list[str] = []
    es: Any = guard.GuardedEs(Recorder(log))
    with pytest.raises(guard.UnsafePrefix):
        await _call(es, method)(**kwargs(bad))
    assert log == []


@pytest.mark.parametrize(("method", "kwargs"), CASES, ids=IDS)
async def test_every_operation_accepts_an_eval_index(method: str, kwargs: Any) -> None:
    log: list[str] = []
    es: Any = guard.GuardedEs(Recorder(log))
    assert await _call(es, method)(**kwargs(GOOD)) == "ok"
    assert log == [method]


async def test_a_bad_index_among_good_ones_is_rejected() -> None:
    es: Any = guard.GuardedEs(Recorder([]))
    with pytest.raises(guard.UnsafePrefix):
        await es.search(index=[GOOD, "chunks"])
    with pytest.raises(guard.UnsafePrefix):
        await es.search(index=f"{GOOD},chunks")


async def test_bulk_action_line_aimed_at_chunks_is_rejected_despite_a_good_kwarg() -> (
    None
):
    es: Any = guard.GuardedEs(Recorder([]))
    with pytest.raises(guard.UnsafePrefix):
        await es.bulk(index=GOOD, operations=_doc_ops("chunks"))


@pytest.mark.parametrize(
    "call",
    [
        lambda es: es.indices.delete(index="eval-*"),
        lambda es: es.delete_by_query(index="eval-*", query={}),
        lambda es: es.indices.delete(index="_all"),
    ],
)
async def test_destructive_operations_refuse_wildcards(call: Any) -> None:
    with pytest.raises(guard.UnsafePrefix):
        await call(guard.GuardedEs(Recorder([])))


async def test_reads_may_use_an_eval_wildcard() -> None:
    es: Any = guard.GuardedEs(Recorder([]))
    assert await es.indices.get(index="eval-*") == "ok"


async def test_unknown_operations_and_positional_arguments_are_refused() -> None:
    es: Any = guard.GuardedEs(Recorder([]))
    with pytest.raises(guard.UnsafePrefix):
        getattr(es.transport, "perform_request")  # noqa: B009
    with pytest.raises(guard.UnsafePrefix):
        getattr(es, "delete_by_query_rethrottle")  # noqa: B009
    with pytest.raises(guard.UnsafePrefix):
        getattr(es.indices, "clear_cache")  # noqa: B009
    with pytest.raises(guard.UnsafePrefix):
        await es.search(GOOD)


def test_production_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(guard.ProductionRefused):
        guard.assert_not_production()
    monkeypatch.setattr(settings, "app_env", "local")
    guard.assert_not_production()


FORBIDDEN = re.compile(
    r"^\s*(import elasticsearch|from elasticsearch)|AsyncElasticsearch|\bget_es\b",
    re.MULTILINE,
)


def test_only_the_guard_module_touches_an_es_client() -> None:
    offenders = [
        path.name
        for path in sorted(EVAL_DIR.glob("*.py"))
        if path.name != "guard.py" and FORBIDDEN.search(path.read_text())
    ]
    assert offenders == []


async def test_serialised_bulk_lines_are_validated_too() -> None:
    import json

    def lines(index: str) -> list[str]:
        return [json.dumps({"index": {"_index": index}}), json.dumps({"a": 1})]

    es: Any = guard.GuardedEs(Recorder([]))
    assert await es.bulk(operations=lines(GOOD)) == "ok"
    with pytest.raises(guard.UnsafePrefix):
        await es.bulk(operations=lines("chunks"))
    with pytest.raises(guard.UnsafePrefix):  # an action line without any target
        await es.bulk(operations=[json.dumps({"index": {}}), json.dumps({"a": 1})])


def test_only_the_serializers_of_the_transport_are_reachable() -> None:
    es: Any = guard.GuardedEs(Recorder([]))
    assert es.transport.serializers == "s"
