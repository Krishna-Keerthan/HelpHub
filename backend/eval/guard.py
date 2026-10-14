"""Safety rails for the evaluation: it may only touch ``eval-`` Elasticsearch
indices and never runs in production.

``GuardedEs`` is the only door to Elasticsearch for everything under ``eval/``
(a static test enforces that nothing else imports or builds a client). It is an
allowlist: every supported operation validates every index or alias it names,
reads and writes alike, and refuses ``chunks`` and any name outside ``eval-``.
Destructive operations also refuse wildcards.
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

import elasticsearch

from app.core.config import settings
from app.services.es_client import alias_name, get_es

EVAL_PREFIX = "eval-"
CLIENT_VERSION = elasticsearch.__version__
BULK_ACTIONS = frozenset({"index", "create", "update", "delete"})
# Methods that carry no index (or only configure the wrapper).
NO_TARGET = frozenset({"info", "close"})
TOP_LEVEL = frozenset(
    {"search", "count", "bulk", "index", "delete", "delete_by_query"} | NO_TARGET
)
INDICES = frozenset(
    {
        "create", "delete", "exists", "exists_alias", "get", "get_alias",
        "get_settings", "put_settings", "refresh", "update_aliases",
    }
)  # fmt: skip
DESTRUCTIVE = frozenset({"bulk", "index", "delete", "delete_by_query", "create"})
DESTRUCTIVE_INDICES = frozenset({"delete", "create", "update_aliases", "put_settings"})


class UnsafePrefix(RuntimeError):
    """An Elasticsearch operation was aimed outside the eval- namespace."""


class ProductionRefused(RuntimeError):
    """An evaluation entry point was started with app_env == "production"."""


def assert_not_production() -> None:
    if settings.app_env == "production":
        raise ProductionRefused("the evaluation never runs with app_env=production")


def assert_eval_prefix() -> None:
    prefix = settings.es_index_prefix
    if not prefix.startswith(EVAL_PREFIX) or len(prefix) <= len(EVAL_PREFIX):
        raise UnsafePrefix("es_index_prefix must start with 'eval-' and name a run")
    if not alias_name().startswith(EVAL_PREFIX):
        raise UnsafePrefix("the alias must be inside the eval- namespace")


def _split(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        if not all(parts):
            raise UnsafePrefix("empty index name")
        return parts
    if isinstance(value, (list, tuple, set, frozenset)):
        return [name for item in value for name in _split(item)]
    raise UnsafePrefix("unrecognised index argument")


def _action_names(actions: Any) -> list[str]:
    names: list[str] = []
    for action in actions or []:
        if not isinstance(action, dict):
            raise UnsafePrefix("unrecognised alias action")
        for body in action.values():
            for key in ("index", "indices", "alias", "aliases"):
                names += _split(body.get(key))
    return names


def _decode(item: Any) -> Any:
    """The client helpers hand bulk lines over already serialised."""
    if isinstance(item, (str, bytes)):
        try:
            return json.loads(item)
        except ValueError:
            return None
    return item


def _bulk_names(operations: Any) -> tuple[list[str], int]:
    """Index names found in bulk action lines, and how many lines name none."""
    names: list[str] = []
    missing = 0
    for raw in operations or []:
        item = _decode(raw)
        if isinstance(item, dict) and len(item) == 1:
            (kind, meta), *_ = item.items()
            if kind in BULK_ACTIONS and isinstance(meta, dict):
                if "_index" in meta:
                    names += _split(meta["_index"])
                else:
                    missing += 1
    return names, missing


def targets(method: str, kwargs: dict[str, Any]) -> list[str]:
    names = _split(kwargs.get("index")) + _split(kwargs.get("name"))
    names += _split(kwargs.get("alias")) + _action_names(kwargs.get("actions"))
    if method == "bulk":
        found, missing = _bulk_names(kwargs.get("operations"))
        if missing and not names:
            raise UnsafePrefix("bulk action without a target index")
        names += found
    return names


def validate(method: str, kwargs: dict[str, Any], *, destructive: bool) -> None:
    names = targets(method, kwargs)
    empty_bulk = method == "bulk" and not kwargs.get("operations")
    if not names and not empty_bulk:
        raise UnsafePrefix(f"{method} names no index")
    for name in names:
        if not name.startswith(EVAL_PREFIX) or len(name) <= len(EVAL_PREFIX):
            raise UnsafePrefix(f"{method} aimed at an index outside eval-")
        if destructive and ("*" in name or name == "_all"):
            raise UnsafePrefix(f"{method} refuses wildcard targets")


class _SerializersOnly:
    """The bulk helper reads ``client.transport.serializers``; nothing else of the
    transport (it could send requests) is reachable."""

    def __init__(self, transport: Any) -> None:
        self._transport = transport

    @property
    def serializers(self) -> Any:
        return self._transport.serializers

    def __getattr__(self, name: str) -> Any:
        raise UnsafePrefix(f"transport.{name} is not allowed")


class GuardedEs:
    """Allowlisted, validating wrapper around the Elasticsearch client."""

    def __init__(
        self,
        client: Any,
        *,
        namespace: str = "",
        check_run_prefix: bool = True,
    ) -> None:
        self._client = client
        self._ns = namespace
        self._check_run_prefix = check_run_prefix

    def without_run_prefix(self) -> "GuardedEs":
        """Same checks on every named index, but not the run-prefix assertion (for
        looking at the whole eval- namespace after a run restored its settings)."""
        return GuardedEs(self._client, check_run_prefix=False)

    @classmethod
    def connect(cls, *, check_run_prefix: bool = True) -> "GuardedEs":
        return cls(get_es(), check_run_prefix=check_run_prefix)

    def _derive(self, client: Any, namespace: str = "") -> "GuardedEs":
        return GuardedEs(
            client, namespace=namespace, check_run_prefix=self._check_run_prefix
        )

    def __getattr__(self, name: str) -> Any:
        if self._ns:
            return self._operation(name, INDICES, DESTRUCTIVE_INDICES)
        if name == "indices":
            return self._derive(self._client.indices, "indices")
        if name == "transport":
            return _SerializersOnly(self._client.transport)
        if name == "options":
            options = self._client.options
            return lambda *a, **kw: self._derive(options(*a, **kw))
        return self._operation(name, TOP_LEVEL, DESTRUCTIVE)

    def _operation(
        self, name: str, allowed: frozenset[str], destructive: frozenset[str]
    ) -> Callable[..., Awaitable[Any]]:
        if name not in allowed:
            raise UnsafePrefix(f"operation {self._ns or 'es'}.{name} is not allowed")
        method = getattr(self._client, name)
        if name in NO_TARGET and not self._ns:
            return method  # type: ignore[no-any-return]

        async def call(*args: Any, **kwargs: Any) -> Any:
            if args:
                raise UnsafePrefix("positional arguments are not allowed")
            if self._check_run_prefix:
                assert_eval_prefix()
            validate(name, kwargs, destructive=name in destructive)
            return await method(**kwargs)

        return call
