import asyncio
import fcntl
import os
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any, TypedDict

import pytest
from httpx import ASGITransport, AsyncClient
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_embedding_provider, get_llm_provider
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.main import app
from app.services.embeddings import FakeEmbeddingProvider
from tests.helpers.fakes import FakeLLMProvider

# gate-allow: secret fake value used only by this test
SEED_PASSWORD = "Password123!Password"
EMBEDDING_DIM = 384
TEST_EMBEDDING_MODEL = "test-model"


class SeededTenant(TypedDict):
    id: uuid.UUID
    slug: str
    user_id: uuid.UUID
    email: str
    role: str
    password: str


MakeTenant = Callable[..., Awaitable[SeededTenant]]


SEED_SLUG_PATTERN = r"^t-[0-9a-f]{12}$"
_MISSING: Any = object()


@pytest.fixture(scope="session", autouse=True)
def no_embedding_warm_up() -> Iterator[None]:
    """The app lifespan never loads the real model during tests."""
    previous = settings.warm_up_embeddings
    settings.warm_up_embeddings = False
    yield
    settings.warm_up_embeddings = previous


@pytest.fixture(autouse=True)
def fake_embedding_provider() -> Iterator[None]:
    """API tests never load the real model. Restores any prior override."""
    previous = app.dependency_overrides.get(get_embedding_provider, _MISSING)
    app.dependency_overrides[get_embedding_provider] = FakeEmbeddingProvider
    try:
        yield
    finally:
        if previous is _MISSING:
            app.dependency_overrides.pop(get_embedding_provider, None)
        else:
            app.dependency_overrides[get_embedding_provider] = previous


@pytest.fixture(autouse=True)
def fake_llm() -> Iterator[FakeLLMProvider]:
    """API tests never call Groq. Restores any prior override."""
    fake = FakeLLMProvider()
    previous = app.dependency_overrides.get(get_llm_provider, _MISSING)
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        yield fake
    finally:
        if previous is _MISSING:
            app.dependency_overrides.pop(get_llm_provider, None)
        else:
            app.dependency_overrides[get_llm_provider] = previous


async def _seed_tenant_slugs() -> set[str]:
    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT slug FROM tenants WHERE slug ~ :pattern"),
                {"pattern": SEED_SLUG_PATTERN},
            )
            return {row[0] for row in rows}
    finally:
        await engine.dispose()


_slugs_before: set[str] | None = None


def _read_seed_slugs() -> set[str] | None:
    """Seeded tenant slugs now in the DB, or None when the DB is unreachable."""
    try:
        return asyncio.run(_seed_tenant_slugs())
    except (SQLAlchemyError, OSError):
        return None


DEFAULT_LOCK_FILE = "/tmp/helphub-pytest.lock"  # noqa: S108 - single-user dev box
_lock_fd: int | None = None


def _lock_held_by_live_parent() -> bool:
    """scripts/flake_hunt.sh holds the lock for the whole hunt and says so."""
    holder = os.environ.get("HELPHUB_PYTEST_LOCK_HOLDER", "")
    return holder.isdigit() and os.path.exists(f"/proc/{holder}")


def _acquire_session_lock() -> None:
    """One pytest session at a time: the database is shared (see CLAUDE.md)."""
    global _lock_fd
    if _lock_held_by_live_parent():
        return
    path = os.environ.get("HELPHUB_PYTEST_LOCK_FILE", DEFAULT_LOCK_FILE)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise pytest.UsageError(
            "another pytest session is running (shared database)"
        ) from None
    _lock_fd = fd


def _release_session_lock() -> None:
    global _lock_fd
    if _lock_fd is not None:
        os.close(_lock_fd)  # closing drops the flock
        _lock_fd = None


async def _reset_chunks_reloptions() -> list[str] | None:
    """Undo a leftover ``autovacuum_enabled=false`` (a killed run never resets it)."""
    engine = create_async_engine(
        settings.migration_database_url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as conn:
            found = (
                await conn.execute(
                    text(
                        "SELECT reloptions FROM pg_class "
                        "WHERE oid = 'public.chunks'::regclass"
                    )
                )
            ).scalar_one()
            if found is not None:
                await conn.execute(
                    text("ALTER TABLE chunks RESET (autovacuum_enabled)")
                )
            return found
    finally:
        await engine.dispose()


def _reset_leftover_reloptions() -> None:
    try:
        found = asyncio.run(_reset_chunks_reloptions())
    except (SQLAlchemyError, OSError):
        return  # DB unreachable: tests fail on their own, clearly
    if found is not None:
        print(
            f"WARNING: chunks had leftover reloptions {found}; reset them",
            file=sys.stderr,
        )


def pytest_sessionstart(session: pytest.Session) -> None:
    global _slugs_before
    _acquire_session_lock()
    _reset_leftover_reloptions()
    _slugs_before = _read_seed_slugs()


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the run (non-zero exit status) if it left seeded tenants behind.

    Done here, not in a fixture, so no individual test is reported as the
    one that errored. Also releases the single-session lock.
    """
    _release_session_lock()
    if _slugs_before is None:
        return
    after = _read_seed_slugs()
    leaked = sorted((after or set()) - _slugs_before)
    if not leaked:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    message = f"test session leaked {len(leaked)} seeded tenant(s): {', '.join(leaked)}"
    if reporter is not None:
        reporter.write_line("")
        reporter.write_sep("=", "TENANT LEAK", red=True, bold=True)
        reporter.write_line(message, red=True)
    if session.exitstatus == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture
async def owner_conn() -> AsyncIterator[AsyncConnection]:
    """Connection as the table owner (MIGRATION_DATABASE_URL); bypasses RLS."""
    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            yield conn
    finally:
        await engine.dispose()


@pytest.fixture
async def app_conn(make_tenant: MakeTenant) -> AsyncIterator[AsyncConnection]:
    """Connection as the runtime role (DATABASE_URL); subject to RLS.

    Depends on ``make_tenant`` only for teardown order: pytest tears down
    dependents first, so this connection's transaction (and any row locks it
    holds) always ends before make_tenant deletes the tenants, whatever order
    a test lists its fixtures in.
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            yield conn
            await conn.rollback()
            # Tests may set the tenant at session level; never leave it behind.
            await conn.execute(text("SELECT set_config('app.tenant_id', '', false)"))
            await conn.commit()
    finally:
        await engine.dispose()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture(scope="session")
def seed_password_hash() -> str:
    return hash_password(SEED_PASSWORD)


@pytest.fixture
async def make_tenant(seed_password_hash: str) -> AsyncIterator[MakeTenant]:
    """Factory: a committed tenant with one user, created as the owner.

    Cleanup deletes exactly the tenants this factory created (users go with
    them via ON DELETE CASCADE), never by pattern.
    """
    created: list[uuid.UUID] = []
    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)

    async def _make(
        *, role: str = "admin", is_active: bool = True, slug: str | None = None
    ) -> SeededTenant:
        slug = slug or f"t-{uuid.uuid4().hex[:12]}"
        email = f"user@{slug}.example.com"
        async with engine.begin() as conn:
            tenant_id = (
                await conn.execute(
                    text(
                        "INSERT INTO tenants (slug, name) VALUES (:slug, :name) "
                        "RETURNING id"
                    ),
                    {"slug": slug, "name": f"Tenant {slug}"},
                )
            ).scalar_one()
            user_id = (
                await conn.execute(
                    text(
                        "INSERT INTO users "
                        "(tenant_id, email, password_hash, role, is_active) "
                        "VALUES (:tid, :email, :hash, :role, :active) RETURNING id"
                    ),
                    {
                        "tid": tenant_id,
                        "email": email,
                        "hash": seed_password_hash,
                        "role": role,
                        "active": is_active,
                    },
                )
            ).scalar_one()
        created.append(tenant_id)
        return {
            "id": tenant_id,
            "slug": slug,
            "user_id": user_id,
            "email": email,
            "role": role,
            "password": SEED_PASSWORD,
        }

    try:
        yield _make
    finally:
        await engine.dispose()
        leaked = await _delete_tenants(created)
        if leaked:
            detail = "; ".join(f"{tid} ({err})" for tid, err in leaked.items())
            raise RuntimeError(f"cleanup failed, leaked tenant ids: {detail}")


async def _delete_tenants(tenant_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Delete exactly ``tenant_ids`` on a fresh owner connection.

    One transaction per id so one failure cannot leak the others; lock_timeout
    keeps a stuck test connection from hanging teardown. Returns the ids that
    could not be deleted, with the error (the caller raises on any).
    """
    leaked: dict[uuid.UUID, str] = {}
    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    try:
        for tenant_id in tenant_ids:
            try:
                async with engine.begin() as conn:
                    await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                    await conn.execute(
                        text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id}
                    )
            except (SQLAlchemyError, OSError) as exc:
                leaked[tenant_id] = repr(exc)
    finally:
        await engine.dispose()
    return leaked


@pytest.fixture
async def two_tenants_seeded(
    make_tenant: MakeTenant,
) -> dict[str, SeededTenant]:
    """Tenant A (admin user) and tenant B (agent user)."""
    return {
        "tenant_a": await make_tenant(role="admin"),
        "tenant_b": await make_tenant(role="agent"),
    }


# --- plumbing helpers for documents / chunks -------------------------------


def auth_headers(tenant: SeededTenant) -> dict[str, str]:
    """Bearer header for the tenant's seeded user (sub = user id, tid = tenant)."""
    token = create_access_token(
        {"sub": str(tenant["user_id"]), "tid": str(tenant["id"])}
    )
    return {"Authorization": f"Bearer {token}"}


def sqlstate(exc: DBAPIError) -> str | None:
    orig = exc.orig
    return getattr(orig, "sqlstate", None) or getattr(
        getattr(orig, "__cause__", None), "sqlstate", None
    )


def constraint_name(exc: DBAPIError) -> str | None:
    orig = exc.orig
    return getattr(orig, "constraint_name", None) or getattr(
        getattr(orig, "__cause__", None), "constraint_name", None
    )


def unit_vector(*components: float) -> list[float]:
    """Pad ``components`` with zeros to EMBEDDING_DIM and L2-normalise."""
    vec = [0.0] * EMBEDDING_DIM
    vec[: len(components)] = components
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


_INSERT_DOCUMENT = text(
    "INSERT INTO documents "
    "(tenant_id, title, raw_text, content_hash, status, created_by) "
    "VALUES (:tid, :title, :raw_text, :content_hash, :status, :created_by) "
    "RETURNING id"
)


def _insert_chunk_stmt(dim: int | None):
    return text(
        "INSERT INTO chunks (tenant_id, document_id, chunk_index, text, "
        "char_start, char_end, embedding, embedding_model) "
        "VALUES (:tid, :document_id, :chunk_index, :text, :char_start, "
        ":char_end, :vec, :model) RETURNING id"
    ).bindparams(bindparam("vec", type_=Vector(dim)))


async def insert_document(
    conn: AsyncConnection,
    tenant_id: uuid.UUID,
    *,
    created_by: uuid.UUID,
    title: str = "Doc",
    raw_text: str = "content",
    content_hash: str | None = None,
    status: str = "READY",
) -> uuid.UUID:
    """Insert a document row on ``conn`` (no commit). Hash defaults to unique."""
    result = await conn.execute(
        _INSERT_DOCUMENT,
        {
            "tid": tenant_id,
            "title": title,
            "raw_text": raw_text,
            "content_hash": content_hash or uuid.uuid4().hex,
            "status": status,
            "created_by": created_by,
        },
    )
    return result.scalar_one()


async def insert_chunk(
    conn: AsyncConnection,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    chunk_index: int = 0,
    content: str = "chunk",
    embedding: list[float] | None = None,
    dim: int | None = EMBEDDING_DIM,
) -> uuid.UUID:
    """Insert a chunk row on ``conn`` (no commit).

    ``tenant_id`` is explicit so tests can pair a tenant with another
    tenant's document. ``dim=None`` skips the client-side dimension check so
    the database is the one to reject a wrong-sized vector.
    """
    result = await conn.execute(
        _insert_chunk_stmt(dim),
        {
            "tid": tenant_id,
            "document_id": document_id,
            "chunk_index": chunk_index,
            "text": content,
            "char_start": 0,
            "char_end": max(len(content), 1),
            "vec": embedding if embedding is not None else unit_vector(1.0),
            "model": TEST_EMBEDDING_MODEL,
        },
    )
    return result.scalar_one()


async def insert_chunks(
    conn: AsyncConnection,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    embeddings: list[list[float]],
) -> None:
    """Bulk insert one chunk per embedding (no commit)."""
    await conn.execute(
        _insert_chunk_stmt(EMBEDDING_DIM),
        [
            {
                "tid": tenant_id,
                "document_id": document_id,
                "chunk_index": i,
                "text": f"chunk {i}",
                "char_start": 0,
                "char_end": 7,
                "vec": vec,
                "model": TEST_EMBEDDING_MODEL,
            }
            for i, vec in enumerate(embeddings)
        ],
    )


DocumentMaker = Callable[..., Awaitable[uuid.UUID]]
ChunkMaker = Callable[..., Awaitable[uuid.UUID]]


@pytest.fixture
async def make_document(owner_conn: AsyncConnection) -> DocumentMaker:
    """Factory: committed document owned by ``tenant`` (cleaned up with it)."""

    async def _make(tenant: SeededTenant, **kwargs: Any) -> uuid.UUID:
        doc_id = await insert_document(
            owner_conn, tenant["id"], created_by=tenant["user_id"], **kwargs
        )
        await owner_conn.commit()
        return doc_id

    return _make


@pytest.fixture
async def make_chunk(owner_conn: AsyncConnection) -> ChunkMaker:
    """Factory: committed chunk for ``document_id`` under ``tenant_id``."""

    async def _make(
        tenant_id: uuid.UUID, document_id: uuid.UUID, **kwargs: Any
    ) -> uuid.UUID:
        chunk_id = await insert_chunk(owner_conn, tenant_id, document_id, **kwargs)
        await owner_conn.commit()
        return chunk_id

    return _make
