"""Safety rails: the evaluation may only write to ``eval-`` Elasticsearch indices.

``GuardedEs`` wraps the client the services receive. Before every write it
re-asserts that ``settings.es_index_prefix`` starts with ``eval-`` and that any
explicit ``index=`` argument does too, so a bug can never touch the real
``chunks`` alias.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import settings
from app.services.es_client import alias_name

EVAL_PREFIX = "eval-"
WRITE_METHODS = frozenset(
    {
        "bulk", "index", "create", "update", "delete", "delete_by_query",
        "update_by_query", "put_alias", "delete_alias", "update_aliases",
        "put_settings", "put_mapping", "forcemerge", "clear_cache",
    }
)  # fmt: skip
# Index operations that are writes ("refresh" is one: the harness refreshes only
# its own eval index) live under ``es.indices``.
INDICES_WRITE_METHODS = WRITE_METHODS | {"refresh", "flush"}


class UnsafePrefix(RuntimeError):
    """An Elasticsearch write was attempted outside the eval- namespace."""


def assert_eval_prefix() -> None:
    prefix = settings.es_index_prefix
    if not prefix.startswith(EVAL_PREFIX) or len(prefix) <= len(EVAL_PREFIX):
        raise UnsafePrefix("es_index_prefix must start with 'eval-' and name a run")
    if not alias_name().startswith(EVAL_PREFIX):
        raise UnsafePrefix("the alias must be inside the eval- namespace")


def _check_index_argument(kwargs: dict[str, Any]) -> None:
    index = kwargs.get("index")
    names = [index] if isinstance(index, str) else list(index or [])
    for name in names:
        if not str(name).startswith(EVAL_PREFIX):
            raise UnsafePrefix("write aimed at an index outside eval-")


class GuardedEs:
    def __init__(self, client: Any, writes: frozenset[str] = WRITE_METHODS) -> None:
        self._client = client
        self._writes = writes

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._client, name)
        if name == "options":
            return lambda *a, **kw: GuardedEs(attr(*a, **kw), self._writes)
        if name == "indices":
            return GuardedEs(attr, INDICES_WRITE_METHODS)
        if name in self._writes and callable(attr):
            return self._guard(attr)
        return attr

    @staticmethod
    def _guard(method: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        async def call(*args: Any, **kwargs: Any) -> Any:
            assert_eval_prefix()
            _check_index_argument(kwargs)
            return await method(*args, **kwargs)

        return call
