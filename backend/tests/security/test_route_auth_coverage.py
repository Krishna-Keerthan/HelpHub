"""Every route authenticates unless it is on the explicit public allowlist."""

from collections.abc import Iterator

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from starlette.routing import Route

from app.api import deps
from app.main import app

# Adding a route here is a security decision: it is reachable without a token.
PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("GET", "/health"),
    # Readiness probe for the host and the uptime bot; returns only ok/not ready.
    ("GET", "/health/ready"),
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    # Exempt on purpose: the credential is the signed refresh token in the body
    # (an access token is rejected, see tests/auth/test_refresh_tokens.py), verified
    # before any database access. /auth/logout is exempt for the same reason, so a
    # client whose access token already expired can still revoke its family.
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
}
# Served by FastAPI itself (not APIRoute instances).
DOCS_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

AUTH_DEPENDENCIES = {
    deps.get_token_subject,
    deps.get_current_user,
    deps.get_current_principal,
    deps.require_admin,
}

# A viewer is read-only. Every write route must pass through one of these gates
# (admin or non-viewer) unless it is listed here as open to every role on purpose.
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
WRITE_GATES = {deps.require_admin, deps.require_writer}
WRITE_OPEN_TO_VIEWERS: set[tuple[str, str]] = {
    ("POST", "/search"),  # a read, sent as POST for the body
    ("POST", "/chat/stream"),  # creates the viewer's own conversations and messages
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
}


def _calls(dependant: Dependant) -> Iterator[object]:
    for dep in dependant.dependencies:
        yield dep.call
        yield from _calls(dep)


def _api_routes() -> list[tuple[str, set[str], Dependant]]:
    """(path, methods, dependant) for every route, including included routers.

    FastAPI keeps included routers unflattened; effective_route_contexts() is
    its internal flattening, so the sanity test below fails loudly if an
    upgrade changes it and routes silently stop being checked.
    """
    found: list[tuple[str, set[str], Dependant]] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            found.append((route.path, set(route.methods), route.dependant))
        elif hasattr(route, "effective_route_contexts"):
            for ctx in route.effective_route_contexts():
                found.append((ctx.path, set(ctx.methods), ctx.dependant))
    return found


def test_route_discovery_sees_included_routers() -> None:
    paths = {path for path, _, _ in _api_routes()}
    assert {"/health", "/auth/me", "/documents", "/search"} <= paths
    assert len(paths) >= 10


def test_every_route_has_an_authentication_dependency_or_is_public() -> None:
    unauthenticated = []
    for path, methods, dependant in _api_routes():
        authenticated = bool(set(_calls(dependant)) & AUTH_DEPENDENCIES)
        for method in methods:
            if not authenticated and (method, path) not in PUBLIC_ROUTES:
                unauthenticated.append(f"{method} {path}")
    assert unauthenticated == []


def test_public_allowlist_has_no_stale_entries() -> None:
    existing = {(m, path) for path, methods, _ in _api_routes() for m in methods}
    assert PUBLIC_ROUTES <= existing


def test_public_routes_do_not_authenticate() -> None:
    # An allowlisted route that does authenticate should leave the allowlist.
    for path, methods, dependant in _api_routes():
        for method in methods:
            if (method, path) in PUBLIC_ROUTES:
                assert not set(_calls(dependant)) & AUTH_DEPENDENCIES, (method, path)


def test_non_api_routes_are_only_the_docs_endpoints() -> None:
    others = [
        r for r in app.routes if not isinstance(r, APIRoute) and isinstance(r, Route)
    ]
    assert {r.path for r in others} <= DOCS_PATHS


# A floor, not an exact count: it only moves up. If route discovery silently
# stops seeing routers, the auth checks above would pass vacuously. The floor is
# paired with REQUIRED_ROUTES so a dropped router cannot hide behind other routes.
MIN_ROUTE_COUNT = 15
REQUIRED_ROUTES = [
    "/auth/login",
    "/auth/register",
    "/documents",
    "/search",
    "/chat/stream",
]


def test_route_count_has_a_floor() -> None:
    pairs = {(m, path) for path, methods, _ in _api_routes() for m in methods}
    assert len(pairs) >= MIN_ROUTE_COUNT, len(pairs)


def test_required_routes_are_present() -> None:
    paths = {path for path, _, _ in _api_routes()}
    assert [p for p in REQUIRED_ROUTES if p not in paths] == []


def test_every_write_route_is_gated_against_viewers_or_explicitly_open() -> None:
    ungated = []
    for path, methods, dependant in _api_routes():
        for method in methods & WRITE_METHODS:
            if (method, path) in WRITE_OPEN_TO_VIEWERS:
                continue
            if not set(_calls(dependant)) & WRITE_GATES:
                ungated.append(f"{method} {path}")
    assert ungated == []


def test_write_open_allowlist_has_no_stale_entries() -> None:
    existing = {(m, path) for path, methods, _ in _api_routes() for m in methods}
    assert WRITE_OPEN_TO_VIEWERS <= existing
